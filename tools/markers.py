"""Which legend label belongs to which gold marker on a map page.

The clue book prints a map with gold markers on it and a legend beside it, but
nothing on the page says which marker is which line. The marker table does.

`0x3D34FD` holds 207 eight-byte records, one per legend line, and the three
fields that matter are positions in exactly the coordinate system the map data
itself uses (see docs/map.md):

    field 1 = level * 40 + cell     a level's row is 40 cells wide
    field 2 = area  * 24 + row      an area is 24 bands
    field 3 = the caption's index in the label table

So a record names its own page, as (area, level), and its own square on it,
`col = cell - 3` for the three columns the page does not print. That replaces
the blanking rounds that attributed 17 pages by experiment: the records place
**35 of the 37** directly, and every group of records falls on exactly one
(area, level), which is what makes the reading trustworthy.

The labels at `0x3D3CCD` are NUL-terminated and packed, not the fixed 25-byte
fields they look like at the start, which is why a naive reading drifts after
about 130 of them.

**The caption is not the record's own position in the table**, which is the
trap: reading it that way produces plausible-looking captions that are simply
the wrong ones, and leaves fifteen pages looking as though the game had no
captions for them. Field 3 is the index, it runs 1..137 against 138 labels, and
markers share captions: KINGDOM OF BARIAG is a marker on several maps.
Verified against the game: clicking a marker prints its caption in the title
bar, and all six of ELFIN CITY's agree, on a page that the index reading had
left blank.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path

from registry import map_registry

MARKERS = 0x3D34FD
RECORD = 8
CELLS = 40          # cells across one level's row
BANDS = 24          # bands in one area
COL0 = 3            # first cell the page prints


def read_markers(world: bytes) -> list[dict]:
    """Every marker record, decoded, in table order.

    The table's end is not recorded anywhere, so it is found by shape: the
    bytes after it are the label strings, which decode as absurd coordinates.
    """
    out = []
    for i in range(1, 250):                      # record 0 is a zero sentinel
        group, f1, f2, f3 = struct.unpack_from("<4H", world, MARKERS + i * RECORD)
        if not (0 < group < 256 and f1 < 900 and f2 < 200):
            break
        level, cell = divmod(f1, CELLS)
        area, row = divmod(f2, BANDS)
        out.append({"index": i, "group": group, "area": area, "level": level,
                    "cell": cell, "col": cell - COL0, "row": row,
                    "field3": f3})
    return out


def read_labels(world: bytes, at: int = 0x3D3CCD, limit: int = 260) -> list[str]:
    """The legend lines: packed NUL-terminated strings, one per marker record."""
    out, i = [], at
    while len(out) < limit:
        end = world.index(b"\0", i)
        text = world[i:end].decode("latin1")
        if text and not all(32 <= ord(c) < 127 for c in text):
            break
        # The game writes an apostrophe as `~`, the same substitution the rest
        # of the text extraction makes; without it these strings compare
        # unequal to every other reading of the same label.
        out.append(text.strip().replace("~", "'"))
        i = end + 1
    return out


def by_page(world: bytes, pages) -> dict[str, list[dict]]:
    """Markers grouped by page title, numbered in reading order.

    Numbered top-left to bottom-right rather than in table order, because the
    number exists to get the eye from a mark on the map to a line in the list.
    A marker outside the printed columns keeps its number and its place in the
    list, since it is a real legend line, but has nothing to draw a badge on.
    """
    slot = {(p["area"], p["level"]): p["title"] for p in pages}
    size = {p["title"]: (p["cols"], p["rows"]) for p in pages}
    labels = read_labels(world)

    found: dict[str, list[dict]] = {}
    for m in read_markers(world):
        title = slot.get((m["area"], m["level"]))
        if title is None:
            continue
        cols, rows = size[title]
        found.setdefault(title, []).append({
            "cell": m["cell"],
            "col": m["col"],
            "row": m["row"],
            "label": labels[m["field3"]] if m["field3"] < len(labels) else "",
            # The page now draws the whole 40-cell row, so a marker is hidden
            # only if its row falls outside the band, not because it stood in
            # one of the three columns the clue book cropped.
            "shown": 0 <= m["cell"] < cols and 0 <= m["row"] < rows,
        })

    out = {}
    for title, marks in found.items():
        marks.sort(key=lambda m: (m["row"], m["col"]))
        for n, m in enumerate(marks, 1):
            m["n"] = n
        out[title] = marks
    return out


def unplaced(world: bytes, pages) -> list[dict]:
    """Labels belonging to a map the panel cannot draw.

    Every label has a page, which the record says, and the registry names
    every map, so this is no longer "the book does not print it". It is the
    narrower statement that we cannot yet draw that map, which is why each
    entry carries the map's name.
    """
    slot = {(p["area"], p["level"]) for p in pages}
    names = map_registry(world)
    labels = read_labels(world)
    out, seen = [], set()
    for m in read_markers(world):
        label = labels[m["field3"]] if m["field3"] < len(labels) else ""
        key = (label, m["area"], m["level"])
        if label and (m["area"], m["level"]) not in slot and key not in seen:
            seen.add(key)
            out.append({"label": label, "area": m["area"], "level": m["level"],
                        "map": names.get((m["area"], m["level"]))})
    return out


if __name__ == "__main__":
    world = Path("game/WORLD.DAT").read_bytes()
    pages = json.loads(Path("data/map_pages.json").read_text())
    marks = by_page(world, pages)
    named = [t for t, ms in marks.items() if all(m["label"] for m in ms)]
    print(f"{len(marks)}/{len(pages)} pages carry markers, "
          f"{len(named)} with a caption on every one")
    for title in sorted(marks):
        ms = marks[title]
        have = sum(1 for m in ms if m["label"])
        off = sum(1 for m in ms if not m["shown"])
        print(f"  {title:28} {len(ms):2} markers, {have:2} named"
              + (f", {off} off the printed page" if off else ""))
