"""Section directory for WORLD.DAT, read out of REGISTER.EXE.

The game keeps an explicit table of contents for WORLD.DAT inside its
executable: a run of little-endian dwords, each the byte offset of a section.
Consecutive entries bound each section, and the final entry equals the length
of WORLD.DAT, so it doubles as an end marker.

There are two such tables. The master table covers the whole data file; a
second, shorter one covers the Restoration ("on-line clue book") corpora.

Everything here is derived from the EXE at run time rather than hardcoded, so
a mismatched build fails an assertion instead of silently decoding garbage.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

MASTER_TABLE = 0x2CF37
RESTORATION_TABLE = 0x2D4AF

# Section indices into the master table, named by what they were confirmed to
# hold. Unlisted indices are decoded but left unnamed.
MAP_NAMES_20 = 1
MAP_NAMES_12 = 2
ITEMS = 4
LORE = 16
CONVO_TOPICS = 23
CONVO_TEXT = 24
ENEMIES = 29
CATEGORIES = 30
SPELLS = 31
PRECREATED_PARTY = 32

# Restoration table indices.
WALKTHROUGH = 0
LEGEND = 2
SPELL_TEXT = 4

ENEMY_RECORD = 106
SPELL_RECORD = 80
WALKTHROUGH_PAGE = 1275
WALKTHROUGH_COLS = 51
WALKTHROUGH_ROWS = 25
SPELL_TEXT_BLOCK = 117
SPELL_TEXT_COLS = 39


@dataclass(frozen=True)
class Section:
    index: int
    offset: int
    size: int

    @property
    def end(self) -> int:
        return self.offset + self.size

    def slice(self, world: bytes) -> bytes:
        return world[self.offset:self.end]

    def records(self, world: bytes, size: int) -> list[bytes]:
        """Split into fixed-size records, asserting the section divides evenly."""
        assert self.size % size == 0, (
            f"section {self.index} @{self.offset:#x} is {self.size} bytes, "
            f"not a multiple of record size {size}"
        )
        buf = self.slice(world)
        return [buf[i:i + size] for i in range(0, len(buf), size)]

    def __repr__(self) -> str:
        return f"<Section {self.index} @{self.offset:#08x} +{self.size}>"


def _read_table(exe: bytes, start: int, limit: int) -> list[Section]:
    """Read ascending dwords from `start` until the run stops making sense.

    A valid entry points inside the data file and is >= its predecessor. The
    last entry is the end marker and does not become a section of its own.
    """
    offsets: list[int] = []
    pos = start
    while pos + 4 <= len(exe):
        value = struct.unpack_from("<I", exe, pos)[0]
        if not (0x1000 <= value <= limit):
            break
        if offsets and value < offsets[-1]:
            break
        offsets.append(value)
        pos += 4
    return [
        Section(i, offsets[i], offsets[i + 1] - offsets[i])
        for i in range(len(offsets) - 1)
    ]


def read_sections(exe: bytes, world_size: int) -> list[Section]:
    return _read_table(exe, MASTER_TABLE, world_size)


def read_restoration_sections(exe: bytes, world_size: int) -> list[Section]:
    return _read_table(exe, RESTORATION_TABLE, world_size)


class Directory:
    """Both tables plus the assertions that prove we read them correctly."""

    def __init__(self, exe: bytes, world: bytes):
        self.exe = exe
        self.world = world
        self.sections = read_sections(exe, len(world))
        self.restoration = read_restoration_sections(exe, len(world))
        self._check()

    def _check(self) -> None:
        assert len(self.sections) >= 35, f"only {len(self.sections)} master sections"
        assert self.sections[-1].end == len(self.world), (
            f"master table ends at {self.sections[-1].end:#x}, "
            f"WORLD.DAT is {len(self.world):#x} bytes"
        )
        for a, b in zip(self.sections, self.sections[1:]):
            assert a.end == b.offset, f"gap between {a} and {b}"
        # Zero-size sections are legitimate: entries 5 and 6 hold the same
        # offset, so section 5 is empty. Only a *negative* span is a bug, and
        # the ascending check in _read_table already rules that out.

        # The record-size assertions that make the whole directory trustworthy.
        assert self[ENEMIES].size % ENEMY_RECORD == 0
        assert self[SPELLS].size % SPELL_RECORD == 0
        assert self.rest(WALKTHROUGH).size % WALKTHROUGH_PAGE == 0
        assert self.spell_text_section().size % SPELL_TEXT_BLOCK == 0

    def __getitem__(self, index: int) -> Section:
        return self.sections[index]

    def rest(self, index: int) -> Section:
        return self.restoration[index]

    def spell_text_section(self) -> Section:
        """Spell descriptions are the Restoration table's last entry, so the
        table has no following offset to bound them. Take the start from the
        table and the end from the next master-table boundary."""
        start = struct.unpack_from(
            "<I", self.exe, RESTORATION_TABLE + 4 * SPELL_TEXT)[0]
        end = next(s.offset for s in self.sections if s.offset > start)
        return Section(SPELL_TEXT, start, end - start)


def load(game_dir: str | Path = "game") -> Directory:
    game = Path(game_dir)
    exe = (game / "REGISTER.EXE").read_bytes()
    world = (game / "WORLD.DAT").read_bytes()
    return Directory(exe, world)


if __name__ == "__main__":
    import sys

    d = load(sys.argv[1] if len(sys.argv) > 1 else "game")
    print(f"REGISTER.EXE {len(d.exe):,} B   WORLD.DAT {len(d.world):,} B")
    print(f"\nmaster table @{MASTER_TABLE:#x}: {len(d.sections)} sections")
    names = {
        MAP_NAMES_20: "map names (20-char)", MAP_NAMES_12: "map names (12+12)",
        ITEMS: "items", LORE: "lore/books", CONVO_TOPICS: "conversation topics",
        CONVO_TEXT: "conversation prose", ENEMIES: "enemies",
        CATEGORIES: "category codes", SPELLS: "spells",
        PRECREATED_PARTY: "pre-created party",
    }
    for s in d.sections:
        head = d.world[s.offset:s.offset + 28]
        ascii_ = "".join(chr(c) if 0x20 <= c < 0x7F else "." for c in head)
        print(f"  [{s.index:2}] {s.offset:#09x} {s.size:>8,}  {names.get(s.index,''):<20} |{ascii_}|")

    print(f"\nrestoration table @{RESTORATION_TABLE:#x}: {len(d.restoration)} sections")
    for s in d.restoration:
        print(f"  [{s.index}] {s.offset:#09x} {s.size:>8,}")
    st = d.spell_text_section()
    print(f"  spell text: {st.offset:#09x} {st.size:,} = "
          f"{st.size // SPELL_TEXT_BLOCK} blocks of {SPELL_TEXT_BLOCK}")
    print(f"\nenemies: {d[ENEMIES].size // ENEMY_RECORD} records of {ENEMY_RECORD}")
    print(f"spells:  {d[SPELLS].size // SPELL_RECORD} records of {SPELL_RECORD}")
    print(f"pages:   {d.rest(WALKTHROUGH).size // WALKTHROUGH_PAGE} of {WALKTHROUGH_PAGE}")
