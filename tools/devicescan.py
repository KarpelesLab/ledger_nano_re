#!/usr/bin/env python3
"""Probe a 2581:3b7c Ledger Nano for the firmware / device info APDUs.

Sends read-only APDUs (each needs no PIN) and prints the raw response plus a
decoded view. Commands probed:
  E0 C0  GET RANDOM            Le random bytes from the hardware TRNG
  E0 C2  GET DEVICE ATTESTATION  batch/derivation ID, modes, versions + ECDSA sig
  E0 C4  GET FIRMWARE VERSION  features, architecture, fw and loader version
  D0 24  GET FIRMWARE UPDATE ID-> 8-byte firmware update ID (pre-setup only)

  E0 C0 and E0 C2 are documented "always available". E0 C4 is also always
  available. D0 24 is pre-issuance only; it works on our unconfigured unit.
  We deliberately avoid VERIFY PIN (wrong PIN 3x erases the device).

GET DEVICE ATTESTATION response layout (firmware lw1-1.0 spec, section 24.2):
  batch id (4, BE) | derivation id (4, BE) | supported-mode bitflag (1) |
  current mode (1) | fw major (2, BE) | fw minor (1) | fw patch (1) |
  loader major (1) | loader minor (1) | signature (var)
The signature is a secp256k1 ECDSA over SHA-256 of (the 8 bytes immediately
before it, i.e. supported..loader) concatenated with the 8-byte blob we sent.
The verification key is looked up by (batch id, derivation id) in the set
Ledger ships in the chrome app (ledger-wallet-chrome, dongle.coffee):
  batch 0 (beta), batch 1, batch 2 (our unit) -- all derivation 1.

Framing (matches get_firmware_version.py / get_operation_mode.py):
  report = CHANNEL(2) + TAG(1) + seq(2) + apdu-len(2) + APDU, padded to 64.
  Written to hidraw as 00 | report (single packet; no report IDs).

Usage: devicescan.py
"""
import hashlib
import os
import sys

from get_firmware_version import CHANNEL, REPORT_SIZE, TAG_APDU, find_device, read_response

# Uncompressed secp256k1 attestation public keys, as 04||X||Y hex strings,
# keyed by (batch id, derivation index).
# Source: LedgerHQ/ledger-wallet-chrome app/src/dongle/dongle.coffee.
_ATTESTATION_HEX = {
    (0, 1): "04e69fd3c044865200e66f124b5ea237c918503931bee070edfcab79a00a25d6"
            "b5a09afbee902b4b763ecf1f9c25f82d6b0cf72bce3faf98523a1066948f1a395f",
    (1, 1): "04223314cdffec8740150afe46db3575fae840362b137316c0d222a071607d61"
            "b2fd40abb2652a7fea20e3bb3e64dc6d495d59823d143c53c4fe4059c5ff16e406",
    (2, 1): "04c370d4013107a98dfef01d6db5bb3419deb9299535f0be47f05939a78b314a"
            "3c29b51fcaa9b3d46fa382c995456af50cd57fb017c0ce05e4a31864a79b8fbfd6",
}
ATTESTATION_KEYS = {
    k: (int(v[2:66], 16), int(v[66:130], 16))
    for k, v in _ATTESTATION_HEX.items()
}

MODES = {0x01: "standard wallet", 0x02: "relaxed wallet",
         0x04: "server", 0x08: "developer"}


# --- minimal secp256k1 ECDSA verifier (pure stdlib, no deps) ----------------
_P = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
_N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
_GX = 0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798
_GY = 0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8


def _inv(x, m):
    return pow(x, m - 2, m)


def _add(q, r):
    if q is None:
        return r
    if r is None:
        return q
    x1, y1 = q
    x2, y2 = r
    if x1 == x2 and (y1 + y2) % _P == 0:
        return None
    m = (3 * x1 * x1) * _inv(2 * y1, _P) % _P if x1 == x2 else (y2 - y1) * _inv(x2 - x1, _P) % _P
    x3 = (m * m - x1 - x2) % _P
    return (x3, (m * (x1 - x3) - y1) % _P)


def _mul(k, pt):
    R, A = None, pt
    while k:
        if k & 1:
            R = _add(R, A)
        A = _add(A, A)
        k >>= 1
    return R


def ecdsa_verify(digest, r, s, pub):
    z = int.from_bytes(digest, "big")
    w = _inv(s, _N)
    pt = _add(_mul(z * w % _N, (_GX, _GY)), _mul(r * w % _N, pub))
    return pt is not None and pt[0] % _N == r


def parse_der(sig):
    assert sig[0] == 0x30 and sig[2] == 0x02, "not a DER ECDSA signature"
    i = 2
    rl = sig[i + 1]
    r = int.from_bytes(sig[i + 2:i + 2 + rl], "big")
    i += 2 + rl
    assert sig[i] == 0x02
    sl = sig[i + 1]
    s = int.from_bytes(sig[i + 2:i + 2 + sl], "big")
    return r, s


def make_report(apdu):
    inner = len(apdu).to_bytes(2, "big") + apdu
    return (CHANNEL + bytes([TAG_APDU, 0, 0]) + inner).ljust(REPORT_SIZE, b"\0")


def send(fd, apdu):
    report = make_report(apdu)
    print(f"> {report.hex(' ')}")
    os.write(fd, b"\0" + report)
    return read_response(fd)


def names(flag, table):
    return ", ".join(n for b, n in table.items() if flag & b) or "none"


def probed(name, resp):
    print(f"    status {resp[-2:].hex()}  full: {resp.hex(' ')}")


def get_random(fd):
    print("\n=== E0 C0 GET RANDOM (Le=16) ===")
    resp = send(fd, bytes([0xE0, 0xC0, 0, 0, 0x10]))
    probed("RANDOM", resp)
    print(f"    random: {resp[:-2].hex(' ')}")
    print("    -> the hardware TRNG responds (non-repeatable randomness).")


def attestation_verify(data, blob):
    batch = int.from_bytes(data[0:4], "big")
    deriv = int.from_bytes(data[4:8], "big")
    sig = data[16:]
    signed8 = data[8:16]
    digest = hashlib.sha256(signed8 + blob).digest()
    r, s = parse_der(sig)
    pub = ATTESTATION_KEYS.get((batch, deriv))
    if pub is None:
        return f"attestation key (batch={batch}, deriv={deriv}) not in known set; sig not verified"
    ok = ecdsa_verify(digest, r, s, pub)
    return f"ECDSA over sha256({signed8.hex()} + blob) vs batch {batch} key: {'VALID' if ok else 'INVALID'}"


def get_attestation(fd):
    print("\n=== E0 C2 GET DEVICE ATTESTATION (8-byte blob) ===")
    blob = bytes([4, 0, 0, 0, 0, 0, 0, 0])
    resp = send(fd, bytes([0xE0, 0xC2, 0, 0, len(blob)]) + blob)
    probed("ATTESTATION", resp)
    data = resp[:-2]
    if resp[-2:] != b"\x90\x00" or len(data) < 16:
        print("    (unexpected length/status; cannot fully decode)")
        return
    batch = int.from_bytes(data[0:4], "big")
    deriv = int.from_bytes(data[4:8], "big")
    sm, cm = data[8], data[9]
    fw = f"{int.from_bytes(data[10:12], 'big')}.{data[12]}.{data[13]}"
    ld = f"{data[14]}.{data[15]}"
    print(f"    batch id:          {batch}")
    print(f"    derivation index:  {deriv}")
    print(f"    supported modes:   0x{sm:02x} ({names(sm, MODES)})")
    print(f"    current mode:      0x{cm:02x} ({MODES.get(cm, 'undocumented')})")
    print(f"    fw (as attested):  {fw}")
    print(f"    loader id:         {ld}")
    print(f"    signature:         {len(data) - 16} bytes, DER ECDSA")
    print("    " + attestation_verify(data, blob))


def get_firmware_version(fd):
    print("\n=== E0 C4 GET FIRMWARE VERSION ===")
    resp = send(fd, bytes([0xE0, 0xC4, 0, 0, 0]))
    probed("FW VERSION", resp)
    data = resp[:-2]
    FEATURES = {0x01: "compressed public keys", 0x02: "screen+buttons in SE",
                0x04: "screen+buttons external", 0x08: "NFC",
                0x10: "BLE / low power", 0x20: "TEE"}
    if resp[-2:] != b"\x90\x00" or len(data) < 5:
        print("    (unexpected length/status; cannot fully decode)")
        return
    print(f"    features:          0x{data[0]:02x} ({names(data[0], FEATURES)})")
    print(f"    architecture:      0x{data[1]:02x}")
    print(f"    firmware:          {data[2]}.{data[3]}.{data[4]}")
    print(f"    loader:            {data[5]}.{data[6]}")


def get_update_id(fd):
    print("\n=== D0 24 GET FIRMWARE UPDATE ID (pre-issuance) ===")
    resp = send(fd, bytes([0xD0, 0x24, 0, 0, 8]) + bytes(8))
    probed("UPDATE ID", resp)
    if resp[-2:] == b"\x90\x00":
        print(f"    firmware update id: {resp[:-2].hex(' ')}")
    else:
        print("    (not available on this unit yet; pre-issuance command)")


def main():
    fd = os.open(find_device(), os.O_RDWR)
    try:
        get_random(fd)
        get_attestation(fd)
        get_firmware_version(fd)
        get_update_id(fd)
    finally:
        os.close(fd)


if __name__ == "__main__":
    main()
