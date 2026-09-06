"""Every animation the game draws over a target, and what asks for it.

Five things draw over a monster or over a character, and each names its
artwork a different way. [spells.md](../docs/spells.md) has the cast's four,
[combat.md](../docs/combat.md) the attack table's and the struck-monster
ladder:

* **bolt** — run 1. A cast's projectile, spell offset 38, handed to the volley
  drawer at image `0x1B547` and placed in the caster's own quarter.
* **area** — run 3. Spell offsets 42 and 44, a first frame and a count, drawn
  through the wide table on the band the flight stopped on.
* **burst** — run 3. Spell offsets 38 and 40, two groups of three frames: the
  first cycles out along the six bands and the second plays where it stopped.
* **rain** — run 6. Spell offset 48 laid down once over each party place, then
  four cursors seeded from offset 50 stepped offset 40 times, each wrapping
  after offset 52 pictures.
* **attack** — run 7, or run 8 where the entry's flags carry `0x0600`. The
  attack table entry's `+2`, drawn over whichever animation slot the blow or
  the cure was queued on, which for a restorative is the healed character's
  own portrait.
* **struck** — run 6. Three constants at `DS:0x5480`, picked by the damage as
  a share of the monster's health and laid at the place the drawing mode
  names plus the monster's own records 54 and 56.

**A spell carries its own recolor** at offsets 54 to 59, up to six bytes each
holding a source group in the high nibble and a destination in the low, which
is the form the enemy record uses at 64 to 69 ([pictures.md](../docs/pictures.md)).
It also carries a **tint** at offset 36, an index into 82 pixel routines at
`cs:0x0D6B` of the blitter's segment, which the cast writes onto its target and
the target's next draw paints itself with. [tints.py](tints.py) reads them.

    python tools/effects.py            # every effect and who asks for it
    python tools/effects.py --frames   # the picture numbers each reaches
"""

from __future__ import annotations

import argparse
import struct

import extract as EX
import sections as S
import spell_sounds as SS
import tints as TI
from disasm import Exe

# The branches of the cast dispatcher that draw, by the image they start at.
BOLT_AREA = 0x1CD82
BURST = 0x1D146
RAIN = 0x1D4D4

# Spell record offsets, all of which mean something else on a branch that does
# not draw. `docs/spells.md` says which branch reads which.
BOLT = 38
BURST_FIRST, BURST_SECOND = 38, 40
AREA_FIRST, AREA_COUNT = 42, 44
RAIN_GROUND, RAIN_FIRST, RAIN_PICTURES = 48, 50, 52
# How many times image 0x1D575 steps the four cursors, which is offset 40 on
# this branch and the second frame group on the burst's.
RAIN_STEPS = 40
TINT = 36
RECOLOR_AT, RECOLOR_LEN = 54, 6

BURST_FRAMES = 3

# Which run each kind draws from.
RUN = {"bolt": 1, "area": 3, "burst": 3, "rain": 6, "struck": 6}
ATTACK_RUN, ATTACK_EQUIPMENT_RUN = 7, 8
EQUIPMENT_FLAG = 0x0600

# The three struck-monster pictures, written once at image 0x0F14E and never
# again, and the damage bands that pick between them.
STRUCK = (18, 19, 24)
STRUCK_BANDS = (10, 30)

# Where the splat lands, by the drawing mode the monster itself took: image
# 0x103F0 walks modes 9 to 14 and writes one corner per mode, and image
# 0x10443 then adds the monster's own records 54 and 56. The six are the three
# hand-to-hand places of each run, and a monster out in the world draws
# through 10 or 13, so it takes the middle place's corner whatever cell it
# stands on. Screen coordinates, so the viewport's own 8 comes off both.
STRUCK_PLACE = {9: (-22, 34), 10: (25, 34), 11: (82, 34),
                12: (-7, 8), 13: (50, 8), 14: (107, 8)}

# What the four places of a rain are drawn at, image 0x1D4FD onward, and how
# far apart the four cursors start (image 0x1D53F). Screen coordinates again.
RAIN_PLACE_X = (8, 64, 120, 176)
RAIN_PLACE_Y = 8
RAIN_CURSOR = (0, 2, 4, 1)

# The bands a bolt and a burst step out along, near to far, which are the six
# a volley's shot takes (docs/combat.md).
BANDS = (0x31, 0x2E, 0x2B, 0x28, 0x24, 0x19)

# What one draw holds for, in BIOS ticks of 55 ms: image 0x1D12E waits one
# between an area's frames, 0x1D87F five between a burst's, and 0x1D5B3 two
# between a rain's steps.
AREA_TICKS, BURST_TICKS, RAIN_TICKS = 1, 5, 2


def recolor(rec: bytes, at: int = RECOLOR_AT) -> dict[int, int]:
    """The spell's own group swaps, source group -> destination group."""
    return {b >> 4: b & 0xF for b in rec[at:at + RECOLOR_LEN] if b}


def _word(rec: bytes, off: int) -> int:
    return struct.unpack_from("<H", rec, off)[0]


def spell_effects(d: S.Directory, exe: Exe) -> list[dict]:
    """One row per spell record that draws something of its own."""
    branches = {b.get("target") or b.get("at"): b for b in SS.branches(exe)}
    records = d[S.SPELLS].records(d.world, S.SPELL_RECORD)
    out = []
    for index, rec in enumerate(records):
        name = rec[:21].split(b"\x00")[0].decode("latin1").strip()
        took = next((tgt for tgt, b in branches.items()
                     if _word(rec, b["field"]) & b["bit"]), None)
        frames: list[int] = []
        kind, steps = None, 0
        if took == BOLT_AREA and _word(rec, AREA_FIRST) and _word(rec, AREA_COUNT):
            kind, first = "area", _word(rec, AREA_FIRST)
            frames = list(range(first, first + _word(rec, AREA_COUNT)))
        elif took == BOLT_AREA and _word(rec, BOLT):
            kind, frames = "bolt", [_word(rec, BOLT)]
        elif took == BURST and _word(rec, BURST_FIRST):
            kind = "burst"
            for base in (_word(rec, BURST_FIRST), _word(rec, BURST_SECOND)):
                frames += list(range(base, base + BURST_FRAMES))
        elif took == RAIN and _word(rec, RAIN_GROUND):
            kind, first = "rain", _word(rec, RAIN_FIRST)
            frames = [_word(rec, RAIN_GROUND)]
            frames += list(range(first, first + _word(rec, RAIN_PICTURES)))
            steps = _word(rec, RAIN_STEPS)
        if kind is None:
            continue
        row = {"spell": index + 1, "name": name, "kind": kind,
               "run": RUN[kind], "frames": frames,
               "recolor": recolor(rec), "tint": _word(rec, TINT)}
        if kind == "rain":
            row["steps"] = steps
        out.append(row)
    return out


def attack_effects(d: S.Directory) -> list[dict]:
    """One row per attack table entry, with the run its `+2` draws from."""
    out = []
    for index, entry in enumerate(EX.attack_table(d.exe)):
        equipment = bool(entry["flags"] & EQUIPMENT_FLAG)
        out.append({"attack": index, "run": ATTACK_EQUIPMENT_RUN if equipment
                    else ATTACK_RUN, "frames": [entry["animation"]],
                    "sound": entry["sound"]})
    return out


def struck_effects() -> list[dict]:
    """The three the damage ladder reaches, hardest last."""
    return [{"band": band, "run": RUN["struck"], "frames": [picture]}
            for band, picture in zip(("to 10 percent", "to 30 percent",
                                      "over 30 percent"), STRUCK)]


def struck_places() -> dict[int, list[int]]:
    """Drawing mode -> the corner the splat is laid at, before the records."""
    return {mode: list(corner) for mode, corner in STRUCK_PLACE.items()}


def wanted(d: S.Directory, exe: Exe) -> dict[int, set[int]]:
    """Run -> every picture any of the three reaches, for a packer."""
    out: dict[int, set[int]] = {}
    for row in spell_effects(d, exe) + attack_effects(d) + struck_effects():
        out.setdefault(row["run"], set()).update(
            n for n in row["frames"] if n)
    return out


def build(d: S.Directory, exe: Exe) -> dict:
    return {"tints": {str(n): row for n, row in TI.tints(exe).items()
                      if "unread" not in row},
            "spells": spell_effects(d, exe),
            "attacks": attack_effects(d),
            "struck": struck_effects(),
            "bands": list(STRUCK_BANDS),
            "places": struck_places(),
            "rain": {"x": list(RAIN_PLACE_X), "y": RAIN_PLACE_Y,
                     "cursor": list(RAIN_CURSOR)},
            "cells": list(BANDS),
            "ticks": {"area": AREA_TICKS, "burst": BURST_TICKS,
                      "rain": RAIN_TICKS}}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("game", nargs="?", default="game")
    ap.add_argument("--frames", action="store_true")
    args = ap.parse_args()

    d = S.load(args.game)
    exe = Exe(f"{args.game}/REGISTER.EXE")
    rows = spell_effects(d, exe)
    print(f"{len(rows)} spells draw an effect of their own")
    for row in rows:
        extra = f"  recolor {row['recolor']}" if row["recolor"] else ""
        tint = f"  tint {row['tint']}" if row["tint"] else ""
        frames = f"  {row['frames']}" if args.frames else \
            f"  {len(row['frames'])} frame{'s' if len(row['frames']) != 1 else ''}"
        print(f"  {row['name']:<22} {row['kind']:<6} run {row['run']}{frames}{extra}{tint}")

    print(f"\n{len(attack_effects(d))} attack table entries")
    for row in attack_effects(d):
        print(f"  attack {row['attack']:>2}  run {row['run']}  picture "
              f"{row['frames'][0]:>3}  sound {row['sound']:>3}")

    print("\nstruck-monster ladder")
    for row in struck_effects():
        print(f"  {row['band']:<16} run {row['run']}  picture {row['frames'][0]}")

    print("\npictures a packer needs:")
    for run, nums in sorted(wanted(d, exe).items()):
        print(f"  run {run}: {len(nums)} pictures")


if __name__ == "__main__":
    main()
