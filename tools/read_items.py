"""Read the game's F5 "INVENTORY ITEMS" detail screens.

The F5 section is two levels deep, unlike F2 and F3: eight categories, then the
items within one. Each item's page is the ground truth for decoding the 58-byte
item record, and it also tells us which fields the game itself thinks matter --
armor prints ABSORPTION where a potion prints RESTORES.

That is why nothing here is keyed by row. Which rows carry text, and what those
rows mean, varies by item; the reader finds the rows that have text and splits
each into its gray caption and its colored value. The game colors a value by
what it is (a figure in yellow, an absorption in red, a container in blue, a
qualifying phrase in green) and that is what lets caption and value be told
apart without knowing where the caption ends.

    y   4  item name (left, white) and its category (right, white)
    y  30..144, every 6px   the body rows, caption then value
"""

from __future__ import annotations

import glob
import re
from pathlib import Path

import ocr

TITLE_ROW = 4
# The title bar carries the name on the left and the category on the right,
# both in white. Where they meet moves with the length of each, so they are
# split at the widest gap on the row rather than at a fixed column.
TITLE_SPLIT_GAP = 6

# Text rows are found rather than assumed. The pages are on a 6px grid but the
# body does not start on a multiple of it, and reading one pixel off slices
# through the glyphs, which does not fail loudly: it quietly teaches the
# alphabet nonsense. So each frame reports where its own text bands begin.
BODY_TOP, BODY_BOTTOM = 30, 145

WHITE = "white"
GRAY = "gray"
ocr.COLORS[WHITE] = lambda r, g, b: r > 185 and g > 185 and b > 185
ocr.COLORS[GRAY] = lambda r, g, b: 130 < r < 190 and 130 < g < 190 and 130 < b < 190

VALUE_INKS = ("yellow", "red", "blue", "green")

CATEGORIES = ["ARMOR / RINGS", "ATTRIBUTE ENHANCERS", "JEWELS/ORES/UNIQUE ITEMS",
              "MAGIC SCROLLS", "POTIONS / MAGIC FOOD", "SUPPLIES",
              "TRANSPORTATIONS", "WEAPONS"]
CONTAINERS = ["CHARACTER PANEL", "ANY PANEL", "BACKPACK", "BOX", "BAG"]

# The captions these pages print, exactly as they appear in the executable's
# label run at 0x2AB60, with their punctuation, which differs by field and is
# part of what is on screen. Generating both ":" and "-" forms instead would
# make every caption ambiguous against itself and nothing would ever be learned.
CAPTIONS = ["BASE VALUE:", "WEIGHT:", "ABSORPTION-", "FITS IN-", "ADDS:",
            "2-HANDED:", "SKILL:", "DURATION-", "HEALTH-", "MAGIC-",
            "USES:", "TIME:", "PROTECTIONS:", "RESTORES-", "DAMAGE:",
            "PROTECTS-", "CURES-"]

# The item's icon is drawn to the left of the captions and its gray pixels read
# as glyphs, so caption reads start past it.
CAPTION_X_MIN = 88


def body_rows(frame) -> list[int]:
    """The y of each text band in the body, by finding where ink starts.

    A band is a row that has ink while the row above it has none: the top of
    a line of glyphs. Cheaper and steadier than assuming a grid.
    """
    inked = []
    for y in range(BODY_TOP, BODY_BOTTOM):
        # Scan only the text column: the item's icon sits to the left and
        # would otherwise register as a text band of its own.
        hit = any(frame._hit(x, y, ink)
                  for ink in (GRAY, *VALUE_INKS)
                  for x in range(CAPTION_X_MIN, frame.w, 2))
        inked.append(hit)
    rows = []
    for i, hit in enumerate(inked):
        if hit and not (i and inked[i - 1]):
            rows.append(BODY_TOP + i)
    return rows


def title_split(frame) -> int:
    """The x at which the name ends and the category begins."""
    cells = frame.cells(TITLE_ROW, WHITE)
    if len(cells) < 2:
        return 320
    widest, at = 0, 320
    for (x0, bits), (x1, _) in zip(cells, cells[1:]):
        gap = x1 - (x0 + len(bits) // 5)
        if gap > widest:
            widest, at = gap, x1
    return at if widest >= TITLE_SPLIT_GAP else 320


def learn_line(alpha, frame, row, color, vocabulary, x_min=0, x_max=None):
    """Teach the alphabet from a line whose text must be one of `vocabulary`.

    A reading with unknown glyphs still constrains the answer: only one entry
    can have that length with those letters in those places. When exactly one
    fits, every unknown glyph on the line is identified at once.
    """
    reading = alpha.read(frame, row, color, x_min, x_max)
    if not reading or "?" not in reading:
        return False
    bare = {v.replace(" ", "").replace("'", ""): v for v in vocabulary}
    hits = [b for b in bare
            if len(b) == len(reading)
            and all(r == "?" or r == c for r, c in zip(reading, b))]
    if len(hits) != 1:
        return False
    try:
        return alpha.learn(frame, row, color, hits[0], x_min, x_max)
    except ValueError:
        # The single fit was still the wrong one: it wants to give a glyph a
        # second meaning. Refuse it rather than corrupt the alphabet.
        return False


def _learn_decimal_point(alpha, frame) -> bool:
    """The weight row's only non-digit glyph is the decimal point.

    Nothing else on these screens prints one, so there is no vocabulary to
    match against, but its position among digits identifies it outright. The
    game drops the leading zero, so ".5" is a legitimate reading.
    """
    for row in body_rows(frame):
        reading = alpha.read(frame, row, "yellow")
        if re.fullmatch(r"\d*\?\d+", reading or ""):
            return alpha.learn(frame, row, "yellow", reading.replace("?", "."))
    return False


def _container_phrases() -> list[str]:
    """Every combination the FITS IN line can print, in the game's own order."""
    out = []
    for n in range(1, len(CONTAINERS) + 1):
        for i in range(len(CONTAINERS) - n + 1):
            out.append(" ".join(CONTAINERS[i:i + n]))
    return out


def build_alphabet(shots, vocabulary):
    """Grow an alphabet from lines whose text is already known.

    Same trick as the spell reader: the item names come out of the record, so
    the title bars are a labeled training set and no glyph has to be guessed.
    Captions, categories and container lists are learned the same way from
    their own fixed vocabularies. Several passes, because each glyph learned
    can unlock a line that was ambiguous while one of its letters was unknown.
    """
    alpha = ocr.standard_alphabet()
    frames = [ocr.Frame(p) for p in shots]
    for _ in range(6):
        learned = 0
        for frame in frames:
            split = title_split(frame)
            learned += learn_line(alpha, frame, TITLE_ROW, WHITE, vocabulary, 0, split)
            learned += learn_line(alpha, frame, TITLE_ROW, WHITE, CATEGORIES, split)
            for row in body_rows(frame):
                learned += learn_line(alpha, frame, row, GRAY, CAPTIONS, CAPTION_X_MIN)
                learned += learn_line(alpha, frame, row, "blue", _container_phrases())
            learned += _learn_decimal_point(alpha, frame)
        if not learned:
            break
    return alpha


def read_name(alpha, frame) -> str:
    return alpha.read(frame, TITLE_ROW, WHITE, 0, title_split(frame)).strip()


def read_row(frame, alpha, row: int) -> tuple[str, str]:
    """One body row, split into its gray caption and its colored value."""
    caption = alpha.read(frame, row, GRAY, CAPTION_X_MIN).strip()
    cells = []
    for ink in VALUE_INKS:
        # Same left bound as the caption: the icon has colored pixels too, and
        # they would otherwise be read as leading glyphs of the value.
        cells.extend(frame.cells(row, ink, CAPTION_X_MIN))
    cells.sort(key=lambda c: c[0])
    value = "".join(alpha.by_bits.get(bits, "?") for _, bits in cells)
    return caption, value


def read_item(frame, alpha) -> dict:
    split = title_split(frame)
    out = {"name": alpha.read(frame, TITLE_ROW, WHITE, 0, split).strip(),
           "category": alpha.read(frame, TITLE_ROW, WHITE, split).strip(),
           "fields": {}}
    for row in body_rows(frame):
        caption, value = read_row(frame, alpha, row)
        key = caption.rstrip(":-").strip()
        if key:
            # A caption with no value is the game saying the field applies to
            # this item but is empty; that is information too, so keep it.
            out["fields"][key] = value or None
    return out


def parse_number(text: str | None) -> float | None:
    """The game prints thousands separators, and drops the leading zero: ".5"."""
    if not text:
        return None
    m = re.search(r"\d*\.\d+|\d+", text.replace(" ", "").replace(",", ""))
    return float(m.group()) if m else None


def read_all(shot_dir: str = "tmp/items", vocabulary=None) -> dict:
    shots = [Path(p) for p in
             sorted(glob.glob(f"{shot_dir}/c[0-9]i[0-9][0-9][0-9].png"))]
    alpha = build_alphabet(shots, vocabulary or [])
    out = {}
    for shot in shots:
        item = read_item(ocr.Frame(shot), alpha)
        if item["name"]:
            out.setdefault(item["name"], item)
    return out
