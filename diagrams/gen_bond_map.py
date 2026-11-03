#!/usr/bin/env python3
"""Generate bond_map.svg. Geometry follows microscope/20261103_153124.JPG."""
from html import escape

# Crop origin in the JPG is (1450, 1300). All drawing coordinates use that crop.
DIE_TOP_CORNERS = [(35, 340), (1780, 10), (1980, 1040), (250, 1340)]
DIE_CROP_CORNERS = [(1000, 330), (800, 850), (485, 715), (685, 210)]

COL = {"VBUS": "#c62828", "D-": "#2e7d32", "D+": "#1565c0", "GND": "#37474f",
       "B2": "#ef6c00", "B3": "#7b1fa2", "NC": "#9e9e9e"}


def solve(a, b):
    n = len(a)
    m = [row[:] + [v] for row, v in zip(a, b)]
    for i in range(n):
        p = max(range(i, n), key=lambda r: abs(m[r][i]))
        m[i], m[p] = m[p], m[i]
        for r in range(n):
            if r != i:
                f = m[r][i] / m[i][i]
                m[r] = [x - f * y for x, y in zip(m[r], m[i])]
    return [m[i][n] / m[i][i] for i in range(n)]


def homography(src, dst):
    a, b = [], []
    for (x, y), (u, v) in zip(src, dst):
        a.append([x, y, 1, 0, 0, 0, -u * x, -u * y]); b.append(u)
        a.append([0, 0, 0, x, y, 1, -v * x, -v * y]); b.append(v)
    return solve(a, b)


H = homography(DIE_TOP_CORNERS, DIE_CROP_CORNERS)


def die(x, y):
    w = H[6] * x + H[7] * y + 1
    return ((H[0] * x + H[1] * y + H[2]) / w, (H[3] * x + H[4] * y + H[5]) / w)


# The 20 pad openings, as approximate pixel positions in die_top.png.
PADS = [(155, 378), (232, 378), (420, 340), (527, 318), (627, 298), (787, 272),
        (882, 248), (978, 228), (1733, 135),
        (335, 1305), (407, 1285), (565, 1255), (728, 1225), (1218, 1130),
        (1300, 1113), (1385, 1100), (1543, 1068), (1628, 1050), (1712, 1033),
        (1797, 1018)]
TORN = {(232, 378), (407, 1285)}
PAIR = [(1300, 1113), (1385, 1100)]
PAIR_MID = ((PAIR[0][0] + PAIR[1][0]) / 2, (PAIR[0][1] + PAIR[1][1]) / 2)

CONTACTS = {"T1": (1235, 1020, "VBUS"), "T2": (1250, 700, "D-"),
            "T3": (1280, 280, "D+"), "T4": (1292, -37, "GND"),
            "B1": (125, 925, "NC"), "B2": (145, 600, "B2"),
            "B3": (185, 190, "B3"), "B4": (230, -144, "NC")}
SIGNAL_TEXT = {"VBUS": "VBUS", "D-": "D-", "D+": "D+", "GND": "GND",
               "B2": "unknown", "B3": "unknown", "NC": "no wire"}
VIA_T4 = (450, 800)
VIA_T1 = (505, 60)

# Traces on the module: (colour key, points)
TRACES = [("GND", [(1228, -88), (1150, -150), (510, -180), (378, -50), (378, 640), (423, 744)]),
          ("VBUS", [(567, 61), (1000, 75), (1080, 180), (1040, 800), (1010, 1090), (1192, 1090)])]
# Lands: the widened copper beside each contact where a wire is bonded.
LANDS = [("B3", (265, 208), (270, 210)), ("B2", (226, 593), (250, 590)),
         ("D+", (1198, 280), (1190, 280)), ("D-", (1196, 639), (1170, 610)),
         ("VBUS", (1157, 994), (1100, 975))]
# Wires: number, colour key, contact-side path, die pad, dashed
WIRES = [
    (1, "B3", [(270, 210), (420, 215), (657, 268)], (407, 1285), True),
    (2, "D+", [(1190, 280), (950, 295)], (335, 1305), False),
    (3, "B2", [(250, 590), (340, 575), (560, 525)], PAIR_MID, True),
    (4, "GND", [(512, 815), (730, 825)], (1733, 135), False),
    (5, "D-", [(1170, 610), (1080, 510), (985, 370)], (155, 378), False),
    (6, "VBUS", [(1100, 975), (1075, 920), (990, 620), (935, 470)], (527, 318), False),
    (7, "VBUS", [(1024, 972), (820, 790), (680, 640)], PAIR_MID, True),
]
LABEL_AT = {1: (440, 190), 2: (1090, 262), 3: (420, 590), 4: (620, 860),
            5: (1115, 490), 6: (1050, 790), 7: (920, 915)}
ROWS = [(1, "B3", "unknown", "(407, 1285)", "torn pad, inferred"),
        (2, "T3", "D+", "(335, 1305)", ""),
        (3, "B2", "unknown", "(1300, 1113) or (1385, 1100)", "unresolved pair"),
        (4, "T4 via", "GND", "(1733, 135)", ""),
        (5, "T2", "D-", "(155, 378)", ""),
        (6, "T1", "VBUS", "(527, 318)", ""),
        (7, "T1", "VBUS", "(1300, 1113) or (1385, 1100)", "unresolved pair")]
ROW_COL = {1: "B3", 2: "D+", 3: "B2", 4: "GND", 5: "D-", 6: "VBUS", 7: "VBUS"}

o = []
def add(s): o.append(s)
def pts(p): return " ".join(f"{x:.1f},{y:.1f}" for x, y in p)
def text(x, y, s, size=26, anchor="start", fill="#212121", weight="normal"):
    add(f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" text-anchor="{anchor}" '
        f'fill="{fill}" font-weight="{weight}">{escape(s)}</text>')

add('<svg xmlns="http://www.w3.org/2000/svg" viewBox="-60 -400 2500 1560" '
    'font-family="Helvetica, Arial, sans-serif">')
add('<rect x="-60" y="-400" width="2500" height="1560" fill="#ffffff"/>')
text(-20, -340, "Ledger Nano: ST23YT66 die and bond wires", 44, weight="bold")
text(-20, -296, "Same orientation as microscope/20261103_153124.JPG, which is mirrored relative to the X-ray", 26, fill="#555555")

for key, p in TRACES:
    add(f'<polyline points="{pts(p)}" fill="none" stroke="{COL[key]}" stroke-opacity="0.35" stroke-width="16" stroke-linejoin="round"/>')
for v in (VIA_T4, VIA_T1):
    key = "GND" if v == VIA_T4 else "VBUS"
    add(f'<circle cx="{v[0]}" cy="{v[1]}" r="62" fill="{COL[key]}" fill-opacity="0.25" stroke="{COL[key]}" stroke-width="4"/>')
text(VIA_T4[0], VIA_T4[1] + 10, "via", 26, "middle")
text(VIA_T1[0], VIA_T1[1] + 10, "via", 26, "middle")

for key, a, b in LANDS:
    add(f'<line x1="{a[0]}" y1="{a[1]}" x2="{b[0]}" y2="{b[1]}" stroke="{COL[key]}" stroke-opacity="0.35" stroke-width="44" stroke-linecap="round"/>')
for name, (x, y, key) in CONTACTS.items():
    add(f'<circle cx="{x}" cy="{y}" r="82" fill="{COL[key]}" fill-opacity="0.18" stroke="{COL[key]}" stroke-width="5"/>')
    text(x, y - 4, name, 34, "middle", COL[key] if key != "NC" else "#616161", "bold")
    text(x, y + 30, SIGNAL_TEXT[key], 24, "middle", "#333333")

outline = [die(*c) for c in DIE_TOP_CORNERS]
add(f'<polygon points="{pts(outline)}" fill="#eceff1" stroke="#455a64" stroke-width="4"/>')
add(f'<polygon points="{pts([die(60, 365), die(1755, 40), die(1950, 1015), die(270, 1310)])}" fill="none" stroke="#b0bec5" stroke-width="2" stroke-dasharray="8 6"/>')
c = die(1000, 680)
text(c[0], c[1] - 20, "ST23YT66", 34, "middle", "#546e7a", "bold")
text(c[0], c[1] + 16, "die", 26, "middle", "#546e7a")

BONDED = {(407, 1285): "B3", (335, 1305): "D+", (1733, 135): "GND", (155, 378): "D-", (527, 318): "VBUS"}
for (x, y) in PADS:
    r = 30
    sq = [die(x - r, y - r), die(x + r, y - r), die(x + r, y + r), die(x - r, y + r)]
    if (x, y) in BONDED:
        f, s = COL[BONDED[(x, y)]], "#000000"
    elif (x, y) in PAIR:
        f, s = "#ffe082", "#000000"
    else:
        f, s = "#ffffff", "#78909c"
    add(f'<polygon points="{pts(sq)}" fill="{f}" stroke="{s}" stroke-width="2"/>')
    if (x, y) in TORN:
        add(f'<line x1="{sq[0][0]:.1f}" y1="{sq[0][1]:.1f}" x2="{sq[2][0]:.1f}" y2="{sq[2][1]:.1f}" stroke="#b71c1c" stroke-width="3"/>')
        add(f'<line x1="{sq[1][0]:.1f}" y1="{sq[1][1]:.1f}" x2="{sq[3][0]:.1f}" y2="{sq[3][1]:.1f}" stroke="#b71c1c" stroke-width="3"/>')

for n, key, path, pad, dashed in WIRES:
    p = path + [die(*pad)]
    dash = ""
    add(f'<polyline points="{pts(p[:-1])}" fill="none" stroke="{COL[key]}" stroke-width="5" stroke-linejoin="round"/>')
    if dashed:
        dash = ' stroke-dasharray="12 8"'
    add(f'<polyline points="{pts(p[-2:])}" fill="none" stroke="{COL[key]}" stroke-width="5"{dash}/>')
    lx, ly = LABEL_AT[n]
    add(f'<circle cx="{lx}" cy="{ly}" r="24" fill="#ffffff" stroke="{COL[key]}" stroke-width="4"/>')
    text(lx, ly + 10, str(n), 28, "middle", COL[key], "bold")

m = die(*PAIR_MID)
add(f'<circle cx="{m[0]:.1f}" cy="{m[1]:.1f}" r="46" fill="none" stroke="#000000" stroke-width="3" stroke-dasharray="6 5"/>')

x0 = 1560
y = -220
text(x0, y, "Bond wires", 34, weight="bold"); y += 50
for label, xx in (("Wire", x0), ("From", x0 + 90), ("Signal", x0 + 220), ("Die pad (die_top.png x, y)", x0 + 350)):
    text(xx, y, label, 24, fill="#555555", weight="bold")
y += 12
add(f'<line x1="{x0}" y1="{y}" x2="2400" y2="{y}" stroke="#999999" stroke-width="2"/>')
y += 40
for n, frm, sig, pad, note in ROWS:
    col = COL[ROW_COL[n]]
    text(x0 + 10, y, str(n), 28, fill=col, weight="bold")
    text(x0 + 90, y, frm, 26); text(x0 + 220, y, sig, 26, fill=col, weight="bold")
    text(x0 + 350, y, pad, 24)
    if note:
        text(x0 + 350, y + 30, note, 22, fill="#666666"); y += 30
    y += 48

y += 30
text(x0, y, "Key", 34, weight="bold"); y += 50
key_rows = [("pad", "#ffffff", "#78909c", "Unbonded pad"), ("pad", "#ffe082", "#000000", "Pad in unresolved pair (wires 3 and 7)"),
            ("torn", "#ffffff", "#78909c", "Torn pad (the one at (407, 1285) is wire 1)")]
for kind, f, s, label in key_rows:
    add(f'<rect x="{x0}" y="{y - 24}" width="30" height="30" fill="{f}" stroke="{s}" stroke-width="2"/>')
    if kind == "torn":
        add(f'<path d="M{x0} {y-24}L{x0+30} {y+6}M{x0+30} {y-24}L{x0} {y+6}" stroke="#b71c1c" stroke-width="3"/>')
    text(x0 + 50, y, label, 24); y += 46
add(f'<line x1="{x0}" y1="{y-10}" x2="{x0+36}" y2="{y-10}" stroke="#333333" stroke-width="5"/>')
text(x0 + 50, y, "Wire, traced in the photo", 24); y += 46
add(f'<line x1="{x0}" y1="{y-10}" x2="{x0+36}" y2="{y-10}" stroke="#333333" stroke-width="5" stroke-dasharray="12 8"/>')
text(x0 + 50, y, "Die end inferred or unresolved", 24); y += 46
add(f'<line x1="{x0}" y1="{y-10}" x2="{x0+36}" y2="{y-10}" stroke="#333333" stroke-opacity="0.35" stroke-width="14"/>')
text(x0 + 50, y, "Module trace", 24); y += 60
for line in ("Pad positions are approximate. Wire paths are simplified.",
             "Signals assume the T row is the four USB pins.",
             "From images only, not confirmed electrically."):
    text(x0, y, line, 24, fill="#555555"); y += 34
add('</svg>')
open("bond_map.svg", "w").write("\n".join(o) + "\n")
