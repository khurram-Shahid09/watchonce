"""Generates public/icons/icon-{16,32,48,128}.png (a red record dot on a dark rounded tile).
Pure standard library so it runs anywhere: python scripts/make-icons.py"""

import struct
import zlib
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "public" / "icons"


def png(size: int) -> bytes:
    tile, dot, ring = (17, 24, 39), (239, 68, 68), (255, 255, 255)
    rows = []
    c = (size - 1) / 2
    radius = size * 0.22  # tile corner radius
    for y in range(size):
        row = bytearray([0])
        for x in range(size):
            # rounded-square mask
            dx = max(abs(x - c) - (c - radius), 0)
            dy = max(abs(y - c) - (c - radius), 0)
            inside = dx * dx + dy * dy <= radius * radius
            d = ((x - c) ** 2 + (y - c) ** 2) ** 0.5
            if not inside:
                row += bytes((0, 0, 0, 0))
            elif d <= size * 0.24:
                row += bytes((*dot, 255))
            elif d <= size * 0.31:
                row += bytes((*ring, 255))
            else:
                row += bytes((*tile, 255))
        rows.append(bytes(row))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(b"".join(rows), 9)) + chunk(b"IEND", b"")


OUT.mkdir(parents=True, exist_ok=True)
for s in (16, 32, 48, 128):
    (OUT / f"icon-{s}.png").write_bytes(png(s))
print(f"wrote icons to {OUT}")
