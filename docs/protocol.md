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
sits in the `D0`–`DF` range the spec never assigns.

**It is a Bitcoin hashing accelerator — a SHA-256 engine with a SHA256d finalize**
(confirmed byte-for-byte against a reference implementation — see "Confirmed: SHA-256
engine" below). The 96-byte `P1=06` body is the engine's working context: a 64-byte
message-block buffer followed by the 32-byte hash state. `P1=05` initialises it
(state ← SHA-256 IV); `P1=06` streams data in and auto-compresses every 64 bytes;
`P1=07` finalises and returns `SHA256(SHA256(message))`, the double-SHA-256 used
throughout Bitcoin (txids, block hashes, Base58Check).

All matrices were captured on a **warmed** device (i.e. after several successful
APDUs). A fresh, immediately-after-power-cycle device shows a different initial
sequence (see "Fresh-boot sequence" below).

Full `P1`×`Lc` matrix (probes below) reveals a real command with three working
sub-commands and a very specific status-word layout:

| `P1` | Response (warmed)                 | Meaning                                  |
| ---- | --------------------------------- | ---------------------------------------- |
| `00` | `Lc=0`→`6700`, `Lc>0`→`6b00`      | invalid P1                               |
| `01`–`03`, `08`, `10`… | `6b00` (all `Lc`) | invalid P1                               |
| `04` | `Lc=0`→`6700`; `Lc≥1`→`9000, 0`   | write to a separate slot; does **not** touch the SHA state or block buffer (purpose open) |
| `05` | `Lc=0`→`6700`; `Lc≥1`→`9000, 0`   | **SHA-256 init**: state ← IV, block buffer + offset cleared (needs `Lc`≥16) |
| `06` | `Lc=0`→`6700`; `Lc≥1`→`9000, 96`  | **SHA-256 update + dump**: write `Lc` bytes into the block, compress on fill, return 64-byte block + 32-byte state |
| `07` | `Lc=0`→`6700`; `Lc≥1`→`9000, 32`  | **SHA256d finalize**: return `SHA256(SHA256(message))` of the whole streamed message (own `Lc` data ignored) |

(`Lc=0` returns `6700` for *every* `P1` — the length check runs before the `P1`
check, so `P1`-validity can only be told apart at `Lc`≥1. A full `P1` sweep at `Lc`≥1
shows exactly four live sub-commands: `04`, `05`, `06`, `07`; all other `P1` → `6b00`.)

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

**Priming rule (confirmed by A/B testing on fresh boots).** The SHA-256 context
must be **initialised** (`P1=05`, `Lc`≥16) before the first `P1=06` read, or that
read returns `6f02` and the device wedges into all-`6faa` until a USB unplug.
`P1=05` is the real init: it resets the hash state to the IV and clears the block
buffer. A write with `Lc=1` does **not** init (the subsequent `P1=06` still returns
`6f02`); `Lc`≥16 is required. The known-good fresh-boot sequence used `P1=04` then
`P1=05` (both `Lc`≥16), but `P1=05` alone does the reset — see the role test below.
`P1=04` leaves the SHA state and block buffer untouched (it writes some other,
still-unidentified slot), so it is not what primes the engine.

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
96-byte `P1=06` response is the SHA-256 working context, split into two fields:

```
offset 0..63   : the 64-byte SHA-256 message-block buffer (fills with streamed input)
offset 64..95  : the 32-byte SHA-256 hash state (the eight 32-bit words H0..H7, big-endian)
```

### Confirmed: SHA-256 engine

The 32-byte state field is a live **SHA-256 hash state register**. Right after a
`P1=05` init it reads the FIPS 180-4 initial hash value:

```
6a09e667 bb67ae85 3c6ef372 a54ff53a 510e527f 9b05688c 1f83d9ab 5be0cd19
```

**The 64-byte buffer is a streaming message block, not a doubling scratchpad.** Each
`P1=06` writes its `Lc` payload bytes **once** at a rolling write offset (advancing by
`Lc`, *not* `2*Lc` — the earlier "append twice" reading was an artifact; the single-write
model is what reproduces the hash exactly). When the offset reaches 64 the engine runs
one **SHA-256 compression** of that block into the state and resets the offset. So the
command is a standard streaming SHA update: push bytes, compress every 64.

**Byte-for-byte verification.** After `P1=05` init (state = IV), feeding three
64-byte blocks and reading the state after each reproduces the SHA-256 midstate chain
exactly (device output == reference `compress()` in Python, all matches):

```
block0 = 00 01 .. 3f                     -> state fc99a2df 88f42a7a 7bb9d180 33cdc6a2 0256755f 9d5b9a50 44a9cc31 5abe84a7
block1 = de*32 ad*32                     -> state a589869b 6df97fe1 d0f214ad 2a918362 e6eb45af ed5af10a bc7ea71d c1a6c8f7
block2 = 40 41 .. 5f 55*32               -> state fca1cbb3 b99c5900 80c8e166 890e9449 ca784ddb 1dad4b72 f25f1933 8280e020
```

Each equals `compress(previous_state, block)`, i.e. the SHA-256 intermediate hash
after absorbing that block. (This is the raw compression / midstate — the length
padding of a full `SHA256()` is never applied, because the engine only ever exposes the
block-level update, not a finalize.) See `tools/sha_test.py` for the driver and the
reference compression used to check it.

The different 32-byte values seen across the earlier session (`ec a0 44…`,
`4d 65 87…`, `6a 09 e6…`) were **not** an NVRAM nonce or device fingerprint — they were
simply whatever midstate the firmware had left in the SHA register at the moment of
reading (e.g. after a boot-time or attestation hash), with `6a 09 e6…` being the
clean post-init IV. The value is stable within a run only because, without a block
completing, no compression fires.

### Sub-command roles (confirmed by a controlled A/B test)

- **`P1=05`** (`Lc`≥16) = **SHA-256 init/reset**. After it, the state is the IV and the
  block buffer + offset are cleared to zero, regardless of the prior state.
- **`P1=06`** = **update + dump**. Writes `Lc` bytes into the block at the offset,
  compresses on fill, returns the 64-byte block and 32-byte state.
- **`P1=07`** (`Lc`≥1, data ignored) = **SHA256d finalize**. Applies SHA-256 MD
  length-padding to the whole streamed message, hashes, then hashes the 32-byte digest
  again, and returns the 32-byte `SHA256(SHA256(message))`. Verified against a reference
  for the empty message, a 16-byte message, a full 64-byte block, and 100- and 200-byte
  messages (all byte-for-byte; see `tools/sha_test.py`). Its own `Lc` payload is a dummy
  (only needed to pass the `Lc`≥1 length gate) — the output depends solely on what was
  streamed via `P1=06`. Empty-message value is `5df6e0e2…9456` = `SHA256(SHA256(""))`.
- **`P1=04`** (`Lc`≥16) = returns `9000` but leaves **both** the SHA state and the block
  buffer unchanged (verified: state held at `52465800…`, earlier `cc` bytes still in the
  buffer with the new byte appended after them). It writes some other, still-unidentified
  slot — possibly a key/IV override for an HMAC or custom-IV mode that no exposed
  sub-command reads back. Its purpose is **open**.

So `E0 D0` is a complete Bitcoin-style hash primitive: init (`05`), streaming update
exposing the live midstate (`06`), and double-SHA-256 finalize (`07`). The exposed
single-SHA digest is only ever the midstate via `P1=06`; `P1=07` is the one that applies
padding and returns a finished (double) digest.

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
 - `E0 D0` (undocumented) → `6700` at `Lc=0`; a **Bitcoin hashing accelerator**, fully
   characterised above (`P1=05` init, `P1=06` streaming update+dump returning the 64-byte
   block buffer and 32-byte hash state, `P1=07` SHA256d finalize, `P1=04` a separate slot
   write).
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
| `E0 d0` | **undocumented** — Bitcoin hash accelerator (spec §§19–25.6) | `Lc=0`→`6700`; `P1=05` `Lc≥16`→init (state=IV); `P1=06` `Lc≥1`→`9000` 96 bytes (64-byte message block + 32-byte hash state, compresses on fill); `P1=07` `Lc≥1`→`9000` 32 bytes (SHA256d of streamed message); `P1=04` `Lc≥1`→`9000 0` (separate slot) |
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
