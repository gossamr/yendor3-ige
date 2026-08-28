"""Turn the captured F5 screens into observed_items.json.

What the clue book shows about an item is partly decodable and partly not. The
decodable parts (base value, weight, absorption) are solved against the
record in extract.py. The rest (which category the book files an item under,
what it protects against, what it adds) has no field in the 58-byte record, so
it is carried here as an observation and kept in separate fields, exactly as
the spell class lists are.
"""

from __future__ import annotations

import glob
import json
import re
from pathlib import Path

import ocr
import read_items as R
import solve_items as SI

# Content read off the game's screens, not decoded from its files. Never
# shipped.
OBSERVED = Path(__file__).resolve().parent.parent / "observed"

ROOT = Path(__file__).resolve().parent

# Words the game runs together on screen, because the reader has no spaces to
# go by. Longest match wins, so "SICKNESS" is not split into "SICK" + "NESS".
VOCABULARY = [
    "CHARACTER PANEL", "ANY PANEL", "BACKPACK", "BOX", "BAG",
    "PERCENT", "OF", "HEALTH", "MAGIC",
    "JINXING", "FROZEN", "PARALYZE", "SICKNESS", "SICK", "POISON", "DISEASE",
    "STRENGTH", "DEXTERITY", "STAMINA", "INTELLIGENCE", "WISDOM", "CHARISMA",
    "CASTING", "POLEARM", "SLASHING", "BASHING", "PROJECTILE", "MAPPING",
    "NAVIGATION", "SURVIVAL", "BARTERING", "REPAIR", "THIEVERY", "LINGUISTICS",
    "UNDEAD", "ATTRIBUTE", "SKILL", "MINUTES", "ANYTIME", "YES", "NO",
    "CHARACTER", "PANEL", "ANY", "3X3",
]
BY_LENGTH = sorted(VOCABULARY, key=len, reverse=True)


def split_words(text: str) -> str:
    """Re-space a run-together value, e.g. "25PERCENTOFHEALTH"."""
    out, i = [], 0
    while i < len(text):
        if text[i] in ",":
            out.append(",")
            i += 1
            continue
        m = re.match(r"[\d.,]+", text[i:])
        if m:
            out.append(m.group())
            i += len(m.group())
            continue
        for word in BY_LENGTH:
            bare = word.replace(" ", "")
            if text.startswith(bare, i):
                out.append(word)
                i += len(bare)
                break
        else:
            out.append(text[i])
            i += 1
    joined = " ".join(out).replace(" ,", ",")
    return re.sub(r"\s+", " ", joined).strip()


def match(reading: str, vocabulary: list[str]) -> str | None:
    """Map a spaceless reading back to the string the executable holds."""
    bare = reading.replace(" ", "").rstrip(":-")
    for word in vocabulary:
        if word.replace(" ", "").rstrip(":-") == bare:
            return word
    return None


# ATTRIBUTE ENHANCERS is not an item list. It is one page of rules, which kind
# of enhancer raises what and by how much, so it is read separately.
ENHANCER_PAGE = "c1i000.png"


def read_enhancers(shot_dir: str, alpha) -> list[dict]:
    path = Path(shot_dir) / ENHANCER_PAGE
    if not path.exists():
        return []
    frame = ocr.Frame(path)
    out = []
    for row in R.body_rows(frame):
        kind = alpha.read(frame, row, "blue", 0).strip()
        amount = alpha.read(frame, row, "red", 0).strip()
        raises = alpha.read(frame, row, "green", 0).strip()
        if kind and amount and raises:
            out.append({"kind": kind, "amount": int(amount), "raises": raises})
    return out


def build(shot_dir: str = "tmp/items", game_dir: str = "game") -> dict:
    names = [n for n, _ in SI.records(game_dir) if n]
    shots = sorted(glob.glob(f"{shot_dir}/c[0-9]i[0-9][0-9][0-9].png"))
    alpha = R.build_alphabet(shots, names)
    by_plain = {}
    for n in names:
        by_plain.setdefault(SI.plain(n), n)

    out = {}
    for shot in shots:
        item = R.read_item(ocr.Frame(shot), alpha)
        name = by_plain.get(SI.plain(item["name"] or ""))
        # The category-list screen gets captured too; it has no item name.
        if not name or name in out or item["category"] == "INVENTORYITEMS":
            continue
        fields = {}
        for caption, value in item["fields"].items():
            # Captions and categories come from fixed lists in the executable,
            # so they are matched back to those rather than re-spaced by
            # guesswork; only free-form values need the word splitter.
            key = match(caption, R.CAPTIONS)
            if not key:
                continue
            fields[key.rstrip(":-").lower()] = split_words(value) if value else None
        out[name] = {"category": match(item["category"], R.CATEGORIES),
                     "fields": fields}
    return out


if __name__ == "__main__":
    names = [n for n, _ in SI.records() if n]
    shots = sorted(glob.glob("tmp/items/c[0-9]i[0-9][0-9][0-9].png"))
    alpha = R.build_alphabet(shots, names)
    payload = {"items": build(), "enhancers": read_enhancers("tmp/items", alpha)}
    OBSERVED.mkdir(exist_ok=True)
    path = OBSERVED / "observed_items.json"
    path.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n")
    print(f"wrote {path}: {len(payload['items'])} items, "
          f"{len(payload['enhancers'])} enhancer rules")
