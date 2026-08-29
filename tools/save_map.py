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
    (150, 2, "facing"),
    (152, 2, "party x"),
    (154, 2, "party y"),
    (156, 2, "day"),
    (162, 2, "clock"),
    (180, 4, "gold"),
    (184, 4, "food"),
    (188, 4, "nuore"),
    (310, 96, "the sky ramp, 32 colors"),
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
    args = ap.parse_args()
    if args.layout or not args.run:
        layout()
        return
    report(Path(args.run), args.first, args.last, args.gap)


if __name__ == "__main__":
    main()
