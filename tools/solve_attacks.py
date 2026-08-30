"""Identify each monster's special attacks from the game's own screen.

The attack line is drawn in blue below the statistics. Rather than transcribe
the game's font by hand, the alphabet is grown from one line whose text is
known (ACOKNIGHT reads "PARTY ATTACK") and then extended by matching
partially-read lines against the attack vocabulary held in the executable.
A line only teaches new letters when it has exactly one possible reading, so
the alphabet can never be corrupted by a guess.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import ocr

# The vocabulary the game prints, taken from the label run in REGISTER.EXE.
# BREAK and DESTROY are prefixes: they combine with the three equipment words.
EQUIPMENT = ["PROJECTILE", "WEAPON", "SHIELD"]
ATTACKS = [
    "PARTY ATTACK", "SICK", "POISON", "DISEASE", "PARALYZE", "FROZEN",
    "STONING", "JINXING", "HEXING", "CURSING",
    "STEAL GOLD", "STEAL FOOD", "STEAL NUORE",
    *EQUIPMENT,
    *[f"{p} {e}" for p in ("BREAK", "DESTROY") for e in EQUIPMENT],
]
# Spaces are not drawn as glyphs, so compare on letters alone.
BARE = {a: a.replace(" ", "") for a in ATTACKS}

BOOTSTRAP_LINE = ("ACOKNIGHT", "PARTYATTACK")
BLUE_X_MIN = 0  # the attack row sits below the portrait, so nothing intrudes


def parses(pattern: str) -> list[list[str]]:
    """Every way `pattern` (letters and '?') splits into comma-separated names."""
    if not pattern:
        return [[]]
    out = []
    for name, bare in BARE.items():
        head, rest = pattern[:len(bare)], pattern[len(bare):]
        if len(head) != len(bare):
            continue
        if any(a != "?" and a != b for a, b in zip(head, bare)):
            continue
        if rest.startswith(","):
            for tail in parses(rest[1:]):
                out.append([name, *tail])
        elif not rest:
            out.append([name])
    return out


def solve(shot_dir: str | Path, order: list[str]):
    shots = sorted(Path(shot_dir).glob("m[0-9][0-9].png"))[:len(order)]
    frames = {n: ocr.Frame(s) for n, s in zip(order, shots)}

    alpha = ocr.standard_alphabet(shot_dir)
    name, text = BOOTSTRAP_LINE
    if not alpha.learn(frames[name], ocr.SPECIAL_ATTACK_ROW, "blue", text, BLUE_X_MIN):
        raise SystemExit("bootstrap line did not have the expected glyph count")

    for _ in range(12):
        learned = 0
        for n, frame in frames.items():
            line = alpha.read(frame, ocr.SPECIAL_ATTACK_ROW, "blue", BLUE_X_MIN)
            if not line or "?" not in line:
                continue
            options = parses(line)
            if len(options) != 1:
                continue
            truth = ",".join(BARE[a] for a in options[0])
            if alpha.learn(frame, ocr.SPECIAL_ATTACK_ROW, "blue", truth, BLUE_X_MIN):
                learned += 1
        if not learned:
            break

    result, unresolved = {}, {}
    for n, frame in frames.items():
        line = alpha.read(frame, ocr.SPECIAL_ATTACK_ROW, "blue", BLUE_X_MIN)
        if not line:
            result[n] = []
            continue
        options = parses(line)
        if len(options) == 1:
            result[n] = options[0]
        else:
            unresolved[n] = (line, len(options))
    return alpha, result, unresolved


if __name__ == "__main__":
    import sys

    rows = json.load(open("tmp/screen_stats.json"))
    alpha, result, unresolved = solve(sys.argv[1] if len(sys.argv) > 1 else "tmp/monsters",
                                      list(rows))
    letters = "".join(sorted({v for v in alpha.by_bits.values() if v.isalpha()}))
    print(f"alphabet: {letters}")
    print(f"resolved {len(result)}/{len(result) + len(unresolved)} monsters")
    for n, (line, count) in unresolved.items():
        print(f"  unresolved {n}: {line!r} ({count} readings)")
    seen = sorted({a for v in result.values() for a in v})
    print(f"\nattacks in use ({len(seen)}): {seen}")
    json.dump(result, open("tmp/attacks.json", "w"), indent=1)
