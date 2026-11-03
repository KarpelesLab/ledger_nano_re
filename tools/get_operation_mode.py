#!/usr/bin/env python3
"""Query the operation mode and second factor of a 2581:3b7c device.

This sends two fixed read-only queries and has no way to send anything else.
Use --dry-run to print the reports without touching the device.
"""
import os
import sys

from get_firmware_version import CHANNEL, REPORT_SIZE, TAG_APDU, find_device, read_response

MODES = {0x01: "standard wallet", 0x02: "relaxed wallet", 0x04: "server", 0x08: "developer"}
SECOND_FACTORS = {
    0x11: "keyboard validation",
    0x12: "security card",
    0x13: "security card and secure screen",
}


def decode_mode(value):
    mode = MODES.get(value & 0x7F, "undocumented")
    forward = ", forward setup seed not yet redeemed" if value & 0x80 else ""
    return mode + forward


def decode_second_factor(value):
    return SECOND_FACTORS.get(value, "undocumented")


QUERIES = [("operation mode", 0x00, decode_mode), ("second factor", 0x01, decode_second_factor)]


def request(p1):
    header = CHANNEL + bytes([TAG_APDU, 0, 0, 0, 5])
    return (header + bytes([0xE0, 0x24, p1, 0, 0])).ljust(REPORT_SIZE, b"\0")


def main():
    dry_run = "--dry-run" in sys.argv[1:]
    fd = None if dry_run else os.open(find_device(), os.O_RDWR)
    try:
        for name, p1, decode in QUERIES:
            report = request(p1)
            print(f"{name}\n> {report.hex(' ')}")
            if dry_run:
                continue
            os.write(fd, b"\0" + report)
            response = read_response(fd)
            status = response[-2:].hex()
            print(f"status word: {status}")
            if status == "9000" and len(response) >= 3:
                print(f"{name}: 0x{response[0]:02x} ({decode(response[0])})")
    finally:
        if fd is not None:
            os.close(fd)


if __name__ == "__main__":
    main()
