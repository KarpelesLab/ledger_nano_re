#!/usr/bin/env python3
"""Query remaining PIN attempts on a 2581:3b7c device (read-only).

Sends VERIFY PIN with P1=0x80, which the spec and btchip-python use to report the
remaining attempt count without consuming one. It does NOT send P1=0x00 (the actual
PIN check, which can wipe the device). Has no way to send anything else.
Use --dry-run to print the report without touching the device.
"""
import os
import sys

from get_firmware_version import CHANNEL, REPORT_SIZE, TAG_APDU, find_device, read_response

# E0 22 80 00 01 00 : VERIFY PIN, P1=0x80 (report attempts), Lc=... matching btchip.
APDU = bytes([0xE0, 0x22, 0x80, 0x00, 0x01, 0x00])
REQUEST = (CHANNEL + bytes([TAG_APDU, 0, 0, 0, len(APDU)]) + APDU).ljust(REPORT_SIZE, b"\0")


def main():
    print(f"> {REQUEST.hex(' ')}")
    if "--dry-run" in sys.argv[1:]:
        return
    fd = os.open(find_device(), os.O_RDWR)
    try:
        os.write(fd, b"\0" + REQUEST)
        response = read_response(fd)
        status = response[-2:].hex()
        print(f"status word: {status}")
        sw = int(status, 16)
        if (sw & 0xFFF0) == 0x63C0:
            print(f"remaining PIN attempts: {sw & 0x0F}")
        elif status == "9000":
            print("status 9000 with data:", response[:-2].hex(' ') or "(none)")
        elif status == "6985":
            print("conditions not satisfied: consistent with a unit that is not set up")
        else:
            print("unexpected status; see the spec's status word table")
    finally:
        os.close(fd)


if __name__ == "__main__":
    main()
