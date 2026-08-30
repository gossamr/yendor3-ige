#!/usr/bin/env python3
"""Check every tracked file for British spellings.

This repository spells American, in identifiers and payload keys as much as
in prose. This is that rule as a check.

Stems are matched inside words, not only as whole words, because the drift
lands in identifiers as much as in prose: `armour` catches `armourShare` and
`share_to_armour`, `colour` catches `recoloured` and `RANGED_RECOLOUR_BYTES`.
Matching is case-insensitive and the replacement keeps the case it found.

The list is explicit rather than a scan for -our, -ise, -yse and -re endings.
A suffix scan reads `four`, `noise`, `premise` and `feature` as hits and needs
an allowlist longer than this file. An explicit list misses a word nobody has
written yet. That is the trade: add the word when it turns up.

A stem that is also the start of an American word carries a lookahead, which
is what keeps `analys` off `analysis`, `optimis` off `optimistic`, `specialis`
off `specialist` and `totall` off `totally`. A check that cries wolf is a
check somebody turns off, so a stem goes in only once its lookahead is right.

Reads only committed paths, so generated data and node_modules are out of
scope by construction.

    python tools/spelling_check.py            # every tracked file
    python tools/spelling_check.py web docs   # only under these paths
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Both of these name the words they are about, so both always match
# themselves. Nothing else is exempt: an exemption is how a check stops
# covering the tree it is there to cover.
SKIP = {"tools/spelling_check.py", "tests/test_spelling_check.py"}

# Names the game itself spells the British way. They are quoted out of its
# data and used as lookup keys into it, so they are not ours to respell.
# Matched only in the caps the game writes them in, which is how extracted
# text is quoted throughout: `SPECTRE` is the monster, "the spectre" is the
# English word and still a hit.
GAME_WORDS = {"SABRE", "SPECTRE"}

# The endings that turn an -ise stem into a word: -ise, -ised, -ises, -iser,
# -ising, -isation, -isable. Each begins with one of these, and none of -ism,
# -ist or -istic does, which is what separates "optimise" from "optimistic".
ISE = r"(?=e|ing|ation|able)"

# The -yse family and "emphasis" share a stem with a noun that is spelled the
# same either side of the Atlantic. "analysis" and "paralyses" stay; the verb
# forms go. "analyses" is both the British verb and the American noun plural,
# so it is left alone rather than guessed at.
YSE = r"(?=e(?!s)|ing)"

# British doubles the l before a vowel suffix where American does not. The
# lookahead is what keeps this off "totally" and off "cancellation", which is
# spelled with two l's in both.
LL = r"(?=ed|ing|er)"

# British stem -> American stem. Stems, not whole words, so one entry covers
# every inflection: "recognis" is recognise, recognised and recognisable.
STEMS = {
    # -our
    "armour": "armor",
    "behaviour": "behavior",
    "colour": "color",
    "endeavour": "endeavor",
    "favour": "favor",
    "flavour": "flavor",
    "honour": "honor",
    "humour": "humor",
    "labour": "labor",
    "neighbour": "neighbor",
    "odour": "odor",
    "rigour": "rigor",
    "rumour": "rumor",
    "savour": "savor",
    "valour": "valor",
    "vapour": "vapor",
    "vigour": "vigor",
    # -re
    "calibre": "caliber",
    "centre": "center",
    "fibre": "fiber",
    "litre": "liter",
    "lustre": "luster",
    "manoeuvre": "maneuver",
    "metre": "meter",
    "sabre": "saber",
    "sombre": "somber",
    "spectre": "specter",
    "theatre": "theater",
    # -ce for -se
    "defence": "defense",
    "licence": "license",
    "offence": "offense",
    "practise": "practice",
    "pretence": "pretense",
    # -ise
    "apologis" + ISE: "apologiz",
    "authoris" + ISE: "authoriz",
    "categoris" + ISE: "categoriz",
    "centralis" + ISE: "centraliz",
    "characteris" + ISE: "characteriz",
    "customis" + ISE: "customiz",
    "equalis" + ISE: "equaliz",
    "finalis" + ISE: "finaliz",
    "generalis" + ISE: "generaliz",
    "initialis" + ISE: "initializ",
    "itemis" + ISE: "itemiz",
    "localis" + ISE: "localiz",
    "maximis" + ISE: "maximiz",
    "memois" + ISE: "memoiz",
    "minimis" + ISE: "minimiz",
    "modernis" + ISE: "moderniz",
    "normalis" + ISE: "normaliz",
    "optimis" + ISE: "optimiz",
    "organis" + ISE: "organiz",
    "penalis" + ISE: "penaliz",
    "prioritis" + ISE: "prioritiz",
    "randomis" + ISE: "randomiz",
    "rationalis" + ISE: "rationaliz",
    "realis" + ISE: "realiz",
    "recognis" + ISE: "recogniz",
    "sanitis" + ISE: "sanitiz",
    "serialis" + ISE: "serializ",
    "specialis" + ISE: "specializ",
    "stabilis" + ISE: "stabiliz",
    "standardis" + ISE: "standardiz",
    "summaris" + ISE: "summariz",
    "synchronis" + ISE: "synchroniz",
    "tokenis" + ISE: "tokeniz",
    "utilis" + ISE: "utiliz",
    "visualis" + ISE: "visualiz",
    # -yse, and the one -is noun that also has a verb
    "analys" + YSE: "analyz",
    "catalys" + YSE: "catalyz",
    "emphasis" + YSE: "emphasiz",
    "paralys" + YSE: "paralyz",
    # doubled l
    "cancell" + LL: "cancel",
    "fuell" + LL: "fuel",
    "labell" + LL: "label",
    "levell" + LL: "level",
    "modell" + LL: "model",
    "signall" + LL: "signal",
    "totall" + LL: "total",
    "travell" + LL: "travel",
    "dialling": "dialing",
    "marvellous": "marvelous",
    # everything else
    "aluminium": "aluminum",
    "amongst": "among",
    "analogue": "analog",
    "artefact": "artifact",
    "cheque": "check",
    "draught": "draft",
    "enquir": "inquir",
    "grey(?!hound)": "gray",
    "judgement": "judgment",
    "learnt": "learned",
    "mould": "mold",
    "moustache": "mustache",
    "plough": "plow",
    "programme": "program",
    "sceptic": "skeptic",
    "smoulder": "smolder",
    "speciality": "specialty",
    "storey": "story",
    "sulphur": "sulfur",
    "towards": "toward",
    "whilst": "while",
}

# Each stem gets a named group, so a match says which entry found it without
# looking the text up again. Longest first, so that a stem added later cannot
# shadow a longer one it happens to be the start of.
GROUP = {f"s{n}": (pat, STEMS[pat])
         for n, pat in enumerate(sorted(STEMS, key=len, reverse=True))}
PATTERN = re.compile(
    "|".join(f"(?P<{name}>{pat})" for name, (pat, _) in GROUP.items()), re.I)


def match_case(found: str, replacement: str) -> str:
    """`replacement` in the case `found` was written in."""
    if found.isupper():
        return replacement.upper()
    if found[0].isupper():
        return replacement.capitalize()
    return replacement


def whole_word(line: str, at: int) -> str:
    """The whole word `line[at]` sits inside.

    A stem matches inside a word, so the match alone cannot say whether it
    landed in `SPECTRE` or in `RANGED_RECOLOUR_BYTES`. The word around it can.
    """
    start = at
    while start and (line[start - 1].isalnum() or line[start - 1] == "_"):
        start -= 1
    end = at
    while end < len(line) and (line[end].isalnum() or line[end] == "_"):
        end += 1
    return line[start:end]


def tracked(paths: list[str]) -> list[Path]:
    """Every file git tracks, narrowed to `paths` if any are given."""
    out = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z", *paths],
                         capture_output=True, text=True, check=True)
    return [ROOT / p for p in out.stdout.split("\0")
            if p and p not in SKIP]


def hits_in_text(text: str) -> list[tuple[int, str, str, str]]:
    """(line number, found, replacement, the line) for each match in `text`."""
    found = []
    for n, line in enumerate(text.splitlines(), 1):
        for m in PATTERN.finditer(line):
            word = m.group(0)
            if whole_word(line, m.start()) in GAME_WORDS:
                continue
            found.append((n, word, match_case(word, GROUP[m.lastgroup][1]),
                          line))
    return found


def hits(path: Path) -> list[tuple[int, str, str, str]]:
    """The same, for a file. A file that is not text holds no prose."""
    try:
        return hits_in_text(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
        return []  # binary, a submodule, or a path git knows and the tree lacks


def main(argv: list[str]) -> int:
    total = 0
    for path in tracked(argv):
        for n, word, fix, line in hits(path):
            total += 1
            print(f"{path.relative_to(ROOT)}:{n}: {word} -> {fix}")
            print(f"    {line.strip()}")
    if total:
        plural = "" if total == 1 else "s"
        print(f"\n{total} British spelling{plural}. This repository spells "
              f"American, in identifiers as well as prose.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
