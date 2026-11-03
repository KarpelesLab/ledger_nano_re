# Host protocol

Summary of Ledger's [btchip technical specification][spec], "Ledger Wallet 1: Common
Technical Specifications", for firmware `lw1-1.0` (March 2015). Our unit reports
firmware 1.0.1.

On our unit, the HID framing and GET FIRMWARE VERSION worked as documented, with the
command sent as `E0 C4 00 00 00`, as `btchip-python` does. GET OPERATION MODE
returned `6985` for both P1 values. VERIFY PIN with P1=`0x80` (report remaining
attempts, `E0 22 80 00 01 00`) also returned `6985`. Both fit an unconfigured unit.
Everything else here is still untested.

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
