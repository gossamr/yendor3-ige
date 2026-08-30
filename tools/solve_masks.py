"""Solve the enemy record's immunity and resistance bit layout.

Method: capture the game's own F2 screen for every monster, read the twelve
effect rows off it (tools/read_stats.py), then look for a (word, bit) in the
106-byte record whose set of monsters is *exactly* the set the game shows for
that effect and state. An exact set match over 70-odd monsters is not
something a wrong bit can fake.

The game lists monsters alphabetically while the records are in table order,
so the alignment is checked both ways, with and without the placeholder
"NOT USED" record, and the one that fits is the right one.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path

import read_stats
import sections as S
from labels import EFFECTS

WORDS = [96, 98, 100, 102]


def records() -> list[tuple[str, bytes]]:
    d = S.load("game")
    out = []
    for rec in d[S.ENEMIES].records(d.world, S.ENEMY_RECORD):
        a = rec[0:13].split(b"\x00")[0].decode("latin1").strip()
        b = rec[13:26].split(b"\x00")[0].decode("latin1").strip()
        name = " ".join(p for p in (a, b) if p)
        if name:
            out.append((name, rec))
    return out


def observed(shot_dir: Path) -> list[list[str]]:
    shots = sorted(shot_dir.glob("m[0-9][0-9].png"))
    return [read_stats.read_effects(p) for p in shots]


def alignments(names: list[str], n_shots: int):
    """Candidate orderings of the game's list against our records."""
    ordered = sorted(names)
    yield "all records", ordered
    if "NOT USED" in ordered:
        yield "skipping NOT USED", [n for n in ordered if n != "NOT USED"]


def bit_sets(recs: dict[str, bytes], names: list[str]):
    """{(word, bit): frozenset(names with that bit set)}"""
    out = {}
    for word in WORDS:
        for bit in range(16):
            hits = frozenset(
                n for n in names
                if struct.unpack_from("<H", recs[n], word)[0] >> bit & 1)
            if hits:
                out[(word, bit)] = hits
    return out


def solve(shot_dir: str | Path = "tmp/monsters"):
    recs = dict(records())
    seen = observed(Path(shot_dir))
    print(f"{len(recs)} records, {len(seen)} captured screens\n")

    best = None
    for label, ordered in alignments(list(recs), len(seen)):
        usable = min(len(seen), len(ordered))
        names = ordered[:usable]
        sets = bit_sets(recs, names)
        found, missing = {}, []
        for e, effect in enumerate(EFFECTS):
            for state in (read_stats.IMMUNE, read_stats.RESISTANT):
                target = frozenset(
                    names[i] for i in range(usable) if seen[i][e] == state)
                if not target:
                    continue
                hit = [k for k, v in sets.items() if v == target]
                if hit:
                    found[(effect, state)] = hit
                else:
                    missing.append((effect, state, len(target)))
        score = len(found)
        print(f"alignment '{label}' over {usable} monsters: "
              f"{score} exact matches, {len(missing)} unmatched")
        if best is None or score > best[0]:
            best = (score, label, names, seen, found, missing, sets)
    return best


if __name__ == "__main__":
    import sys

    score, label, names, seen, found, missing, sets = solve(
        sys.argv[1] if len(sys.argv) > 1 else "tmp/monsters")
    print(f"\n=== best alignment: {label} ===")
    for (effect, state), where in sorted(found.items()):
        loc = ", ".join(f"word {w} bit {b}" for w, b in where)
        print(f"  {effect:<16} {state:<10} -> {loc}")
    if missing:
        print("\nnot matched by any single bit:")
        for effect, state, n in missing:
            print(f"  {effect:<16} {state:<10} ({n} monsters)")
