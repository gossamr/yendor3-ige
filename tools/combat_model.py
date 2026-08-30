"""Monsters killed between rests, for any class and any spending policy.

The manual's strategy chapters all ask one question, given a budget of bonus
points where do they go, and answer it with one measure: how many monsters
a character kills before running out of the resource that limits them. Health
limits a fighter, the magic pool limits a caster, and overkill counts for
nothing either way, because damage landing on a corpse buys nothing.

This module is that measure, written once. It was previously worked out inline
and separately for casters and for fighters, which let the two drift onto
different assumptions: different budgets, and monsters picked two different
ways. Everything here is level-matched: a character of level L is measured
against the worst monster of level L that regular play puts in front of them,
bosses excluded, because `data/enemies.json` carries a level for every monster.

    python tools/combat_model.py                # breakpoints and both policies
    python tools/combat_model.py --json

Nothing here is read out of the executable. It composes the formulas that
`tools/levels.py` and `tools/skills.py` decode, so if those are wrong this is
wrong in the same direction.
"""

from __future__ import annotations

import json
import statistics as st
from dataclasses import dataclass
from pathlib import Path

from levels import (ATTACK_ROLL, BONUS_CAP, BONUS_PCT, BONUS_THRESHOLD,
                    CLASSES, PCT_BONUS_FROM_CHARISMA, PCT_HEALTH_FROM_STAMINA,
                    PCT_MAGIC, MAGIC_BLEND, INT, WIS, pct, roll_odds)
from skills import HEALTH_PCT_OF_STAMINA, MODIFIER, casting_and_magic

ROOT = Path(__file__).resolve().parent.parent

LEVEL_CAP = 40          # the highest level the experience ladder fills in
PER_LEVEL = 2           # what a training adds to every attribute and skill
ROLL_CAP = 60           # and so the ceiling on any creation blend
TRAININGS = LEVEL_CAP - 1

# --- Resistance ------------------------------------------------------------
#
# A monster carries a word at record offset 102 naming what it shrugs off.
# Every blow builds a word describing itself, and the applier tests the two
# against each other.
#
# **Resistance is 50% and never compounds.** The check leaves on the first bit
# that matches rather than carrying on through the rest, so a monster that
# resists two of the things a blow is made of still halves it once. Blazios is
# the only monster carrying two resistance bits and no blow in the game
# matches both, so this is a statement about the code rather than a case that
# arises; it is written this way so that it stays right if either changes.
#
# See docs/monsters.md for the record layout. The offsets are read here rather
# than out of data/enemies.json because the extractor does not carry offset 100
# or 102 yet.

ENEMY_BASE, ENEMY_REC, ENEMY_COUNT = 0x417075, 106, 73
OFF_IMMUNITY, OFF_RESISTANCE = 100, 102

# What a blow sets. A shot sets bit 15, and bit 11 as well if the weapon behind
# it is enchanted; an ordinary damage spell sets bit 13. A melee swing builds no
# word at all (image 0x00E73 resolves it and 0x00EC8 subtracts it with nothing
# in between) so nothing can halve a swing.
BLOW_SHOT = 0x8000
BLOW_ENCHANTED = 0x0800
BLOW_SPELL = 0x2000
BLOW_ANTI_UNDEAD = 0x0200
BLOW_MELEE = 0x0000

# Bit 14 prints on the PHYSICAL row and no blow sets it. Nine monsters carry
# it, so on the game as shipped their RESISTANT line never fires. If it turns
# out to mean a melee swing, set this to BLOW_SHOT's sibling and every melee
# figure against those nine halves. Kept as a switch rather than a guess.
MELEE_RESISTED = False
BIT_14 = 0x4000


def resistances(path: Path | None = None) -> dict[str, dict[str, int]]:
    """{name: {"resistance": word, "immunity": word}} read from WORLD.DAT."""
    raw = (path or ROOT / "game" / "WORLD.DAT")
    if not raw.exists():
        return {}
    data = raw.read_bytes()
    out = {}
    for i in range(ENEMY_COUNT):
        rec = data[ENEMY_BASE + i * ENEMY_REC:ENEMY_BASE + (i + 1) * ENEMY_REC]
        if len(rec) < ENEMY_REC:
            break
        parts = [rec[0:13], rec[13:26]]
        name = " ".join(p.split(b"\x00")[0].decode("latin1").strip()
                        for p in parts).strip()
        if not name or name == "NOT USED":
            continue
        out[name] = {
            "resistance": int.from_bytes(
                rec[OFF_RESISTANCE:OFF_RESISTANCE + 2], "little"),
            "immunity": int.from_bytes(
                rec[OFF_IMMUNITY:OFF_IMMUNITY + 2], "little"),
        }
    return out


_RESIST_CACHE: dict[str, int] | None = None


def _from_extract() -> dict[str, int]:
    """The resistance word, offset 102 only.

    Read straight from the record rather than from the extractor's booleans,
    because `resist_magic` merges two different mechanics: bit 13 of this word,
    which halves an ordinary damage spell, and bit 4 of the *immunity* word,
    which is a different thing entirely and is handled by `immune_to`. The
    game's own F2 page merges them too, printing one MAGIC DAMAGE row, so
    the merge is faithful to the display and wrong for the arithmetic.
    """
    return {name: fields["resistance"] & (BLOW_SPELL | BLOW_SHOT | BIT_14)
            for name, fields in resistances().items()}


# Immunity is not a strong resistance. A monster immune to a damage type takes
# **nothing** from it, not half, and only from that one type. The types are the
# bottom bits of the immunity word; the top bits are the six conditions, which
# are a separate question and not damage at all.
DAMAGE_TYPES = ("MAGIC DAMAGE", "FIRE", "COLD", "ELECTRIC", "POWER")

_IMMUNE_CACHE: dict[str, set[str]] | None = None


def immune_elements() -> dict[str, set[str]]:
    """{name: the damage types that monster takes nothing from}."""
    global _IMMUNE_CACHE
    if _IMMUNE_CACHE is None:
        records = json.loads((ROOT / "data" / "enemies.json").read_text())
        records = records if isinstance(records, list) else records["enemies"]
        _IMMUNE_CACHE = {
            r["name"]: {e for e in (r.get("immune") or []) if e in DAMAGE_TYPES}
            for r in records}
    return _IMMUNE_CACHE


def immune_to(foe: dict, spell: dict) -> bool:
    """Whether this monster takes nothing at all from this spell.

    A spell with no element is not of any of the five types and so is not
    stopped by any of them; 39 of the 70 damage spells are in that position,
    which is why an immunity narrows a caster's list rather than disarming it.
    """
    elements = {e.upper() for e in (spell.get("element") or [])}
    return bool(elements & immune_elements().get(foe.get("name", ""), set()))


def foe_resistance(foe: dict) -> int:
    """The resistance word of the monster a table is measured against.

    Interpolated levels carry a made-up name and so resist nothing, which is
    the right default: the row is a line between two monsters, not one you
    can meet.
    """
    global _RESIST_CACHE
    if _RESIST_CACHE is None:
        _RESIST_CACHE = _from_extract()
    return _RESIST_CACHE.get(foe.get("name", ""), 0)


def spell_blow(spell: dict) -> int:
    """The word a spell's blow carries, from its record at offset 76.

    Across the 70 listed damage spells, 59 set bit 13 and are halved by a
    spell-resistant monster. The four that set nothing deal 10 to 45 damage,
    so there is no dodging this by spell choice.
    """
    return spell.get("blow", (spell.get("unknown") or {}).get("u76", 0))


def resisted(blow: int, monster_resistance: int) -> float:
    """The multiplier on a blow's damage: 1.0, or 0.5 if anything matches.

    Half is the floor. One matching bit is enough and further matches change
    nothing, because the check leaves as soon as one hits.

    A melee swing passes `BLOW_MELEE`, which is zero and so matches nothing --
    unless MELEE_RESISTED is turned on, which is what bit 14 would mean if it
    is ever pinned down.
    """
    word = blow
    if MELEE_RESISTED and blow == BLOW_MELEE:
        word = BIT_14
    return 0.5 if word & monster_resistance else 1.0


# --- The monsters ---------------------------------------------------------


def enemies_by_level(path: Path | None = None,
                     bosses: bool = False) -> dict[int, dict[str, float]]:
    """The worst monster at each level, gaps filled by interpolation.

    One real monster per level, not a maximum taken field by field: the four
    fields have to describe something the player can actually meet. Taking each
    field's worst independently builds a chimera: at level 40 it would carry
    the Black Dragon's absorption and accuracy with the Titan Lord's damage and
    health, which is harder than anything in the game.

    "Worst" is the monster carrying the most experience, which is the game's
    own ranking of difficulty.

    Bosses are excluded by default, because they are not what a character meets
    on an ordinary floor of a dungeon: the Titan Lord's 2,000 health is a fight
    you plan for, not one you budget a rest around. **A boss is a monster that
    carries food.** Ten of the 71 do, and they are exactly the named
    individuals (Wasp Queen, King Bariag, Pixie Leader, Acoknight, Queen
    Obversia, Vishan, King Slator, Titan Lord, Chaotic Minotaur, Blazios. At
    every other level the top two monsters are within 20% of each other on
    experience, so there is no spike left once the food-carriers are out.

    Paltivar is the exception the flag misses: it carries no food but is the
    final boss at level 45, above `LEVEL_CAP`, and serves only as the
    absorption benchmark.

    A build has to survive what the level can throw at it, which the median
    hides. Levels 12, 23, 24, 43 and 44 have no monster of their own, and
    excluding bosses empties 15 as well; a character passing through them is
    measured against the line between its neighbors rather than dropped.
    """
    rows = [e for e in json.loads(
        (path or ROOT / "data" / "enemies.json").read_text()) if e["listed"]
        and (bosses or not e["food"])]
    grouped: dict[int, list[dict]] = {}
    for e in rows:
        grouped.setdefault(e["level"], []).append(e)
    fields = ("absorption", "accuracy", "damage", "health", "dexterity")
    table = {}
    for lvl, g in grouped.items():
        worst = max(g, key=lambda e: e["experience"])
        table[lvl] = {f: float(worst[f]) for f in fields}
        table[lvl]["name"] = worst["name"]
    known = sorted(table)
    for lvl in range(known[0], known[-1] + 1):
        if lvl in table:
            continue
        lo = max(k for k in known if k < lvl)
        hi = min(k for k in known if k > lvl)
        span = hi - lo
        table[lvl] = {f: table[lo][f] + (table[hi][f] - table[lo][f])
                      * (lvl - lo) / span for f in fields}
        table[lvl]["name"] = f'between {table[lo]["name"]} and {table[hi]["name"]}'
    return table


# Group size and PARTY ATTACK, from the word at record offset 96. Bits 15/14/13
# take only three of their eight combinations (000, 110, 101) and the
# engagement code at image 0x12b5c fills three buffers of 0x9c bytes, so they
# encode how many of a monster can be fighting you at once. Bit 12 is PARTY
# ATTACK: that monster swings at all four characters instead of one.
GROUP_BITS, PARTY_ATTACK_BIT = 0xE000, 0x1000


def group_size(monster: dict) -> int:
    """How many of this monster can engage at once: 1, 2 or 3."""
    bits = monster["masks"]["w96"] & GROUP_BITS
    if not bits:
        return 1
    return 3 if bits == 0xA000 else 2


def attacks_the_party(monster: dict) -> int:
    """Attacks a full group of this monster lands on the party in a round.

    A monster takes one turn and makes one attack, so a group of three
    delivers three, spread over the four characters. A PARTY ATTACK monster
    swings at all four inside its own turn, so the same group delivers twelve.

    This is a party-wide total. What `clear_group` wants is the per-character
    rate below, which is a quarter of it: getting those two the wrong way
    round is what put a factor of four into MANUAL.md's damage-taken columns.
    """
    return group_size(monster) * (
        4 if monster["masks"]["w96"] & PARTY_ATTACK_BIT else 1)


def attacks_a_character(monster: dict) -> float:
    """Attacks ONE of these lands on ONE character in a round.

    An ordinary monster draws its target uniformly from the four party slots,
    so it averages a quarter of an attack on any one of them. A PARTY ATTACK
    monster swings at every character, so it lands exactly one on each, four
    times the damage on the character you are counting, whatever the group
    size. This is the `attacks_each` argument `clear_group` takes.
    """
    return 1.0 if monster["masks"]["w96"] & PARTY_ATTACK_BIT else 0.25


def breakpoints(table: dict[int, dict[str, float]],
                min_loss: int = 4) -> list[dict]:
    """Levels where monster absorption outruns the +2 a level you gain.

    A character's attack skill rises by exactly PER_LEVEL each training, so the
    margin only worsens where the monsters gain more than that. `min_loss` is
    how much ground has to be lost in one level to be worth naming.
    """
    out = []
    for lvl in sorted(table)[1:]:
        if lvl - 1 not in table:
            continue
        gained = table[lvl]["absorption"] - table[lvl - 1]["absorption"]
        lost = gained - PER_LEVEL
        if lost >= min_loss:
            out.append({"level": lvl, "absorption": table[lvl]["absorption"],
                        "jump": gained, "margin_lost": lost})
    return out


# --- The character ---------------------------------------------------------


def natural_attack(class_code: int, skill: str, level: int,
                   roll: int = ROLL_CAP) -> int:
    """Attack skill before any points are spent.

    The blend of an all-`roll` character is `roll` exactly, because every
    recipe's weights sum to 100. Casting is not a blend and comes from its own
    dispatch, which is why it can start above the roll.
    """
    if skill == "casting":
        base, _ = casting_and_magic(class_code, roll, roll)
    else:
        base = roll + MODIFIER[skill].get(class_code, 0)
    return base + PER_LEVEL * (level - 1) if base else 0


def best_attack(class_code: int, level: int, roll: int = ROLL_CAP
                ) -> tuple[str, int]:
    """The attack skill this class should be using, and its natural value."""
    options = ["projectile", "slashing", "bashing", "polearm", "casting"]
    scored = [(natural_attack(class_code, s, level, roll), s) for s in options]
    value, skill = max(scored)
    return skill, value


def health_pool(stamina_roll: int, level: int) -> int:
    """Maximum health at a level: the creation quarter plus a share each time.

    Non-retroactive. Each training adds a percentage of the stamina *as it
    stands then*, so points bought early are counted at every later level and
    points bought late are counted once.
    """
    total = pct(stamina_roll, HEALTH_PCT_OF_STAMINA)
    for lvl in range(1, level):
        total += pct(stamina_roll + PER_LEVEL * (lvl - 1),
                     PCT_HEALTH_FROM_STAMINA)
    return total


def magic_pool(class_code: int, level: int, int_roll: int = ROLL_CAP,
               wis_roll: int = ROLL_CAP) -> int:
    """Maximum magic points, accumulated the same non-retroactive way."""
    blend = MAGIC_BLEND.get(class_code)
    if blend is None:
        return 0
    _, total = casting_and_magic(class_code, int_roll, wis_roll)
    for lvl in range(1, level):
        attrs = {INT: int_roll + PER_LEVEL * (lvl - 1),
                 WIS: wis_roll + PER_LEVEL * (lvl - 1)}
        total += pct(sum(pct(attrs[w], p) for w, p in blend), PCT_MAGIC)
    return total


def budget(charisma_roll: int, stop_after: int) -> dict[int, int]:
    """Points free for everything else, by level, after the charisma policy.

    Charisma bought at the bonus screen reaches the stored column when the
    screen closes, so it raises every later grant, which is what makes buying
    it early worth more than it costs. `stop_after` is the last level at which
    charisma is topped up.
    """
    charisma, granted, spent, free = charisma_roll, 0, 0, {1: 0}
    for lvl in range(1, TRAININGS + 1):
        granted += min(BONUS_CAP, pct(charisma, PCT_BONUS_FROM_CHARISMA))
        if lvl <= stop_after:
            buy = max(0, min(100 - charisma, granted - spent))
            charisma += buy
            spent += buy
        charisma += PER_LEVEL
        free[lvl + 1] = granted - spent
    return free


def absorption(armor: int, dexterity: int) -> int:
    """Worn armor plus a fifth of whatever dexterity has over 72."""
    excess = dexterity - BONUS_THRESHOLD
    return armor + (pct(excess, BONUS_PCT) if excess > 0 else 0)


# The three weapons of Light hold 250 damage where the next tier holds 30, and
# cost 8,000 where that tier costs 10,000: 32 gold a point of damage against
# 333. Nothing else in the list is priced like that, and they are the only
# weapons with no enchanted forms, which is what a shop series always has. They
# are quest items: the walkthrough says to collect the ANVIL OF LIGHT, itself a
# unique worth nothing, before taking the portal. So the 8,000 is what a shop
# pays you for one rather than what one costs, and a strategy figure built on
# 250 damage describes a character who has finished a quest chain rather than
# one who has shopped. `shop_weapons` therefore keeps only the enchantable
# series, which is every weapon a merchant actually stocks.


def shop_weapons(path: Path | None = None, melee: bool = True,
                 two_handed: bool = False, items: list | None = None
                 ) -> list[tuple[int, int, str]]:
    """(damage, price, name) for every buyable weapon and enchanted form.

    `items` is the decoded records, for a caller that already holds them;
    without it they are read from data/. `two_handed` includes the two-handers
    rather than selecting them, so a caller that wants only those takes the
    difference between the two lists.

    Two-handed weapons are excluded by default. They are the only ones that
    reach 40 damage, but carrying one costs the shield: the equip dispatch
    refuses a shield while `[si+0x15c]` bit 0x20 is set, and refuses a
    two-handed weapon while the shield slot is full, and the Gold Shield's
    30 absorption is worth more than the 10 extra damage in every build.
    """
    if items is None:
        items = json.loads((path or ROOT / "data" / "items.json").read_text())
    out = []
    for i in items:
        if i["category"] != "WEAPONS" or not i["value"]:
            continue
        damage = i["fields"].get("damage")
        if not damage or not i["variants"]:      # no series = not shop stock
            continue
        ranged = i["fields"].get("skill") == "PROJECTILE"
        if ranged == melee:
            continue
        if not two_handed and i["fields"].get("2-handed") == "YES":
            continue
        base = int(damage)
        out.append((base, i["value"], i["name"]))
        out += [(base + v["plus"], v["value"], f'{i["name"]} +{v["plus"]}')
                for v in i["variants"]]
    return sorted(out, key=lambda r: -r[0])


def weapon_afforded(level: int, experience: dict[int, int],
                    share: float = 0.2, stock: list | None = None) -> int:
    """Damage of the best weapon the gold will stretch to at this level."""
    spare = (gold_earned(level, experience)
             - 100 * level * (level - 1) / 2) * share
    for damage, price, _ in (stock if stock is not None else shop_weapons()):
        if price <= spare:
            return damage
    return 1  # bare hands until the first knife


# --- What gold can actually have bought by a given level -------------------
#
# The armor track is not a free parameter. Monsters carry gold in a fixed
# ratio to the experience they give (a median of 1.11 gold per point across
# the 71 listed) so reaching a level implies having earned a knowable amount,
# and the experience ladder in REGISTER.EXE fixes what reaching it takes.

GOLD_PER_XP = 1.11
PARTY = 4
# The best set is one item per slot, not the eight highest-absorption items in
# the game: the equip dispatch at image 0x04237 reads a category from the item
# record's word at +0x0c and each destination slot must be empty, so the four
# body armors that head the absorption list compete for one place. Seven slots
# carry absorption: the shield, two rings, and four worn pieces (body, head,
# hands, feet. There is no cloak slot; robes and cloaks are body armor. Quest
# loot is excluded, since an item whose base value is zero is not something four
# characters can equip.
#
# The rings contribute 45 either way. No ring has a +N form, and the second one
# is not a second Ring of Invisibility: Yardley makes four from one copper bar,
# which is one per party member.
UNENCHANTED = (111, 13_075)   # best purchasable item per slot
ENCHANTED = (161, 442_224)    # the same slots, every piece taken as far as it
                              # goes; the difference is nearly all enchanting
# The same sets without the shield, for a two-handed weapon: a Gold Shield is
# 20 absorption for 1,000 gold, or 30 for 57,654 at +10.
UNENCHANTED_2H = (91, 12_075)
ENCHANTED_2H = (131, 384_570)
def gold_earned(level: int, experience: dict[int, int]) -> float:
    """One character's share of what the party has collected by this level."""
    return experience.get(level, 0) * GOLD_PER_XP / PARTY


def armor_afforded(level: int, experience: dict[int, int],
                    share_to_armor: float = 0.5, shield: bool = True) -> int:
    """Absorption the gold will stretch to, once training is paid for.

    Training is the one unavoidable competing cost and it is quadratic in
    level: 100 gold times the level, once per level already held. What is left
    is split between armor and everything else a party buys (weapons, food,
    potions, raising the dead) which `share_to_armor` sets. Armor is cheap
    up to the plain set and then roughly a hundred times dearer, because past
    that point the money is buying enchantment rather than another piece.
    """
    spare = (gold_earned(level, experience)
             - 100 * level * (level - 1) / 2) * share_to_armor
    if spare <= 0:
        return 0
    plain_cap, plain_cost = UNENCHANTED if shield else UNENCHANTED_2H
    if spare <= plain_cost:
        return int(spare / (plain_cost / plain_cap))
    top_cap, top_cost = ENCHANTED if shield else ENCHANTED_2H
    per_point = (top_cost - plain_cost) / (top_cap - plain_cap)
    return min(top_cap, plain_cap + int((spare - plain_cost) / per_point))


# --- The fight -------------------------------------------------------------


def hit_odds(margin: float) -> float:
    return roll_odds(ATTACK_ROLL, int(margin))


def landed(damage: float, margin: float) -> float:
    if margin < 0:
        return 0.0
    return max(1.0, damage * margin / 100)


def expected(damage: float, accuracy: float, opposing: float) -> float:
    margin = accuracy - opposing
    return hit_odds(margin) * landed(damage, margin)


@dataclass
class Encounter:
    """One character against the median monster of their own level."""

    level: int
    accuracy: float
    damage: float
    absorption: float
    health: float
    pool: float = 0.0        # magic points; 0 for a class that has none
    cost: float = 0.0        # magic points per cast

    def kills_per_rest(self, foe: dict[str, float]) -> float:
        """Monsters killed before the limiting resource runs out.

        Overkill is discarded: however hard an attack lands, one attack kills
        at most one monster. Health limits a fighter and the pool limits a
        caster, so whichever runs out first is the one that counts.
        """
        out = expected(self.damage, self.accuracy, foe["absorption"])
        if out <= 0:
            return 0.0
        per_attack = min(1.0, out / foe["health"])
        incoming = expected(foe["damage"], foe["accuracy"], self.absorption)
        attacks = float("inf") if incoming <= 0 else self.health / incoming
        if self.cost:
            attacks = min(attacks, self.pool / self.cost)
        return attacks * per_attack


def clear_group(output: float, incoming: float, monster_health: float,
                size: int, attacks_each: int, first: bool,
                arriving: int = 1) -> tuple[int, float]:
    """Rounds to clear a group, and damage one character takes doing it.

    Monsters are not all present when the fight starts. The engagement code
    adds them one at a time as each closes to melee, so `arriving` is how many
    join per round: 1 if you are fighting somewhere they reach you singly, up
    to `size` if you let them gather. That spread is the whole of tactical play:
    against the same monsters a party that kills as fast as they arrive can
    take nothing at all, and the same party letting three close at once can
    take more than its health.

    `output` is the party's damage a round, `incoming` one attack's damage,
    `attacks_each` what one monster puts on one character a round.
    """
    remaining, engaged, killed = size, 0, 0
    current, taken, rounds = 0.0, 0.0, 0
    while killed < size and rounds < 100:
        rounds += 1
        join = min(arriving, remaining)
        remaining -= join
        engaged += join
        if current <= 0 and engaged > killed:
            current = monster_health
        if not first:
            taken += (engaged - killed) * incoming * attacks_each
        spare = output
        while spare > 0 and killed < size and engaged > killed:
            if spare >= current:
                spare -= current
                killed += 1
                current = monster_health if engaged > killed else 0.0
            else:
                current -= spare
                spare = 0.0
        if killed >= size:
            break
        if first:
            taken += (engaged - killed) * incoming * attacks_each
    return rounds, taken


def grants(charisma_roll: int, stop_after: int) -> list[tuple[int, int]]:
    """(level reached, points free to spend on arrival), for each training."""
    charisma, granted, spent, out = charisma_roll, 0, 0, []
    for lvl in range(1, TRAININGS + 1):
        granted += min(BONUS_CAP, pct(charisma, PCT_BONUS_FROM_CHARISMA))
        if lvl <= stop_after:
            buy = max(0, min(100 - charisma, granted - spent))
            charisma += buy
            spent += buy
        charisma += PER_LEVEL
        out.append((lvl + 1, granted - spent))
    return out


CAP_PER_REST = 100  # past this the limiting resource is not the constraint


def spell_options(class_name: str, level: int) -> list[tuple[float, float]]:
    """(damage, magic cost) for every damage spell learned by this level."""
    import spell_curve

    return [(s["damage"], s["mp"])
            for lvl, s in spell_curve.for_class(spell_curve.load(), class_name)
            if lvl <= level and s["mp"]]


def first_strike_cost(level: int, table: dict[int, dict[str, float]],
                      charisma_roll: int = 52) -> int:
    """Dexterity points needed to act before the worst monster of this level.

    Turn order is rebuilt every round and sorted by dexterity, so this is a
    running requirement, not a one-off. It is a threshold rather than a scale --
    matching the monster wins the round as completely as passing it by fifty --
    so buying ahead of the monster in front of you is damage you did not do.

    **Matching is enough.** Characters are added to the turn list before
    monsters and the sort only moves an entry when the one behind is strictly
    faster, so a monster of equal dexterity still acts second. The total lands
    on a multiple of five, which the absorption bonus wants anyway.
    """
    natural = ROLL_CAP + PER_LEVEL * (level - 1)
    need = max(0, int(table[level]["dexterity"]) - natural)
    while need and (natural + need) % 5:
        need += 1
    return need


def career(class_code: int, switch: int, first: str, second: str,
           *, charisma_roll: int = 52, stop_after: int = 4,
           armor: int = ENCHANTED[0], weapon: float = 30.0,
           first_strike: bool = False, dex_from: int | None = None) -> dict:
    """Walk a character to level 40 under an ordered spending policy.

    The order is charisma, then `first`, then optionally dexterity, then
    `second`. `first` is bought at every training up to and including `switch`;
    charisma is handled before that by `stop_after`.

    `first_strike` inserts the dexterity phase **after** `first` rather than
    reserving points across it. That ordering matters for a caster: intelligence
    compounds, since a point adds to the pool at every training still to come,
    so dexterity bought during the intelligence years costs endgame pool twice
    over. Bought after them it costs only the skill points it displaces. The
    phase runs until dexterity clears the monster of the level and then stops,
    because turn order is a threshold and buying past it is wasted.

    `dex_from` makes that a third phase with a level of its own: from `dex_from`
    on, everything goes to dexterity instead of `second`, and it keeps going
    past first strike rather than stopping there. A caster has three places to
    put points where a fighter has two, so the second switch is a real decision
    and `caster_schedule` in `ladder.py` searches both at once.

    Returns kills per rest at each level, so a policy can be judged on the whole
    run as well as at the end.
    """
    table = enemies_by_level()
    caster = class_code in MAGIC_BLEND
    class_name = CLASSES[class_code].upper()
    skill, _ = best_attack(class_code, 1)
    bought = {"attack": 0, "intelligence": 0, "dexterity": 0}
    per_level, detail, held = {}, {}, 0
    for level, free in grants(charisma_roll, stop_after):
        gain = free - held
        held = free
        if level <= switch:
            bought[first] += gain
        elif dex_from is not None and level >= dex_from:
            bought["dexterity"] += gain
        else:
            if first_strike:
                take = max(0, min(gain, first_strike_cost(level, table)
                                  - bought["dexterity"]))
                bought["dexterity"] += take
                gain -= take
            bought[second] += gain
        accuracy = natural_attack(class_code, skill, level) + bought["attack"]
        dexterity = ROLL_CAP + PER_LEVEL * (level - 1) + bought["dexterity"]
        shared = dict(level=level, accuracy=accuracy,
                      absorption=absorption(armor, dexterity),
                      health=health_pool(52, level))
        if caster:
            pool = magic_pool(class_code, level,
                              ROLL_CAP + bought["intelligence"],
                              ROLL_CAP + bought["intelligence"])
            # The spell to cast is the one that kills most before the pool runs
            # out, which is rarely the hardest-hitting one: a cheap spell that
            # still kills outright beats an expensive one that overkills.
            #
            # "Outright" is the part that has to be enforced. `kills_per_rest`
            # scores a fractional kill per cast, so without this filter the
            # cheapest spell in the list wins by being cast hundreds of times:
            # Magic Attack at 9 damage and 2 magic scores 27 kills against a
            # Black Dragon it would need 38 casts to bring down. Spells that
            # kill in one cast are preferred, and the rest of the list is the
            # fallback for levels where nothing does.
            options = spell_options(class_name, level) or [(0.0, 0.0)]
            margin = shared["accuracy"] - table[level]["absorption"]
            lethal = [ds for ds in options
                      if landed(ds[0], margin) >= table[level]["health"]]
            best = max(lethal or options,
                       key=lambda ds: Encounter(damage=ds[0], pool=pool,
                                                cost=ds[1], **shared
                                                ).kills_per_rest(table[level]))
            fight = Encounter(damage=best[0], pool=pool, cost=best[1], **shared)
        else:
            fight = Encounter(damage=weapon, **shared)
        per_level[level] = min(CAP_PER_REST, fight.kills_per_rest(table[level]))
        foe = table[level]
        margin = fight.accuracy - foe["absorption"]
        detail[level] = {
            "accuracy": accuracy, "dexterity": dexterity,
            "absorption": fight.absorption, "pool": fight.pool,
            "cost": fight.cost, "spell": fight.damage,
            "margin": margin, "hit": hit_odds(margin),
            "dealt": landed(fight.damage, margin),
            "foe_health": foe["health"],
            "bought": dict(bought),
        }
    return {"per_level": per_level, "skill": skill, "detail": detail,
            "career": sum(per_level.values()), "at_20": per_level.get(20),
            "at_40": per_level.get(40)}


def main(argv: list[str]) -> None:
    table = enemies_by_level()
    steps = [s for s in breakpoints(table) if s["level"] <= LEVEL_CAP]
    if "--json" in argv:
        print(json.dumps({"breakpoints": steps}, indent=2))
        return
    print("Levels where the monsters gain more absorption than your +2:\n")
    print(f"  {'level':>5} {'absorption':>11} {'jump':>6} {'margin lost':>12}")
    for s in steps:
        print(f"  {s['level']:>5} {s['absorption']:>11.0f} "
              f"{s['jump']:>+6.0f} {s['margin_lost']:>12.0f}")

    print("\nMage: intelligence first, then casting.")
    print(f"  {'switch at':>10} {'career':>9} {'at 20':>8} {'at 40':>8}")
    for switch in (0, 8, 11, 13, 16, 20):
        r = career(7, switch, "intelligence", "attack")
        print(f"  {switch:>10} {r['career']:>9.0f} {r['at_20']:>8.1f} "
              f"{r['at_40']:>8.1f}")

    print("\nFighter: weapon skill first, then dexterity (armor 161).")
    print(f"  {'switch at':>10} {'career':>9} {'at 20':>8} {'at 40':>8}")
    for switch in (40, 35, 30, 25, 20, 15):
        r = career(1, switch, "attack", "dexterity")
        fmt = lambda v: "never dies" if v == float("inf") else f"{v:.1f}"
        print(f"  {switch:>10} {r['career']:>9.0f} {fmt(r['at_20']):>8} "
              f"{fmt(r['at_40']):>8}")


if __name__ == "__main__":
    import sys

    main(sys.argv[1:])
