"""Leveling, training and bonus points, read out of REGISTER.EXE.

None of this lives in `WORLD.DAT`: the experience ladder, the price of a
training session and the spells a class is handed on the way up are all
constants compiled into the executable's data segment, and the arithmetic that
turns a character's attributes into health, magic and bonus points is inline
code. This module reads the tables from the file and mirrors the formulas, so
a different build produces different numbers instead of silently wrong ones.

    python tools/levels.py             # the whole report
    python tools/levels.py --json      # the same, machine-readable

Coordinates. The game is a real-mode 16-bit program whose startup stub does
`mov ax, 0x1ddb; mov ds, ax`, so DGROUP begins at image offset 0x1ddb0, i.e.
file offset 0x21db0 once the 16 KB header is added. Every `DS_*` constant
below is an offset the code uses directly.

Everything here was read out of the disassembly, not off the running game --
`inferred` in the sense tools/README.md uses, with one anchor in observed
data: the four PRE-CREATED PARTY records in WORLD.DAT are level-1 characters
whose attributes fall in the 45..60 window character creation rolls, both
endpoints included.
"""

from __future__ import annotations

import json
import struct
from dataclasses import dataclass, field
from pathlib import Path

HEADER = 0x400 * 16
DGROUP = 0x1DDB
DBASE = HEADER + DGROUP * 16  # file offset of DS:0000

# --- Addresses, all DS-relative unless the name says otherwise -------------

DS_XP_TABLE = 0xC75F  # 4-byte packed-BCD thresholds, one per level from 2
DS_XP_TABLE_END = 0xC8C3  # the code's own bound: `cmp di, 0xc8c3 / jae`
DS_SPELLS_BY_LEVEL = 0xB8B5  # 6 magic classes x 40 words
DS_PROMOTE_2 = 0x5448  # set to 10 by the init block at image 0x0f0e2
DS_PROMOTE_3 = 0x544A  # set to 30 there too

LEVEL_CAP = 0x5A  # `cmp [si+0x16], 0x5a` clamps level at 90
BONUS_CAP = 0x0F  # `cmp ax, 0xf` clamps bonus points at 15
STAT_CAP = 0x3E7  # add_stat's ceiling for everything but health/magic
POOL_CAP = 0x270F  # ...which get 9999 instead
TRAIN_BASE_PRICE = 0x64  # `mov ax, 0x64` before the price quote
POINTS_BASE_PRICE = 0x3E8  # the bonus-point vendor's `mov ax, 0x3e8`

# Percentages the level-up code passes to the round-to-nearest helper at
# image 0x15862: `mul bx / add ax, 50 / div 100`.
PCT_HEALTH_FROM_STAMINA = 0x1E  # 30
PCT_BONUS_FROM_CHARISMA = 0x0D  # 13
PCT_MAGIC = 0x1E  # 30, applied to the class-weighted attribute blend

# Strength adds to damage, and dexterity to absorption, only above 72, and
# then only a fifth of the excess (image 0x05c44). Creation rolls 45-60, so
# both bonuses start at zero for every character in the game.
BONUS_THRESHOLD = 0x48   # 72
BONUS_PCT = 0x14         # 20

# Which melee skill a weapon draws on, by the flag in its record's word 2
# (image 0x0652a). A weapon carrying none of these adds no accuracy at all.
WEAPON_SKILL = {0x4000: "slashing", 0x2000: "bashing", 0x1000: "polearm"}


# The attack resolver, at image 0x1586f. Five call sites, and one routine
# settles every attack in the game: melee, missile, spell and monster. There is
# no second roll and no constant multiplier anywhere in it; see ATTACK_ROLL
# below.
ATTACK_ROLL = 0x37  # rand(55): 56 values, not equally likely; see roll_odds


def roll_odds(n: int, threshold: int) -> float:
    """P(rand(n) <= threshold), for the generator at image 0x174ac.

    The generator masks its 16-bit output down to the bit width of `n` and
    subtracts `n` once if the result still overshoots. So the raw range is
    0..2**k-1 for the smallest k with 2**k > n, and the values 1..2**k-1-n are
    reached twice while 0 and the rest are reached once. It is uniform only
    when n is one less than a power of two.
    """
    raw = 1
    while raw <= n:
        raw *= 2
    folded = raw - 1 - n           # 1..folded are hit twice
    if threshold < 0:
        return 0.0
    threshold = min(threshold, n)
    return (threshold + 1 + min(folded, threshold)) / raw


def attack_margin(accuracy: int, absorption: int) -> int:
    return accuracy - absorption


def attack_hit_odds(accuracy: int, absorption: int) -> float:
    """Probability the attack lands. A negative margin can never hit."""
    return roll_odds(ATTACK_ROLL, attack_margin(accuracy, absorption))


def attack_damage(damage: int, accuracy: int, absorption: int) -> int:
    """Damage on a hit: the margin doubles as the percentage delivered.

    A landed hit always does at least 1. Because the same margin decides both
    whether you hit and how hard, a margin over 100 delivers more than the
    damage stat, which is as close to a critical hit as the game gets.
    """
    margin = attack_margin(accuracy, absorption)
    if margin < 0 or damage == 0:
        return 0
    return max(1, pct(damage, margin))


def attack_expected(damage: int, accuracy: int, absorption: int) -> float:
    return attack_hit_odds(accuracy, absorption) * attack_damage(
        damage, accuracy, absorption)


def attribute_bonus(value: int) -> int:
    """Strength's contribution to damage, or dexterity's to absorption."""
    excess = value - BONUS_THRESHOLD
    return pct(excess, BONUS_PCT) if excess > 0 else 0

# --- The character record --------------------------------------------------
#
# 500 bytes. Two parallel 64-byte stat blocks hold the same 27 fields in the
# same order as the labels at REGISTER.EXE:0x29EA4 (STRENGTH, DEXTERITY,
# STAMINA, INTELLIGENCE, WISDOM, CHARISMA, five unnamed combat fields, HEALTH,
# MAGIC POINTS, one unnamed, then the twelve skills, then one unnamed).
#
# CURRENT is the working copy the game plays with, the only column the panel
# prints, and the one equipment bonuses are added into. BASE is the stored
# character: what the level-up raises and what its formulas read.
#
# The two are kept in step by a matched pair of block copies. `commit` (image
# 0x0a631) writes CURRENT over BASE; `revert` (image 0x0a659) writes BASE over
# CURRENT. Both copy indices 0-10 and 13-26, skipping health and magic. The
# bonus-point screen reverts on entry and commits on exit (images 0x09d2a and
# 0x09d6c), which is what makes spent points permanent and why the level-up's
# +2 reaches the working column. Resting reverts too, which is how a drained
# stat recovers. Damage subtracts from
# CURRENT health (`sub [bx+0x52], ax` at image 0x03737) and potions clamp it
# to BASE health, which is what fixes the two blocks' roles.

REC_SIZE = 500
OFF_NAME = 0x00  # 14 bytes
OFF_CLASS = 0x0E  # 1..9, +10 per promotion tier
OFF_LEVEL = 0x16
OFF_EXPERIENCE = 0x18  # 4 bytes, packed BCD like the enemy rewards
OFF_CONDITIONS = 0x1C
OFF_READY_LEVEL = 0x1E  # 0 = not ready; otherwise the level trainable now

# The four party slots, as a table of four record handles at DS:0xd0c9. Every
# loop over the party walks it: the attack round at image 0x0c186, the round's
# per-character readouts, and the creature target picker at 0x125b3.
PARTY_TABLE = 0xD0C9
PARTY_SIZE = 4
CURRENT = 0x3C  # stat index 0 of the current column
BASE = 0x7C  # stat index 0 of the base column
STAT_STRIDE = 2

# Indices 6-10 have blank captions in the label run, but the equipment
# assembly at image 0x0649e names them by construction: it adds the projectile
# skill and the missile weapon's damage into 6 and 7, the matching melee skill
# and the hand weapon's damage into 8 and 9, and armor into 10, and the F1
# panel prints 8, 9 and 10 beside the captions ACCURACY, DAMAGE and ABSORPTION.
STAT_NAMES = [
    "strength", "dexterity", "stamina", "intelligence", "wisdom", "charisma",
    "ranged_accuracy", "ranged_damage", "accuracy", "damage", "absorption",
    "health", "magic_points", "unknown_13",
    "survival", "projectile", "slashing", "bashing", "polearm", "casting",
    "mapping", "navigation", "bartering", "repair", "thievery", "linguistics",
    "unknown_26",
]
STR_, DEX, STA, INT, WIS, CHA = range(6)
HEALTH, MAGIC = 11, 12
FIRST_SKILL, LAST_SKILL = 14, 25

# Classes, in the order character creation lists them at 0x29A5B. The record
# stores 1..9; the two promoted tiers add 10 and 20, which the level-up code
# undoes by subtracting 10 until the value drops to 9 or below.
CLASSES = [
    None, "fighter", "merchant", "rogue", "monk",
    "alchemist", "paladin", "mage", "druid", "marksman",
]

# How each class turns attributes into magic points, straight off the dispatch
# at image 0x09a9a. Classes 1-3 never reach it and gain nothing.
MAGIC_BLEND: dict[int, list[tuple[int, int]]] = {
    4: [(WIS, 100)],            # monk        100% cleric
    5: [(WIS, 75), (INT, 25)],  # alchemist    75% cleric  25% wizard
    6: [(WIS, 50)],             # paladin      50% cleric  50% fighter
    7: [(INT, 100)],            # mage        100% wizard
    8: [(INT, 75), (WIS, 25)],  # druid        75% wizard  25% cleric
    9: [(INT, 50)],             # marksman     50% wizard  50% fighter
}
MAGIC_CLASS_ORDER = [4, 5, 6, 7, 8, 9]  # the spell table's six rows


def load(path: str | Path = "game/REGISTER.EXE") -> bytes:
    return Path(path).read_bytes()


def ds(offset: int) -> int:
    """File offset of DS:offset."""
    return DBASE + offset


# --- The arithmetic --------------------------------------------------------


def pct(value: int, percent: int) -> int:
    """The helper at image 0x15862: `mul bx / add ax, 50 / div 100`.

    Round-to-nearest, and it discards DX before dividing, so it is only
    correct while value * percent stays under 65486, which every caller
    does, the largest being 999 * 100.
    """
    return (value * percent + 50) // 100


def bonus_points(base_charisma: int) -> int:
    """Training points granted at a level-up, capped at 15.

    Read off the *base* charisma column, never the current one. Bonus points
    spent on charisma raise only the current column, so pumping charisma does
    not buy more points at the next training: the ceiling is what counts,
    and it moves by exactly +2 a level.
    """
    return min(BONUS_CAP, pct(base_charisma, PCT_BONUS_FROM_CHARISMA))


def health_gain(base_stamina: int) -> int:
    return pct(base_stamina, PCT_HEALTH_FROM_STAMINA)


def magic_gain(class_code: int, base_int: int, base_wis: int) -> int:
    """0 for the six non-casting class codes; otherwise the class blend.

    The blend is summed at full precision and only then run through the 30%
    step, matching `[0x53ee] += pct(...)` followed by `pct(total, 30)`.
    """
    tier_free = class_code
    while tier_free > 9:
        tier_free -= 10
    blend = MAGIC_BLEND.get(tier_free)
    if blend is None:
        return 0
    attrs = {INT: base_int, WIS: base_wis}
    total = sum(pct(attrs[which], weight) for which, weight in blend)
    return pct(total, PCT_MAGIC)


def training_cost(level: int, npc_factor: int) -> int:
    """Gold for one training session, at a trainer with the given factor.

    The quote routine at image 0x091eb multiplies its base price by the NPC
    record's word at +0x18, then adds that product to a 32-bit BCD accumulator
    once per level the character already has. `level` is therefore the level
    being trained *from*, not the one being trained to.
    """
    return TRAIN_BASE_PRICE * npc_factor * level


# --- Shop prices -----------------------------------------------------------
#
# Every service an NPC sells is quoted by the one routine at image 0x091eb:
# a base price, multiplied by the NPC's own factor at `+0x18`, then added into
# a 32-bit BCD accumulator once per level the character already has. Only the
# base differs between services.

SERVICE_BASE = {
    "train": 0x64,            # one level, image 0x09e15
    "bonus_points": 0x3E8,    # per point, image 0x0981a
    "replenish_health": 0x14,  # image 0x099a9
    "raise_dead": 0x64,       # image 0x09992
}

# Cure-conditions has no fixed base: the routine at image 0x092b1 sums a weight
# for each condition bit that is set. Nine conditions occupy bits 15 down to 7.
#
# The bit order is NOT the order the PROTECTIONS panel prints the names in.
# What fixes it is the resist chain at image 0x03875, which pairs each attack
# bit with the protection field that defends against it: bit 0x8000 adds
# `[bx+0x24]`, the third protection word, so bit 15 is sickness rather than
# disease. Each row below is (name, bit, cure weight, protection field).
CONDITIONS = (
    ("sickness", 0x8000, 5, 0x24),
    ("poison", 0x4000, 10, 0x22),
    ("disease", 0x2000, 20, 0x20),
    ("paralyze", 0x1000, 40, 0x2A),
    ("frozen", 0x0800, 50, 0x28),
    ("stoning", 0x0400, 60, 0x26),
    ("jinxing", 0x0200, 20, 0x30),
    ("hexing", 0x0100, 30, 0x2E),
    ("cursing", 0x0080, 40, 0x2C),
)
PROTECTIONS = 0x20  # nine words, in the order the panel prints them
DEAD_BIT = 0x40          # set when current health hits 0, image 0x03745

# stoning | frozen | paralyze | dead. One mask takes a character out of play
# everywhere: it blocks training (image 0x065c5), drops them from the attack
# round (0x0c196), and makes creatures reroll rather than target them
# (0x125dc). The other five conditions leave a character acting and targetable.
INCAPACITATED = 0x1C40

# Which party member a creature attacks, at image 0x125b3: rand(3) picks one of
# the four PARTY_TABLE slots, and the roll repeats while the slot is empty or
# INCAPACITATED. Nothing weights the choice by slot, so the game has no front
# or back rank. Nor could it: the party is a single point, and the
# hand-to-hand/ranged distinction is measured from that one position against
# the creature's (image 0x1252d) rather than per character.
TARGET_ROLL = PARTY_SIZE - 1  # rand() is inclusive; see ATTACK_ROLL above

# Printable keys are dispatched through a jump table at image 0x777, indexed
# (ascii - 0x20) * 2 (image 0x0011a). `A` and `S` both enter ATTACK_ROUTINE,
# guarded by opposite senses of HAND_TO_HAND, so exactly one of the two is live
# at any moment and the other returns without spending a turn. `S` additionally
# sets VOLLEY, which is what selects the four-slot party volley inside.
KEY_HANDLERS = 0x777
ATTACK_ROUTINE = 0x0C13E
STATE_WORD = 0x5370
HAND_TO_HAND = 0x1000    # a creature has closed; set at image 0x12b6a
MODE_WORD = 0x536E
VOLLEY = 0x100

SUPPLIES_PER_UNIT = 10   # food and nuore, image 0x06107; flat, minimum 10 units

# What the bartering skill does, from image 0x0a6aa. The selected barterer's
# *working* bartering value (char+0x68, the column bonus points move, not the
# natural one the level-up grows) picks a spread percentage from this ladder,
# and the item's stored value is then scaled to `100 + p` percent to buy and
# `100 - p` percent to sell. The final `(999, 55)` rung is the compare against
# the stat cap; above it the code falls through to 55 again, so it is dead.
BARTER_SPREAD = ((54, 55), (64, 45), (79, 35), (100, 25),
                 (124, 15), (149, 8), (999, 2))


def barter_spread(bartering: int) -> int:
    """The spread percentage a barterer of this skill gets."""
    for ceiling, spread in BARTER_SPREAD:
        if bartering <= ceiling:
            return spread
    return 55


def buy_price(value: int, bartering: int) -> int:
    return value * (100 + barter_spread(bartering)) // 100


def sell_price(value: int, bartering: int) -> int:
    return value * (100 - barter_spread(bartering)) // 100


def cure_base(conditions: int) -> int:
    """Base price to cure whichever condition bits are set."""
    return sum(w for _, bit, w, _f in CONDITIONS if conditions & bit)


def restore_base(conditions: int, hurt: bool, dead: bool) -> int:
    """`TO COMPLETELY RESTORE YOU`: cures, plus health, plus raising."""
    return (cure_base(conditions)
            + (SERVICE_BASE["replenish_health"] if hurt else 0)
            + (SERVICE_BASE["raise_dead"] if dead else 0))


SKILL_CHECK_FLOOR = 5      # `cmp ax, 5 / jg` at image 0x17892
SKILL_CHECK_PER_LEVEL = 5  # `mov ax, 5 / imul bx` at image 0x17889
SKILL_CHECK_ROLL = 100     # rand(100): 101 values, 1..27 twice as likely


def skill_check_chance(skill: int, level: int, difficulty: int) -> int:
    """The number the d100 must not exceed, from the resolver at 0x17882.

    `skill + 5 x (level - difficulty)`, floored at 5. A level is therefore
    worth five skill points on every check that goes through here: picking a
    lock, disarming a trap, resisting a condition, sizing up a monster.
    """
    return max(SKILL_CHECK_FLOOR,
               skill + SKILL_CHECK_PER_LEVEL * (level - difficulty))


def skill_check_odds(skill: int, level: int, difficulty: int) -> float:
    """Probability of success: `rand(100)` must not exceed the chance.

    The roll runs 0..100 but is not flat: 1..27 come up twice as often as
    anything else, so a low chance succeeds more often than its face value.
    """
    return roll_odds(SKILL_CHECK_ROLL,
                     skill_check_chance(skill, level, difficulty))


def service_cost(base: int, level: int, npc_factor: int) -> int:
    """Gold for any quoted service: base x the NPC's factor x current level."""
    return base * npc_factor * level


def bonus_point_cost(level: int, points: int) -> int:
    """Gold at the vendor who sells bonus points outright (image 0x097db).

    The same quote routine, with a base of 1000, and for this NPC the word
    at +0x18 is both the number of points handed over and the multiplier, so
    the price per point is flat.
    """
    return POINTS_BASE_PRICE * points * level


# --- The tables ------------------------------------------------------------


def bcd(raw: bytes) -> int:
    """Packed BCD, most significant pair first, as the reward fields use."""
    return int(raw.hex())


SENTINEL_XP = 99_999_999  # every rung past level 40 holds this and nothing pays it


def experience_table(exe: bytes) -> dict[int, int]:
    """Level -> experience needed to become ready for it.

    89 four-byte entries covering levels 2..90. The ladder is only filled in
    through level 40; every entry past it is 99,999,999, which no reward in
    the game can reach, so 40 is the real cap and 90 only the clamp.
    """
    start, end = ds(DS_XP_TABLE), ds(DS_XP_TABLE_END)
    raw = exe[start:end]
    assert len(raw) % 4 == 0, "experience table does not divide into dwords"
    return {i // 4 + 2: bcd(raw[i:i + 4]) for i in range(0, len(raw), 4)}


def reachable_levels(table: dict[int, int]) -> int:
    """The highest level whose threshold is not the 99,999,999 sentinel."""
    return max(lvl for lvl, xp in table.items() if xp < SENTINEL_XP)


def spells_by_level(exe: bytes) -> dict[str, dict[int, list[int]]]:
    """class -> even level -> spell records granted on reaching it.

    `test [si+0x16], 1 / jne` skips odd levels outright, and the index is
    `level / 2 - 1` into 20 four-byte slots, so a class can learn at most two
    spells at each of levels 2, 4, ... 40. Zero is the empty slot.
    """
    out: dict[str, dict[int, list[int]]] = {}
    for row, class_code in enumerate(MAGIC_CLASS_ORDER):
        start = ds(DS_SPELLS_BY_LEVEL) + row * 0x50
        words = struct.unpack_from("<40H", exe, start)
        per_level: dict[int, list[int]] = {}
        for slot in range(20):
            got = [w for w in words[slot * 2:slot * 2 + 2] if w]
            if got:
                per_level[(slot + 1) * 2] = got
        out[CLASSES[class_code]] = per_level
    return out


def promotion_levels(exe: bytes) -> tuple[int, int]:
    """The two levels at which the class code gains 10 and takes a new title.

    Stored as zero in the file and written by the init block at image 0x0f0e2,
    so they are read from the instruction stream rather than from data.
    """
    image = 0x0F0E2
    tier2 = struct.unpack_from("<H", exe, HEADER + image + 4)[0]
    tier3 = struct.unpack_from("<H", exe, HEADER + image + 10)[0]
    return tier2, tier3


# --- Report ----------------------------------------------------------------


@dataclass
class Report:
    experience: dict[int, int]
    reachable: int
    level_clamp: int = LEVEL_CAP
    promote: tuple[int, int] = (0, 0)
    spells: dict[str, dict[int, list[int]]] = field(default_factory=dict)


def build(exe: bytes) -> Report:
    table = experience_table(exe)
    return Report(
        experience=table,
        reachable=reachable_levels(table),
        promote=promotion_levels(exe),
        spells=spells_by_level(exe),
    )


def main(argv: list[str]) -> None:
    exe = load()
    rep = build(exe)

    if "--json" in argv:
        print(json.dumps({
            "experience": rep.experience,
            "reachable_level": rep.reachable,
            "level_clamp": rep.level_clamp,
            "promotion_levels": list(rep.promote),
            "spells_by_level": rep.spells,
        }, indent=2))
        return

    print(f"Levels: ladder filled through {rep.reachable}, "
          f"clamped at {rep.level_clamp}; promotions at {rep.promote[0]} and {rep.promote[1]}")
    print()
    print("  level   experience     delta")
    prev = 0
    for lvl in range(2, rep.reachable + 1):
        xp = rep.experience[lvl]
        print(f"  {lvl:>5}   {xp:>10,}  {xp - prev:>+10,}")
        prev = xp
    print()

    print("Bonus points against base charisma (15 is the cap):")
    row = [f"{c}->{bonus_points(c)}" for c in range(45, 125, 5)]
    print("  " + "  ".join(row))
    print()

    print("Training cost = 100 x trainer factor x current level. At factor 1:")
    print("  " + "  ".join(f"L{l}={training_cost(l, 1):,}" for l in (1, 5, 10, 20, 39)))
    print()

    print("Spells granted, by class and level:")
    for name, per_level in rep.spells.items():
        got = ", ".join(f"{lvl}:{ids}" for lvl, ids in sorted(per_level.items()))
        print(f"  {name:<10} {got}")


if __name__ == "__main__":
    import sys

    main(sys.argv[1:])
