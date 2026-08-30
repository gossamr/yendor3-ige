"""Read the game's bitmap font off captured frames.

The stat screens draw text in a fixed 6-pixel advance with 5-pixel-tall glyphs,
and each field has its own color: yellow for the reward figures, red for the
combat statistics, green for immunities, blue for the special attacks. That is
enough structure to segment characters reliably; identifying them is then a
matter of matching against templates lifted from screens whose text we already
know.

Templates are bootstrapped from monsters whose values were confirmed by hand
against the game, so the alphabet is derived from the game itself rather than
transcribed.
"""

from __future__ import annotations

from pathlib import Path

import pngutil

GLYPH_H = 5

# Where each field sits. y is the first row of the 5-pixel band.
REWARD_ROWS = {"experience": 16, "gold": 22, "food": 28, "nuore": 34}
STAT_ROWS = {
    "health": 46, "accuracy": 52, "dexterity": 58, "absorption": 64,
    "damage": 70, "ranged_accuracy": 76, "ranged_damage": 82,
}
# The effect rows hold one of two words rather than a figure, so
# tools/read_stats.py reads them by the width of the green run instead.
EFFECT_ROW0, EFFECT_PITCH = 94, 6
EFFECT_ROWS = 12          # labels.EFFECTS, top to bottom
SPECIAL_ATTACK_ROW = 169

# Values are drawn in the right-hand column; the monster portrait fills the
# left of the screen and can contain pixels of the same ink colors, so reads
# start well clear of it.
VALUE_X_MIN = 200

# The font is proportional ("1" is three pixels wide where "7" is five) so
# characters are separated by blank columns rather than a fixed advance. Each
# field has its own ink color, which is what keeps the value text apart from
# the gray label beside it.
COLORS = {
    "yellow": lambda r, g, b: r > 200 and g > 180 and b < 100,
    "red":    lambda r, g, b: r > 140 and g < 60 and b < 60,
    "blue":   lambda r, g, b: b > 150 and r < 120 and g < 120,
    "green":  lambda r, g, b: g > 90 and r < 60 and b < 60,
}


class Frame:
    def __init__(self, path: str | Path):
        self.w, self.h, self.px = pngutil.read(str(path))

    def _hit(self, x: int, y: int, color: str) -> bool:
        i = (y * self.w + x) * 3
        return COLORS[color](self.px[i], self.px[i + 1], self.px[i + 2])

    def cells(self, row: int, color: str, x_min: int = 0,
              gap: int = 0, x_max: int | None = None) -> list[tuple[int, str]]:
        """Segment one text band into glyphs, splitting on blank columns.

        Returns (x, bitmap) per glyph, the bitmap being rows of '#' and '.'
        joined by '/', so its width is part of its identity. Characters are
        one blank column apart, and no glyph in this font has a fully blank
        interior column, so splitting on any gap is safe.
        """
        rows = range(row, min(row + GLYPH_H, self.h))
        inked = [any(self._hit(x, y, color) for y in rows)
                 for x in range(self.w)]
        out, run_start, blanks = [], None, 0
        limit = self.w if x_max is None else min(self.w, x_max)
        for x in range(x_min, limit):
            if inked[x]:
                if run_start is None:
                    run_start = x
                blanks = 0
            elif run_start is not None:
                blanks += 1
                if blanks > gap:
                    out.append((run_start, self._bitmap(run_start, x - blanks, row, color)))
                    run_start = None
        if run_start is not None:
            out.append((run_start, self._bitmap(run_start, limit - 1, row, color)))
        return out

    def _bitmap(self, x0: int, x1: int, row: int, color: str) -> str:
        return "/".join(
            "".join("#" if self._hit(x, row + dy, color) else "."
                    for x in range(x0, x1 + 1))
            for dy in range(GLYPH_H))


class Alphabet:
    """Glyph bitmap -> character, learned from screens with known text."""

    def __init__(self) -> None:
        self.by_bits: dict[str, str] = {}

    def learn(self, frame: Frame, row: int, color: str, text: str,
              x_min: int = 0, x_max: int | None = None) -> bool:
        cells = frame.cells(row, color, x_min, x_max=x_max)
        if len(cells) != len(text):
            return False
        for (_, bits), ch in zip(cells, text):
            known = self.by_bits.get(bits)
            if known is not None and known != ch:
                raise ValueError(f"glyph maps to both {known!r} and {ch!r}")
            self.by_bits[bits] = ch
        return True

    def read(self, frame: Frame, row: int, color: str, x_min: int = 0,
             x_max: int | None = None) -> str:
        return "".join(self.by_bits.get(bits, "?")
                       for _, bits in frame.cells(row, color, x_min, x_max=x_max))

    def number(self, frame: Frame, row: int, color: str, x_min: int = 0,
               x_max: int | None = None):
        """A reward or stat figure; None when the field is blank."""
        text = self.read(frame, row, color, x_min, x_max).replace(",", "").strip()
        if not text:
            return None
        return int(text) if text.isdigit() else text


# Ground truth for bootstrapping: three monsters whose screens were read by
# hand against the running game. Between them they cover every digit and the
# thousands separator. Identifiers are the frame's index in the game's
# alphabetical list, which is how capture_monsters.js names its output.
BOOTSTRAP = {
    "m00": {  # ACOKNIGHT
        ("experience", "yellow"): "1,000",
        ("gold", "yellow"): "3,000",
        ("food", "yellow"): "4",
        ("nuore", "yellow"): "40",
        ("health", "red"): "175",
        ("accuracy", "red"): "110",
        ("dexterity", "red"): "115",
        ("absorption", "red"): "48",
        ("damage", "red"): "87",
    },
    "m01": {  # ALLIGATOR
        ("experience", "yellow"): "1,100",
        ("gold", "yellow"): "1,200",
        ("nuore", "yellow"): "40",
        ("health", "red"): "165",
        ("accuracy", "red"): "142",
        ("dexterity", "red"): "134",
        ("absorption", "red"): "71",
        ("damage", "red"): "145",
    },
    "m05": {  # BLAZIOS, supplies the digit 9
        ("health", "red"): "2900",
        ("accuracy", "red"): "235",
        ("dexterity", "red"): "260",
        ("absorption", "red"): "165",
        ("damage", "red"): "390",
    },
}

ROWS = {**REWARD_ROWS, **STAT_ROWS}


# The bootstrap frames are also kept under these names in OBSERVED, which
# does not ship. With them present, no capture run is required to build the
# alphabet.
FIXTURE_NAMES = {"m00": "acoknight", "m01": "alligator", "m05": "blazios"}
OBSERVED = Path(__file__).resolve().parent.parent / "observed"


def bootstrap_frame(shot: str, shot_dir: str | Path = "tmp/monsters") -> Path:
    """Returns the capture in shot_dir if there is one, else the kept frame."""
    for path in (Path(shot_dir) / f"{shot}.png",
                 OBSERVED / f"{FIXTURE_NAMES[shot]}.png"):
        if path.exists():
            return path
    raise FileNotFoundError(
        f"no capture of {FIXTURE_NAMES[shot]} in {shot_dir}; "
        "run tools/capture_monsters.js")


def standard_alphabet(shot_dir: str | Path = "tmp/monsters") -> Alphabet:
    alpha = Alphabet()
    for shot, fields in BOOTSTRAP.items():
        frame = Frame(bootstrap_frame(shot, shot_dir))
        for (field, color), text in fields.items():
            if not alpha.learn(frame, ROWS[field], color, text, VALUE_X_MIN):
                raise ValueError(
                    f"{shot} {field}: glyph count does not match {text!r}")
    return alpha


def read_screen(frame: Frame, alpha: Alphabet) -> dict:
    out = {}
    for field, row in REWARD_ROWS.items():
        out[field] = alpha.number(frame, row, "yellow", VALUE_X_MIN)
    for field, row in STAT_ROWS.items():
        out[field] = alpha.number(frame, row, "red", VALUE_X_MIN)
    return out
