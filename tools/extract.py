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

import items as I
import labels as L
import levels as LV
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


# --- items -----------------------------------------------------------------
#
# 631 records of 58 bytes: 19 bytes of fields then three 13-byte name fields, a
# name running across all three ("BROKEN" + "BO STICK" is one item).
#
# The decoding lives in `tools/items.py`, which reads the record, the three
# properties tables, the effects table and the six category lists in
# REGISTER.EXE. What that module returns for an item is exactly the set of rows
# the game's own F5 page prints for it, so the captures below are the check on
# the decode rather than its source.
ITEM_BASE = 0x083EE8
ITEM_RECORD = I.RECORD
ITEM_FIELD_BYTES = I.FIELD_BYTES
ITEM_NAME_LEN = I.NAME_LEN
ITEM_NAME_FIELDS = I.NAME_FIELDS

# Every row of an F5 page is decoded. The captures are the check, in
# tests/test_extract.py.

# The clue book files items under eight categories, in this order. Six of them
# are lists, and their contents come out of REGISTER.EXE; the other two are
# pages of their own: ATTRIBUTE ENHANCERS is a page of rules and
# TRANSPORTATIONS is three things that are not items at all.
ITEM_CATEGORIES = L.ITEM_CATEGORIES

# Enhancement runs to +10, so the digits are not always one: `\d` alone left
# the nine +10 items unmatched, which both leaked them into the list as items
# in their own right and hid them from the variant table.
#
# The optional space is for `RUBY MORNING STAR + 2`, which the game's own data
# spells with a stray space. Without it that single entry stayed outside its
# own series, which showed up as a hole between +1 and +3 exactly where its
# value belongs. How far a series runs is per item (that weapon stops at +8,
# the nine longest reach +10), so the fold walks to MAX_PLUS rather than to
# any one item's ceiling.
PLUS = re.compile(r"^(.*?) \+ ?(\d+)$")
MAX_PLUS = 10


def item_name(rec: bytes) -> str:
    return I.name(rec)


def extract_items(d: S.Directory) -> list[dict]:
    """Every item, with the rows its clue-book page prints.

    An item's category is the list it appears in, and its fields are what the
    F5 renderers would print for it, so an item the book never indexes still
    gets its value, weight and where it fits, and the 461 records the capture
    never reached are no longer blank.
    """
    items = I.Items(d)
    category_of = {}
    for category, ids in items.categories().items():
        for item_id in ids:
            category_of[item_id] = category

    rows = []
    for item_id, rec in enumerate(items.records, 1):
        name = items.names[item_id - 1]
        if not name:
            continue
        page = items.page(item_id)
        rows.append({
            "id": item_id,
            "name": name,
            "value": page["base value"],
            "weight": page["weight"],
            "absorption": page.get("absorption"),
            # A magic scroll names the spell it teaches; the F5 page does not
            # print it, so it is a key of its own rather than a field.
            "spell": items.scroll_spell(rec),
            # Which slot it occupies; the F5 page has no such row either.
            "slot": items.equip_slot(rec),
            "category": category_of.get(item_id),
            "listed": item_id in category_of,
            # Value, weight and absorption are their own keys on the item, so
            # the page's copy of them would be printed twice.
            "fields": {k: v for k, v in page.items()
                       if k not in ("base value", "weight", "absorption")},
        })

    # The book lists a base item once and puts its enchanted forms behind a
    # +0..+10 selector, so fold "CLOTHES +1" into CLOTHES rather than listing it
    # as a separate item the way the record does. Only the top tier of gear
    # reaches +10: nine items, all Royal Plate, Gold Shield or a heavy weapon.
    by_name = {r["name"]: r for r in rows}
    out = []
    for row in rows:
        if PLUS.match(row["name"]):
            continue
        variants = []
        for plus in range(1, MAX_PLUS + 1):
            variant = (by_name.get(f"{row['name']} +{plus}")
                       or by_name.get(f"{row['name']} + {plus}"))
            if variant:
                # The enchanted form's own id, which the panel needs to hand
                # one over. It is the base plus the enchantment on all 327 of
                # them, but it is read rather than computed.
                variants.append({"plus": plus, "id": variant["id"],
                                 "value": variant["value"],
                                 "weight": variant["weight"],
                                 "absorption": variant["absorption"]})
        out.append({**row, "variants": variants})
    return out


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


# --- driver ----------------------------------------------------------------

# The NPC and conversation-topic tables, decoded in docs/shops.md. Only the
# training service is read here; the rest of what an NPC does is not in the
# panel.
NPC_BASE, NPC_REC, NPC_COUNT = 0x3D8EB9, 40, 141
TOPIC_BASE, TOPIC_REC, TOPIC_COUNT = 0x3DA4C1, 60, 1073
TRAIN_SELECT = 0x0800  # topic +18, the handler the dispatch at 0x02ac9 picks

# A trainer's ceiling is `+0x16` of its record and the refusal above it is coded
# at image 0x09d80. A *floor* is not in the record, and nothing found reads one,
# but NPC 33 states one in its own dialogue ("once you are level 30, I can
# handle all of your training needs") and it holds in play. The hand-off is the
# corroboration: NPC 104 trains through exactly 30 and NPC 33 begins there, so
# the two cover 1-30 and 30-40 between them with no gap and no overlap.
TRAINER_FLOOR = {33: 30}


def extract_trainers(world: bytes) -> list[dict]:
    """Every NPC that sells levels, with the ceiling and the price it charges.

    Found by the topic's dispatch field rather than its keyword, so a trainer
    named something other than TRAIN would still be caught. `+0x16` of the NPC
    record is the highest level it will train you to and `+0x18` its price
    factor; offsets past those are zero on all five, so there is no floor and
    every trainer starts at level 1.
    """
    def word(buf, off):
        return struct.unpack_from("<H", buf, off)[0]

    npcs = [world[NPC_BASE + i * NPC_REC: NPC_BASE + (i + 1) * NPC_REC]
            for i in range(NPC_COUNT)]
    owner = {}
    for i, rec in enumerate(npcs):
        first, count = word(rec, 8), word(rec, 4)
        for t in range(first, first + count):
            owner[t] = i

    out = []
    for t in range(1, TOPIC_COUNT + 1):
        rec = world[TOPIC_BASE + (t - 1) * TOPIC_REC: TOPIC_BASE + t * TOPIC_REC]
        if word(rec, 14) or word(rec, 18) != TRAIN_SELECT:
            continue
        i = owner.get(t)
        if i is None:
            continue
        out.append({"npc": i,
                    "from": TRAINER_FLOOR.get(i, 1),
                    "through": word(npcs[i], 0x16),
                    "factor": word(npcs[i], 0x18)})
    return sorted(out, key=lambda r: (r["through"], r["from"]))


def extract_leveling(d: S.Directory) -> dict:
    """The leveling tables, which the clue book has no page for.

    All of this is compiled into REGISTER.EXE rather than stored in WORLD.DAT,
    so the game never shows it: the trainer quotes one price and the character
    screen names one level. The panel can show the whole ladder.
    """
    table = LV.experience_table(d.exe)
    real = {lvl: xp for lvl, xp in table.items() if xp < LV.SENTINEL_XP}
    tier2, tier3 = LV.promotion_levels(d.exe)
    return {
        # Cumulative experience for each level that can actually be reached.
        "experience": [{"level": lvl,
                        "total": real[lvl],
                        "step": real[lvl] - real.get(lvl - 1, 0)}
                       for lvl in sorted(real)],
        "cap": max(real),
        # price = base x the trainer's own factor x the level you train away
        # from, so the factor is the only part that varies between towns.
        "train_base": LV.TRAIN_BASE_PRICE,
        # min(15, round(base charisma x 13%)), which is worth showing as the
        # staircase it is rather than as a formula.
        "bonus_points": [{"charisma": c, "points": LV.bonus_points(c)}
                         for c in range(45, 121)],
        "bonus_cap": LV.BONUS_CAP,
        "promotions": {"second": tier2, "third": tier3},
        "trainers": extract_trainers(d.world),
        "spells_by_level": LV.spells_by_level(d.exe),
    }


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
        "items": extract_items(d),
        "leveling": extract_leveling(d),
        "enhancers": I.Items(d).enhancers(),
        "transports": I.Items(d).transports(),
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
