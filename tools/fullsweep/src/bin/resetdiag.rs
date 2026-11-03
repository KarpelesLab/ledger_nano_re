use rawusb::hid::HidDevice;
use std::time::{Duration, Instant};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    fn query(h: &HidDevice) -> Option<String> {
        let rep: Vec<u8> = (0..64).map(|i| match i {
            0=>0x01,1=>0x01,2=>0x05,3=>0,4=>0,5=>0,6=>5,
            7=>0xE0,8=>0xC4,9=>0,10=>0,11=>0,_=>0
        }).chain(0u8..0).collect::<Vec<_>>();
        let mut rep = [0u8;64];
        rep[0]=1;rep[1]=1;rep[2]=5;rep[5]=0;rep[6]=5;
        rep[7]=0xE0;rep[8]=0xC4;
        let to_send: Vec<u8> = std::iter::once(0u8).chain(rep.iter().copied()).collect();
        let _ = rep;
        if h.write(&to_send, Duration::from_millis(400)).is_err() { return Some("send-fail".into()); }
        let mut buf=[0u8;64];
        match h.read(&mut buf, Duration::from_millis(400)) {
            Ok(n) if n>=9 => {
                let len = u16::from_be_bytes([buf[5],buf[6]]) as usize;
                if len>=2 && 7+len<=n {
                    let sw=u16::from_be_bytes([buf[7+len-2],buf[7+len-1]]);
                    return Some(format!("{sw:04x}"));
                }
                Some("parse".into())
            }
            Ok(_) => Some("short".into()),
            Err(_) => None, // timeout
        }
    }
    let t = std::time::Instant::now();
    let ctx = rawusb::Context::new()?;
    let dev = ctx.find_device(0x2581,0x3b7c)?.ok_or("no dev")?;
    let mut hid = HidDevice::open(&dev)?;
    let first = query(&hid);
    eprintln!("t=0s initial E0 C4 = {first:?}");
    for i in 0..20u8 {
        let _ = hid.handle().reset();
        std::thread::sleep(Duration::from_millis(300));
        let d2 = ctx.find_device(0x2581,0x3b7c)?.ok_or("no dev")?;
        hid = HidDevice::open(&d2)?;
        let h = hid.handle();
        let _ = h.clear_halt(0x82);
        let _ = h.clear_halt(0x02);
        std::thread::sleep(Duration::from_millis(800));
        let mut sw = None;
        for _ in 0..200 {
            if let Some(s)=query(&hid){ sw=Some(s); break; }
            std::thread::sleep(Duration::from_millis(50));
        }
        let el = t.elapsed();
        match sw.as_deref() {
            Some("9000")=>{ eprintln!("t={:?} reset#{i} -> RECOVERED (9000)", el); return Ok(()); }
            Some(s)=> eprintln!("t={:?} reset#{i} -> {s}", el),
            None=> eprintln!("t={:?} reset#{i} -> timeout", el),
        }
    }
    eprintln!("not recovered in 20 resets over {:?}", t.elapsed());
    Ok(())
}
