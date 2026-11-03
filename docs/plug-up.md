# Plug-up research notes

Plug-up owns USB vendor ID `0x2581`, which our device uses. These notes separate
what sources state from what we infer.

## Company timeline

| Date       | Event                                                                                                                       | Source |
| ---------- | --------------------------------------------------------------------------------------------------------------------------- | ------ |
| 2011-07-04 | Plug-up International, originally from the Le Mans area, sets up near Rouen. Its product is a credit-card-style USB card for linking offline and online marketing. | [Rouen Normandy Invest][invest] |
| 2014-04-21 | Announces Authentikator for FIDO, a USB smartcard token built on an STMicroelectronics secure USB microcontroller platform. Named CEO: Guillaume Moatti. | [CIOL][ciol] |
| Undated    | Happlink SAS takes over the business from liquidation in March of an unknown year, keeping about 15 staff, with Corinne Mancel-Toulot leading. The Security Key product continues. | [Le Journal des Entreprises][jde], search excerpt only |
| 2014-2016  | Archived redirects run from `sk.plug-up.com` to `sk.happlink.com`, per snapshots dated 2014 and 2016.                        | [The Wiert Corner][wiert] |
| 2020-01-31 | A blog post describes the company as long gone. No second source confirms the closure.                                      | [The Wiert Corner][wiert] |

## Links to Ledger

Stated by sources:

- Ledger says its CTO, Nicolas Bacca, designed "the 2nd commercial U2F
  implementation for Plug-up/Happlink". ([Ledger][ledger-u2f])
- `btchip-js-api`, Ledger's HW.1 JavaScript API, requires the Plug-up Bridge Chrome
  extensions and uses `ubinity/PlugupExtension`. ([btchip-js-api][jsapi])
- The BTChip announcement names the ST23YT66 as its chip. Its author, `btchip`, is
  Nicolas Bacca, so this is a first-hand source. ([BitcoinTalk][btc])
- The HW.1 is also described as based on the ST23YT66. ([Saleem Rashid][rashid])
- Electrum lists `2581:3b7c`, our device's ID, as "HW.1 Ledger production".
  ([Electrum][electrum])

Not established:

- No source found says Plug-up manufactured the HW.1 or Nano.
- No source found says Ledger's hardware or firmware derives from a Plug-up
  platform. The shared vendor ID and software dependency are suggestive only.
- No source found says what contacts `B2` and `B3` carry.

## Vendor ID 0x2581

| PID      | Name                        | Source                             |
| -------- | --------------------------- | ---------------------------------- |
| `0x1807` | Generic HID Smartcard       | `usb.ids`                          |
| `0x1807` | HW.1 legacy btchip          | [Electrum][electrum]               |
| `0x1808` | WinUSB Smartcard            | `usb.ids`                          |
| `0x2b7c` | HW.1 transitional production | [Electrum][electrum]              |
| `0x3b7c` | HW.1 Ledger production      | [Electrum][electrum]; our device   |
| `0x4b7c` | HW.1 Ledger test            | [Electrum][electrum]               |
| `0xf1d0` | Nitrokey U2F                | `usb.ids`, [Nitrokey rules][nk]    |
| `0xf1d0` | Happlink (formerly Plug-Up) Security KEY | [libu2f-host rules][u2f] |

The same ID, `0xf1d0`, is named for both Nitrokey and Happlink. That may mean a
rebranded token, but no source found says so.

## Other ST23YT66 products

Public FIPS 140-2 security policies exist for other tokens on this chip, and may
hold chip-level details. Neither has been read closely yet.

- [SecureMetric ST3 ACE][fips-st3]
- [HyperSecu HYP2003][fips-hyp]

A retailer listing was reported to say the Plug-up U2F key uses the ST23YT66, but
the page returned 404 when opened, so this is unverified.

## Related: Ledger Security Bulletin 017

[LSB 017][lsb] covers the HW.1 and Nano, and describes their keycard scheme:

- `SET_USER_KEYCARD` can be brute-forced with physical access and knowledge of the
  PIN. Its comparison exits early, which leaks timing, and it has no try counter.
- After 30 failed keycard attempts during signing, the device erases its secrets.
- No fix will be provided, because the products are discontinued.

## Leads not yet followed

- Archived Plug-up and Happlink sites, listed in [The Wiert Corner][wiert]. The
  Wayback Machine could not be reached from this environment.
- [`ubinity/PlugupExtension`][pue], for the host-side protocol.
- The rest of the [BitcoinTalk thread][btc]. Only its first 100,000 characters were
  checked, out of about 378,000.
- French company registry entry for Happlink, SIREN 811284769, on [Pappers][pappers].
  The page refused automated access.

[invest]: https://www.rouennormandyinvest.com/actualites/plug-up-sinstalle-a-rouen/
[ciol]: https://www.ciol.com/plug-announces-certified-fido-ready-uaf-usb-token/
[jde]: https://lejournaldesentreprises.com/normandie/article/rouen-happlink-reprend-lactivite-de-plug-international-65025
[wiert]: https://wiert.me/2020/01/31/happlink-plugup-died-but-you-can-still-use-their-u2f-usb-key/
[ledger-u2f]: https://www.ledger.com/fido-u2f
[jsapi]: https://github.com/LedgerHQ/btchip-js-api
[btc]: https://bitcointalk.org/index.php?topic=134999.0
[rashid]: https://saleemrashid.com/2018/03/20/breaking-ledger-security-model/
[electrum]: https://github.com/spesmilo/electrum/blob/master/electrum/plugins/ledger/ledger.py
[nk]: https://github.com/Nitrokey/libnitrokey/blob/master/data/41-nitrokey.rules
[u2f]: https://github.com/Yubico/libu2f-host/blob/master/70-u2f.rules
[fips-st3]: https://csrc.nist.gov/csrc/media/projects/cryptographic-module-validation-program/documents/security-policies/140sp2302.pdf
[fips-hyp]: https://csrc.nist.gov/csrc/media/projects/cryptographic-module-validation-program/documents/security-policies/140sp2950.pdf
[lsb]: https://donjon.ledger.com/lsb/017/
[pue]: https://github.com/ubinity/PlugupExtension
[pappers]: https://www.pappers.fr/entreprise/happlink-811284769
