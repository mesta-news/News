"""Small PNG icons drawn in pure Python: one coloured disc per tab for notifications."""

from __future__ import annotations

import struct
import zlib


def _png(size: int, pixel) -> bytes:
    rows = b"".join(b"\x00" + b"".join(bytes(pixel(x, y)) for x in range(size)) for y in range(size))
    chunk = lambda tag, data: (struct.pack("!I", len(data)) + tag + data
                               + struct.pack("!I", zlib.crc32(tag + data) & 0xFFFFFFFF))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack("!IIBBBBB", size, size, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b""))


def _coverage(x: int, y: int, c: float, r: float) -> float:
    """How much of pixel (x, y) lies inside a circle (soft 1px edge)."""
    d = ((x + .5 - c) ** 2 + (y + .5 - c) ** 2) ** .5
    return max(0.0, min(1.0, r - d + .5))


def disc_png(color: str, size: int = 96) -> bytes:
    """A filled disc in `color` (#rrggbb) with a white ring, like a category dot."""
    rgb = tuple(int(color.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    c = size / 2

    def pixel(x, y):
        outer = _coverage(x, y, c, c - 2)
        ring = _coverage(x, y, c, c * .42) - _coverage(x, y, c, c * .30)
        r, g, b = (round(v + (255 - v) * ring) for v in rgb)
        return (r, g, b, round(255 * outer))

    return _png(size, pixel)


def badge_png(size: int = 72) -> bytes:
    """Monochrome badge for the Android status bar (only the alpha channel is used)."""
    c = size / 2
    return _png(size, lambda x, y: (255, 255, 255, round(255 * max(
        _coverage(x, y, c, c * .9) - _coverage(x, y, c, c * .62), _coverage(x, y, c, c * .3)))))
