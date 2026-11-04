#!/usr/bin/env python3
"""Generate assets/app.ico -- the product shortcut icon (G4.1).

Stdlib only on purpose: the icon must be reproducible on the Linux build host
without Pillow, and shipping a binary that nobody can regenerate is exactly the
kind of thing that rots.  The drawing is deliberately simple -- a dark rounded
plate, a white play mark and a green "online" light, i.e. the same idea the
control panel shows.

Usage: python3 tools/make_icon.py --out assets/app.ico
"""

from __future__ import annotations

import argparse
import struct
from pathlib import Path

SIZES = (16, 32, 48, 64, 256)
PLATE = (31, 41, 55, 255)      # #1F2937
PLATE_EDGE = (17, 24, 39, 255)
PLAY = (255, 255, 255, 255)
LIGHT = (34, 197, 94, 255)     # online green
BG = (0, 0, 0, 0)


def _blend(dst, src):
    sa = src[3] / 255.0
    return tuple(int(round(dst[i] * (1 - sa) + src[i] * sa)) for i in range(3)) \
        + (max(dst[3], src[3]),)


def _pixel(size, x, y):
    """One RGBA pixel: rounded plate + play triangle + status light."""
    cx, cy = (size - 1) / 2.0, (size - 1) / 2.0
    radius = size * 0.46
    # rounded square via "signed distance to the centre, clamped per axis"
    half = size * 0.46
    dx = max(abs(x - cx) - (half - size * 0.16), 0.0)
    dy = max(abs(y - cy) - (half - size * 0.16), 0.0)
    dist = (dx * dx + dy * dy) ** 0.5
    if dist > size * 0.16:
        return BG
    plate = PLATE_EDGE if dist > size * 0.13 else PLATE
    px = plate

    # play triangle (points right), centred a bit left of the middle
    tx = x - (cx - size * 0.06)
    ty = y - cy
    h = size * 0.26
    if abs(ty) <= h and tx >= -h * 0.75 and tx <= h * 0.75 * (1 - abs(ty) / h):
        px = _blend(px, PLAY)

    # status light, upper right
    lx, ly, lr = cx + size * 0.28, cy - size * 0.28, size * 0.13
    if (x - lx) ** 2 + (y - ly) ** 2 <= lr * lr:
        px = _blend(px, LIGHT)
    return px


def _dib(size):
    rows = []
    for y in range(size - 1, -1, -1):        # bottom-up
        row = bytearray()
        for x in range(size):
            r, g, b, a = _pixel(size, x, y)
            row += bytes((b, g, r, a))
        rows.append(bytes(row))
    xor = b"".join(rows)
    mask_row = ((size + 31) // 32) * 4        # AND mask, 4-byte aligned
    and_mask = bytes(mask_row * size)
    header = struct.pack("<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0,
                         len(xor) + len(and_mask), 0, 0, 0, 0)
    return header + xor + and_mask


def build_ico(sizes=SIZES) -> bytes:
    images = [(s, _dib(s)) for s in sizes]
    out = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    directory, blobs = b"", b""
    for size, data in images:
        dim = 0 if size >= 256 else size
        directory += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32,
                                 len(data), offset)
        blobs += data
        offset += len(data)
    return out + directory + blobs


def validate(data: bytes) -> dict:
    reserved, kind, count = struct.unpack_from("<HHH", data, 0)
    assert reserved == 0 and kind == 1, "not an ICO"
    entries = []
    for i in range(count):
        w, h, colors, res, planes, bits, size, off = struct.unpack_from(
            "<BBBBHHII", data, 6 + 16 * i)
        assert off + size <= len(data), f"entry {i} runs past EOF"
        entries.append({"width": w or 256, "height": h or 256, "bits": bits,
                        "bytes": size, "offset": off})
    return {"count": count, "entries": entries, "total_bytes": len(data)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="assets/app.ico")
    args = ap.parse_args(argv)
    data = build_ico()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    info = validate(data)
    print(f"{out}  {info['total_bytes']} bytes, {info['count']} sizes: "
          + ", ".join(f"{e['width']}x{e['height']}" for e in info["entries"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
