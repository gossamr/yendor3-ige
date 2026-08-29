"""Solve the spell record against the game's own F3 screens.

Same method as the enemy record: read every spell's clue-book page, then look
for the field in the 80-byte record whose values match exactly across all of
them. An exact match over ~99 spells is not something a wrong offset can fake.
"""

from __future__ import annotations

import glob
import json
import struct
from pathlib import Path

import ocr
import read_spells
import sections as S

MAGIC_CLASSES = ["MONK", "ALCHEMIST", "PALADIN", "MAGE", "DRUID", "MARKSMAN"]


def records():
    d = S.load("game")
    out = []
    for rec in d[S.SPELLS].records(d.world, S.SPELL_RECORD):
        name = rec[:21].split(b"\x00")[0].decode("latin1").strip()
        out.append((name, rec))
    return out


def read_all(shot_dir="tmp/spells"):
    """Every captured screen, keyed by the spell name read off its title bar.

    Aligning by name rather than by position is what makes this reliable: the
    list walk skipped one entry (SHARD OF ICE) when the page scrolled, and a
    positional mapping would have been silently wrong from there on.
    """
    names = [n for n, _ in records() if n != "ERROR"]
    shots = [Path(p) for p in sorted(glob.glob(f"{shot_dir}/m[0-9][0-9][0-9].png"))]
    alpha = read_spells.build_alphabet(shots, names)
    # The game writes an apostrophe as "~", which has no glyph in the alphabet
    # and reads as "?", so names are compared with those positions removed.
    plain = lambda t: t.replace("?", "").replace(" ", "").replace("'", "")
    by_name = {plain(n): n for n in names}
    out = {}
    for shot in shots:
        frame = ocr.Frame(shot)
        name = by_name.get(plain(read_spells.read_name(alpha, frame)))
        if name and name not in out:
            out[name] = read_spells.read_spell(frame, alpha)
    return out


def u16(rec, off):
    return struct.unpack_from("<H", rec, off)[0]


def solve(shot_dir="tmp/spells"):
    recs = records()
    by_name = read_all(shot_dir)
    listed = [(n, r) for n, r in recs if n in by_name]
    seen = [by_name[n] for n, _ in listed]
    print(f"{len(recs)} records, {len(listed)} matched to a screen by name\n")

    def find(target, label):
        """An offset whose u16 equals `target` for every spell."""
        hits = []
        for off in range(22, 79):
            if [u16(r, off) for _, r in listed] == target:
                hits.append(("u16", off))
            if off < 80 and [r[off] for _, r in listed] == target:
                hits.append(("u8", off))
        print(f"  {label:<28} {hits if hits else 'no exact match'}")
        return hits

    print("costs:")
    find([s["mp"] or 0 for s in seen], "MP")
    find([s["nuore"] or 0 for s in seen], "nuore")

    print("\nper-class level (0 = cannot cast):")
    for cls in MAGIC_CLASSES:
        target = []
        for s in seen:
            row = next((c for c in s["classes"] if c["class"] == cls), None)
            target.append(row["level"] if row and row["level"] else 0)
        find(target, cls.lower())

    print("\nlearned from a scroll rather than training (bit search):")
    for cls in MAGIC_CLASSES:
        want = {i for i, s in enumerate(seen)
                if any(c["class"] == cls and c["source"] == "SCROLL"
                       for c in s["classes"])}
        hits = [(off, bit) for off in range(22, 80) for bit in range(8)
                if {i for i, (_, r) in enumerate(listed) if r[off] >> bit & 1} == want]
        print(f"  {cls.lower():<28} {hits[:4] if hits else 'no exact match'}")

    for field in ("affects", "when"):
        print(f"\n{field}:")
        values = sorted({s[field] for s in seen if s[field]})
        for off in range(22, 79):
            column = [u16(r, off) for _, r in listed]
            mapping = {}
            ok = True
            for value, s in zip(column, seen):
                if s[field] is None:
                    continue
                if mapping.setdefault(value, s[field]) != s[field]:
                    ok = False
                    break
            if ok and len(mapping) >= max(2, len(values) - 1):
                print(f"  u16 @{off}: {len(mapping)} distinct -> {mapping}")
                break
        else:
            print("  no column maps cleanly")
    return listed, seen
