#!/usr/bin/env python3
"""Convert firmware/*.js APDU lists into binary files under firmware/bin/.

For each input this writes:
  NAME.apdu  the APDUs exactly as listed, concatenated
  NAME.data  only the data field of each APDU, concatenated

It also prints each file's commands, entropy and repeated 8-byte blocks.
It only reads the .js files as text and never executes them.
"""
import collections
import math
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent / "firmware"
OUT = ROOT / "bin"
HEX_STRING = re.compile(r'"([0-9A-Fa-f]+)"')


def entropy(data):
    if not data:
        return 0.0
    counts = collections.Counter(data)
    return -sum(c / len(data) * math.log2(c / len(data)) for c in counts.values())


def repeated_blocks(data):
    blocks = collections.Counter(data[i:i + 8] for i in range(0, len(data) - 7, 8))
    return sum(c - 1 for c in blocks.values())


def main():
    OUT.mkdir(exist_ok=True)
    print(f"{'file':<34} {'apdus':>5} {'bad':>3} {'data':>7} {'H':>5} {'rep':>4}  commands")
    for path in sorted(ROOT.glob("*.js")):
        name = path.stem.removeprefix("btchipfirmware-")
        apdus = [bytes.fromhex(h) for h in HEX_STRING.findall(path.read_text())]
        payload = b""
        commands = collections.Counter()
        bad = 0
        for apdu in apdus:
            commands[apdu[:2].hex().upper()] += 1
            if len(apdu) < 5 or len(apdu) != 5 + apdu[4]:
                bad += 1
            payload += apdu[5:]
        (OUT / f"{name}.apdu").write_bytes(b"".join(apdus))
        (OUT / f"{name}.data").write_bytes(payload)
        summary = " ".join(f"{k}x{v}" for k, v in sorted(commands.items()))
        print(f"{name:<34} {len(apdus):>5} {bad:>3} {len(payload):>7} "
              f"{entropy(payload):>5.2f} {repeated_blocks(payload):>4}  {summary}")


if __name__ == "__main__":
    main()
