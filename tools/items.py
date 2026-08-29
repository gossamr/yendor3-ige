#!/usr/bin/env python3
"""Item properties, decoded out of the game's own files.

Everything the clue book's F5 "INVENTORY ITEMS" pages print comes from four
places, and this module reads all four:

* **the 58-byte record** in `WORLD.DAT` section 4: value, weight, where the
  item fits, and two pointers;
* **a properties entry**, 12 bytes for armor and weapons and 8 for everything
  else, picked by the record's category word;
* **an effects entry**, 16 bytes, holding up to four (character-record offset,
  amount) pairs, the ADDS and PROTECTIONS rows;
* **`REGISTER.EXE`**, which holds the six category lists the book files items
  under, the names of the fields an effect writes, the attribute-enhancer
  rules, the three transports, and the potion lines.

The loader at image `0x0f44c` is what fixes the shape: given a 1-based item id
it copies the record to `0xe4c`, the effects entry to `0xe3c` and the
properties entry to `0xe30`, and the page renderers read only those three
buffers. Its three `add si` immediates (`0x940`, `0x139c`, `0x1854` from a
base of `WORLD.DAT` section 6) are the three properties tables, and each
lands on a section boundary exactly.

    python tools/items.py             # the tables
    python tools/items.py NAME        # one item's page, as the book prints it
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

import labels as L
import sections as S
from mz import HEADER

# --- the record ------------------------------------------------------------

RECORD = 58
FIELD_BYTES = 19
NAME_LEN = 13
NAME_FIELDS = 3

PROPS_PTR = 0     # uint16, byte offset into this item's properties table
EFFECT_PTR = 2    # uint16, byte offset into the effects table
VALUE = 5         # packed BCD, three bytes
WEIGHT = 10       # uint16, tenths
CATEGORY = 12     # uint16, the properties-table selector and the equip slot
CONTAINERS = 14   # uint16, where the item fits

# The category word's three table selectors, tested in this order by `0x0f4cc`.
WEARABLE = 0x0E00   # shield, ring, worn      -> the armor table
WEAPONRY = 0xC000   # hand, missile           -> the weapon table
CARRIED = 0x0100    # tools, keys, food       -> the misc table
IS_CONTAINER = 0x2000  # the backpack, box and bag themselves

# The FITS IN line, from `0x071d3`: three bits of the containers word, and when
# none of them is set the item is either a container's own contents or a thing
# that can only be handed between characters.
CONTAINER_BITS = ((0x8000, "BACKPACK"), (0x4000, "BOX"), (0x2000, "BAG"))
CHARACTER_PANEL = "CHARACTER PANEL"
ANY_PANEL = "ANY PANEL"

# The properties tables, as `0x0f4cc` computes them: an offset from the pool
# base, and the number of bytes it copies.
TABLES = {
    "armor": (WEARABLE, 0x0940, 12),
    "weapon": (WEAPONRY, 0x1854, 12),
    "misc": (CARRIED, 0x139C, 8),
}

# Within a properties entry. The first byte is the item's primary combat
# number (absorption for armor, damage for a weapon) and the word at 2
# carries the equip slot, the skill and the two flags (see docs/items.md).
PROP_PRIMARY = 0
PROP_FLAGS = 2
PROP_KIND = 2     # in a misc entry: what the entry's parameter means
PROP_PARAM = 4    # in a misc entry: the parameter itself

MISC_MAGIC = 0x8000     # +4 is magic points, printed as a percentage
MISC_SCROLL = 0x2600    # +4 is a 1-based spell id
MISC_DURATION = 0x1000  # the category word's bit, not the entry's

SPELL_NAME_LEN = 21

# --- REGISTER.EXE ----------------------------------------------------------

# The Restoration list registry: a table of pointers to the lists its screens
# page through, indexed by list id - 1 (image `0x06944`). Each list is a count
# word then that many 4-byte entries of (record id, flags).
#
# The registry covers the whole clue book, not just items: list 1 is the 54
# maps, list 2 the 71 creatures, list 3 the 98 spells, lists 5-10 the six
# classes' spell lists, and 12-17 the six item categories. `book_list` reads
# any of them, which is how a section knows which records the book indexes
# without a screen reading of its contents.
LIST_TABLE = 0xF6A8
LIST_ENTRY = 4

# The lists other sections ask for by name.
MAP_LIST = 1
CREATURE_LIST = 2
SPELL_LIST = 3

# Which list id goes with which caption is set by the F5 menu, one branch per
# category, as `mov ax, <caption> / mov [0xe96], ax / mov [0xe92], <list id>`.
# Reading the pairs out of those branches means the category names and the
# lists that fill them come from the file together.
_MENU_PATTERN = bytes.fromhex("a3960ec706920e")
ITEM_LIST_IDS = range(12, 18)

# The two name tables an effects entry indexes. Both are runs of fixed-width,
# NUL-terminated strings, and the offset they are indexed by is a character
# record offset: `(offset - first) // 2`.
ADDS_NAMES = (0x80F4, 0x3C, 27)   # image 0x083ef, the loop at 0x08400
PROT_NAMES = (0x7E63, 0x20, 9)    # image 0x084ea, the loop at 0x084f3

# The renderer prints an effect as PROTECTIONS when its offset is one of the
# nine condition words and as ADDS when it names an attribute or a skill.
# Both bounds are the renderer's own (`0x083c6`, `0x084c7`).
PROT_MAX = 0x30
ADDS_MIN, ADDS_MAX = 0x3C, 0xAE

# The attribute-enhancer page (image `0x06f2f`) is six rows of constants: a
# kind, an amount printed as a single ASCII digit, and which of the two
# routines prints it: `0x0709c` says ATTRIBUTE, `0x070e7` says SKILL.
ENHANCER_ROWS = 0x06F2F
ENHANCER_KINDS = ("SCROLLS", "PARCHMENTS", "WANDS", "RODS", "GEMS", "STONES")

# The three transports the book prints, from the four-entry table at ds:0x7af4.
# The renderer at `0x0797e` reads a name, a BCD value, a use count and a flag
# word; `0x07937` walks entries 0, 1 and 3, skipping the FLYING RUG.
TRANSPORT_TABLE = 0x7AF4
TRANSPORT_RECORD = 26
TRANSPORT_NAME = 0
TRANSPORT_VALUE = 0x0E   # packed BCD, four bytes
TRANSPORT_USES = 0x16
TRANSPORT_WHEN = 0x18
TRANSPORT_ANYTIME = 0x0002
TRANSPORT_PAGE = (0, 1, 3)

# The potion lines are the one part of an F5 page that is neither in WORLD.DAT
# nor in a table: `0x07429` switches on the item id and prints immediates held
# in the code. They are transcribed here with the address each was read from,
# and `verify()` asserts the bytes are still there, so a different build fails
# rather than printing the wrong figures.
#
# The id is the record index plus one, which is what `[0x5426]` holds.
POTION_LINES = {
    0x34: ("restores", 25, "PERCENT OF HEALTH"),
    0x35: ("restores", 50, "PERCENT OF HEALTH"),
    0x36: ("restores", 100, "PERCENT OF HEALTH"),
    0x37: ("restores", 50, "PERCENT OF MAGIC"),
    0x38: ("restores", 100, "PERCENT OF MAGIC"),
    0x39: ("cures", None, "SICK, POISON, DISEASE"),
    0x3D: ("damage", 60, None),
    0x3E: ("damage", 35, "POISON"),
    0x3F: ("damage", 85, "UNDEAD"),
}
# The flask is the same page but reached by a variable rather than a constant:
# `[0x5464]` is set at image 0x0f130, and its line is 40 over a 3x3.
FLASK_ID_AT = HEADER + 0x0F130 + 4  # the immediate of `mov [0x5464], <id>`
FLASK_LINE = ("damage", 40, "3 X 3")

# The MAGIC- line is gated on two more ids, at image `0x06c14`.
MAGIC_IDS = (0x1F, 0x20)

# Every immediate above, with the instruction it was read from, so that a build
# whose code differs fails loudly instead of being decoded with these numbers.
# `mov ax, <amount> / cmp word ptr [0x5426], <id>` is the shape of each arm.
def _arm(amount: int, item_id: int) -> bytes:
    return b"\xb8" + struct.pack("<H", amount) + b"\x83\x3e\x26\x54" + bytes([item_id])


_CODE_CHECKS = [
    ("potion arm", _arm(amount, item_id))
    for item_id, (_, amount, _) in POTION_LINES.items() if amount is not None
] + [
    ("cures arm", b"\x83\x3e\x26\x54\x39"),
    ("flask arm", b"\xb8\x28\x00\x8b\x16\x64\x54\x39\x16\x26\x54"),
    ("magic gate", b"\x83\x3e\x26\x54\x1f\x7c\x0c\x83\x3e\x26\x54\x20"),
    ("duration gate", b"\xf7\x44\x0c\x00\x10\x74\x05"),
    # The loader: the three properties-table offsets and the effects copy.
    ("armor table", b"\x81\xc6\x40\x09"),
    ("weapon table", b"\x81\xc6\x54\x18"),
    ("misc table", b"\x81\xc6\x9c\x13"),
]


# --- reading ---------------------------------------------------------------

def _u16(buf: bytes, off: int) -> int:
    return struct.unpack_from("<H", buf, off)[0]


def bcd(buf: bytes, off: int, length: int) -> int:
    total = 0
    for b in buf[off:off + length]:
        hi, lo = b >> 4, b & 0xF
        if hi > 9 or lo > 9:
            return 0
        total = total * 100 + hi * 10 + lo
    return total


def _ds(exe: bytes, offset: int, length: int) -> bytes:
    """A slice of the data segment, addressed the way the code addresses it."""
    start = L.DGROUP + offset
    return exe[start:start + length]


def _strings(exe: bytes, offset: int, count: int) -> list[str]:
    """`count` NUL-terminated strings starting at a DS offset.

    The field-name tables are padded to a fixed width, and a blank entry is
    meaningful: it marks an offset the table covers but the game never names.
    """
    out: list[str] = []
    pos = L.DGROUP + offset
    for _ in range(count):
        end = exe.index(b"\x00", pos)
        out.append(exe[pos:end].decode("latin1").strip())
        pos = end + 1
    return out


def book_list(exe: bytes, list_id: int) -> list[int]:
    """One of the clue book's lists, as the 1-based record ids it holds."""
    pointer = _u16(_ds(exe, LIST_TABLE + 2 * (list_id - 1), 2), 0)
    count = _u16(_ds(exe, pointer, 2), 0)
    body = _ds(exe, pointer + 2, count * LIST_ENTRY)
    return [_u16(body, k * LIST_ENTRY) for k in range(count)]


def name(rec: bytes) -> str:
    """The item's name, which runs across all three of its name fields.

    A name is a stored string, so it goes through the game's charset: the
    apostrophe is held as `~`, and MAGE'S CHAIN MAIL ARMOR is stored
    "MAGE~S CHAIN MAIL ARMOR".
    """
    parts = [L.text(rec[FIELD_BYTES + k * NAME_LEN:
                        FIELD_BYTES + k * NAME_LEN + NAME_LEN - 1]).strip()
             for k in range(NAME_FIELDS)]
    return " ".join(p for p in parts if p)


class Items:
    """Every item table in one place, read from a section directory."""

    def __init__(self, d: S.Directory):
        self.d = d
        self.exe = d.exe
        self.world = d.world
        section = d[S.ITEMS]
        self.records = section.records(d.world, RECORD)
        self.names = [name(r) for r in self.records]
        # The properties pool: `0x0f44c` reads the effects entry and all three
        # properties tables through one base, and that base is section 6. Each
        # table offset landing on a later section boundary is the check.
        self.pool = d.sections[6].offset
        for table, (_, offset, _size) in TABLES.items():
            assert any(s.offset == self.pool + offset for s in d.sections), (
                f"the {table} table is not on a section boundary")
        self.verify()

    # -- the record's own fields --

    def value(self, rec: bytes) -> int:
        return bcd(rec, VALUE, 3)

    def weight(self, rec: bytes) -> float:
        return _u16(rec, WEIGHT) / 10

    def table_of(self, rec: bytes) -> str | None:
        """Which properties table this item's pointer indexes, or None."""
        category = _u16(rec, CATEGORY)
        for table, (bits, _offset, _size) in TABLES.items():
            if category & bits:
                return table
        return None

    def properties(self, rec: bytes) -> bytes | None:
        table = self.table_of(rec)
        if table is None:
            return None
        _bits, offset, size = TABLES[table]
        at = self.pool + offset + _u16(rec, PROPS_PTR)
        return self.world[at:at + size]

    def scroll_spell(self, rec: bytes) -> str | None:
        """The spell a magic scroll teaches, by name.

        A scroll's misc entry is `10 00 00 26 <spell id> 00 00 00`, the same
        shape for all 26, and the id is 1-based into the spell table. The clue
        book's F5 page does not print it, since it is on the spell's own F3 page,
        so it is not part of `page()`.
        """
        props = self.properties(rec)
        if props is None or _u16(props, PROP_KIND) != MISC_SCROLL:
            return None
        spell = _u16(props, PROP_PARAM)
        records = self.d[S.SPELLS].records(self.world, S.SPELL_RECORD)
        if not 0 < spell <= len(records):
            return None
        return L.text(records[spell - 1][:SPELL_NAME_LEN]).strip()

    def equip_slot(self, rec: bytes) -> str | None:
        """Which slot the item is worn or wielded in, or None if it is carried.

        The clue book prints no such row: it is the equip dispatch's own
        reading of the record, and the armor entry's for the four worn slots.
        """
        category = _u16(rec, CATEGORY)
        for bit, text in SLOT_BITS:
            if category & bit:
                return text
        if category & WORN:
            props = self.properties(rec)
            flags = _u16(props, PROP_FLAGS) if props else 0
            for bit, text in WORN_BITS:
                if flags & bit:
                    return text
        return None

    def fits_in(self, rec: bytes) -> str:
        mask = _u16(rec, CONTAINERS)
        held = [text for bit, text in CONTAINER_BITS if mask & bit]
        if held:
            return " ".join(held)
        return CHARACTER_PANEL if _u16(rec, CATEGORY) & IS_CONTAINER else ANY_PANEL

    # -- the effects entry --

    def effects(self, rec: bytes) -> list[tuple[int, int]]:
        """Up to four (character-record offset, amount) pairs.

        The loop stops at a zero offset, which is how a shorter list ends.
        """
        pointer = _u16(rec, EFFECT_PTR)
        if not pointer:
            return []
        entry = self.world[self.pool + pointer:self.pool + pointer + 16]
        out = []
        for k in range(4):
            offset, amount = struct.unpack_from("<HH", entry, k * 4)
            if offset == 0:
                break
            out.append((offset, amount))
        return out

    def _named(self, effects, table, low, high) -> list[tuple[int, str]]:
        base, first, count = table
        names = _strings(self.exe, base, count)
        out = []
        for offset, amount in effects:
            if low <= offset <= high:
                index = (offset - first) // 2
                if 0 <= index < count and names[index]:
                    out.append((amount, names[index]))
        return out

    def adds(self, rec: bytes) -> list[tuple[int, str]]:
        return self._named(self.effects(rec), ADDS_NAMES, ADDS_MIN, ADDS_MAX)

    def protections(self, rec: bytes) -> list[tuple[int, str]]:
        return self._named(self.effects(rec), PROT_NAMES, 0, PROT_MAX)

    # -- the book's own filing --

    def categories(self) -> dict[str, list[int]]:
        """Each F5 category and the 1-based item ids the book files under it.

        Read from the menu branches rather than transcribed, so the caption and
        the list it opens come out of the file as a pair.
        """
        labels = L.label_index(self.exe)
        by_offset = {off - L.DGROUP: text for text, off in labels.items()}
        out: dict[str, list[int]] = {}
        pos = 0
        while True:
            pos = self.exe.find(_MENU_PATTERN, pos + 1)
            if pos < 0:
                break
            if self.exe[pos - 3] != 0xB8:
                continue
            caption = _u16(self.exe, pos - 2)
            list_id = _u16(self.exe, pos + len(_MENU_PATTERN))
            if list_id in ITEM_LIST_IDS:
                out[by_offset[caption]] = book_list(self.exe, list_id)
        assert len(out) == len(ITEM_LIST_IDS), f"found {len(out)} item categories"
        return out

    # -- the two pages that are not item lists --

    def enhancers(self) -> list[dict]:
        """The ATTRIBUTE ENHANCERS page: six kinds, an amount, and what it raises.

        The amount is printed as a single character, so the code holds it as
        one: `mov byte ptr [0xe9a], '3'`. Which of the two tail routines the row
        calls is what says ATTRIBUTE or SKILL, and they alternate.
        """
        out = []
        for k, kind in enumerate(ENHANCER_KINDS):
            digit, raises = _enhancer_row(self.exe, k)
            out.append({"kind": kind, "amount": digit, "raises": raises})
        return out

    def transports(self) -> list[dict]:
        """The TRANSPORTATIONS page: the book prints three of the four."""
        out = []
        for k in TRANSPORT_PAGE:
            rec = _ds(self.exe, TRANSPORT_TABLE + k * TRANSPORT_RECORD,
                      TRANSPORT_RECORD)
            out.append({
                "name": rec[TRANSPORT_NAME:].split(b"\x00")[0].decode("latin1").strip(),
                "value": bcd(rec, TRANSPORT_VALUE, 4),
                "uses": _u16(rec, TRANSPORT_USES),
                "when": ("ANYTIME" if _u16(rec, TRANSPORT_WHEN) & TRANSPORT_ANYTIME
                         else "BETWEEN 7P.M. AND 7A.M."),
            })
        return out

    # -- one page --

    def page(self, item_id: int) -> dict:
        """What the clue book prints for an item, keyed by its own captions.

        Only the rows the game itself would print: the renderers are gated, and
        reporting a figure the game keeps blank would be inventing one. The
        primary properties byte is absorption on the armor page and damage on
        the weapon page, and means something else again on the misc page, so it
        is read through the same gate the game uses.
        """
        rec = self.records[item_id - 1]
        props = self.properties(rec)
        table = self.table_of(rec)
        out: dict[str, object] = {
            "base value": self.value(rec),
            "weight": self.weight(rec),
            "fits in": self.fits_in(rec),
        }
        if table == "armor":
            out["absorption"] = props[PROP_PRIMARY]
            out["protections"] = [f"{amount} {what}"
                                  for amount, what in self.protections(rec)]
            out["adds"] = [f"{amount} {what}" for amount, what in self.adds(rec)]
        elif table == "weapon":
            out["damage"] = props[PROP_PRIMARY]
            out["skill"] = skill_of(_u16(props, PROP_FLAGS))
            out["2-handed"] = "YES" if _u16(props, PROP_FLAGS) & TWO_HANDED else "NO"
            out["adds"] = [f"{amount} {what}" for amount, what in self.adds(rec)]
        elif table == "misc":
            out.update(self._misc_lines(item_id, rec, props))
        return {k: v for k, v in out.items() if v not in ([], None)}

    def _misc_lines(self, item_id: int, rec: bytes, props: bytes) -> dict:
        """The misc page's one variable row, gated exactly as `0x06bf7` gates it."""
        if _u16(rec, CATEGORY) & MISC_DURATION:
            return {"duration": f"{_u16(props, PROP_PARAM) * 10} MINUTES"}
        if item_id in MAGIC_IDS:
            return {"magic": f"{_u16(props, PROP_PARAM)} PERCENT"}
        if item_id == self.flask_id():
            row, amount, suffix = FLASK_LINE
            return {row: f"{amount} {suffix}"}
        if item_id in POTION_LINES:
            row, amount, suffix = POTION_LINES[item_id]
            text = " ".join(str(p) for p in (amount, suffix) if p is not None)
            return {row: text}
        return {}

    def flask_id(self) -> int:
        return _u16(self.exe, FLASK_ID_AT)

    # -- the check that keeps the transcribed constants honest --

    def verify(self) -> None:
        for what, pattern in _CODE_CHECKS:
            assert pattern in self.exe, f"{what} not found in REGISTER.EXE"


# The weapon entry's flag word. Kept module-level because docs/items.md and the
# equip dispatch both describe it as one field.
TWO_HANDED = 0x0001
SKILL_BITS = ((0x8000, "PROJECTILE"), (0x4000, "SLASHING"),
              (0x2000, "BASHING"), (0x1000, "POLEARM"))

# Where an item is equipped. The record's category word picks the slot the
# dispatch at `0x04237` routes to; for the worn category the sub-dispatch at
# `0x0431d` reads four more bits out of the armor entry. WORN is not a slot of
# its own: an item carrying it always carries one of the four.
SLOT_BITS = ((0x8000, "MISSILE WEAPON"), (0x4000, "HAND WEAPON"),
             (0x2000, "AMMUNITION"), (0x0800, "SHIELD"), (0x0400, "RING"))
WORN = 0x0200
WORN_BITS = ((0x8000, "HEAD"), (0x4000, "BODY"),
             (0x1000, "FEET"), (0x0800, "HANDS"))


def skill_of(flags: int) -> str | None:
    for bit, text in SKILL_BITS:
        if flags & bit:
            return text
    return None


def _enhancer_row(exe: bytes, index: int) -> tuple[int, str]:
    """One row of the ATTRIBUTE ENHANCERS page: its amount and what it raises.

    The rows are a fixed sequence of `mov byte ptr [0xe9a], '<digit>'` followed
    by a call to one of two tail routines. Both are read from the code so a
    change to either shows up as a different answer rather than a silent one.
    """
    rows = []
    pos = 0
    while True:
        pos = exe.find(b"\xc6\x06\x9a\x0e", pos + 1)
        if pos < 0:
            break
        digit = exe[pos + 4]
        call = exe[pos + 5:pos + 8]
        if not (0x30 <= digit <= 0x39) or call[0] != 0xBB:
            continue
        # `mov bx, <kind> / call <tail>`; the tail's relative target separates
        # the ATTRIBUTE routine from the SKILL one.
        target = struct.unpack_from("<h", exe, pos + 9)[0] + (pos + 11)
        rows.append((digit - 0x30, target))
    assert len(rows) == len(ENHANCER_KINDS), f"{len(rows)} enhancer rows"
    tails = sorted({t for _, t in rows})
    assert len(tails) == 2, "the enhancer page should have two tail routines"
    amount, tail = rows[index]
    return amount, "ATTRIBUTE" if tail == tails[0] else "SKILL"


def load(game_dir: str | Path = "game") -> Items:
    return Items(S.load(game_dir))


if __name__ == "__main__":
    items = load()
    if len(sys.argv) > 1:
        wanted = " ".join(sys.argv[1:]).upper()
        for i, n in enumerate(items.names, 1):
            if n == wanted:
                print(f"{n}  (id {i})")
                for k, v in items.page(i).items():
                    print(f"  {k:<12} {v}")
                break
        else:
            print(f"no item named {wanted!r}")
        sys.exit(0)

    for category, ids in items.categories().items():
        print(f"{category}: {len(ids)} items")
    print()
    for rule in items.enhancers():
        article = "an" if rule["raises"][0] in "AEIOU" else "a"
        print(f"  {rule['kind']:<12} +{rule['amount']} to {article} {rule['raises'].lower()}")
    print()
    for t in items.transports():
        print(f"  {t['name']:<14} {t['value']:>6,}  {t['uses']} uses  {t['when']}")
