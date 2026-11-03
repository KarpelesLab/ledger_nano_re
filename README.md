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
- Seven thin bond wires run from the contacts and one round feature to the die.
  See [Bond wire map](#bond-wire-map).
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

Six bond sites are clearly visible, out of 20 pad openings along the two long
edges. The wire map below indicates a seventh on a damaged pad.

## Wires through the compound

![Bond wires seen through the compound](microscope/20261103_153124.JPG)

`microscope/20261103_153124.JPG` (5376 x 3024 px, RaySmart VMS700, no scale
reference)

This view shows the wires and the die through the transparent compound. It has
the same handedness as `die_top.png`, so it is only rotated relative to that
photo and mirrored relative to the X-ray.

`microscope/die_overlay.png` shows `die_top.png` warped onto this view. The
warp uses hand-picked die corners. The pad positions line up with the pale pad
openings visible on the die, including the group of four. The 180-degree
alternative puts that group at the wrong end of the die, so it was rejected.

## Bond wire map

Contacts are named by their position in the X-ray as stored: `T1` to `T4` along
the top row and `B1` to `B4` along the bottom row, each numbered left to right.
In `20261103_153124.JPG`, the right column reads `T1` to `T4` from bottom to top,
and the left column reads `B1` to `B4` from bottom to top.

Die pad coordinates are approximate pixel positions in the unflipped
`die_top.png`.

| Wire | From                 | Die pad (x, y) | Pad appearance                     | Confidence |
| ---- | -------------------- | -------------- | ---------------------------------- | ---------- |
| 1    | `B3`                 | (407, 1285)    | Torn up, no bond visible           | Inferred   |
| 2    | `T3`                 | (335, 1305)    | Brown residue                      | Good       |
| 3    | `B2`                 | See below      | Dark bond ball                     | Pair only  |
| 4    | Via connected to `T4` | (1733, 135)   | Dark bond ball                     | Good       |
| 5    | `T2`                 | (155, 378)     | Brown residue                      | Good       |
| 6    | `T1`                 | (527, 318)     | Dark bond ball                     | Good       |
| 7    | `T1`                 | See below      | Dark bond ball                     | Pair only  |

- Wires 3 and 7 land on the adjacent pads at (1300, 1113) and (1385, 1100). The
  images do not show which wire goes to which pad.
- Wire 1 reaches the die where the knife damage crosses the pad at (407, 1285).
  That is why only six sites are visible in the die photo.
- The torn pad at (232, 378) has no visible wire.
- `T1` has two bond wires, and `B1` and `B4` have none. `T4` has no direct wire
  and reaches the die through its via.
- Two round features are vias or similar: one connects to `T1` with no wire, and
  one connects to `T4` with wire 4.

This map comes from images only and has not been confirmed electrically.
