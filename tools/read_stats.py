"""Read the game's F2 monster screen straight off a captured frame.

The twelve effect rows sit at a fixed pitch and their values are drawn in the
game's green, so IMMUNE and RESISTANT can be told apart by the width of the
green run alone, with no character recognition needed. That turns a screenful of
ground truth into three numbers per creature, cheaply enough to do all 72.

Geometry, measured from the captures (320x200 frames):
    row k of 12 occupies y = 94 + 6k .. +4
    values are drawn from x = 230 rightwards
    IMMUNE spans ~34px, RESISTANT ~53px
"""

from __future__ import annotations

from pathlib import Path

import labels as L
import pngutil

ROW0_Y = 94
ROW_PITCH = 6
ROW_HEIGHT = 5
VALUE_X = 230
RESISTANT_MIN_WIDTH = 45

NONE = "-"
IMMUNE, RESISTANT = L.EFFECT_VALUES  # the only two, and both are in the EXE


def _green(r: int, g: int, b: int) -> bool:
    return g > 60 and g > r * 2 and g > b * 2


def read_effects(path: str | Path) -> list[str]:
    """The twelve effect values, in the executable's label order."""
    w, h, px = pngutil.read(str(path))
    out = []
    for k in range(12):
        xs: list[int] = []
        for y in range(ROW0_Y + k * ROW_PITCH, ROW0_Y + k * ROW_PITCH + ROW_HEIGHT):
            if y >= h:
                continue
            row = y * w
            for x in range(VALUE_X, w):
                i = (row + x) * 3
                if _green(px[i], px[i + 1], px[i + 2]):
                    xs.append(x)
        if not xs:
            out.append(NONE)
        else:
            width = max(xs) - min(xs) + 1
            out.append(RESISTANT if width >= RESISTANT_MIN_WIDTH else IMMUNE)
    return out


if __name__ == "__main__":
    import sys

    from labels import EFFECTS

    for arg in sys.argv[1:]:
        print(arg)
        for name, value in zip(EFFECTS, read_effects(arg)):
            if value != NONE:
                print(f"    {name:<16} {value}")
