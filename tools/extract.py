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


def build(game_dir: str | Path = "game", out_dir: str | Path = "data") -> dict:
    d = S.load(game_dir)
    missing = L.verify(d.exe)
    assert not missing, f"EXE is missing expected labels: {missing}"

    pages = extract_walkthrough(d)
    payload = {
        "walkthrough": pages,
        "walkthrough_index": walkthrough_sections(pages),
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
    print(f"\nwrote data/*.json")
