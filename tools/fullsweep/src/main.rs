//! fullsweep — probe the Ledger Nano 1 (2581:3b7c) HID interface with rawusb.
//!
//! Subcommands:
//!   probe          dump the HID report descriptor and run one E0 C4 query
//!   sweep          probe every (CLA, INS) at P1=P2=0, Lc=0, print a TSV
//!
//! Uses usbfs (via rawusb) so only the `usb` group is needed, and the device
//! can self-reset (USBDEVFS_RESET) to recover from the all-`6faa` transient
//! state whenever the periodic E0 C4 health gate fails.

use rawusb::hid::HidDevice;
use std::collections::BTreeMap;
use std::io::{BufWriter, Write};
use std::time::{Duration, Instant};

const VID: u16 = 0x2581;
const PID: u16 = 0x3b7c;
const TAG_APDU: u8 = 0x05;
const REPORT: usize = 64;
const TIMEOUT: std::time::Duration = std::time::Duration::from_millis(2500);

struct Ledger {
    hid: HidDevice,
}

impl Ledger {
    pub fn open() -> Result<Self, Box<dyn std::error::Error>> {
        let ctx = rawusb::Context::new()?;
        let dev = ctx.find_device(VID, PID)?.ok_or("no 2581:3b7c device")?;
        let hid = HidDevice::open(&dev)?;
        // Force a kernel-driver detach so the interrupt IN endpoint is ours to
        // read (the kernel hid-usb driver otherwise consumes the reports).
        if hid.handle().kernel_driver_active(0)? {
            hid.handle().detach_kernel_driver(0)?;
        }
        Ok(Self { hid })
    }

    /// OUT report: ch(01 01) tag(05) seq(00 00) len(2 BE) apdu, zero-padded to 64.
    fn build_out(apdu: &[u8]) -> [u8; REPORT] {
        let mut r = [0u8; REPORT];
        r[0] = 0x01;
        r[1] = 0x01;
        r[2] = TAG_APDU;
        r[5] = (apdu.len() >> 8) as u8;
        r[6] = apdu.len() as u8;
        r[7..7 + apdu.len()].copy_from_slice(apdu);
        r
    }

    /// Locate the [01 01 05] channel marker (tolerates an optional leading
    /// report-ID byte at offset 0).
    fn find_base(buf: &[u8]) -> Option<usize> {
        (0..2usize).find(|&b| buf.len() >= b + 3 && buf[b..b + 3] == [0x01, 0x01, 0x05])
    }

    /// Send an APDU (P1=P2=0, no data) and return (status_word, data).
    fn query_full(&self, apdu: &[u8]) -> Result<(u16, Vec<u8>), Box<dyn std::error::Error>> {
        let rep = Self::build_out(apdu);
        let to_send: Vec<u8> = std::iter::once(0x00u8).chain(rep.iter().copied()).collect();
        self.hid.write(&to_send, TIMEOUT)?;

        // Reassemble the payload. Report layout (base = start of [01 01 05]):
        //   [0:2] channel, [2] tag, [3:5] sequence
        //   seq 0  : [5:7]   2-byte big-endian payload length, [7:]  payload
        //   seq >0 : [5:]    payload (no length field)
        // Loops until `length` bytes are accumulated (handles Le > 57).
        let mut payload: Vec<u8> = Vec::new();
        let mut total_len: Option<usize> = None;
        let mut seq: u16 = 0;
        loop {
            let mut buf = [0u8; REPORT];
            let n = self.hid.read(&mut buf, TIMEOUT)?;
            let base = Self::find_base(&buf[..n]).ok_or("no channel header")?;
            let body = &buf[base..n];
            if body.len() < 5 || body[2] != TAG_APDU {
                return Err(format!("bad resp header {:02x?}", &body[..body.len().min(8)]).into());
            }
            if u16::from_be_bytes([body[3], body[4]]) != seq {
                return Err(format!("seq mismatch (got {} want {})",
                    u16::from_be_bytes([body[3], body[4]]), seq).into());
            }
            let (start, is_first) = if seq == 0 {
                if body.len() < 7 {
                    return Err("first report too short".into());
                }
                total_len = Some(u16::from_be_bytes([body[5], body[6]]) as usize);
                (7, true)
            } else {
                (5, false)
            };
            let _ = is_first;
            let mut chunk = &body[start..];
            if let Some(tl) = total_len {
                // Only need the bytes up to `tl`.
                let remaining = tl.saturating_sub(payload.len());
                if chunk.len() > remaining {
                    chunk = &chunk[..remaining];
                }
            }
            payload.extend_from_slice(chunk);
            seq += 1;
            if let Some(tl) = total_len {
                if payload.len() >= tl {
                    break;
                }
            } else if seq >= 1 {
                break;
            }
        }
        if payload.len() < 2 {
            return Err("response too short".into());
        }
        Ok((
            u16::from_be_bytes([payload[payload.len() - 2], payload[payload.len() - 1]]),
            payload[..payload.len() - 2].to_vec(),
        ))
    }

    fn query(&self, cla: u8, ins: u8) -> Result<(u16, Vec<u8>), Box<dyn std::error::Error>> {
        self.query_full(&[cla, ins, 0x00, 0x00, 0x00])
    }

    fn healthy(&self) -> bool {
        matches!(self.query(0xE0, 0xC4), Ok((0x9000, _)))
    }

    /// USB port reset; if the device re-enumerated with new addresses, reopen
    /// it and clear any endpoint stalls, then wait (up to ~15 s) for it to
    /// be healthy. Falls back to a second reset + reopen if the first one
    /// didn't bring it back.
    fn reset(&mut self) -> Result<bool, Box<dyn std::error::Error>> {
        // A pure USB port reset is not always enough to clear the all-`6faa`
        // firmware state, so always reopen the device and clear the endpoint
        // stalls (which forces a fresh claim), then give the firmware time.
        for attempt in 0..3u8 {
            let _ = self.hid.handle().reset();
            std::thread::sleep(Duration::from_millis(200));
            *self = Ledger::open()?;
            for ep in [0x82u8, 0x02u8] {
                let _ = self.hid.handle().clear_halt(ep);
            }
            if attempt == 0 {
                eprintln!("  reset #0: reopened + cleared halt");
            }
            if self.wait_healthy(Duration::from_secs(6)) {
                eprintln!("  reset: healthy again");
                return Ok(true);
            }
        }
        eprintln!("  reset: still not healthy after 3 attempts");
        Ok(false)
    }

    /// Poll E0 C4 with a fast timeout until `dur` elapses or the device is
    /// healthy.
    fn wait_healthy(&self, dur: Duration) -> bool {
        let fast = Duration::from_millis(200);
        let mut last_err = String::from("no response");
        let deadline = std::time::Instant::now() + dur;
        while std::time::Instant::now() < deadline {
            let apdu = [0xE0u8, 0xC4, 0u8, 0u8, 0u8];
            let rep = Self::build_out(&apdu);
            let to_send: Vec<u8> = std::iter::once(0u8).chain(rep.iter().copied()).collect();
            let out: Result<u16, String> = self
                .hid
                .write(&to_send, fast)
                .map_err(|e| e.to_string())
                .and_then(|_| {
                    let mut buf = [0u8; REPORT];
                    let n = self.hid.read(&mut buf, fast).map_err(|e| e.to_string())?;
                    if n < 9 {
                        return Err("short".into());
                    }
                    let len = u16::from_be_bytes([buf[5], buf[6]]) as usize;
                    if len < 2 || 7 + len > n {
                        return Err("bad len".into());
                    }
                    Ok(u16::from_be_bytes([buf[7 + len - 2], buf[7 + len - 1]]))
                });
            match out {
                Ok(0x9000) => return true,
                Ok(sw) => last_err = format!("sw={sw:04x}"),
                Err(e) => last_err = e,
            }
            std::thread::sleep(Duration::from_millis(80));
        }
        eprintln!("  reset: not healthy yet ({last_err})");
        false
    }
}

fn probe(dev: &Ledger) -> Result<(), Box<dyn std::error::Error>> {
    eprintln!("max_input_report_len = {}", dev.hid.max_input_report_len());
    let (sw, data) = dev.query(0xE0, 0xC4)?;
    println!("E0 C4: sw={sw:04x} data={}", data_hex(&data));
    Ok(())
}

/// Probe one (cla, ins) with transient-state recovery.
///
/// A real `6faa` and the all-`6faa` transient state are indistinguishable by
/// the status word alone (e.g. `E0 C2` normally answers `6faa` at `Lc=0`). So
/// only when we get a `6faa` do we spend one extra `E0 C4` ping to disambiguate
/// the two. A bare timeout means the device has wedged, which we clear with a
/// self-reset.
fn query_and_record(
    dev: &mut Ledger,
    cla: u8,
    ins: u8,
    out: &mut BufWriter<std::fs::File>,
    groups: &mut BTreeMap<u16, usize>,
    resets: &mut u64,
) -> Result<(), Box<dyn std::error::Error>> {
    let r = loop {
        match dev.query(cla, ins) {
            Ok(r) if r.0 != 0x6faa => break r,
            Ok(r) => {
                // sw == 0x6faa: is it real, or the transient state?
                if dev.healthy() {
                    break r; // E0 C4 answered 9000, so the 6faa was genuine
                }
                if !dev.reset()? {
                    eprintln!("  transient state (cla={cla:02x} ins={ins:02x}) did not clear after self-reset; please POWER-CYCLE and re-run");
                    return Err("power-cycle needed".into());
                }
                *resets += 1;
            }
            Err(e) if rawusb_err_is_timeout(&e) => {
                if !dev.reset()? {
                    eprintln!("  timeout at (cla={cla:02x} ins={ins:02x}) and reset did not clear; please POWER-CYCLE and re-run");
                    return Err("power-cycle needed".into());
                }
                *resets += 1;
            }
            Err(e) => return Err(e),
        }
    };
    let has = usize::from(!r.1.is_empty());
    writeln!(out, "{cla:02x} {ins:02x} {:04x} {has} {}", r.0, data_hex(&r.1))
        .map_err(|e| format!("write: {e}; {cla:02x} {ins:02x}"))?;
    *groups.entry(r.0).or_insert(0) += 1;
    Ok(())
}

fn sweep(dev: &mut Ledger) -> Result<(), Box<dyn std::error::Error>> {
    let path = std::env::var("FULLSWEEP_OUT").unwrap_or_else(|_| "/tmp/fullsweep.tsv".into());
    let exists = std::path::Path::new(&path).exists();
    let file = std::fs::OpenOptions::new().create(true).append(true).open(&path)?;
    let mut out = BufWriter::new(file);

    // Resume: read completed (cla, ins) pairs from any existing TSV.
    let mut done: std::collections::BTreeSet<(u8, u8)> =
        std::collections::BTreeSet::new();
    if exists {
        for line in std::fs::read_to_string(&path)?.lines() {
            if let Some(rest) = line.strip_prefix(' ') {
                if rest.starts_with('[') {
                    continue; // progress line
                }
            }
            if line.starts_with('#') {
                continue;
            }
            let mut it = line.split_whitespace();
            let cla_s = it.next().ok_or("bad line")?;
            let ins_s = it.next().ok_or("bad line")?;
            let sw_s = it.next();
            // A complete line has a 4-hex-digit status word; skip truncated
            // partial lines (e.g. a command written but killed before flush).
            if let (Some(sw), Ok(c), Ok(i)) = (
                sw_s,
                u8::from_str_radix(cla_s, 16),
                u8::from_str_radix(ins_s, 16),
            ) {
                let sw_ok = sw.bytes().count() == 4
                    && sw.bytes().all(|b| b.is_ascii_hexdigit());
                if sw_ok {
                    done.insert((c, i));
                }
            }
        }
        eprintln!("resuming: {} (cla,ins) already done", done.len());
    } else {
        writeln!(out, "# cla ins sw has_data data")?;
    }

    if !dev.healthy() {
        eprintln!("not healthy at start; resetting...");
        if !dev.reset()? {
            eprintln!("please POWER-CYCLE the device and re-run");
            return Err("device not healthy after reset".into());
        }
    }

    // Optional range via FULLSWEEP_LIST=e0:c1-ff,f0:00-ff (comma-separated
    // cla:ins_lo-ins_hi). Default is all 65 536 (cla, ins) pairs in a flat
    // order.
    let mut tasks: Vec<(u8, u8)> = Vec::new();
    if let Ok(spec) = std::env::var("FULLSWEEP_LIST") {
        for pair in spec.split(',') {
            if let Some((cla_s, range)) = pair.split_once(':') {
                if let Some((lo, hi)) = range.split_once('-') {
                    if let (Ok(c), Ok(l), Ok(h)) = (
                        u8::from_str_radix(cla_s, 16),
                        u8::from_str_radix(lo, 16),
                        u8::from_str_radix(hi, 16),
                    ) {
                        for i in l..=h {
                            tasks.push((c, i));
                        }
                    }
                }
            }
        }
    } else {
        for c in 0u8..=0xFF {
            for i in 0u8..=0xFF {
                tasks.push((c, i));
            }
        }
    }

    let count_cap: Option<usize> = std::env::var("FULLSWEEP_N")
        .ok()
        .and_then(|s| s.parse().ok());

    let mut groups: BTreeMap<u16, usize> = BTreeMap::new();
    let mut resets = 0u64;
    let mut total = 0usize;
    let start = Instant::now();

    for (cla, ins) in &tasks {
        if done.contains(&(*cla, *ins)) {
            continue;
        }
        query_and_record(dev, *cla, *ins, &mut out, &mut groups, &mut resets)?;
        out.flush().map_err(|e| format!("flush error: {e}; {cla:02x} {ins:02x}"))?;
        total += 1;

        if total % 512 == 0 {
            let el = start.elapsed().as_secs_f64();
            let per = el / total as f64;
            let rem = per * (65536u32.saturating_sub(total as u32)) as f64;
            eprintln!("  [{total}/65536] eta {rem:.0}s ({} resets)", resets);
        }
        if let Some(cap) = count_cap {
            if total >= cap {
                break;
            }
        }
    }

    out.flush()?;
    eprintln!("\n=== grouped by status word ({} total, {} resets) ===", total, resets);
    for (sw, count) in &groups {
        eprintln!("  sw={sw:04x}: {count}");
    }
    Ok(())
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let cmd = std::env::args().nth(1).unwrap_or_else(|| "probe".into());
    let mut dev = Ledger::open()?;
    match cmd.as_str() {
        "probe" => probe(&dev),
        "sweep" => sweep(&mut dev),
        "one" => {
            // one <hex cla> <hex ins> [more pairs...]
            let args: Vec<String> = std::env::args().skip(2).collect();
            for chunk in args.chunks(2) {
                let cla = u8::from_str_radix(&chunk[0], 16)?;
                let ins = u8::from_str_radix(&chunk[1], 16)?;
                let (sw, data) = dev.query(cla, ins)?;
                println!(
                    "{cla:02x} {ins:02x} {sw:04x} {} ({} bytes) {}",
                    usize::from(!data.is_empty()),
                    data.len(),
                    if data.len() > 24 {
                        data_hex(&data[..24]) + " ..."
                    } else {
                        data_hex(&data)
                    }
                );
            }
            Ok(())
        }
        "apdu" => {
            // apdu <full 5+ byte APDU hex, e.g. e0 d0 00 00 04 00000000>
            let hex = std::env::args().nth(2).ok_or("missing apdu hex")?;
            let clean: String = hex.chars().filter(|c| !c.is_whitespace()).collect();
            let bytes: Vec<u8> = (0..clean.len())
                .step_by(2)
                .map(|i| u8::from_str_radix(&clean[i..i + 2], 16))
                .collect::<Result<_, _>>()?;
            if bytes.len() < 5 {
                return Err("apdu shorter than 5 bytes (CLA INS P1 P2 Lc)".into());
            }
            let (sw, data) = dev.query_full(&bytes)?;
            let limit = if std::env::var_os("FULL").is_some() {
                data.len()
            } else {
                data.len().min(40)
            };
            println!(
                "{sw:04x} ({} bytes) {}{}",
                data.len(),
                data_hex(&data[..limit]),
                if limit < data.len() { " ..." } else { "" }
            );
            Ok(())
        }
        other => Err(format!("unknown subcommand {other}").into()),
    }
}

fn rawusb_err_is_timeout(e: &Box<dyn std::error::Error>) -> bool {
    matches!(e.downcast_ref::<rawusb::Error>(), Some(err) if err.is_timeout())
}

fn data_hex(d: &[u8]) -> String {
    d.iter().map(|b| format!("{b:02x}")).collect::<Vec<_>>().join(" ")
}
