#!/usr/bin/env python3
"""Confirm the undocumented `E0 D0` command is a SHA-256 engine.

`E0 D0` exposes a SHA-256 compression core. Its 96-byte `P1=06` response is:
    bytes 0..63  : the SHA-256 message-block buffer (streamed input, rolling offset)
    bytes 64..95 : the 32-byte SHA-256 hash state (H0..H7, big-endian)

Sub-commands:
    P1=05 (Lc>=16) : init  -> state = SHA-256 IV, block buffer/offset cleared
    P1=06 (Lc>=1)  : write Lc bytes into the block at the offset; when the block
                     fills to 64 bytes, run one SHA-256 compression into the state;
                     return the 64-byte block + 32-byte state
    P1=04 (Lc>=16) : writes a separate, still-unidentified slot (purpose open);
                     leaves the SHA state and block buffer untouched

This script inits the engine, streams three known 64-byte blocks, and checks that
the device's hash state after each block equals compress(previous_state, block)
from the reference SHA-256 compression below.

Transport: shells out to the `fullsweep` tool (usbfs, no root needed). Build it with
    cargo build --release --manifest-path tools/fullsweep/Cargo.toml
Run from the repo root:
    python3 tools/sha_test.py
"""
import os
import subprocess

FS = os.path.join(os.path.dirname(__file__), "fullsweep", "target", "release", "fullsweep")

# ---- reference SHA-256 compression (one 64-byte block -> new 8-word state) ----
K = [
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2]
IV = [0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19]
M = 0xffffffff


def rotr(x, n):
    return ((x >> n) | (x << (32 - n))) & M


def compress(state, block):
    w = [int.from_bytes(block[i:i + 4], "big") for i in range(0, 64, 4)]
    for i in range(16, 64):
        s0 = rotr(w[i - 15], 7) ^ rotr(w[i - 15], 18) ^ (w[i - 15] >> 3)
        s1 = rotr(w[i - 2], 17) ^ rotr(w[i - 2], 19) ^ (w[i - 2] >> 10)
        w.append((w[i - 16] + s0 + w[i - 7] + s1) & M)
    a, b, c, d, e, f, g, h = state
    for i in range(64):
        S1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25)
        ch = (e & f) ^ ((~e & M) & g)
        t1 = (h + S1 + ch + K[i] + w[i]) & M
        S0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22)
        maj = (a & b) ^ (a & c) ^ (b & c)
        t2 = (S0 + maj) & M
        h, g, f, e, d, c, b, a = g, f, e, (d + t1) & M, c, b, a, (t1 + t2) & M
    return [(x + y) & M for x, y in zip(state, [a, b, c, d, e, f, g, h])]


def state_bytes(st):
    return b"".join(x.to_bytes(4, "big") for x in st)


# ---- device driver (via fullsweep) ----
def send(p1, data=b""):
    lc = len(data)
    apdu = f"e0 d0 {p1:02x} 00 {lc:02x} {data.hex()}".strip()
    env = dict(os.environ, FULL="1")
    out = subprocess.run([FS, "apdu", apdu], capture_output=True, text=True, env=env).stdout.strip()
    sw = out.split()[0]
    body = b""
    if "bytes)" in out:
        hexpart = out.split("bytes)", 1)[1].strip()
        if hexpart:
            body = bytes(int(x, 16) for x in hexpart.split())
    return sw, body


def device_state(body):
    return body[64:96] if len(body) >= 96 else None


def main():
    # init (P1=05, Lc>=16); the leading P1=04 matches the observed fresh-boot recipe
    send(0x04, b"\x01" * 16)
    sw, _ = send(0x05, b"\x01" * 16)
    print(f"init P1=05 -> {sw}")

    # three known 64-byte blocks, streamed as 32+32 (each P1=06 writes once)
    blocks = [
        bytes(range(0x00, 0x40)),              # 00 01 .. 3f
        bytes([0xde] * 32) + bytes([0xad] * 32),
        bytes(range(0x40, 0x60)) + bytes([0x55] * 32),
    ]

    chain = IV[:]
    ok = True
    for i, blk in enumerate(blocks):
        send(0x06, blk[:32])                   # first half (offset 0 -> 32)
        _, body = send(0x06, blk[32:])         # second half completes the block -> compress
        got = device_state(body)
        chain = compress(chain, blk)
        want = state_bytes(chain)
        match = got == want
        ok &= match
        print(f"block{i}: device={got.hex() if got else '??'} expected={want.hex()} "
              f"{'MATCH' if match else 'MISMATCH'}")

    print("\nE0 D0 confirmed as a SHA-256 engine." if ok else "\nMISMATCH - see output above.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
