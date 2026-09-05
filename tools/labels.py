"""UI label strings lifted out of REGISTER.EXE.

The game builds its Restoration ("on-line clue book") screens from a
contiguous run of NUL-separated strings near the end of the executable's data.
That run is the authoritative naming for the binary tables: it gives the field
captions, the ordered effect names behind the immunity/resistance bitmasks,
the special-attack vocabulary, the item categories and the magic-user classes.

We read the strings from the file rather than transcribing them, so a
different build produces different labels instead of silently mislabeled data.
"""

from __future__ import annotations

from pathlib import Path

LABEL_REGION = (0x2A780, 0x2B300)

# The game's character set substitutions: it has no apostrophe glyph and uses
# '~' instead, and writes fractions like "1\2" with a backslash. Every stored
# string goes through these, item names included: "MAGE~S CHAIN MAIL ARMOR"
# is a raw read, not a name.
CHARSET = str.maketrans({"~": "'", "\\": "/"})


def text(raw: bytes) -> str:
    """One stored string: NUL-terminated, space-padded, in the game's charset."""
    return raw.split(b"\x00")[0].decode("latin1").translate(CHARSET).rstrip()


def read_strings(exe: bytes, start: int, end: int, minimum: int = 2) -> list[tuple[int, str]]:
    """Every printable-ASCII run of `minimum`+ chars in [start, end), with offsets."""
    out: list[tuple[int, str]] = []
    cur = bytearray()
    begin = start
    for i in range(start, min(end, len(exe))):
        b = exe[i]
        if 0x20 <= b < 0x7F:
            if not cur:
                begin = i
            cur.append(b)
        else:
            if len(cur) >= minimum:
                out.append((begin, cur.decode("latin1")))
            cur.clear()
    if len(cur) >= minimum:
        out.append((begin, cur.decode("latin1")))
    return out


def label_index(exe: bytes) -> dict[str, int]:
    """Label text -> file offset, for the Restoration label region."""
    return {text: off for off, text in read_strings(exe, *LABEL_REGION)}


# --- Ordered enumerations -------------------------------------------------
#
# Order matters: these are read off the EXE in the order the strings appear,
# which is the order the game's screens print them. Where a mapping onto a
# binary field has been confirmed against the data it is noted; where it has
# not, the consumer keeps the field as `unknown_*`.

# The twelve effects behind the monster IMMUNE / RESISTANT rows, in EXE order.
EFFECTS = [
    "POISON", "DISEASE", "PARALYSIS", "FREEZING", "HEXING", "CURSING",
    "FIRE", "COLD", "ELECTRIC", "POWER", "MAGIC DAMAGE", "PHYSICAL DAMAGE",
]

# The monster stat captions, in EXE order. Note the *record* order differs:
# see extract.ENEMY_FIELDS for the confirmed byte offsets.
MONSTER_STATS = [
    "STRENGTH", "HEALTH", "ACCURACY", "DEXTERITY",
    "ABSORPTION", "DAMAGE", "RANGED ACC.", "RANGED DAM.",
]

# Where the data segment starts in the file. The startup stub does
# `mov ax, 0x1ddb0 >> 4 / mov ds, ax`, so a DS offset is this plus the offset
# (see docs/leveling.md). Tables addressed as DS:xxxx are read through it.
DGROUP = 0x1DDB0 + 0x4000

SPECIAL_ATTACKS = [
    "PARTY ATTACK", "BREAK", "DESTROY", "POISON", "DISEASE", "PARALYZE",
    "FROZEN", "STONING", "JINXING", "HEXING", "CURSING", "STEAL GOLD",
    "STEAL FOOD", "STEAL NUORE", "PROJECTILE", "WEAPON", "SHIELD",
]

ITEM_CATEGORIES = [
    "ARMOR / RINGS", "ATTRIBUTE ENHANCERS", "JEWELS/ORES/UNIQUE ITEMS",
    "MAGIC SCROLLS", "POTIONS / MAGIC FOOD", "SUPPLIES",
    "TRANSPORTATIONS", "WEAPONS",
]

CONTAINERS = ["CHARACTER PANEL", "ANY PANEL", "BACKPACK", "BOX", "BAG"]

# Six magic-user classes, each with three advancement tiers.
CLASS_TIERS = [
    ("MONK", "CLERIC", "PRIEST"),
    ("ALCHEMIST", "TRANSMUTER", "HEALER"),
    ("PALADIN", "CAVALIER", "HERO"),
    ("MAGE", "WIZARD", "SORCERER"),
    ("DRUID", "ENCHANTER", "SAGE"),
    ("MARKSMAN", "RANGER", "KNIGHT"),
]

SKILL_RATINGS = ["POOR", "AVERAGE", "GOOD", "GREAT"]

# The only two words an F2 effect row can hold. They sit consecutively in the
# label run at 0x2AAB0, so the column's whole vocabulary comes out of the file
# and tools/read_stats.py only has to say which of the two a row holds.
EFFECT_VALUES = ["IMMUNE", "RESISTANT"]

SPELL_AFFECTS = [
    "ALL", "ONE", "MONSTER", "CHARACTER",
    "VISIBLE MONSTERS", "VISIBLE UNDEADS", "INSECT", "UNDEAD", "CREATION",
]

SPELL_WHEN = [
    "IN HAND TO HAND", "IN A STRAIGHT LINE", "IN A 3X3 AREA",
    "AT A DISTANCE", "OUT OF HAND TO HAND", "ANYTIME",
]

RESTORATION_MENU = [
    "F1 MAPS (WORLD, TOWNS, MINES, ETC.)",
    "F2 MONSTER STATISTICS",
    "F3 SPELLS (INFORMATION ON ALL SPELLS)",
    "F4 MAGIC USERS (SPELLS BY CLASS)",
    "F5 INVENTORY ITEMS (ARMOR, POTIONS, ETC.)",
    "F6 COMPLETE WALK THROUGH OF THE GAME",
]

# The words the three screens in front of the world are built out of, at their
# own DS offsets rather than in the Restoration run: the game draws these with
# its own text routine as each screen is put up (docs/creation.md). The five
# words the first menu offers are not here, because that screen is a picture:
# they are painted into run 0 picture 2 along with its wall.
CREATION_LABELS = {
    "screen": 0x7C94,           # CHARACTER CREATION
    "pick_class": 0x7CA7,
    "quit": 0x7D17,             # QUIT "CREATE"
    "male": 0x7D25,
    "female": 0x7D2C,
    "pick_portrait": 0x7D33,
    "select": 0x7D43,           # SELECT AN
    "option": 0x7D4D,
    "class": 0x7D54,
    "take_four": 0x7D5A,        # TAKE UP TO FOUR
    "items": 0x7D6A,
    "name_character": 0x7D70,
    "enter_name": 0x7D7F,
    "keep_character": 0x7D8E,
    "preview": 0x7D9D,          # CHARACTER PREVIEW
    "delete": 0x7DAF,
    "return": 0x7DB6,
    "sure": 0x7DBD,             # ARE YOU SURE?
    "yes_delete": 0x7DCB,
    "no_keep": 0x7DD7,
    "portrait": 0x8863,
    "roll_attributes": 0x8899,
    "pick_items": 0x88A9,
    # The disk panel's own, which is where a party is written down and read
    # back: the game reaches it from inside the world rather than from the
    # menu, but the words are the same ones.
    "save": 0x7C20,
    "load": 0x7C25,
    "new_game": 0x8712,
}


def creation_labels(exe: bytes) -> dict[str, str]:
    """The creation screens' own words, by the name this module gives each."""
    return {name: text(exe[DGROUP + at:DGROUP + at + 32])
            for name, at in CREATION_LABELS.items()}


# Every string above must actually be present in the EXE; verify() proves it.
_ALL = (EFFECTS + MONSTER_STATS + SPECIAL_ATTACKS + ITEM_CATEGORIES
        + CONTAINERS + SKILL_RATINGS + EFFECT_VALUES + SPELL_WHEN
        + RESTORATION_MENU + [t for tier in CLASS_TIERS for t in tier])


def verify(exe: bytes) -> list[str]:
    """Return the labels this module names that the EXE does not contain.

    Matching is loose about the trailing punctuation the game uses for
    captions (`STRENGTH-`, `POISON:`), which is presentation, not identity.
    """
    blob = exe[LABEL_REGION[0]:LABEL_REGION[1]]
    return [s for s in _ALL if s.encode("latin1") not in blob]


def load(game_dir: str | Path = "game") -> bytes:
    return (Path(game_dir) / "REGISTER.EXE").read_bytes()


if __name__ == "__main__":
    exe = load()
    missing = verify(exe)
    print(f"{len(_ALL)} declared labels, {len(missing)} missing from the EXE")
    for m in missing:
        print("  MISSING:", m)
    idx = label_index(exe)
    print(f"\n{len(idx)} strings in the label region {LABEL_REGION[0]:#x}-{LABEL_REGION[1]:#x}")
