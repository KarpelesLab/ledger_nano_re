# Firmware updates

Newer firmware images are public in Ledger's archived
[`ledger-wallet-chrome`][repo] repo, under `app/firmwares`. They are not stored here.
Our test unit reports firmware 1.0.1, and the newest image is 1.0.4.

## Versions

From `app/firmwares/manifest.yml` and the app's English messages:

| Firmware | Internal `os` | Release note                                                                  |
| -------- | ------------- | ----------------------------------------------------------------------------- |
| 1.0.0    | 1.1.0.0       | Adds transaction validation on a smartphone                                   |
| 1.0.1    | 1.1.0.1       | Adds P2SH, fixes crypto library bugs                                          |
| 1.0.2    | 1.1.0.2       | Fixes spurious reinitialization, adds Segwit and Bitcoin Cash signatures, speeds up crypto |
| 1.0.3    | 1.1.0.3       | Fixes Segwit handling for non-multisig transactions                           |
| 1.0.4    | 1.1.0.4       | Fixes Segwit and Bitcoin Cash handling                                        |

The app's manifest encodes these versions with architecture `0x20`, which matches the
architecture byte our unit returns. Older HW.1 versions (1.4.x) use `0x00`.

## What the images contain

Each version has these files, as lists of APDUs in hex:

| File                 | Commands seen                  | Size for 1.0.4 |
| -------------------- | ------------------------------ | -------------- |
| `reloader`           | `D0 42 06 00`                  | About 8 KB     |
| `loader`             | `E0 05` to `E0 09`             | About 117 KB   |
| `init`               | `D0 20` and `D0 22`            | 225 bytes      |
| `*-from-loader`      | Not examined                   | About 7-9 KB   |

- The spec describes update data as 3DES-CBC encrypted with a diversified firmware
  update key, with a CRC-16 of the cleartext. The images look encrypted, so they
  should not be expected to disassemble. Their entropy has not been measured.
- The spec describes encryption, not signing.
- A target key is disabled after 10 invalid CRC-16 values in sequence, so bad images
  can permanently block updates.

## Update flow

From `app/src/fup/firmware_update_request.coffee`, read but not traced fully:

- `F0 01 01 00 00` reads a bootloader customer ID. The app matches it against 11 known
  IDs, `0143` to `014E`, to select an image variant.
- `E0 22 80 00 01 00` checks remaining PIN attempts. Compared with the bytes planned
  for this query, this is the form to use.
- Firmware below 1.1.0 needs a keycard seed before updating, and it is written back
  with `D0 26`. The seed is 32 hex characters, and `SeedingKeycard` is a required state.
- The app also runs the `init` script, which uses factory commands (`D0 20`, `D0 22`).

Not known:

- Whether a downgrade is possible. The manifest marks versions 1.0.1 and later as
  `overwrite: true`, which covers reinstalling the same version.
- Whether an update preserves the unit's original attestation key.

The Chrome app no longer runs on current Chrome, so installing would need a new loader
based on this code.

[repo]: https://github.com/LedgerHQ/ledger-wallet-chrome
