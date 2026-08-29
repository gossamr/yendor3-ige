#!/usr/bin/env python3
"""Make created characters survive, by writing them into the roster template.

The game keeps its character roster in `CURGAME`: ten 500-byte slots in the
first 5,000 bytes, of which slot 0 is a header, slots 1-5 are free, and slots
6-9 hold SQUIRE, DIANA, YENDOR and JOSEPHINE. KEEP CHARACTER writes exactly
those 5,000 bytes, so a character is on disk the moment it is kept.

It still does not survive, and watching the filesystem says why (see
docs/saves.md, "The roster in a save is written but never read"):

  * every launch does `truncate CURGAME 0` then `write CURGAME at 0 len 81037`
  * NEW GAME does the same 81,037-byte write

Both rebuild the whole file, roster included, and the game never reads the
roster back out of `CURGAME`: it is written there, never loaded from there.
So nothing put into `CURGAME` can last, and the rebuild's source is
`WORLD.DAT` at 0x41D72F, whose first 5,000 bytes are that same slot table.

That is the one place a character can be put and stay put. Copying the kept
slots into it makes them part of the roster the game restores from, so they
appear in Assemble a Party at every launch, and NEW GAME no longer clears them.

    python tools/keep_characters.py --list                    # what is where
    python tools/keep_characters.py --from tmp/CURGAME --out tmp/game-chars

Characters accumulate. Once slot 1 of the template is taken the next character
kept lands in slot 2, so grafting after each session builds the roster up rather
than replacing it, as long as the game being played is the grafted copy.
There are five slots.
"""

from __future__ import annotations

import shutil
from pathlib import Path

ROSTER = 0x41D72F      # "PRE-CREATED PARTY", the roster template in WORLD.DAT
SLOT = 500             # bytes per character record
SLOTS = 10             # slot 0 is a header, 1-5 are free, 6-9 are the stock four
CREATED = range(1, 6)  # the slots Character Creation fills
SAVE_SIZE = 81037      # CURGAME and every SAVGAMEn are exactly this long


def name_of(record: bytes) -> str:
    """The character's name: a NUL-terminated string at the top of the record."""
    return record.split(b"\0", 1)[0].decode("latin1", "replace").strip()


def slots(blob: bytes, base: int = 0) -> list[tuple[int, str]]:
    """Every occupied slot of a roster, as (index, name)."""
    out = []
    for i in range(SLOTS):
        rec = blob[base + i * SLOT:base + (i + 1) * SLOT]
        n = name_of(rec)
        if n and n.isprintable():
            out.append((i, n))
    return out


def read_roster(path: Path) -> bytes:
    """The 5,000-byte roster out of a CURGAME or SAVGAMEn file."""
    blob = path.read_bytes()
    if len(blob) != SAVE_SIZE:
        raise SystemExit(
            f"{path}: expected a {SAVE_SIZE}-byte game file, got {len(blob)}")
    return blob[:SLOTS * SLOT]


def graft(world: bytes, roster: bytes, which=CREATED) -> tuple[bytes, list[str]]:
    """Copy the created slots of `roster` into a copy of `world`.

    Only slots 1-5 are touched: slot 0 is the header and 6-9 are the four the
    game ships, and overwriting either would lose something the player did not
    create. An empty slot in the source clears nothing: a character kept in
    one session and a character kept in the next therefore accumulate.
    """
    out = bytearray(world)
    moved = []
    for i in which:
        rec = roster[i * SLOT:(i + 1) * SLOT]
        n = name_of(rec)
        if not n or not n.isprintable():
            continue
        at = ROSTER + i * SLOT
        out[at:at + SLOT] = rec
        moved.append(f"slot {i}: {n}")
    return bytes(out), moved


def build_game_dir(source: Path, game: Path, out: Path) -> list[str]:
    """A complete game directory whose WORLD.DAT carries the kept characters.

    Writing back into the game's own directory is allowed, since that is what
    a player running plain DOSBox actually wants, but the original is kept as
    WORLD.DAT.orig the first time, so the graft is always reversible.
    """
    out.mkdir(parents=True, exist_ok=True)
    if out.resolve() == game.resolve():
        backup = game / "WORLD.DAT.orig"
        if not backup.exists():
            shutil.copy2(game / "WORLD.DAT", backup)
    for f in game.iterdir():
        if f.is_file() and f.name.upper() != "WORLD.DAT":
            target = out / f.name
            if not target.exists() or target.stat().st_size != f.stat().st_size:
                shutil.copy2(f, target)
    # Build on the output copy when there is one, so characters accumulate
    # across runs rather than each run replacing the last.
    existing = out / "WORLD.DAT"
    base = existing if existing.exists() else game / "WORLD.DAT"
    world, moved = graft(base.read_bytes(), read_roster(source))
    (out / "WORLD.DAT").write_bytes(world)
    return moved


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="source", help="a CURGAME or SAVGAMEn file")
    ap.add_argument("--game", default="game")
    ap.add_argument("--out", default="tmp/game-chars")
    ap.add_argument("--list", action="store_true",
                    help="show the roster in WORLD.DAT and in --from")
    a = ap.parse_args()

    world = (Path(a.game) / "WORLD.DAT").read_bytes()
    if a.list or not a.source:
        print(f"{a.game}/WORLD.DAT roster at {ROSTER:#x}:")
        for i, n in slots(world, ROSTER):
            print(f"  slot {i}: {n}")
        if a.source:
            print(f"\n{a.source} roster:")
            for i, n in slots(read_roster(Path(a.source))):
                print(f"  slot {i}: {n}")
        raise SystemExit(0)

    moved = build_game_dir(Path(a.source), Path(a.game), Path(a.out))
    for m in moved:
        print(f"kept {m}")
    print(f"{len(moved)} character(s) written into {a.out}/WORLD.DAT")
