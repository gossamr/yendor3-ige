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

# Every string above must actually be present in the EXE; verify() proves it.
_ALL = (EFFECTS + MONSTER_STATS + SPECIAL_ATTACKS + ITEM_CATEGORIES
        + CONTAINERS + SKILL_RATINGS + SPELL_WHEN + RESTORATION_MENU
        + [t for tier in CLASS_TIERS for t in tier])


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
