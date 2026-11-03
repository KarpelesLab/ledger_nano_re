#!/usr/bin/env python3
"""Sweep a 2581:3b7c device over candidate APDUs to find undocumented ones.

Usage:
  sweep.py calibrate        # probe known + bogus INS to find the error baseline
  sweep.py probe CLA INS... # probe specific (CLA, INS) with P1=P2=0, no data
  sweep.py sweep CLA        # probe the whole 256-INS space for one CLA
"""
import os
import sys

from get_firmware_version import find_device, read_response
from devicescan import make_report, send


def q(fd, cla, ins, p1=0, p2=0, data=b""):
    apdu = bytes([cla, ins, p1, p2, len(data)]) + data
    r = send(fd, apdu)
    return r[-2:].hex(), r[:-2]


def calibrate():
    fd = os.open(find_device(), os.O_RDWR)
    try:
        print("=== calibration ===")
        for label, (cla, ins) in {
            "E0 C4  (GET FIRMWARE VERSION, known)": (0xE0, 0xC4),
            "E0 C0  (GET RANDOM, known)": (0xE0, 0xC0),
            "E0 C2  (ATTESTATION, known)": (0xE0, 0xC2),
            "E0 5A  (bogus, no data)": (0xE0, 0x5A),
            "E0 5B  (bogus, no data)": (0xE0, 0x5B),
            "D0 24  (GET FW UPDATE ID, known)": (0xD0, 0x24),
            "D0 5A  (bogus, no data)": (0xD0, 0x5A),
            "F0 5A  (bogus, no data)": (0xF0, 0x5A),
            "00 5A  (bogus, no data)": (0x00, 0x5A),
            "FF 5A  (bogus, no data)": (0xFF, 0x5A),
        }.items():
            sw, data = q(fd, cla, ins)
            print(f"  {label:40} sw={sw}  data_len={len(data)}")
    finally:
        os.close(fd)


def probe(cla_ins):
    fd = os.open(find_device(), os.O_RDWR)
    try:
        items = []
        for pair in cla_ins:
            cla, ins = (int(x, 16) for x in pair.split(":"))
            items.append((cla, ins))
        for cla, ins in items:
            sw, data = q(fd, cla, ins)
            print(f"  {cla:02x} {ins:02x}  sw={sw}  data_len={len(data)}"
                  f"  data={data.hex(' ') if data else ''}")
    finally:
        os.close(fd)


def healthy(fd):
    """Return True if the device answers E0 C4 with 9000."""
    sw, _ = q(fd, 0xE0, 0xC4)
    return sw == "9000"


def sweep(cla, health_interval=32):
    """Probe all 256 INS for one CLA, re-checking device health every `health_interval`
    INS (and up front) so a degraded device can't contaminate the results."""
    seen = {}
    fd = os.open(find_device(), os.O_RDWR)
    died_at = None
    try:
        for ins in range(256):
            if health_interval and (ins % health_interval == 0) and not healthy(fd):
                died_at = ins
                print(f"\n!! device died (E0 C4 != 9000) before INS {ins:02x}; "
                      f"INS 00..{ins-1:02x} valid, {ins:02x}..ff untested", flush=True)
                break
            sw, data = q(fd, cla, ins)
            key = (sw, len(data) > 0)
            seen.setdefault(key, []).append(ins)
            print(f"  {cla:02x} {ins:02x}  sw={sw}  data_len={len(data)}", flush=True)
    finally:
        os.close(fd)
    print("\n=== "
          + ("completed: all 256 INS probed while device healthy ==="
             if died_at is None else f"partial: stopped at INS {died_at:02x} ==="))
    print("=== grouped ===")
    for (sw, has_data), ins_list in sorted(seen.items(), key=lambda kv: (-int(kv[0][0], 16), kv[0])):
        print(f"  sw={sw} has_data={has_data}: {len(ins_list)} INS")
        for i in ins_list:
            print(f"      {cla:02x} {i:02x}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "probe"
    if cmd == "calibrate":
        calibrate()
    elif cmd == "probe" and len(sys.argv) >= 3:
        probe(sys.argv[2:])
    elif cmd == "sweep" and len(sys.argv) >= 3:
        sweep(int(sys.argv[2], 16))
