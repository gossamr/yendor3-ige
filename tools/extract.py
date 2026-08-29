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
import pictures as P
import pngutil
import sections as S
import tiles

# --- text ------------------------------------------------------------------

text = L.text  # one stored string, in the game's charset; see labels.CHARSET


def reflow(lines: list[str]) -> str:
    """Join fixed-width lines back into prose.

    Lines are hard-wrapped at a fixed column with the remainder space-padded,
    so a single space at each join reconstructs the sentence.
    """
    return " ".join(line.strip() for line in lines if line.strip())


# --- monster art -----------------------------------------------------------

# The picture a creature is drawn with. tools/pictures.py has the file's shape;
# what is decided here is which of the ten pictures to show and how to store it.
#
# The first of the ten is the creature standing still. The other nine are the
# rest of the walk cycle, the attack and the death, which a still picture has
# no use for.
MONSTER_FRAME = 0
# Section 12's first palette. The map screen draws with it too. Drawing these
# pictures with it reproduces the clue book's own monster screens pixel for
# pixel on 64 of the 71 creatures the game lists; on the other seven the
# capture caught the page mid-refresh, with the top of the creature on one
# step of the walk cycle and the bottom on the next. tools/verify_monsters.py
# measures this.
MONSTER_PALETTE = 0


def monster_art(d: S.Directory, pics: bytes, enemies: list[dict]) -> dict[str, dict]:
    """name -> a PNG of the creature, cropped to its own pixels.

    Each picture carries a palette of just the colors it uses, which is what
    keeps 71 of them inside a quarter of a megabyte. Index 0 is the
    transparent one; the game's own transparent value, 0xFF, would need a
    256-entry alpha table to say so.
    """
    runs = P.read_runs(d.exe, len(pics))
    palette = tiles.palette(d, MONSTER_PALETTE)
    out = {}
    for e in enemies:
        # The game omits the placeholder record from its own list and never
        # draws it, so the picture its sprite field points at is not a
        # creature: it is the scenery that run 2 starts with.
        if not e["listed"]:
            continue
        run, raw = P.creature(
            pics, runs, e["sprite"], e["masks"]["w96"], e["masks"]["w98"],
            {s["from"]: s["to"] for s in e["recolour"]}, MONSTER_FRAME)
        w, h, crop = _cropped(raw, run.width)
        png = _indexed(w, h, crop, palette)
        out[e["name"]] = _png_entry(w, h, png)
    return out


# The projectile run. Each picture holds the shot at the four angles it can
# travel at, so it is shown whole rather than cut up: which of the four the
# game picks is a property of the shot, not of the creature.
PROJECTILE_RUN = 1


def projectile_art(d: S.Directory, pics: bytes, enemies: list[dict]) -> dict[str, dict]:
    """picture number -> a PNG of the shot, for every picture a creature fires.

    Keyed by the picture rather than by the creature because seven pictures
    serve all thirteen shooters: three of them fire the same arrows.
    """
    runs = P.read_runs(d.exe, len(pics))
    run = runs[PROJECTILE_RUN]
    palette = tiles.palette(d, MONSTER_PALETTE)
    out = {}
    for e in enemies:
        shot = e["ranged"]
        if not shot or str(shot["picture"]) in out:
            continue
        raw = P.recoloured(P.picture(pics, run, shot["picture"]),
                           {s["from"]: s["to"] for s in shot["recolour"]})
        w, h, crop = _cropped(raw, run.width)
        out[str(shot["picture"])] = _png_entry(w, h, _indexed(w, h, crop, palette))
    return out


def _cropped(raw: bytes, width: int) -> tuple[int, int, bytes]:
    x0, y0, x1, y1 = P.bounds(raw, width)
    return x1 - x0, y1 - y0, b"".join(raw[y * width + x0:y * width + x1]
                                      for y in range(y0, y1))


def _indexed(w: int, h: int, crop: bytes, palette: list[bytes]) -> bytes:
    """A PNG carrying only the colors this picture uses, transparent at 0."""
    used = sorted(set(crop) - {P.TRANSPARENT})
    slot = {v: i + 1 for i, v in enumerate(used)}
    return pngutil.encode_indexed(
        w, h, bytes(slot.get(v, 0) for v in crop),
        [b"\x00\x00\x00"] + [palette[v] for v in used], transparent=0)


def _png_entry(w: int, h: int, png: bytes) -> dict:
    return {"width": w, "height": h,
            "src": "data:image/png;base64," + base64.b64encode(png).decode()}


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
    pics = (Path(game_dir) / "PICTURES.VGA").read_bytes()

    pages = extract_walkthrough(d)
    payload = {
        "monster_art": monster_art(d, pics, enemies),
        "projectile_art": projectile_art(d, pics, enemies),
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
