"""Read the clue book's F4 pages: which spells each magic class can cast.

F3 prints at most three class rows per spell, so it cannot show every
(class, spell) pair. F4 lists them the other way round, by class, and does.
That makes these pages the check on the class decode in `extract.py`, which
builds the same relation from three tables in the binary.

The list uses a different font from the spell pages, the same trap as the map
titles, so the alphabet is learned here from the class-selection page, whose
six lines are known strings, and then extended by matching partly-read rows
against the spell names until nothing new is learned.

    YENDOR_GAME_DIR=tmp/game-patched bun tools/capture_classes.js
    python tools/read_class_spells.py
"""

from __future__ import annotations

import collections
import glob
import json
import re
from pathlib import Path

import ocr

# Content read off the game's screens, not decoded from its files. Never
# shipped.
OBSERVED = Path(__file__).resolve().parent.parent / "observed"

ROOT = Path(__file__).resolve().parent.parent
CLASSES = ["MONK", "ALCHEMIST", "PALADIN", "MAGE", "DRUID", "MARKSMAN"]
TIERS = ["MONK / CLERIC / PRIEST", "ALCHEMIST / TRANSMUTER / HEALER",
         "PALADIN / CAVALIER / HERO", "MAGE / WIZARD / SORCERER",
         "DRUID / ENCHANTER / SAGE", "MARKSMAN / RANGER / KNIGHT"]
ROW_TOP, ROW_STEP, ROW_END, TEXT_X = 27, 10, 175, 20


def _rows(frame: ocr.Frame):
    """The (row, color) of every line of text on a list page."""
    out = []
    for row in range(ROW_TOP, ROW_END, ROW_STEP):
        for color in ("yellow", "gray"):
            if frame.cells(row, color, TEXT_X):
                out.append((row, color))
                break
    return out


def read(shot_dir: str = "tmp/f4") -> dict[str, list[str]]:
    ocr.COLORS.setdefault("gray", lambda r, g, b: r > 150 and g > 150 and b > 150)
    alpha = ocr.Alphabet()
    menu = ocr.Frame(f"{shot_dir}/00-classes.png")
    for row, text in zip(range(ROW_TOP, ROW_TOP + 6 * ROW_STEP, ROW_STEP), TIERS):
        for color in ("yellow", "gray"):
            if alpha.learn(menu, row, color, text.replace(" ", ""), TEXT_X):
                break

    spells = json.loads((ROOT / "data" / "spells.json").read_text())
    flat = {s["name"].replace(" ", ""): s["name"] for s in spells}
    frames = {p: ocr.Frame(p) for p in sorted(glob.glob(f"{shot_dir}/c*-p*.png"))}

    # The menu gives most letters; the rest are learned from rows that only one
    # spell name can match.
    while True:
        learned = 0
        for frame in frames.values():
            for row, color in _rows(frame):
                text = alpha.read(frame, row, color, TEXT_X)
                if "?" not in text or "MORE" in text:
                    continue
                pattern = re.compile(
                    "^" + "".join("." if c == "?" else re.escape(c) for c in text) + "$")
                hits = [k for k in flat if pattern.match(k)]
                if len(hits) == 1 and alpha.learn(frame, row, color, hits[0], TEXT_X):
                    learned += 1
        if not learned:
            break

    out: dict[str, set] = collections.defaultdict(set)
    unread = []
    for path, frame in frames.items():
        which = int(re.search(r"c(\d)-", path).group(1))
        for row, color in _rows(frame):
            text = alpha.read(frame, row, color, TEXT_X)
            if "MORE" in text or not text.strip():
                continue
            if text in flat:
                out[CLASSES[which]].add(flat[text])
            else:
                unread.append((path, text))
    if unread:
        raise SystemExit(f"{len(unread)} rows could not be read: {unread[:5]}")
    return {c: sorted(out[c]) for c in CLASSES}


if __name__ == "__main__":
    lists = read()
    OBSERVED.mkdir(exist_ok=True)
    (OBSERVED / "observed_class_spells.json").write_text(
        json.dumps(lists, indent=1) + "\n")
    for name, spells in lists.items():
        print(f"  {name:10} {len(spells)} spells")
