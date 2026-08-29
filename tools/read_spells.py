"""Read the game's F3 "SPELL INFORMATION" screen.

The clue book shows, for each spell: which classes can cast it and at what
level, whether each learns it by training or from a scroll, its MP and nuore
cost, what it affects, and when it can be cast. That is the ground truth for
decoding the 80-byte spell record, and it is what the panel needs to show.

Layout, measured on 320x200 frames:

    y  4   spell name (left) and "SPELL INFORMATION" (right)
    y 28   "CLASS:    LEVEL:" header
    y 34   up to three class rows, 6px apart: name, level, and the source
           ("TRAINING" in yellow, "SCROLL" in blue)
    y 40   MP value, right-hand side
    y 46   NUORE value, right-hand side
    y 76   "AFFECTS:" and its value
    y 88   "WHEN:" and its value
"""

from __future__ import annotations

from pathlib import Path

import ocr

TITLE_ROW = 4
# The title bar carries the spell name on the left and "SPELL INFORMATION" on
# the right; the name is what identifies the screen.
TITLE_X = (0, 190)
CLASS_HEADER_ROW = 28
CLASS_ROW0, CLASS_PITCH, CLASS_ROWS = 34, 6, 3
MP_ROW, NUORE_ROW = 40, 46
COST_X_MIN = 200

# Column bounds within a class row. The MP and NUORE labels sit to the right of
# the class table and would otherwise be read as part of it.
NAME_X = (40, 102)
LEVEL_X = (103, 120)
SOURCE_X = (112, 190)
AFFECTS_ROW = 76
WHEN_ROW = 88

# "AFFECTS:" is gray and ends here; its value follows in a mix of blue (the
# quantifier or targeting phrase) and gray (the noun).
AFFECTS_VALUE_X = 94

# Colors on this screen. Gray is the ordinary text; the source column and the
# AFFECTS/WHEN values are color-coded, which is what makes them separable
# without knowing where one word ends and the next begins.
GRAY = "gray"
ocr.COLORS[GRAY] = lambda r, g, b: r > 150 and g > 150 and b > 150

CLASSES = ["MONK", "ALCHEMIST", "PALADIN", "MAGE", "DRUID", "MARKSMAN",
           "FIGHTER", "MERCHANT", "ROGUE"]
SOURCES = ["TRAINING", "SCROLL"]
AFFECTS = ["ALL VISIBLE MONSTERS", "ALL VISIBLE UNDEADS", "ONE MONSTER",
           "ONE CHARACTER", "ALL CHARACTERS", "ALL MONSTERS", "ONE INSECT",
           "ONE UNDEAD", "ALL UNDEADS", "ALL INSECTS", "CREATION",
           "ALL IN HAND TO HAND"]
# The gray half of the AFFECTS line: everything after the colored quantifier.
AFFECTS_NOUNS = [
    "VISIBLE MONSTERS", "VISIBLE UNDEADS", "MONSTERS", "MONSTER",
    "CHARACTERS", "CHARACTER", "UNDEADS", "UNDEAD", "INSECTS", "INSECT",
    "CREATION",
    "MONSTERS IN A 3X3 AREA", "MONSTERS IN A STRAIGHT LINE",
    "MONSTERS IN HAND TO HAND", "CHARACTERS IN HAND TO HAND",
]

WHEN = ["IN HAND TO HAND", "IN A STRAIGHT LINE", "IN A 3X3 AREA",
        "AT A DISTANCE", "OUT OF HAND TO HAND", "ANYTIME"]

# Labels whose text is fixed, used to teach the alphabet its letters.
FIXED_LABELS = [
    (CLASS_HEADER_ROW, GRAY, 0, "CLASS:LEVEL:"),
    (WHEN_ROW, GRAY, 0, "WHEN:"),
]


def read_mixed(alpha: ocr.Alphabet, frame: ocr.Frame, row: int,
               colors: dict[str, int]) -> str:
    """Read one line whose words are split across several ink colors.

    Each color gets its own left bound: the gray run has to start past the
    "AFFECTS:" label, while the colored run starts at the value itself and
    must not be clipped, or its first letter is lost.
    """
    cells = []
    for color, x_min in colors.items():
        cells.extend(frame.cells(row, color, x_min))
    cells.sort(key=lambda c: c[0])
    return "".join(alpha.by_bits.get(bits, "?") for _, bits in cells)


def learn_labels(alpha: ocr.Alphabet, frame: ocr.Frame) -> None:
    for row, color, x_min, text in FIXED_LABELS:
        alpha.learn(frame, row, color, text, x_min)


def learn_from(alpha: ocr.Alphabet, frame: ocr.Frame, row: int, color: str,
               vocabulary: list[str], x_min: int = 0,
               x_max: int | None = None) -> bool:
    """Teach the alphabet from a line whose text must be one of `vocabulary`."""
    reading = alpha.read(frame, row, color, x_min, x_max)
    if not reading or "?" not in reading:
        return False
    bare = {v.replace(" ", ""): v for v in vocabulary}
    hits = [b for b in bare
            if len(b) == len(reading)
            and all(r == "?" or r == c for r, c in zip(reading, b))]
    if len(hits) != 1:
        return False
    return alpha.learn(frame, row, color, hits[0], x_min, x_max)


def read_name(alpha: ocr.Alphabet, frame: ocr.Frame) -> str:
    return alpha.read(frame, TITLE_ROW, GRAY, *TITLE_X)


def learn_names(alpha: ocr.Alphabet, frames: list[ocr.Frame],
                names: list[str]) -> int:
    """Teach letters from the title bar, which must be one of the known names.

    Aligning by name rather than by position matters: the list walk can skip an
    entry when the page scrolls, and a positional mapping would then be wrong
    from that point on without any sign of it.
    """
    bare = {n.replace(" ", "").replace("'", ""): n for n in names}
    learned = 0
    for f in frames:
        reading = read_name(alpha, f)
        if not reading or "?" not in reading:
            continue
        hits = [b for b in bare
                if len(b) == len(reading)
                and all(r == "?" or r == c for r, c in zip(reading, b))]
        if len(hits) == 1 and alpha.learn(f, TITLE_ROW, GRAY, hits[0], *TITLE_X):
            learned += 1
    return learned


def build_alphabet(shots: list[Path], names: list[str] | None = None) -> ocr.Alphabet:
    """Digits from the monster screens, letters from these."""
    alpha = ocr.standard_alphabet()
    frames = [ocr.Frame(s) for s in shots]
    for f in frames:
        learn_labels(alpha, f)
    for _ in range(8):
        learned = 0
        for f in frames:
            for i in range(CLASS_ROWS):
                row = CLASS_ROW0 + i * CLASS_PITCH
                learned += learn_from(alpha, f, row, GRAY, CLASSES, *NAME_X)
                for color in ("yellow", "blue"):
                    learned += learn_from(alpha, f, row, color, SOURCES, *SOURCE_X)
            learned += learn_from(alpha, f, WHEN_ROW, "green", WHEN)
            # The AFFECTS value spans two colors, so it is learned per color
            # against the words that can appear in each.
            learned += learn_from(alpha, f, AFFECTS_ROW, GRAY,
                                  AFFECTS_NOUNS, AFFECTS_VALUE_X)
            learned += learn_from(alpha, f, AFFECTS_ROW, "blue",
                                  ["ALL", "ONE", "ALL VISIBLE", "ONE VISIBLE",
                                   "ALL IN A 3X3 AREA", "ALL IN HAND TO HAND",
                                   "ALL IN A STRAIGHT LINE"], 0)
        if names:
            learned += learn_names(alpha, frames, names)
        if not learned:
            break
    return alpha


def read_spell(frame: ocr.Frame, alpha: ocr.Alphabet) -> dict:
    out: dict = {"classes": [], "mp": None, "nuore": None,
                 "affects": None, "when": None}
    for i in range(CLASS_ROWS):
        row = CLASS_ROW0 + i * CLASS_PITCH
        name = alpha.read(frame, row, GRAY, *NAME_X)
        if name not in CLASSES:
            continue
        level = alpha.number(frame, row, GRAY, *LEVEL_X)
        source = None
        for color, label in (("yellow", "TRAINING"), ("blue", "SCROLL")):
            if alpha.read(frame, row, color, *SOURCE_X).startswith(label[:4]):
                source = label
        out["classes"].append({"class": name, "level": level, "source": source})
    out["mp"] = alpha.number(frame, MP_ROW, "yellow", COST_X_MIN)
    out["nuore"] = alpha.number(frame, NUORE_ROW, "yellow", COST_X_MIN)
    out["when"] = alpha.read(frame, WHEN_ROW, "green", 0) or None
    # "AFFECTS:" is gray, the quantifier ("ALL"/"ONE") is blue, and the rest is
    # gray again, so the value is assembled from the two colors.
    out["affects"] = read_mixed(
        alpha, frame, AFFECTS_ROW, {"blue": 0, GRAY: AFFECTS_VALUE_X}) or None
    return out
