#!/usr/bin/env python3
"""Decode WORLD.DAT into JSON, driven by the section directory in REGISTER.EXE.

Runs once per copy of the game rather than per page load: the Makefile runs
it at build time, and the hosted cabinet runs this same file under pyodide in
the tab when a player brings their own copy. Either way the panel is built
from its output rather than reading WORLD.DAT itself.

Field naming policy: a field is given a real name only where its meaning was
confirmed against evidence (the prose descriptions, the creature families, a
monotonic difficulty progression, or a targeted immunity test). Everything
else keeps an `unknown_<offset>` name so that unverified guesses can never be
mistaken for facts. See README in tools/ for what is confirmed and how.
"""

from __future__ import annotations

import base64
import json
import sys
import re
import struct
from pathlib import Path

import labels as L
import markers
import sections as S

# --- text ------------------------------------------------------------------

text = L.text  # one stored string, in the game's charset; see labels.CHARSET


def reflow(lines: list[str]) -> str:
    """Join fixed-width lines back into prose.

    Lines are hard-wrapped at a fixed column with the remainder space-padded,
    so a single space at each join reconstructs the sentence.
    """
    return " ".join(line.strip() for line in lines if line.strip())


# --- walkthrough -----------------------------------------------------------

def extract_walkthrough(d: S.Directory) -> list[dict]:
    sec = d.rest(S.WALKTHROUGH)
    pages = []
    for p in range(sec.size // S.WALKTHROUGH_PAGE):
        base = sec.offset + p * S.WALKTHROUGH_PAGE
        rows = [
            text(d.world[base + r * S.WALKTHROUGH_COLS:
                         base + (r + 1) * S.WALKTHROUGH_COLS])
            for r in range(S.WALKTHROUGH_ROWS)
        ]
        pages.append({"page": p + 1, "rows": rows})
    return pages


def walkthrough_sections(pages: list[dict]) -> list[dict]:
    """The `NN. LOCATION` headings, for a navigation index."""
    out = []
    for pg in pages:
        for row in pg["rows"]:
            s = row.strip()
            head = s.split(".", 1)
            if len(head) == 2 and head[0].isdigit() and head[1].startswith(" "):
                out.append({"n": int(head[0]), "title": head[1].strip(),
                            "page": pg["page"]})
    return out


# --- fixed-width name tables ----------------------------------------------

def fixed_width(buf: bytes, width: int) -> list[str]:
    return [text(buf[i:i + width]).strip()
            for i in range(0, len(buf) - width + 1, width)]


def extract_maps(d: S.Directory) -> list[str]:
    names = fixed_width(d[S.MAP_NAMES_20].slice(d.world), 20)
    return [n for n in names if n]


# 25 visible characters plus a NUL terminator. Slot 0 is a column ruler
# ("1234567890123456789012345") the developers left in the data; it is kept so
# the indices here line up with the game's own, and skipped by the panel.
LEGEND_RECORD = 26
LEGEND_RULER = "1234567890123456789012345"


# The clue book's maps are drawn pictures, not tile grids: the 37 x 64 table
# at 0x8CDDE holds tile-placement coordinates into a graphics bank, so there is
# nothing to decode into cells. The pages are captured from the running game
# instead (tools/capture_maps.js) and indexed by the title read off each frame.
# Each page as its tile grid plus the handful of 8x8 tiles it is drawn with:
# about 2 kB a page, against 6 kB for a PNG of the same thing, and the panel
# draws it at whatever size it has rather than scaling a bitmap.
_MAP_PAGES = ROOT / "data" / "map_pages.json" if (ROOT := Path(__file__).resolve().parent.parent) else None
MAP_PAGES = json.loads(_MAP_PAGES.read_text()) if _MAP_PAGES and _MAP_PAGES.exists() else []

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pack_maps import WALKED_LINKS as _WALKED_LINKS  # noqa: E402
import links as K  # noqa: E402

def extract_legend(d: S.Directory) -> list[str]:
    """The map legend labels, which stop well short of the section's end.

    The Restoration directory entry runs to the start of the next one, but the
    labels themselves fill only the first 138 records; after that comes the
    spell-text index and then the descriptions. Striding 26 bytes over those
    produces convincing-looking garbage ("To a Single Player.", "Of Cold
    Damage. Be Caref"), so the run is cut at the first record that is not a
    clean NUL-terminated label.
    """
    raw = d.rest(S.LEGEND).slice(d.world)
    labels = []
    for i in range(len(raw) // LEGEND_RECORD):
        rec = raw[i * LEGEND_RECORD:(i + 1) * LEGEND_RECORD]
        end = rec.find(b"\x00")
        if end < 0 or any(c and not (32 <= c < 127) for c in rec[:end]) \
                or any(rec[end:]):
            break
        labels.append(text(rec[:end]))
    return labels


def build(game_dir: str | Path = "game", out_dir: str | Path = "data") -> dict:
    d = S.load(game_dir)
    missing = L.verify(d.exe)
    assert not missing, f"EXE is missing expected labels: {missing}"

    pages = extract_walkthrough(d)
    payload = {
        "walkthrough": pages,
        "walkthrough_index": walkthrough_sections(pages),
        "maps": extract_maps(d),
        "legend": extract_legend(d),
        "map_pages": MAP_PAGES,
        "map_marks": markers.by_page(d.world, MAP_PAGES),
        "map_unplaced": markers.unplaced(d.world, MAP_PAGES),
        # Where each door goes, keyed "<map>|<legend line>" so the panel can
        # look a legend line up directly. Decoded: section 28 places the
        # doors and DS:0xBA95 says where each one lands (`tools/links.py`).
        # The walked links are merged over the top for what the decode does
        # not reach: Saxon's ship is a script cell rather than a door, so no
        # door record carries its destination.
        "map_links": {**K.by_label(d, MAP_PAGES,
                                   markers.by_page(d.world, MAP_PAGES)),
                      **{f"{a}|{b}": v for (a, b), v in _WALKED_LINKS.items()}},
        "labels": {
            "effects": L.EFFECTS,
            "monster_stats": L.MONSTER_STATS,
            "special_attacks": L.SPECIAL_ATTACKS,
            "item_categories": L.ITEM_CATEGORIES,
            "class_tiers": [list(t) for t in L.CLASS_TIERS],
            "skill_ratings": L.SKILL_RATINGS,
            "spell_affects": L.SPELL_AFFECTS,
            "spell_when": L.SPELL_WHEN,
            "menu": L.RESTORATION_MENU,
        },
    }


    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for key, value in payload.items():
        (out / f"{key}.json").write_text(json.dumps(value, indent=1))
    (out / "restoration.json").write_text(json.dumps(payload, separators=(",", ":")))
    return payload


if __name__ == "__main__":
    import sys

    p = build(sys.argv[1] if len(sys.argv) > 1 else "game")
    print(f"walkthrough   {len(p['walkthrough']):>4} pages, "
          f"{len(p['walkthrough_index'])} sections")
    print(f"maps          {len(p['maps']):>4}")
    print(f"legend        {len(p['legend']):>4}")
    print(f"\nwrote data/*.json")
