#!/usr/bin/env python3
"""Check the immunity and resistance words against the game's own F2 rows.

`tools/capture_monsters.js` photographs the F2 MONSTER STATISTICS page for
every creature the game lists, in the order it lists them. Below the combat
figures the page prints twelve rows, `labels.EFFECTS` in order, each blank or
carrying one word. Ten of them are single bits of the immunity word at record
offset 100. The other two are the resistance word at 102, which the printer
sorts into a magic row and a physical row itself, the magic row also answering
bit 4 of the immunity word. docs/monsters.md sets the masks out.

`tools/read_stats.py` reads a row by the width of its green run, which is
enough because `IMMUNE` and `RESISTANT` are the only two words the column can
hold: they sit consecutively in the label run at `0x2AAB0` and `labels.verify`
holds both to the file. Nothing in that chain reads the immunity word, so
agreement here is a check on the decode rather than a restatement of it.

    bun tools/capture_monsters.js --out=tmp/monsters --count=72
    PYTHONPATH=tools python tools/verify_effects.py [tmp/monsters]
"""

from __future__ import annotations

import re
import struct
import sys
from pathlib import Path

import labels as L
import read_stats as RS
import sections as S

# Which bit of the immunity word each row prints, in labels.EFFECTS order.
# The last two rows are the resistance word instead, and are handled below.
IMMUNE_BITS = (15, 14, 13, 12, 11, 10, 3, 2, 1, 0)

RESIST_MAGIC = 0x3A00        # image 0x07E6A passes this mask
RESIST_PHYSICAL = 0xC000     # image 0x07E9C
MAGIC_VIA_IMMUNITY = 0x0010  # tested at 0x07E6D, right after the magic mask


def expected(immunity: int, resistance: int) -> list[str]:
    """The twelve rows the printer should draw for one creature."""
    rows = [RS.IMMUNE if immunity >> b & 1 else RS.NONE for b in IMMUNE_BITS]
    magic = resistance & RESIST_MAGIC or immunity & MAGIC_VIA_IMMUNITY
    rows.append(RS.RESISTANT if magic else RS.NONE)
    rows.append(RS.RESISTANT if resistance & RESIST_PHYSICAL else RS.NONE)
    return rows


def creatures(d: S.Directory) -> list[dict]:
    """Every creature the book lists, in the alphabetical order F2 uses."""
    out = []
    for rec in d[S.ENEMIES].records(d.world, S.ENEMY_RECORD):
        if not any(rec):
            continue
        name = " ".join(f.split(b"\x00")[0].decode("latin1").strip()
                        for f in (rec[0:13], rec[13:26])).strip()
        if name == "NOT USED":
            continue
        out.append({"name": name,
                    "immunity": struct.unpack_from("<H", rec, 100)[0],
                    "resistance": struct.unpack_from("<H", rec, 102)[0]})
    return sorted(out, key=lambda c: c["name"])


def main(shot_dir: str = "tmp/monsters") -> int:
    shots = sorted(p for p in Path(shot_dir).glob("m*.png")
                   if re.fullmatch(r"m\d+\.png", p.name))
    if not shots:
        print(f"no captures in {shot_dir}; run tools/capture_monsters.js")
        return 2

    listed = creatures(S.load())
    agree = filled = 0
    rows = 0
    for creature, shot in zip(listed, shots):
        got = RS.read_effects(shot)
        want = expected(creature["immunity"], creature["resistance"])
        for row, (g, w) in enumerate(zip(got, want)):
            rows += 1
            filled += g != RS.NONE
            if g == w:
                agree += 1
            else:
                print(f"  {creature['name']:20} {L.EFFECTS[row]:16} "
                      f"screen {g}, record {w}")
    print(f"{agree}/{rows} effect rows agree, over {len(listed)} creatures; "
          f"{filled} of them carry a word")
    return 0 if agree == rows and rows else 1


if __name__ == "__main__":
    raise SystemExit(main(*sys.argv[1:]))
