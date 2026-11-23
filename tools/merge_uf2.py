#!/usr/bin/env python3
"""Combine the PicoBoot firmware and the Swiss payload into one UF2, so a single
drag-and-drop flashes both.

Usage: merge_uf2.py picoboot_full_pico.uf2 swiss_rXXXX.uf2 out.uf2

Takes the firmware blocks (below 0x10080000) from the PicoBoot image and the
RP2040 payload blocks from the Swiss image, then renumbers them. Original Pico
and Pico W only (RP2040). For a Pico 2, change FAMILY and use picoboot_full_pico2.uf2.
"""
import struct
import sys

FAMILY = 0xE48BFF56        # RP2040
PAYLOAD_START = 0x10080000  # PicoBoot v0.4+ payload slot
MAGIC0 = 0x0A324655


def blocks(path):
    data = open(path, "rb").read()
    assert len(data) % 512 == 0, f"{path}: not a UF2 file"
    return [data[i:i + 512] for i in range(0, len(data), 512)]


def header(block):
    return struct.unpack("<8I", block[:32])  # magic0, magic1, flags, addr, size, blockNo, numBlocks, family


def main(firmware_path, swiss_path, out_path):
    firmware = [b for b in blocks(firmware_path) if header(b)[7] == FAMILY and header(b)[3] < PAYLOAD_START]
    payload = [b for b in blocks(swiss_path) if header(b)[7] == FAMILY and header(b)[3] >= PAYLOAD_START]
    assert firmware, "no RP2040 firmware blocks found in the PicoBoot image"
    assert payload, "no RP2040 payload blocks found in the Swiss image"

    merged = firmware + payload
    addrs = [header(b)[3] for b in merged]
    assert len(addrs) == len(set(addrs)), "firmware and payload overlap"

    out = bytearray()
    for i, b in enumerate(merged):
        h = list(header(b))
        assert h[0] == MAGIC0
        h[5], h[6] = i, len(merged)
        out += struct.pack("<8I", *h) + b[32:]
    open(out_path, "wb").write(out)
    print(f"{len(firmware)} firmware + {len(payload)} payload blocks -> {out_path}")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    main(*sys.argv[1:])
