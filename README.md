# Ledger Nano reverse engineering

Reverse engineering of the original Ledger Nano, a legacy product with no
display. It runs on an STMicroelectronics ST23YT66 connected directly to USB.

## X-ray imaging

![X-ray of the Ledger Nano module](xray/202610260220940004_20261103013.png)

`xray/202610260220940004_20261103013.png` (688 x 834 px, no scale reference)

Initial observations from the image, not yet checked against the physical device:

- The module has eight contact segments, in two rows of four.
- Each segment has a round or rounded landing point, and traces run off the top
  and bottom edges of the module.
- Two more round features sit near the centre, just above the split between the
  two rows.
- Thin bond wires are faintly visible in the central area, running from the
  contact traces to the die. About six can be followed, but their die ends are
  hard to resolve.
- Two of the wires appear to start from the same landing on the top-left contact.
- A fainter rectangular shape extends below the module.

## Die photo

![Microscope photo of the die](microscope/die_top.png)

`microscope/die_top.png` (2000 x 1412 px, no scale reference)

Optical microscope image of the die, which appears to be stitched from several
fields. It is mirrored relative to the X-ray. To compare them, flip it
horizontally:

```sh
magick microscope/die_top.png -flop die_top_flopped.png
```

The die was extracted mechanically with a knife, not chemically. The cracks,
gouges and missing fragments on its surface come from that extraction, so they
are not device features.

Six bond wire sites are visible, out of 20 pad openings along the two long edges.
Pixel coordinates are for the unflipped image and are approximate:

| Edge   | Position (x, y) | Appearance                   |
| ------ | --------------- | ---------------------------- |
| Top    | (155, 378)      | Brown residue, near the edge |
| Top    | (527, 318)      | Dark bond ball               |
| Top    | (1733, 135)     | Dark bond ball, corner       |
| Bottom | (335, 1305)     | Brown residue, near the edge |
| Bottom | (1300, 1113)    | Dark bond ball               |
| Bottom | (1385, 1100)    | Dark bond ball, pad damaged  |

The wire locations look broadly similar in the X-ray and the mirrored photo, but
each wire has not yet been matched to a specific pad.
