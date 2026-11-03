# Host protocol

Summary of Ledger's [btchip technical specification][spec], "Ledger Wallet 1: Common
Technical Specifications", for firmware `lw1-1.0` (March 2015). Our unit reports
firmware 1.0.1.

On our unit, the HID framing and the read-only info commands all worked as documented
(`tools/devicescan.py`):

- **GET RANDOM (`E0 C0 00 00`, `Le`)** returned `Le` random bytes with status `9000`.
- **GET DEVICE ATTESTATION (`E0 C2 00 00 08` + 8-byte blob)** returned batch id `2`,
  derivation id `1`, supported-mode flag `0x20`, current mode `0x01`, firmware `1.1.16`
  internal form, loader id `0.00`, and a valid ECDSA secp256k1 signature. The signature
  is over `sha256(<the 8 firmware/mode/loader bytes> || blob)`, and verifies against the
  batch-2 public key that Ledger ships in its archived chrome app. The nonce is fresh
  each call, so repeated responses differ.
- **GET FIRMWARE VERSION (`E0 C4 00 00 00`)** returned features `0x01` (compressed keys),
  architecture `0x20`, firmware `1.0.1`, loader `1.16`.
- **GET FIRMWARE UPDATE ID (`D0 24 00 00 08` + 8 bytes)** returned `9000` with the 8-byte
  value `00 00 00 00 00 00 00 01`. The command needs data (case 4); with `Lc=0` it
  returns `6700` Incorrect length. This is documented as pre-issuance, matching the
  unit's unconfigured state.

GET OPERATION MODE (`E0 24`) returned `6985` for both P1 values. VERIFY PIN with P1=`0x80`
(report remaining attempts, `E0 22 80 00 01 00`) also returned `6985`. Both fit an
unconfigured unit.

## Full 65,536-command sweep (256 CLA × 256 INS)

We sent every `(CLA, INS)` pair at `P1=P2=0`, `Lc=0` — the whole 65,536-command space —
using [`tools/fullsweep`](../tools/fullsweep) (Rust over `rawusb`/usbfs, so only the
`usb` group is needed; it self-resets on a wedged device and resumes from its TSV).
The device sits in `E0`/`D0` handler space; with no application loaded, `P1`/`P2` and
data matter only for the handful of commands that return `6700` (see
[next section](#probing-the-6700-group)). The virgin unit returns:

| Status word | Count | Meaning |
| --- | --- | --- |
| `6d00` | 65,499 | unimplemented / not this CLA |
| `6700` | 33 | implemented, `Lc`-dependent |
| `9000` | 3 | `E0 C0`, `E0 C4`, `E0 CA` |
| `6985` | 1 | `E0 24` (conditions not satisfied) |

**Only `CLA` `E0` and `D0` have any handler at all.** The other 254 CLAs (`00`–`DF`
below `E0`, and `E1`–`FF`) answered `6d00` for all 256 `INS` values. In a virgin
(1.0.1, no-app) unit the `F0` "Bitcoin dongle" CLA space is therefore entirely
unimplemented — no app is present.

- `E0`: 31 non-`6d00` INS — `C0 C4 CA` (`9000`), `24` (`6985`), and 27 INS returning
  `6700`: `10 12 14 20 22 26 28 30 32 34 36 38 3a 40 42 44 46 48 4a 4e b0 b2 b4 b6 c2 c6 d0`.
  (`E0 C2`, device attestation, is among these — it needs `Lc=8` to return `9000`.)
- `D0`: 6 non-`6d00` INS, all `6700`: `20 22 24 26 28 42`.

The merged raw output is [tools/fullsweep/tsv/full_65536_p12_0_l0.tsv](../tools/fullsweep/tsv/full_65536_p12_0_l0.tsv)
(`cla ins sw has_data data`, 65,536 lines).

### Undocumented command found — `E0 D0`

`E0 D0` returned `6700` at `Lc=0` (implemented, data-dependent) but appears **nowhere**
in the spec (§§19–25.6). Its neighbours `E0 CF` and `E0 D1` are `6d00`, so it is a
genuine stand-alone handler, not a `P1`/`P2` variant missed by the `P1=P2=0` probe. It
sits in the `D0`–`DF` range the spec never assigns — a candidate for a private / debug
"SET" command.

All matrices were captured on a **warmed** device (i.e. after several successful
APDUs). A fresh, immediately-after-power-cycle device shows a different initial
sequence (see "Fresh-boot sequence" below).

Full `P1`×`Lc` matrix (probes below) reveals a real command with three working
sub-commands and a very specific status-word layout:

| `P1` | Response (warmed)                 | Meaning                                  |
| ---- | --------------------------------- | ---------------------------------------- |
| `00` | `Lc=0`→`6700`, `Lc>0`→`6b00`      | invalid P1                               |
| `01`–`03`, `08`, `10`… | `6b00` (all `Lc`) | invalid P1                               |
| `04` | `Lc=0`→`6700`; `Lc≥1`→`9000, 0`   | "ack / write" sub-command (any `Lc` accepted) |
| `05` | `Lc=0`→`6700`; `Lc≥1`→`9000, 0`   | "ack / write" sub-command (any `Lc` accepted) |
| `06` | `Lc=0`→`6700`; `Lc≥1`→`9000, 96`  | "read+dump" sub-command (returns 96 bytes) |

### Fresh-boot sequence

A freshly powered-up device (before any other APDU) does not immediately accept
`P1=06`. Observed in two consecutive fresh-boot captures:

```
fresh boot
  P1=06 Lc=0          -> 6700          (standard wrong-lc)
  P1=06 Lc=1 data=00  -> 6f02 (0 bytes)   NEW status word on fresh boot only
  P1=06 Lc=1 data=00  -> 6faa (0 bytes)   all-6faa wedge (see below)
  (every other INS after this returns 6faa until a USB unplug)
```

`6f02` does not appear in spec §27's explicit status-word table, but the spec
defines `6fxx` as **"Technical problem (Internal error, please report)"** — so
`6f02` is a command-specific internal-error substatus, distinct from the generic
`6faa` that the whole device falls into afterwards. Reproducible across every
fresh-boot capture this session.

**Priming rule (confirmed by A/B testing on fresh boots).** A `P1=04` or `P1=05`
write with `Lc` ≥ 16 primes the scratch pad so that the *next* `P1=06` read returns
`9000` with the usual 96-byte body instead of `6f02`. A `P1=04`/`P1=05` write with
`Lc=1` does **not** prime (the first subsequent `P1=06` still returns `6f02`). The
primiting call consumes its own payload into an internal slot — we did not see the
`P1=04`/`P1=05` payload land in the 64-byte scratch dump on subsequent `P1=06` reads,
so the two writes are independent of the scratch buffer (they appear to be a small
separate scratch area, or a register write).

```
fresh boot:  P1=04 Lc=1  data=00           -> 9000, 0    (not a priming write)
             P1=06 Lc=1  data=00           -> 6f02, 0    (still unprimed)
             P1=05 Lc=1  data=00           -> 6faa       (wedge)

fresh boot:  P1=04 Lc=16 data=01*16        -> 9000, 0    (priming write)
             P1=05 Lc=16 data=01*16        -> 9000, 0    (priming write)
             P1=06 Lc=1  data=00           -> 9000, 96   (scratch dump + 32-byte tail)
             P1=06 Lc=1  data=00           -> 9000, 96   (stable)
```

### The `E0 CB`–`FF` range is unimplemented (not a real "reserved" block)

Earlier sweep output (taken while the device was in the all-`6faa` wedge) reported a
"contiguous 53-INS `E0 CB`–`FF` 6faa block". A clean re-sweep on a healthy, warmed
device shows the entire range `E0 CB`–`E0 FF` is `6d00` (unimplemented) **except `D0`**,
which is the only handler there and is fully documented above. The `6faa` we saw before
was the transient all-`6faa` wedge, not real per-INS behaviour:

```
healthy E0 CB-FF sweep, P1=P2=0, Lc=0:
  E0 cb,cc,cd,ce,cf (5)
  E0 d1..df  (15)
  E0 e0..ef  (16)
  E0 f0..ff  (16)         -> all 6d00   (52 INS)
  E0 d0                      -> 6700   (the one real handler)
```

This confirms `D0` is a stand-alone handler and its `CB..FF` neighbours are
plain-`6d00` "not this INS"-style responses, consistent with the `E0 20..C6` handler
map elsewhere in this document.

P2 is **ignored** by all three (identical responses for P2=`00`/`01`/`02`/`80`). The
96-byte `P1=06` response is split into two fields:

```
offset 0..63   : a 64-byte persistent scratch buffer  (see below)
offset 64..95  : a 32-byte non-zero value  (e.g. 6a 09 e6 67 bb 67 ae 85 3c 6e f3
                 72 a5 4f f5 3a 51 0e 52 7f 9b 05 68 8c 1f 83 d9 ab 5b e0 cd 19)
```

**The 64-byte scratch buffer.** It is *not* a one-shot echo — it is a persistent work
buffer that **accumulates** across `P1=06` calls and is only cleared on a power cycle.
On each `P1=06` call the command appends the `Lc`-byte request data **twice** at the
current write offset (advancing by `2*Lc`). After a fresh power cycle the buffer reads
all zero; each subsequent call appends behind the previous content. Reproducing the
observed sequence (fresh device):

```
send  Lc=4 ab cd ef 01  ->  buf: ab cd ef 01 ab cd ef 01 ...
send  Lc=2 b2 c3        ->  buf: ab cd ef 01 ab cd ef 01 b2 c3 b2 c3 ...
send  Lc=1 d4           ->  buf: ... b2 c3 b2 c3 d4 d4 ...
```

(each line shows the growing tail; the buffer is dumped back to the host verbatim on
every `P1=06` response). This makes `P1=06` behave like a "append to RAM scratchpad
and dump the pad" primitive.

**The 32-byte tail value.** From repeated clean reads:

- **Stable** across repeated `P1=06` reads, across `Lc` (`1`/`2`/`4`/`8`/`16`/`32`/`48`),
  across `P2`, and across `P1=04` / `P1=05` writes with an `Lc=1` zero payload. Six
  back-to-back reads returned byte-identical tails.
- **Not** `SHA256` of the empty field, the input data, or any obvious hash of
  `Lc`/P1/P2 (checked against six candidate inputs).
- **Not** a fixed ROM constant: over the session the value was observed to take
  different stable values in turn (`ec a0 44…` → `4d 65 87…` → `6a 09 e6…`). Each was
  held for many operations before changing. The change coincided with device-state
  transitions (power-cycles / clear-halt after the transient all-`6faa` wedges), so
  the value is a **stored, reset-dependent value** — plausibly an NVRAM counter, a
  ROM-derived fingerprint re-seeded on power-up, or a one-time-pad / nonce state.
  It is the strongest direct "device identity / state" reading available outside the
  attestation signature, consistent with a private/debug `E0 D0` handler.

  (Early in the session an awk-based parser reported spurious per-read churn; clean
  byte-level parsing shows the value is in fact flat across a run. The genuine
  transitions were the power-cycle-related ones above.)

`P1=04` and `P1=05` return `9000` with no body for any `Lc`≥1 regardless of `P2` —
consistent with **write/set** sub-commands that consume `Lc` bytes of input and return
nothing. They were only probed with zero payloads; whether non-zero `P1=04`/`P1=05`
data mutates the `P1=06` value (and thus what the command *does*) is still open.

### Spec commands not implemented in 1.0.1

`E0 A0` (GET TRANSACTION LIMIT, §22.1) and `E0 A2` (SET TRANSACTION LIMIT, §22.2) are
documented but return `6d00` here — the server-mode transaction-limit pair was not
enabled in 1.0.1. Every other spec command is present.

## Probing the `6700` group

Sending zeroed data of varying `Lc`:

- `D0 24` → `9000` update id `00 00 00 00 00 00 00 01` (confirmed).
- `D0 20` `D0 22` `D0 26` `D0 28` → `6985` (factory-init commands; implemented but
  pre-issuance only, so they report "conditions not satisfied").
- `D0 42` → `6b00` Incorrect parameter P1/P2. The spec (`§25.6`) defines it as
  **FIRMWARE UPDATE / bootloader entry**: P1=`03` start, P1=`06` load, variable `Lc`,
  available only before setup. P1/P2 = `00 00` is therefore rejected.
- `E0 20` (SETUP) → `6a80` Invalid data.
 - `E0 D0` (undocumented) → `6700` at `Lc=0`; fully characterised above (three
   sub-commands `P1=04/05/06`, the `P1=06` read returning a 96-byte body with a
   deterministic 32-byte device blob).
- All the other even-instruction `E0`s → `6985`.

`6a80` and `6b00` are both defined in spec §27 as distinct status words; neither was
seen before this probe. `E0 CA` (`9000`, no data, any P1/P2 `→ 6faa`) is the
GET POINT OF SALE SEED command (`§24.5`) — in a virgin unit it succeeds but returns an
empty seed block rather than a nonce-derived one.

## Cross-reference: spec commands vs. this unit

The 38 commands documented in spec §§19–25.6 all return a real (non-`6d00`) status in
the full sweep; **one extra, undocumented command also exists — `E0 D0`**. The two
server-mode Transaction-Limit commands (`E0 A0`/`A2`) are documented but `6d00` (not
enabled in 1.0.1).

| APDU | Command (spec §) | Virgin-state response |
| --- | --- | --- |
| `E0 20` | SETUP (§19.1) | `6a80` |
| `E0 10` | SET USER KEYCARD (§19.2) | `6985` |
| `E0 12` | SETUP SECURE SCREEN (§19.3) | `6985` |
| `E0 14` | SET ALT COIN VERSIONS (§19.4) | `6985` |
| `E0 22` | VERIFY PIN (§19.5) | `6985` |
| `E0 24` | GET OPERATION MODE (§19.6) | `6985` |
| `E0 26` | SET OPERATION MODE (§19.7) | `6700` (except `Lc=1` → `6985`) |
| `E0 28` | SET KEYBOARD CONFIG (§19.8) | `6985` |
| `E0 40` | GET WALLET PUBLIC KEY (§20.1) | `6985` |
| `E0 42` | GET TRUSTED INPUT (§20.2) | `6985` |
| `E0 44` | UNTRUSTED HASH TXN IN START (§20.3) | `6985` |
| `E0 46` | ... FINALIZE (§20.4) | `6985` |
| `E0 48` | UNTRUSTED HASH SIGN (§20.5) | `6985` |
| `E0 4a` | ... FINALIZE FULL (§20.6) | `6985` |
| `E0 4e` | SIGN MESSAGE (§20.7) | `6985` |
| `E0 30` | STORE TRUST ROOT BIP 70 (§21.1) | `6700` at `Lc=0`, `6d00` with data |
| `E0 32` | CREATE CERT BIP 70 (§21.2) | `6985` |
| `E0 34` | CREATE PAYMENT REQ BIP 70 (§21.3) | `6985` |
| `E0 36` | PROCESS CERT BIP 70 (§21.4) | `6985` |
| `E0 38` | PARSE PAYMENT REQ BIP 70 (§21.5) | `6985` |
| `E0 3a` | ... FINALIZE BIP 70 (§21.6) | `6700` at `Lc=0`, `6d00` with data |
| `E0 a0` | GET TRANSACTION LIMIT (§22.1) | `6d00` |
| `E0 a2` | SET TRANSACTION LIMIT (§22.2) | `6d00` |
| `E0 b0` | IMPORT PRIVATE KEY (§23.1) | `6985` |
| `E0 b2` | GET PUBLIC KEY (§23.2) | `6985` |
| `E0 b4` | DERIVE BIP32 KEY (§23.3) | `6985` |
| `E0 b6` | ECDSA SIGN/VERIFY IMMEDIATE (§23.4) | `6985` |
| `E0 c0` | GET RANDOM (§24.1) | `9000` |
| `E0 c2` | GET DEVICE ATTESTATION (§24.2) | `6700` at Lc=0; `9000` with Lc=8 |
| `E0 c4` | GET FIRMWARE VERSION (§24.3) | `9000` |
| `E0 c6` | COMPOSE M OF N ADDRESS (§24.4) | `6700` at `Lc=0`, `6d00` with data |
| `E0 ca` | GET POINT OF SALE SEED (§24.5) | `9000`, empty |
| `E0 d0` | **undocumented** (spec §§19–25.6) | `Lc=0`→`6700`; `P1=04/05` `Lc≥1`→`9000 0`; `P1=06` `Lc≥1`→`9000` 96 bytes (64 zero + 32-byte device blob) |
| `D0 20` | FACTORY INIT KEYS (§25.1) | `6985` |
| `D0 22` | FACTORY INIT ATTESTATION (§25.2) | `6985` |
| `D0 24` | GET FIRMWARE UPDATE ID (§25.3) | `9000` `00 00 00 00 00 00 00 01` |
| `D0 26` | FACTORY INIT KEYCARD SEED (§25.4) | `6985` |
| `D0 28` | FACTORY INIT BIP 70 TRUST ROOT (§25.5) | `6985` |
| `D0 42` | FIRMWARE UPDATE / bootloader (§25.6) | `6b00` (wrong P1/P2) |

`E0 a0`/`a2` (Transaction Limit §22) answer `6d00` — server-mode commands that were
not enabled in 1.0.1.

## USB HID framing

Messages travel in 64-byte HID interrupt reports, which matches the
[descriptors we read](../README.md#usb-identity). Each report starts with this header:

| Field          | Size | Value                                  |
| -------------- | ---- | -------------------------------------- |
| Channel ID     | 2    | `0x0101`, big endian (not used yet)    |
| Command tag    | 1    | `0x05` APDU, `0x02` ping               |
| Sequence index | 2    | Big endian, `0x0000` for the first     |

The payload follows. A command is a 2-byte big-endian length, then
`CLA INS P1 P2 Lc` and optional data. A response is a 2-byte big-endian length, then
data and a status word.

## Commands that the spec says need no PIN

| APDU          | Command                | Returns                                         |
| ------------- | ---------------------- | ----------------------------------------------- |
| `E0 C4 00 00` | GET FIRMWARE VERSION   | Feature flags, architecture, firmware and loader versions |
| `E0 C2`       | GET DEVICE ATTESTATION | Key IDs, modes, versions, signature             |
| `E0 C0`       | GET RANDOM             | Random bytes                                    |

`E0 22 80` (VERIFY PIN with P1 = `0x80`) is documented as returning the remaining PIN
attempts rather than checking a PIN. `E0 24` (GET OPERATION MODE) is documented as
available after setup.

## Commands that can destroy data

- **VERIFY PIN (`E0 22 00`):** three wrong PINs in a row erase the device. It must be
  physically reset after each wrong PIN.
- **Second factor:** 30 invalid challenges in a row erase the device.
- **SETUP (`E0 20`):** only works before setup or after a wipe.
- **FIRMWARE UPDATE (`D0 42`):** device dependent, and needs user data wiped first.
- **Factory commands (`D0 20` to `D0 28`):** documented as pre-issuance only.

Do not send VERIFY PIN with P1 = `0x00` unless a wipe is acceptable.

## Keycard

The spec describes a keycard that maps each character from `0x30` to `0x7a` to a hex
digit. Each digit comes from encrypting `00..50` with the keycard's 3DES-2 seed in CBC
mode, then XORing the two nibbles of each output byte. See also
[LSB 017](https://donjon.ledger.com/lsb/017/).

## Hardware

The spec does not mention the ST23YT66, its pins, GPIO or SPI, so it does not explain
`B2` and `B3`.

[spec]: https://ledgerhq.github.io/btchip-doc/bitcoin-technical.html
