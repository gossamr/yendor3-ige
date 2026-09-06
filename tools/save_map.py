#!/usr/bin/env python3
"""What changed in the game's state file, step by step.

`tools/save_probe.js` plays a scripted session and takes CURGAME after every
step. CURGAME is the save format, and SAVGAMEn is a byte copy of it, and the
game writes single records back to it as they change, so diffing consecutive
snapshots names fields: whatever moved when the party moved is where the party
is kept.

    .venv/bin/python tools/save_map.py tmp/save-probe/walk
    .venv/bin/python tools/save_map.py tmp/save-probe/walk --from=05 --to=06
    .venv/bin/python tools/save_map.py --layout        # the sections

An offset is named from `tools/saves.py`'s model, so a changed byte reports as
`seen grid y=47 cells 456-463` or `slot 6 +82 (current hit points)` rather than
as a number. `docs/saves.md` has what each section holds.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import saves as S

SLOT = S.ROSTER_SLOT
SLOTS = S.ROSTER_SLOTS
ROSTER_BYTES = SLOTS * SLOT

# Offsets inside the roster's header slot, and inside a 500-byte character
# record. What each one is, and how it was established, is in docs/saves.md.
HEADER: list[tuple[int, int, str]] = [
    (0, 20, "the save's name, over the head of PRE-CREATED PARTY"),
    (S.LIGHT_AT, 2, "light flags"),
    (32, 2, "the party's own flags, five bits of them the mapping bands"),
    *((S.PARTY_AVERAGES_AT + 2 * i, 2, f"{skill} party average")
      for i, skill in enumerate(S.PARTY_AVERAGES)),
    (S.DAY_SONG_AT, 2, "day song"),
    (S.NIGHT_SONG_AT, 2, "night song"),
    (S.ARRIVAL_DRAIN_AT, 2, "step counter cleared on arrival"),
    (S.SKY_WINDOW_AT, 2, "where the sky window sits on its gradient"),
    (S.SKY_STEP_AT, 2, "the step the sky window moves by"),
    (S.NEXT_RECORD_AT, 2, "next container record to hand out"),
    (S.FREE_HEAD_AT, 2, "container free-list head"),
    (S.ENVIRONMENT_AT, 2, "environment"),
    (S.KEY_RING_AT, 2, "key ring"),
    (S.CARRIED_COUNTS_AT, 12, "carried light counts, 6 strengths"),
    (S.LIGHT_TIMERS_AT, 2 * S.LIGHT_STRENGTHS, "cast light timers"),
    (S.AREA_AT, 2, "ambient area"),
    (S.DAWN_AT, 2, "dawn windows already fired"),
    (S.DRAIN_AT, 2, "condition drain step count"),
    (S.COLD_DRAIN_AT, 2, "cold drain step count"),
    (150, 2, "facing"),
    (152, 2, "party x"),
    (154, 2, "party y"),
    (156, 2, "day"),
    (S.MONTH_AT, 2, "month"),
    (S.YEAR_AT, 2, "year"),
    (162, 2, "clock"),
    (180, 4, "gold"),
    (184, 4, "food"),
    (188, 4, "nuore"),
    (S.MARK_SPARE_AT, 2, "carried by MARK, put back by RETURN"),
    (S.QUEST_FLAGS_AT, 2 * S.QUEST_FLAG_WORDS, "fourteen quest flag words"),
    (S.MARK_AT, 14, "where MARK OR RETURN wrote the party"),
    (S.PARTY_PANEL_AT, 4 * S.PARTY_PANEL_SLOTS, "the party's own panel slots"),
    (310, 96, "the sky ramp, 32 colors"),
    (S.SKY_SLIDE_AT, 2, "sky slide left to run"),
    (S.CAST_BY_AT, 2, "who cast last"),
    (S.SETTINGS_AT, 4, "the two words NEW GAME preserves"),
    (S.AUDIO_AT, 2, "music and sound"),
    (S.REPAINT_AT, 2, "ticks between view repaints"),
    (S.PARTY_SKILLS_AT, 2 * len(S.PARTY_SKILLS), "who acts for each party skill"),
    (492, 8, "the roster slots that are playing"),
]
CHARACTER: list[tuple[int, int, str]] = [
    (0, 14, "name, NUL terminated"),
    (14, 2, "class"),
    (16, 2, "sex"),
    (22, 2, "level"),
    (24, 4, "experience"),
    (28, 2, "conditions"),
    (S.LIVE, 52, "the live block"),
    (S.MAXIMUM, 52, "the same block again, the maximum"),
    (S.CARRIED_AT, 2, "weight carried"),
    (S.PANEL_AT, 4 * S.PANEL_SLOTS, "the eight panel slots"),
    (S.SPELL_BOOK_AT, 2 * S.SPELL_BOOK_WORDS, "spell book, one bit per spell"),
    (S.PORTRAIT_AT, 2, "portrait"),
    (30, 2, "levels owed"),
    (S.PROTECTIONS_AT, 2 * S.PROTECTIONS, "the nine protection words"),
    *((at, 2, f"protection {i}") for i, at in enumerate(S.PROTECTION_ORDER)),
    (S.FLIGHT_COUNTS_AT, 2 * S.FLIGHT_COUNTS, "flight use counts"),
    (S.MARK_AT, 14, "where MARK OR RETURN wrote the party"),
    *((S.SEEDS_AT + 2 * i, 2, f"{seed} seed") for i, seed in enumerate(S.SEEDS)),
    *((at + 2, 2, f"{name} state") for name, at in S.EQUIPMENT.items()
      if name in S.PAIRED_SLOTS),
    (S.CAST_AT, 2, "where the cast menu was left"),
    (S.GALLERY_AT, 2, "the gallery cell the portrait came from"),
    (S.CHALLENGES_AT, 2, "the once-per-character services taken"),
    (S.FLIGHTS_AT, 2, "transport bits"),
    (S.CHOOSER_REFUSAL_AT, 2, "bit 0x8000 refuses the open chooser"),
    (S.MAX_SEEDS_AT, 10, "the maximum column's five seeds"),
    *((S.OPEN_STACK_AT + i * S.OPEN_STACK_STRIDE, S.OPEN_STACK_STRIDE,
       f"open container, level {S.OPEN_STACK_DEPTH - i}")
      for i in range(S.OPEN_STACK_DEPTH)),
    *((at, 2, f"{name} wear") for name, at in S.WEAR.items()),
    (S.MEMBER_AT, 2, "open-container depth, store last resolved, membership, two-handed"),
    *((at, 2, name) for name, at in S.EQUIPMENT.items()),
    # The named words inside the two blocks, so a change reports as the field
    # rather than as the block it sits in.
    *((base + off, 2, name)
      for base in (S.LIVE, S.MAXIMUM)
      for off, name in [
          *((S.OFF_ATTRIBUTES + 2 * i, n) for i, n in enumerate(S.ATTRIBUTES)),
          *((S.OFF_COMBAT + 2 * i, n) for i, n in enumerate(S.COMBAT)),
          *((S.OFF_SKILLS + 2 * i, n) for i, n in enumerate(S.SKILLS)),
          (S.OFF_HEALTH, "health"), (S.OFF_MAGIC, "magic"),
          (S.OFF_CAPACITY, "weight capacity"),
      ]),
]


def snapshots(run: Path) -> list[dict]:
    index = json.loads((run / "index.json").read_text())["steps"]
    out = []
    for s in index:
        p = run / f"{s['tag']}.bin"
        if p.exists():
            out.append({**s, "bytes": p.read_bytes()})
    return out


def ranges(a: bytes, b: bytes, gap: int = 8):
    """Changed byte ranges, joining ones separated by less than `gap`."""
    out: list[list[int]] = []
    n = min(len(a), len(b))
    for i in range(n):
        if a[i] == b[i]:
            continue
        if out and i - out[-1][1] < gap:
            out[-1][1] = i + 1
        else:
            out.append([i, i + 1])
    return [(lo, hi) for lo, hi in out]


def _best(fields, off: int) -> str | None:
    """The narrowest field covering an offset, so `current hit points` wins
    over the 52-byte block it sits in."""
    hits = [(ln, name) for lo, ln, name in fields if lo <= off < lo + ln]
    return min(hits)[1] if hits else None


def where(at: int) -> str:
    """The most specific name the layout has for an offset."""
    if at < ROSTER_BYTES:
        slot, off = divmod(at, SLOT)
        who = "header" if slot == 0 else f"slot {slot}"
        name = _best(HEADER if slot == 0 else CHARACTER, off)
        return f"{who} +{off}" + (f" ({name})" if name else "")
    for s in S.sections():
        if not s.base <= at < s.end:
            continue
        n, r = divmod(at - s.base, s.record or 1)
        if s.index == 1:
            return f"seen grid y={n} cells {r * 8}-{r * 8 + 7}"
        if s.index in (3, 4, 5):
            return f"section {s.index} bits {n * 8}-{n * 8 + 7}"
        return f"section {s.index} record {n} +{r}"
    return f"past the end +{at}"


def words(blob: bytes, lo: int, hi: int) -> str:
    part = blob[lo:hi]
    if hi - lo <= 16:
        return part.hex(" ")
    return part[:16].hex(" ") + f" ... ({hi - lo} bytes)"


def report(run: Path, first: str | None, last: str | None, gap: int) -> None:
    shots = snapshots(run)
    if first or last:
        shots = [s for s in shots
                 if (not first or s["tag"] >= first) and (not last or s["tag"] <= last)]
    print(f"{len(shots)} snapshots in {run}")
    for prev, cur in zip(shots, shots[1:]):
        rs = ranges(prev["bytes"], cur["bytes"], gap)
        writes = " ".join(f"{t['file']}@{t['at']}+{t['len']}"
                          for t in cur.get("touched", []) if t["op"] == "write")
        total = sum(hi - lo for lo, hi in rs)
        print(f"\n[{cur['step']:02d}] {cur['label']}  keys={cur['keys']!r}"
              f"  {len(rs)} ranges, {total} bytes"
              + (f"\n     writes: {writes}" if writes else ""))
        for lo, hi in rs:
            print(f"     {lo:>6}-{hi:<6} {where(lo):<44}"
                  f" {words(prev['bytes'], lo, hi)}  ->  {words(cur['bytes'], lo, hi)}")


def layout() -> None:
    for s in S.sections():
        print(f"{s.base:>8} {s.size:>8} {str(s.records):>6} x {s.record}"
              f"  {s.name}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("run", nargs="?", help="a directory written by tools/save_probe.js")
    ap.add_argument("--from", dest="first", default=None, help="first snapshot tag prefix")
    ap.add_argument("--to", dest="last", default=None, help="last snapshot tag prefix")
    ap.add_argument("--gap", type=int, default=8,
                    help="join changed ranges closer together than this")
    ap.add_argument("--layout", action="store_true", help="print what is known")
    ap.add_argument("--diff", nargs=2, metavar=("WAS", "NOW"),
                    help="two save files, named field by field")
    args = ap.parse_args()
    if args.diff:
        was, now = (Path(p).read_bytes() for p in args.diff)
        for lo, hi in ranges(was, now, args.gap):
            print(f"  {lo}-{hi - 1}  {where(lo)}"
                  f"   {was[lo:hi].hex()} -> {now[lo:hi].hex()}")
        moved = sum(1 for a, b in zip(was, now) if a != b)
        print(f"{moved} bytes differ")
        return
    if args.layout or not args.run:
        layout()
        return
    report(Path(args.run), args.first, args.last, args.gap)


if __name__ == "__main__":
    main()
