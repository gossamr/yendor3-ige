"""The 82 pixel routines a cast paints its target with.

Spell offset 36 is a tint, 1 to 82, and the cast writes it onto the target's
own `+0x18` (image `0x1CCFB`). The next draw of that target hands it to the
blitter, which turns it into a near pointer through a table at `cs:0x0D6B` of
its own segment and calls it once per pixel (image `0x19E2F`).

The routines are four shapes and nothing else, which is what makes them worth
reading rather than reproducing:

* **1** rolls the generator and drops the pixel where the roll is even, so the
  target flickers see-through.
* **2 to 5** shade the pixel by -8, -4, +4 or +8 and clamp it inside its own
  group, leaving a pixel of group 13 or above alone.
* **6 to 19** move the pixel into one group, 0 to 13, keeping its shade.
* **20 to 43** do both: into a group, then shaded.

44 and up are read the same way and no spell names one; 31 distinct tints are
used, all of them 43 or under.

    python tools/tints.py          # every tint and what it does
"""

from __future__ import annotations

import argparse
import struct

from disasm import Exe

# The blitter's own segment, and the table of near pointers inside it. Image
# 0x19E39 is `shl bx, 1 / add bx, 0xD6B / mov bx, cs:[bx]`.
BLITTER = 0x19AF0
TABLE = 0x0D6B
TINTS = 82

# The pixel comes in and goes out through the blitter's own frame word.
PIXEL = "word ptr [bp - 0x4c]"
# Where the shading shapes jump, which is the tail that clamps.
TAIL = 0x1A647
# The generator the flicker rolls.
RANDOM = 0x174AC


def table(exe: Exe) -> list[int]:
    """The near offset of each tint's routine, 0 for the unused first entry."""
    at = exe.file_of(BLITTER + TABLE)
    return list(struct.unpack_from(f"<{TINTS + 2}H", exe.data, at))


def read(exe: Exe, off: int) -> dict:
    """One routine, as the group it moves a pixel into and the shade it adds.

    Read off the instructions rather than transcribed: a shape that stops
    matching is reported as unread rather than guessed at.
    """
    group, delta, flicker = None, 0, False
    for ins in exe.disasm(BLITTER + off, 10):
        # Tint 5 is the last of the shading four and falls into the tail
        # rather than jumping to it, so arriving there is the end of a
        # routine as much as the jump is.
        if ins.address == TAIL:
            break
        text = f"{ins.mnemonic} {ins.op_str}"
        if text == f"mov ax, {PIXEL}":
            continue
        # The flicker's own preamble: it points DS at the generator's segment
        # and puts it back, and drops the pixel on an even roll.
        if flicker and ins.mnemonic in ("pop", "test", "jne", "mov"):
            continue
        if text in ("push ds", "mov ds, ax") or text.startswith("mov ax, 0x1ddb"):
            continue
        if text == "and al, 0xf":
            group = 0
            continue
        if text.startswith("or al, "):
            group = int(text.split(", ")[1], 0) >> 4
            continue
        if text.startswith(f"mov {PIXEL}, "):
            delta = int(text.split(", ")[1], 0)
            delta -= 0x10000 if delta > 0x8000 else 0
            continue
        if ins.mnemonic == "lcall":
            flicker = True
            continue
        if ins.mnemonic in ("ret", "retf"):
            break
        if ins.mnemonic == "jmp" and int(ins.op_str, 0) == TAIL:
            break
        return {"unread": text}
    if flicker:
        return {"kind": "flicker"}
    if group is None:
        return {"kind": "shade", "delta": delta}
    if delta:
        return {"kind": "group and shade", "group": group, "delta": delta}
    return {"kind": "group", "group": group}


def tints(exe: Exe) -> dict[int, dict]:
    """Tint number -> what it does to a pixel. Entry 0 is unused."""
    return {n: read(exe, off) for n, off in enumerate(table(exe)) if n and off}


# A pixel of this group or above is left as it is, which is the ramp the game
# twinkles on its own timer (image 0x1A647, `cmp al, 0xD0`).
UNTOUCHED_FROM = 0xD0


def paint(row: dict, index: int, roll: int = 1) -> int:
    """One pixel through one tint. 0xFF is what a dropped pixel becomes.

    `roll` is what the generator answered, which only the flicker reads.
    """
    if row.get("kind") == "flicker":
        return index if roll & 1 else 0xFF
    if "group" in row:
        index = (row["group"] << 4) | (index & 0x0F)
    if not row.get("delta"):
        return index
    if index >= UNTOUCHED_FROM:
        return index
    floor, ceiling = index & 0xF0, (index & 0xF0) | 0x0F
    return max(floor, min(ceiling, index + row["delta"]))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("game", nargs="?", default="game")
    args = ap.parse_args()
    exe = Exe(f"{args.game}/REGISTER.EXE")
    rows = tints(exe)
    shapes: dict[str, list[int]] = {}
    for n, row in rows.items():
        shapes.setdefault(row.get("kind", "unread"), []).append(n)
    for kind, ns in shapes.items():
        print(f"{kind:16} {len(ns):3}: {ns[:16]}{' ...' if len(ns) > 16 else ''}")
    print()
    for n in sorted(rows)[:44]:
        row = rows[n]
        said = " ".join(f"{k} {v}" for k, v in row.items() if k != "kind")
        print(f"  {n:3}  {row.get('kind', 'unread'):16} {said}")


if __name__ == "__main__":
    main()
