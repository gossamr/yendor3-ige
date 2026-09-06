"""What the game shows before the menu and after the last key.

Three things sit outside every other decoder's reach, and
[world-dat.md](../docs/world-dat.md) records all three:

* **section 33**, a 640 by 480 PCX in 256 colors, which image `0x158AE` shows
  in VESA mode `0x101`. It is byte for byte the `LOGO.PCX` that ships beside
  the game.
* **section 34**, 880 character and attribute pairs, which image `0x0074F`
  copies to `B800:0000` after `INT 10h AX=0003` has put the adapter back in
  text mode. 80 columns by 11 rows.
* **the twenty abort messages**, which image `0x18C1A` prints before
  `INT 21h AH=4Ch`. `DS:0x53E0` holds the code and indexes twenty near offsets
  at `cs:0x39E`, each a stub naming a message.

    python tools/startup.py             # the messages and the screen
    python tools/startup.py --logo OUT  # the logo as a PNG
"""

from __future__ import annotations

import struct
from pathlib import Path

import sections as S
from mz import HEADER

LOGO = 33
EXIT_SCREEN = 34

# The PCX header fields this reads, by the offsets ZSoft put them at.
PCX_MAGIC, PCX_RLE, PCX_TAIL = 0x0A, 1, 769

EXIT_COLS = 80

# The abort handler's own segment, its jump table and how many entries it has.
# The stubs sit immediately before the table, each `mov ax, imm16` then a jump
# into the teardown, so the message address is the immediate.
ABORT_SEGMENT = 0x18930
ABORT_TABLE = 0x39E
ABORT_CODES = 20
STUB_MOV_AX = 0xB8
# Code 0 falls into the teardown with `ax` already set by the handler itself.
ABORT_FALLTHROUGH = 4


def logo(world: bytes, d: S.Directory) -> dict:
    """Section 33 decoded: its shape, its palette and one byte a pixel."""
    raw = d.sections[LOGO].slice(world)
    magic, _ver, encoding, bits = raw[0], raw[1], raw[2], raw[3]
    xmin, ymin, xmax, ymax = struct.unpack_from("<4H", raw, 4)
    planes, stride = raw[65], struct.unpack_from("<H", raw, 66)[0]
    assert magic == PCX_MAGIC and encoding == PCX_RLE, "section 33 is not a PCX"
    assert bits == 8 and planes == 1, f"{bits} bits in {planes} planes"
    width, height = xmax - xmin + 1, ymax - ymin + 1

    body, at, end = bytearray(), 128, len(raw) - PCX_TAIL
    while at < end:
        byte = raw[at]
        at += 1
        if byte & 0xC0 == 0xC0:
            body += bytes([raw[at]]) * (byte & 0x3F)
            at += 1
        else:
            body.append(byte)
    assert at == end, f"the run stopped at {at}, not at the palette at {end}"
    assert len(body) == stride * height, f"{len(body)} bytes for {stride}x{height}"

    palette = raw[-768:]
    pixels = b"".join(bytes(body[y * stride:y * stride + width])
                      for y in range(height))
    return {"width": width, "height": height, "stride": stride,
            "palette": [tuple(palette[i * 3:i * 3 + 3]) for i in range(256)],
            "pixels": pixels}


def exit_screen(world: bytes, d: S.Directory) -> list[dict]:
    """Section 34 as rows of text and the attribute each row is written in.

    The screen blanks with both `0x20` and `0x00`, which a text-mode adapter
    draws the same, so a NUL comes back as a space. Everything else is CP437,
    which is what the border is made of.
    """
    raw = d.sections[EXIT_SCREEN].slice(world)
    cells = len(raw) // 2
    assert cells % EXIT_COLS == 0, f"{cells} cells is not a whole row of {EXIT_COLS}"
    rows = []
    for top in range(0, cells, EXIT_COLS):
        glyphs = bytes(raw[(top + c) * 2] or 0x20 for c in range(EXIT_COLS))
        inks = {raw[(top + c) * 2 + 1] for c in range(EXIT_COLS)
                if glyphs[c] != 0x20}
        rows.append({"text": glyphs.decode("cp437"), "attributes": sorted(inks)})
    return rows


def abort_messages(exe: bytes) -> list[str]:
    """The twenty strings the abort handler prints, by the code that names each."""
    at = HEADER + ABORT_SEGMENT
    out = []
    for code in range(ABORT_CODES):
        stub = struct.unpack_from("<H", exe, at + ABORT_TABLE + code * 2)[0]
        where = (struct.unpack_from("<H", exe, at + stub + 1)[0]
                 if exe[at + stub] == STUB_MOV_AX else ABORT_FALLTHROUGH)
        end = exe.index(b"$", at + where)
        out.append(exe[at + where:end].decode("latin1")
                   .replace("\n\r", " ").strip())
    return out


def build(game_dir: str | Path = "game") -> dict:
    d = S.load(game_dir)
    picture = logo(d.world, d)
    return {"logo": {k: v for k, v in picture.items() if k != "pixels"},
            "exit_screen": exit_screen(d.world, d),
            "abort_messages": abort_messages(d.exe)}


if __name__ == "__main__":
    import sys

    d = S.load("game")
    if "--logo" in sys.argv:
        sys.path.insert(0, str(Path(__file__).parent))
        import pngutil

        picture = logo(d.world, d)
        palette = picture["palette"]
        rgb = b"".join(bytes(palette[v]) for v in picture["pixels"])
        out = sys.argv[sys.argv.index("--logo") + 1]
        pngutil.write(out, picture["width"], picture["height"], rgb)
        print(f"{out}: {picture['width']} x {picture['height']}")
    else:
        for row in exit_screen(d.world, d):
            print(f"  |{row['text']}|")
        print()
        for code, message in enumerate(abort_messages(d.exe)):
            print(f"  {code:2}  {message}")
