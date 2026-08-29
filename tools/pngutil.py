"""Minimal PNG read/write plus crop-and-zoom, for inspecting captured frames.

The emulator hands back 320x200 frames, which is too small to read the game's
own numbers reliably. Cropping and nearest-neighbor upscaling makes the
on-screen values legible so they can be checked against the decoded tables.
"""
from __future__ import annotations

import struct
import zlib


def read(path: str) -> tuple[int, int, bytes]:
    data = open(path, "rb").read()
    i, w, h, idat = 8, 0, 0, b""
    while i < len(data):
        ln = struct.unpack(">I", data[i:i + 4])[0]
        typ, body = data[i + 4:i + 8], data[i + 8:i + 8 + ln]
        i += 12 + ln
        if typ == b"IHDR":
            w, h = struct.unpack(">II", body[:8])
        elif typ == b"IDAT":
            idat += body
    raw = zlib.decompress(idat)
    stride = w * 3
    out, prev, pos = bytearray(), bytearray(stride), 0
    for _ in range(h):
        f = raw[pos]; pos += 1
        line = bytearray(raw[pos:pos + stride]); pos += stride
        if f == 1:
            for x in range(3, stride):
                line[x] = (line[x] + line[x - 3]) & 255
        elif f == 2:
            for x in range(stride):
                line[x] = (line[x] + prev[x]) & 255
        elif f == 3:
            for x in range(stride):
                line[x] = (line[x] + ((line[x - 3] if x >= 3 else 0) + prev[x]) // 2) & 255
        elif f == 4:
            for x in range(stride):
                a = line[x - 3] if x >= 3 else 0
                b = prev[x]
                c = prev[x - 3] if x >= 3 else 0
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                line[x] = (line[x] + (a if pa <= pb and pa <= pc else (b if pb <= pc else c))) & 255
        out += line
        prev = line
    return w, h, bytes(out)


def _chunk(tag: bytes, data: bytes) -> bytes:
    c = tag + data
    return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)


def _png(ihdr: bytes, raw: bytes, extra: bytes = b"") -> bytes:
    return (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr) + extra
            + _chunk(b"IDAT", zlib.compress(raw, 9)) + _chunk(b"IEND", b""))


def encode(w: int, h: int, rgb: bytes) -> bytes:
    """A truecolor PNG, as bytes."""
    raw = b"".join(b"\x00" + rgb[y * w * 3:(y + 1) * w * 3] for y in range(h))
    return _png(struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0), raw)


def write(path: str, w: int, h: int, rgb: bytes) -> None:
    open(path, "wb").write(encode(w, h, rgb))


def encode_indexed(w: int, h: int, idx: bytes, palette: list[bytes],
                   transparent: int | None = None) -> bytes:
    """A palettized PNG, as bytes.

    One byte a pixel indexing `palette`, which holds up to 256 RGB triples.
    `transparent` names the one entry drawn as nothing; every other entry is
    opaque, so the alpha table it needs is only as long as that index.
    """
    assert len(palette) <= 256, f"{len(palette)} colors is more than a palette holds"
    raw = b"".join(b"\x00" + idx[y * w:(y + 1) * w] for y in range(h))
    extra = _chunk(b"PLTE", b"".join(bytes(c) for c in palette))
    if transparent is not None:
        extra += _chunk(b"tRNS", b"\xff" * transparent + b"\x00")
    return _png(struct.pack(">IIBBBBB", w, h, 8, 3, 0, 0, 0), raw, extra)


def zoom(src: str, dst: str, box: tuple[int, int, int, int], scale: int = 4) -> tuple[int, int]:
    w, h, px = read(src)
    x0, y0, x1, y1 = box
    x1, y1 = min(x1, w), min(y1, h)
    cw, ch = (x1 - x0) * scale, (y1 - y0) * scale
    out = bytearray()
    for y in range(ch):
        sy = y0 + y // scale
        for x in range(cw):
            sx = x0 + x // scale
            i = (sy * w + sx) * 3
            out += px[i:i + 3]
    write(dst, cw, ch, bytes(out))
    return cw, ch


if __name__ == "__main__":
    import sys
    src, dst = sys.argv[1], sys.argv[2]
    box = tuple(int(v) for v in sys.argv[3].split(","))
    scale = int(sys.argv[4]) if len(sys.argv) > 4 else 4
    print(zoom(src, dst, box, scale))
