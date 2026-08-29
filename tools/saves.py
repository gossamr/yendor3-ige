#!/usr/bin/env python3
"""The save file, read the way the game reads it.

`CURGAME` is the game's live state file and `SAVGAMEn` is a byte-for-byte copy
of it, so there is one format and this reads both. Neither is a memory dump:
the game keeps the file as a **random-access record store** and writes single
records back to it as they change: a hundred bytes when the party crosses a
row, one byte when a door opens.

The store's shape is not guessed. `REGISTER.EXE` carries a table of section
offsets in its data segment at `DS:0xB167`, and one stub per section that
points a file handle at the right entry and sets the record length:

    file offset = section base + record number x record length

which is the seek at image `0x039ED` (`mul [bx+8]`, `add [bx+0xa]`,
`INT 21h AH=42h`). `sections()` reads the offsets out of the executable rather
than trusting a constant here, so a different build would be read correctly or
fail loudly.

    .venv/bin/python tools/saves.py tmp/save-probe/base/SAVGAME1
    .venv/bin/python tools/saves.py --layout

What each section is, and how it was established, is in `docs/saves.md`.
"""

from __future__ import annotations

import struct
import sys
from dataclasses import dataclass
from pathlib import Path

from mz import HEADER, Image
from sections import MASTER_TABLE

SAVE_SIZE = 81037

# The load image offset of DS:0. Fixed by the four filenames the game keeps in
# its data segment: PICTURES.VGA is at DS:0x969E both here and in the running
# guest, which is the anchor tools/fight_probe.js uses to find the segment.
DGROUP = 0x1DDB0
ANCHOR = (0x969E, b"PICTURES.VGA")

# The section offset table: seven uint32 file offsets and a zero terminator,
# and then WORLD.DAT's own section directory, which tools/sections.py already
# reads. The two tables abut, so CURGAME's is addressed from that one rather
# than from a constant of its own: DS:0xB167 is the same place said the other
# way, and sections() checks the two agree.
SECTION_COUNT = 7
FILE_TABLE = 0xB167

# The 14-byte file handle the game keeps for CURGAME, followed by its name.
# The seek at image 0x039ED reads +6 and +8 and the base at +10.
HANDLE = 0x967A
H_FILE, H_BUF_SEG, H_BUF_OFF, H_LEN, H_RECORD, H_BASE = 0, 2, 4, 6, 8, 10

ROSTER_SLOT = 500
ROSTER_SLOTS = 10

# Gold, food and nuore, and a character's experience, are packed BCD: two
# decimal digits to a byte, most significant byte first, four bytes wide. The
# item table's BASE VALUE uses the same encoding (see docs/items.md), which is
# what made it recognisable: 3,557 gold reads `00 00 35 57`.
PURSE = {"gold": 180, "food": 184, "nuore": 188}
EXPERIENCE_AT, BCD_BYTES = 24, 4

# The live block, at the offsets the F1 sheet prints them in. The same 26 words
# appear again 64 bytes later holding the maximum.
LIVE, MAXIMUM = 60, 124
ATTRIBUTES = ("strength", "dexterity", "stamina", "intelligence",
              "wisdom", "charisma")
# The five combat words the equip dispatch derives, which tools/fight_probe.js
# already writes at 0x48, 0x4A, 0x4C and 0x4E. The sheet's ACC and DAM rows are
# the hand pair; the shot pair is not printed there.
COMBAT = ("shot accuracy", "shot damage", "accuracy", "damage", "absorption")
SKILLS = ("survival", "projectile", "slashing", "bashing", "polearm",
          "casting", "mapping", "navigate", "bartering", "repair",
          "thievery", "linguistic")
# Offsets within the block, from `LIVE`.
OFF_ATTRIBUTES, OFF_COMBAT, OFF_SKILLS = 0, 12, 28
OFF_HEALTH, OFF_MAGIC, OFF_CAPACITY = 22, 24, 26
CARRIED_AT = 280            # tenths of a unit, as is the capacity at LIVE+26

# The eight panel slots, then the equipment, each an item id and a second word
# that is the item's own state, and for a container its record in section 2.
PANEL_AT, PANEL_SLOTS = 282, 8
EQUIPMENT = {"missile": 314, "container": 318, "hand": 322, "shield": 326,
             "ring": 330, "ring 2": 334, "worn": 338}
# The playing party, as roster slot numbers, in the last four words of the
# header slot.
PARTY_AT, PARTY_MAX = 492, 4

# The world grid: 7 areas of 24 bands, and a band is 20 levels of 40 cells --
# five bytes to a level, so a hundred to a band. The same geometry as the
# clue book's tables at WORLD.DAT 0x3C4F02.
AREAS, BANDS, LEVELS, CELLS = 7, 24, 20, 40
BAND_BYTES = LEVELS * CELLS // 8          # 100

# The creature structs the map keeps: eighty of them, at DS:0x122C.
SPAWN_SLOTS, CREATURE = 80, 156

# Facings, as the look-ahead dispatch at image 0x112D6 tests them.
FACING = {0x8000: "north", 0x4000: "south", 0x2000: "west", 0x1000: "east"}

# The clock counts minutes and wraps at 1,440, advancing the day beside it.
DAY_AT, CLOCK_AT, MINUTES_PER_DAY = 156, 162, 1440


@dataclass(frozen=True)
class Section:
    index: int
    base: int
    end: int
    record: int | None      # record length; None where the game varies it
    name: str

    @property
    def size(self) -> int:
        return self.end - self.base

    @property
    def records(self) -> int | None:
        return None if not self.record else self.size // self.record


# Record length per section, and the image address of the stub that sets it.
# Section 1's is not an immediate: the stub copies it from DS:0x5492, which
# holds 100 in every run seen.
STUBS: dict[int, tuple[int, int | None, str]] = {
    0: (0x17E64, 5000, "roster: ten 500-byte slots"),
    1: (0x17EDC, 100, "seen grid: one bit per world cell"),
    2: (0x17EF6, 34, "containers: eight items each"),
    3: (0x17EA1, 1, "the chest path is finished with this bundle: one bit each"),
    4: (0x17E82, 1, "items handed over: one byte a bundle, one bit an item"),
    5: (0x17EC0, 1, "world flags, set and cleared by number"),
    6: (0x17E46, 12480, "the eighty creature structs, from DS:0x122C"),
}

# What sections 3 and 4 are indexed by: WORLD.DAT's section 10, a thousand
# 26-byte records of eight item ids and a gold amount.
TREASURE_SECTION, TREASURE_RECORD = 10, 26
TREASURE_ITEMS, TREASURE_GOLD = slice(2, 10), 10

# Section 3 is banked. Two entry points load a record of that table: the one at
# image 0x252E indexes section 3 at the record number and section 4 with it,
# and the one at 0x25CB adds DS:0xF48 and never touches section 4. Which one a
# thing goes through is a flag on the map object that names it: `[si+2]`
# bit 0x8000 for the first, 0x4000 for the second, at image 0x10BDA.
#
# So the same bundle of items and gold is reachable two ways, and each way has
# its own bank of "this one has been dealt with" bits. Only bank 0 has been
# seen set in a save.
BANK_AT = 0x0F076       # `mov word ptr [0xF48], 0x3F0`, the only write
BANK = 1008
# The byte the stub writes its record length with: `mov word ptr [bx+6], imm`.
STUB_LEN_OPCODE = bytes([0xC7, 0x47, H_LEN])


def _exe(path: str | Path = "game/REGISTER.EXE") -> Image:
    return Image(path)


def dgroup(exe: Image | None = None) -> int:
    """The image offset of DS:0, checked against the string it is anchored on."""
    exe = exe or _exe()
    off, want = ANCHOR
    at = HEADER + DGROUP + off
    if exe.data[at:at + len(want)] != want:
        raise ValueError(f"DS:0x{off:04x} is not {want!r}; DGROUP has moved")
    return DGROUP


def table_at() -> int:
    """The file offset of CURGAME's section table.

    It ends where WORLD.DAT's master table begins: seven offsets and a
    terminator, thirty-two bytes.
    """
    return MASTER_TABLE - 4 * (SECTION_COUNT + 1)


def sections(exe: Image | None = None) -> list[Section]:
    """The seven sections, out of the executable's own offset table."""
    exe = exe or _exe()
    at = table_at()
    if at != HEADER + dgroup(exe) + FILE_TABLE:
        raise ValueError("the two ways of addressing the table disagree")
    offs = list(struct.unpack_from(f"<{SECTION_COUNT}I", exe.data, at))
    if offs[0] != 0:
        raise ValueError(f"the table does not start at 0: {offs}")
    if list(offs) != sorted(offs) or len(set(offs)) != len(offs):
        raise ValueError(f"section offsets are not increasing: {offs}")
    terminator = struct.unpack_from("<I", exe.data, at + 4 * SECTION_COUNT)[0]
    if terminator != 0:
        raise ValueError(f"no terminator after {SECTION_COUNT} sections")
    # The file ends where the last section does, and the last section is a
    # single record whose length its stub carries, so the file's size is
    # derived here rather than asserted.
    ends = offs[1:] + [offs[-1] + STUBS[SECTION_COUNT - 1][1]]
    return [Section(i, b, e, STUBS[i][1], STUBS[i][2])
            for i, (b, e) in enumerate(zip(offs, ends))]


def bank_size(exe: Image | None = None) -> int:
    """The stride between section 3's banks, out of the instruction that sets
    it: `mov word ptr [0xF48], imm` at image 0x0F076, the only write to it."""
    exe = exe or _exe()
    at = HEADER + BANK_AT
    if exe.data[at:at + 4] != bytes([0xC7, 0x06, 0x48, 0x0F]):
        raise ValueError("the bank stride is not written where it was")
    return struct.unpack_from("<H", exe.data, at + 4)[0]


def stub_record_length(exe: Image, index: int) -> int | None:
    """The record length the section's stub writes, read back from its bytes.

    Proving the constants rather than restating them: each stub ends with
    `mov word ptr [bx+6], imm16`, and section 1's does not, because its length
    comes from a variable.
    """
    at = HEADER + STUBS[index][0]
    window = exe.data[at:at + 40]
    hit = window.find(STUB_LEN_OPCODE)
    if hit < 0:
        return None
    return struct.unpack_from("<H", window, hit + 3)[0]


# --- reading a save ---------------------------------------------------------

def treasure_table(world: str | Path = "game/WORLD.DAT",
                   exe: Image | None = None) -> list[tuple[int, ...]]:
    """WORLD.DAT's treasure table, as tuples of 13 words."""
    from sections import load as load_directory

    d = load_directory(Path(world).parent)
    s = d.sections[TREASURE_SECTION]
    blob = Path(world).read_bytes()[s.offset:s.offset + s.size]
    return [struct.unpack_from("<13H", blob, n * TREASURE_RECORD)
            for n in range(len(blob) // TREASURE_RECORD)]


def offset(section: Section, record: int) -> int:
    """Where a record lands, by the game's own arithmetic."""
    if not section.record:
        raise ValueError(f"section {section.index} has no fixed record length")
    return section.base + record * section.record


def name_of(record: bytes) -> str:
    return record.split(b"\0", 1)[0].decode("latin1", "replace").strip()


def bcd(blob: bytes, at: int, length: int = BCD_BYTES) -> int:
    """A packed-BCD counter: two digits a byte, most significant byte first."""
    out = 0
    for byte in blob[at:at + length]:
        hi, lo = byte >> 4, byte & 0xF
        if hi > 9 or lo > 9:
            raise ValueError(f"0x{byte:02x} at {at} is not two decimal digits")
        out = out * 100 + hi * 10 + lo
    return out


class Save:
    def __init__(self, blob: bytes, exe: Image | None = None):
        if len(blob) != SAVE_SIZE:
            raise ValueError(f"expected {SAVE_SIZE} bytes, got {len(blob)}")
        self.blob = blob
        self.sections = sections(exe)

    def section(self, i: int) -> bytes:
        s = self.sections[i]
        return self.blob[s.base:s.end]

    def record(self, i: int, n: int) -> bytes:
        s = self.sections[i]
        at = offset(s, n)
        return self.blob[at:at + s.record]

    # -- section 0, the roster ----------------------------------------------
    @property
    def title(self) -> str:
        """The save's name, typed at the slot. It is written over the head of
        the roster header, which ships holding `PRE-CREATED PARTY`."""
        return name_of(self.blob[:ROSTER_SLOT])

    def roster(self) -> list[tuple[int, str]]:
        out = []
        for i in range(ROSTER_SLOTS):
            n = name_of(self.blob[i * ROSTER_SLOT:(i + 1) * ROSTER_SLOT])
            if n and n.isprintable():
                out.append((i, n))
        return out

    def _hw(self, at: int) -> int:
        return self.blob[at] | (self.blob[at + 1] << 8)

    @property
    def party(self) -> list[int]:
        """The roster slots that are playing, at the end of the header slot.

        Four words in the order they were picked. An unused one reads 0, which
        is not a slot a character can be in: slot 0 is the header. Assembling
        a party of SQUIRE and JOSEPHINE writes 6, 9, 0, 0.
        """
        got = [self._hw(PARTY_AT + 2 * i) for i in range(PARTY_MAX)]
        return [n for n in got if n]

    @property
    def where(self) -> dict:
        """The party's position. x and y are cells over the whole world grid,
        so the area is y // 24 and the map level is x // 40."""
        x, y = self._hw(152), self._hw(154)
        facing = self._hw(150)
        clock = self._hw(CLOCK_AT)
        return {
            "x": x, "y": y,
            "area": y // BANDS, "band": y % BANDS,
            "level": x // CELLS, "cell": x % CELLS,
            "facing": FACING.get(facing, f"0x{facing:04x}"),
            "day": self._hw(DAY_AT), "clock": clock,
            "time": f"{clock // 60:02d}:{clock % 60:02d}",
        }

    @property
    def purse(self) -> dict:
        """Gold, food and nuore, which the F5 panel prints. All party-wide."""
        return {k: bcd(self.blob, at) for k, at in PURSE.items()}

    def character(self, slot: int) -> dict | None:
        """One roster slot, in the terms the F1 sheet prints."""
        rec = self.blob[slot * ROSTER_SLOT:(slot + 1) * ROSTER_SLOT]
        name = name_of(rec)
        if not name or not name.isprintable():
            return None

        def w(at):
            return rec[at] | (rec[at + 1] << 8)

        def block(base):
            return {
                **{n: w(base + OFF_ATTRIBUTES + 2 * i)
                   for i, n in enumerate(ATTRIBUTES)},
                **{n: w(base + OFF_COMBAT + 2 * i)
                   for i, n in enumerate(COMBAT)},
                **{n: w(base + OFF_SKILLS + 2 * i)
                   for i, n in enumerate(SKILLS)},
                "health": w(base + OFF_HEALTH),
                "magic": w(base + OFF_MAGIC),
                "capacity": w(base + OFF_CAPACITY) / 10,
            }

        panel = [(w(PANEL_AT + 4 * i), w(PANEL_AT + 4 * i + 2))
                 for i in range(PANEL_SLOTS)]
        return {
            "slot": slot, "name": name,
            "class": w(14), "sex": w(16), "level": w(22),
            "experience": bcd(rec, EXPERIENCE_AT),
            "conditions": w(28),
            "carried": w(CARRIED_AT) / 10,
            "now": block(LIVE), "most": block(MAXIMUM),
            "panel": [p for p in panel if p[0]],
            "equipment": {k: w(at) for k, at in EQUIPMENT.items() if w(at)},
        }

    def characters(self) -> list[dict]:
        return [c for c in (self.character(i) for i in range(1, ROSTER_SLOTS)) if c]

    # -- section 1, the seen grid -------------------------------------------
    def seen(self, x: int, y: int) -> bool:
        """Has the party laid eyes on this cell?

        The bit is set by the routine at image 0x11268: the byte is x // 8 of
        the row for y, and the bit is 0x80 >> (x % 8).
        """
        at = offset(self.sections[1], y) + x // 8
        return bool(self.blob[at] & (0x80 >> (x % 8)))

    def seen_cells(self) -> list[tuple[int, int]]:
        s = self.sections[1]
        out = []
        for y in range(AREAS * BANDS):
            row = self.blob[offset(s, y):offset(s, y) + BAND_BYTES]
            for i, byte in enumerate(row):
                if not byte:
                    continue
                for bit in range(8):
                    if byte & (0x80 >> bit):
                        out.append((i * 8 + bit, y))
        return out

    # -- section 2, containers ----------------------------------------------
    def container(self, n: int) -> list[tuple[int, int]]:
        """A container's eight (item, word) pairs, empty ones dropped.

        A character points at one by number: the item id of the container
        itself is at character +0x13E and this record number at +0x140.
        """
        rec = self.record(2, n)
        pairs = struct.unpack_from("<16H", rec, 2)
        return [(pairs[i], pairs[i + 1]) for i in range(0, 16, 2) if pairs[i]]

    # -- sections 3, 4 and 5, bit arrays ------------------------------------
    def bit(self, section: int, n: int) -> bool:
        s = self.sections[section]
        return bool(self.blob[s.base + n // 8] & (0x80 >> (n % 8)))

    def bits_set(self, section: int) -> list[int]:
        s = self.sections[section]
        out = []
        for i, byte in enumerate(self.blob[s.base:s.end]):
            for bit in range(8):
                if byte & (0x80 >> bit):
                    out.append(i * 8 + bit)
        return out

    def banks(self) -> dict[int, list[int]]:
        """Section 3's set bits, split by bank. Bank 0 is what a container
        reached through the first entry point sets; bank 1 is the second."""
        out: dict[int, list[int]] = {0: []}
        for bit in self.bits_set(3):
            out.setdefault(bit // BANK, []).append(bit % BANK)
        return out

    def treasures(self, table: list[tuple[int, ...]]) -> list[dict]:
        """Every bundle the party has had items out of, and what is gone.

        Section 4 gives a bundle a byte and each of its eight item slots a bit
        of that byte, set as the item is handed over. Section 3's bank 0 gives
        the same bundle one bit, and that bit belongs to the chest path alone
        A bundle handed over some other way has the byte and not the bit,
        which is what `chest` reports.
        """
        opened, taken = set(self.banks()[0]), self.section(4)
        out = []
        for n, byte in enumerate(taken):
            if not byte and n not in opened:
                continue
            rec = table[n]
            items = rec[TREASURE_ITEMS]
            out.append({
                "treasure": n,
                "chest": n in opened,
                "gold": rec[TREASURE_GOLD],
                "taken": [items[i] for i in range(8) if byte & (0x80 >> i)],
                "left": [items[i] for i in range(8)
                         if items[i] and not byte & (0x80 >> i)],
            })
        return out

    # -- section 6, the creatures on the map --------------------------------
    def creatures(self) -> list[tuple[int, str]]:
        """The occupied spawn slots, by the name each struct carries at +0x32."""
        s = self.sections[6]
        out = []
        for i in range(SPAWN_SLOTS):
            at = s.base + i * CREATURE
            n = name_of(self.blob[at + 0x32:at + 0x32 + 12])
            if n and n.isprintable():
                out.append((i, n))
        return out


# --- the command line -------------------------------------------------------

def print_layout() -> None:
    exe = _exe()
    print(f"DGROUP at image 0x{dgroup(exe):05x}; section table at "
          f"DS:0x{FILE_TABLE:04x}, file 0x{table_at():05x}\n")
    print(f"{'#':>2} {'base':>7} {'size':>7} {'record':>7} {'count':>6}  what")
    for s in sections(exe):
        got = stub_record_length(exe, s.index)
        note = "" if got in (s.record, None) else f"  (stub says {got})"
        print(f"{s.index:>2} {s.base:>7} {s.size:>7} {str(s.record):>7}"
              f" {str(s.records):>6}  {s.name}{note}")


def print_save(path: Path) -> None:
    save = Save(path.read_bytes())
    print(f"{path}  {len(save.blob):,} bytes")
    print(f"  title      {save.title!r}")
    print(f"  roster     " + ", ".join(f"{i}:{n}" for i, n in save.roster()))
    print(f"  party      {save.party}")
    p = save.purse
    print(f"  purse      {p['gold']:,} gold, {p['food']} food, {p['nuore']} nuore")
    for c in save.characters():
        n, m = c["now"], c["most"]
        print(f"  {c['slot']} {c['name']:<11} class {c['class']:2d} level {c['level']:2d}"
              f"  ex {c['experience']:>7,}"
              f"  health {n['health']}/{m['health']}  magic {n['magic']}/{m['magic']}"
              f"  weight {c['carried']}/{n['capacity']}")
    w = save.where
    print(f"  position   x={w['x']} y={w['y']}"
          f"  area {w['area']} band {w['band']} level {w['level']} cell {w['cell']}"
          f"  facing {w['facing']}  day {w['day']} {w['time']}")
    seen = save.seen_cells()
    print(f"  seen       {len(seen)} cells")
    used = [(n, save.container(n)) for n in range(save.sections[2].records)]
    used = [(n, c) for n, c in used if c]
    print(f"  containers {len(used)} in use"
          + ("" if not used else "  " + "; ".join(
              f"{n}: {c}" for n, c in used[:6])))
    try:
        table = treasure_table()
    except Exception as e:                      # no game directory to read
        print(f"  treasure   not read: {e}")
    else:
        found = save.treasures(table)
        emptied = [t for t in found if not t["left"]]
        given = [t for t in found if not t["chest"]]
        print(f"  bundles    {len(found)} touched, {len(emptied)} emptied,"
              f" {sum(t['gold'] for t in found):,} gold in them")
        for t in found[:4]:
            print(f"               {t['treasure']:4d} gold {t['gold']:6,}"
                  f"  took {t['taken']}" + (f"  left {t['left']}" if t["left"] else ""))
        if given:
            print("  handed over, not through the chest path: " + ", ".join(
                f"{t['treasure']} ({t['gold']:,} gold, {len(t['taken'])} items)"
                for t in given))
        for n, bits in sorted(save.banks().items()):
            if n == 0:
                continue
            print(f"  bank {n}     {len(bits)} set: " + ", ".join(
                f"{b} ({table[b][TREASURE_GOLD]:,} gold,"
                f" {sum(1 for i in table[b][TREASURE_ITEMS] if i)} items)"
                for b in bits[:6]))
    print(f"  flags      {save.bits_set(5)[:24]}")
    print(f"  creatures  {save.creatures()}")


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if not a.startswith("-")]
    if "--layout" in argv or not args:
        print_layout()
        return 0
    for a in args:
        print_save(Path(a))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
