#!/usr/bin/env python3
"""Send GET FIRMWARE VERSION to a 2581:3b7c device and decode the reply.

This sends one fixed command and has no way to send anything else.
Use --dry-run to print the report without touching the device.
"""
import glob
import os
import select
import sys

VID_PID = "0003:00002581:00003B7C"
CHANNEL = b"\x01\x01"
TAG_APDU = 0x05
REPORT_SIZE = 64
TIMEOUT_S = 3

# First report: channel, tag, sequence 0, length 5, then E0 C4 00 00 00.
# The last byte matches LedgerHQ/btchip-python, which sends 00 here.
REQUEST = (CHANNEL + bytes([TAG_APDU, 0, 0, 0, 5, 0xE0, 0xC4, 0, 0, 0])).ljust(REPORT_SIZE, b"\0")

FEATURES = {
    0x01: "compressed public keys",
    0x02: "screen and buttons handled by Secure Element",
    0x04: "screen and buttons handled externally",
    0x08: "NFC transport and payment",
    0x10: "BLE transport and low power",
    0x20: "Trusted Execution Environment",
}


def find_device():
    found = []
    for uevent in glob.glob("/sys/class/hidraw/hidraw*/device/uevent"):
        with open(uevent) as f:
            if f"HID_ID={VID_PID}" in f.read():
                found.append("/dev/" + uevent.split("/")[4])
    if len(found) != 1:
        sys.exit(f"expected exactly one 2581:3b7c hidraw node, found {found}")
    return found[0]


def read_report(fd):
    ready, _, _ = select.select([fd], [], [], TIMEOUT_S)
    if not ready:
        sys.exit(f"no response within {TIMEOUT_S} s")
    return os.read(fd, REPORT_SIZE)


def read_response(fd):
    payload, sequence, length = b"", 0, None
    while length is None or len(payload) < length:
        report = read_report(fd)
        print(f"< {report.hex(' ')}")
        if len(report) < 5 or report[:2] != CHANNEL or report[2] != TAG_APDU:
            sys.exit("unexpected report header")
        if int.from_bytes(report[3:5], "big") != sequence:
            sys.exit("unexpected sequence index")
        body = report[5:]
        if sequence == 0:
            length = int.from_bytes(body[:2], "big")
            body = body[2:]
        payload += body
        sequence += 1
    return payload[:length]


def decode(response):
    if len(response) < 2:
        sys.exit("response too short")
    data, status = response[:-2], response[-2:].hex()
    print(f"status word: {status}")
    print(f"data: {data.hex(' ') or '(none)'}")
    if status != "9000":
        sys.exit(f"device returned status {status}")
    if len(data) < 5:
        sys.exit("data shorter than the documented layout")
    names = [name for bit, name in FEATURES.items() if data[0] & bit]
    print(f"features: 0x{data[0]:02x} ({', '.join(names) or 'none'})")
    print(f"architecture: 0x{data[1]:02x}")
    print(f"firmware: {data[2]}.{data[3]}.{data[4]}")
    if len(data) >= 7:
        print(f"loader: {data[5]}.{data[6]}")


def main():
    print(f"> {REQUEST.hex(' ')}")
    if "--dry-run" in sys.argv[1:]:
        return
    path = find_device()
    print(f"device: {path}")
    fd = os.open(path, os.O_RDWR)
    try:
        # The leading zero is the hidraw report number, as there are no report IDs.
        os.write(fd, b"\0" + REQUEST)
        decode(read_response(fd))
    finally:
        os.close(fd)


if __name__ == "__main__":
    main()
