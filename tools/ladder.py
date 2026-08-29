"""Regenerates the strategy tables `MANUAL.md` prints.

Those tables were hand-computed and their derivations were never written down,
which cost a session of reverse-engineering the column definitions back out of
the printed numbers, and hid two errors while it did. This module is the
derivation. Change a build or a basis here and re-run; do not edit the numbers
in the manual by hand.

    python tools/ladder.py             # every table, on the real roll
    python tools/ladder.py --compare   # the same, beside the flat-roll model

`--compare` exists because the roll changed once already: `rand(55)` is not
uniform (see `docs/combat.md`), and being able to print both models beside each
other is what showed that the correction moves the defensive columns and leaves
every offensive one untouched. If a third model ever turns up, add it here
rather than re-deriving the tables.

## Who is fighting whom

Two framings, and mixing them up is the other easy mistake.

**The ladder, the bosses, the marginal-points table and the career walk are
party against group**: offence is *four* characters of the same build, focus
-firing the selected creature, and every damage-taken figure is what **one** of
those four takes. The two do not scale together: four characters deal four
times the damage, but against a PARTY ATTACK creature each of them still takes
the whole group's attention, so a party of four facing three Black Dragons is
absorbing 2,076 a round between them while one character sees 519 of it.

**`survival()` alone is solo**: one character with the whole group on him and
nobody else swinging. That is the worst case the game offers and the right one
for sizing armor, and it is why its rounds-to-kill are four times longer than
the ladder's.

Four identical builds is a modelling convenience, not a party anyone plays --
the manual's own advice is to mix one berserker with a healer. A mixed party is
not modeled here.

## The conventions, which are the part that goes wrong

**`attacks_each` is one creature's attacks on one character**, so it is 1 for a
PARTY ATTACK creature and 0.25 for anything else. `attacks_the_party` is the
party-wide total and is four times larger; passing it to `clear_group` is the
mistake that put a factor of four into the damage-taken columns.

**"Party rounds" is `group x health / (4 x one character's output)`**, four
characters of the same build, overkill not carried between creatures.

**"Taken all three" is the fight lost**, `arriving=group`: everything closes
before you kill anything. The other bound, `arriving=1`, is still computed but
is not worth a column: creatures of one type share a dexterity and the sort is
stable, so they act as a block, and a party that outruns them lands its whole
round before any of them swings. That makes the one-at-a-time case entirely
determined by whether the party one-rounds an arrival, which is printed as its
own yes/no instead.

**Every build spends 510 points**, which is what a charisma roll of 52 pays out
over 39 trainings once 40 have gone into charisma itself. The totals below add
up to exactly that, and `budget()` is where the number comes from.

**The basis creature is the hardest regular creature of the level**, one real
creature, chosen by experience with bosses excluded, not a field-by-field
maximum over the level. `enemies_by_level` does that.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import combat_model as C
import levels as L

LEVEL = 40
NATURAL_SKILL = C.natural_attack(1, "slashing", LEVEL)      # 143
NATURAL_ATTR = C.ROLL_CAP + C.PER_LEVEL * (LEVEL - 1)       # 138
HEALTH = C.health_pool(52, LEVEL)                           # 1066
ARMOUR_SHIELD, ARMOUR_2H = C.ENCHANTED[0], C.ENCHANTED_2H[0]
PARTY = 4

def raw(name):
    """The creature's record with its mask words, which `enemies_by_level`
    drops. `group_size` and `attacks_a_character` both need them."""
    import json
    records = json.loads((C.ROOT / "data" / "enemies.json").read_text())
    records = records if isinstance(records, list) else records["enemies"]
    return {c["name"]: c for c in records}[name]


# Weapon damage, from `shop_weapons`: 30 is the best one-handed purchase
# (Emerald Cutlass +8, Sapphire Cudgel +8) and 40 the best two-handed
# (2-Handed Sword +10 and two others), which costs the shield.
ONE_HANDED, TWO_HANDED = 30, 40


class Build:
    """One column of the ladder. Skill, strength and dexterity are points
    *bought*; the natural value of each is added here, not by the caller."""

    def __init__(self, name, skill, strength, dexterity, weapon, armour):
        self.name = name
        self.skill, self.strength, self.dexterity = skill, strength, dexterity
        self.weapon, self.armour = weapon, armour

    @property
    def spent(self):
        return self.skill + self.strength + self.dexterity

    @property
    def accuracy(self):
        return NATURAL_SKILL + self.skill

    @property
    def damage(self):
        return self.weapon + L.attribute_bonus(NATURAL_ATTR + self.strength)

    @property
    def absorption(self):
        return self.armour + L.attribute_bonus(NATURAL_ATTR + self.dexterity)


# The berserker's split is 331/47/132, which is what MANUAL.md's derived tables
# were computed from (absorption 171, accuracy 474). Its *schedule* table quotes
# 336/47/127 instead. Both spend 510; they are two different builds and the
# manual prints them as one. 331/47/132 is kept here because it is the split the
# numbers in the manual belong to.
BUILDS = [
    Build("Berserker",   331, 47, 132, TWO_HANDED, ARMOUR_2H),
    Build("Rarely hit",  276, 47, 187, ONE_HANDED, ARMOUR_SHIELD),
    Build("Untouchable", 176,  2, 332, ONE_HANDED, ARMOUR_SHIELD),
]
# The healer spends its 510 on wisdom, dexterity and casting instead, so it has
# no weapon row; only its absorption is comparable.
HEALER = Build("Healer", 0, 0, 127, ONE_HANDED, ARMOUR_SHIELD)


# --- the two roll models ---------------------------------------------------

def folded(margin):
    """What the generator at image 0x174ac actually does."""
    return L.roll_odds(L.ATTACK_ROLL, int(margin))


def flat(margin):
    """The model the manual's tables were computed under: an even d56."""
    if margin < 0:
        return 0.0
    return min(int(margin) + 1, L.ATTACK_ROLL + 1) / (L.ATTACK_ROLL + 1)


def per_hit(damage, margin):
    return 0 if margin < 0 else max(1, L.pct(int(damage), int(margin)))


def output(odds, damage, accuracy, absorption):
    """One attacker's expected damage a round."""
    margin = accuracy - absorption
    return odds(margin) * per_hit(damage, margin)


# --- the tables ------------------------------------------------------------

def ladder(odds, foe):
    """MANUAL: *One ladder, three places to stop*, and *Where the three builds
    stand at level 40*."""
    record = raw(foe["name"])
    atk, size = C.attacks_a_character(record), C.group_size(record)
    rows = []
    for b in list(BUILDS) + [HEALER]:
        margin = foe["accuracy"] - b.absorption
        incoming = odds(margin) * per_hit(foe["damage"], margin)
        mine = PARTY * output(odds, b.damage, b.accuracy, foe["absorption"])
        rows.append({
            "build": b.name,
            "absorption": b.absorption,
            "hit_you": odds(margin),
            # What lands when it lands. `taken_a_round` folds the hit chance
            # in, which is the healing cadence; this is the survivability
            # figure, and against three creatures the worst round is 3x it.
            "per_hit": per_hit(foe["damage"], margin),
            "party_rounds": size * foe["health"] / mine if mine else None,
            "one_rounds": bool(mine) and mine >= foe["health"],
            "acts_first": NATURAL_ATTR + b.dexterity > foe["dexterity"],
            "taken_a_round": incoming * size * atk,
            "taken_singly": C.clear_group(mine, incoming, foe["health"], size,
                                          atk, True, arriving=1)[1],
            "taken_together": C.clear_group(mine, incoming, foe["health"], size,
                                            atk, True, arriving=size)[1],
        })
    rows[-1]["party_rounds"] = None       # the healer carries no weapon
    rows[-1]["taken_singly"] = rows[-1]["taken_together"] = None
    return rows


# Paltivar is the fastest and the hardest-swinging thing in the game, and two of
# the stops are named by it rather than by the creature of the level.
PALTIVAR_DEX, PALTIVAR_ACC = 265, 240

# Each stop says what it is aiming at, because they do not all aim at the same
# thing. "turn order" buys dexterity until nothing outruns you and stops; a
# number is a chance of being hit, measured against `acc`. The berserker is the
# only one carrying a two-hander, which costs it the shield's 30 absorption and
# is why its chance is so much worse for the same money.
STOPS = (
    ("Berserker",     "turn order", PALTIVAR_ACC, True),
    ("Half the time",  0.50,        None,         False),
    ("Rarely hit",     0.266,       None,         False),
    ("Untouchable",    0.0,         PALTIVAR_ACC, False),
)


def stops(odds, foe, targets=STOPS, budget=510):
    """STRATEGY: *pick a stopping point*. One row per stop, all from one place.

    A stop is a chance of being hit, and the dexterity that reaches it is
    whatever the armour of the day leaves to buy. Two of them are measured
    against Paltivar rather than against the creature of the level: the
    berserker because turn order is the one thing it will not go without, and
    the untouchable stop because being unhittable by the last boss is the point
    of paying for it.

    Everything after the purchase is the same fight against the level's own
    group: four of the build, `arriving=size` for the lost-fight column because
    that is the engagement nobody controlled.
    """
    record = raw(foe["name"])
    atk, size = C.attacks_a_character(record), C.group_size(record)
    rows = []
    for name, target, acc, two_handed in targets:
        weapon = TWO_HANDED if two_handed else ONE_HANDED
        armour = ARMOUR_2H if two_handed else ARMOUR_SHIELD
        if target == "turn order":
            # Matching is enough: characters sort ahead of creatures on a tie.
            dexterity = max(0, PALTIVAR_DEX - NATURAL_ATTR)
            while (NATURAL_ATTR + dexterity) % 5:
                dexterity += 1
        else:
            aim = foe["accuracy"] if acc is None else acc
            for dexterity in range(0, budget + 1):
                absorb = armour + L.attribute_bonus(NATURAL_ATTR + dexterity)
                if odds(aim - absorb) <= target:
                    break
            else:
                continue
        spare = budget - dexterity
        build = max(
            (Build(name, spare - st, st, dexterity, weapon, armour)
             for st in range(spare + 1)),
            key=lambda b: output(odds, b.damage, b.accuracy, foe["absorption"]))
        margin = foe["accuracy"] - build.absorption
        incoming = odds(margin) * per_hit(foe["damage"], margin)
        mine = PARTY * output(odds, build.damage, build.accuracy,
                              foe["absorption"])
        blow = per_hit(foe["damage"], margin)
        rows.append({
            "build": name, "target": target,
            "dexterity": build.dexterity,
            "sheet": NATURAL_ATTR + build.dexterity,
            "skill": build.skill, "strength": build.strength,
            "weapon": weapon, "absorption": build.absorption,
            "hit_you": odds(margin),
            "per_hit": blow if odds(margin) else 0,
            "worst_round": blow * size if odds(margin) else 0,
            "party_rounds": size * foe["health"] / mine if mine else None,
            "one_rounds": bool(mine) and mine >= foe["health"],
            "taken_together": C.clear_group(mine, incoming, foe["health"], size,
                                            atk, True, arriving=size)[1],
            "health": HEALTH,
        })
    return rows


def skill_returns(odds, foe, points=(0, 70, 176, 276, 336)):
    """MANUAL: *Past the breakpoints it keeps paying*. One character, one
    weapon, clearing the whole group alone."""
    damage = ONE_HANDED + L.attribute_bonus(NATURAL_ATTR + 47)
    out = []
    for spent in points:
        accuracy = NATURAL_SKILL + spent
        margin = accuracy - foe["absorption"]
        mine = output(odds, damage, accuracy, foe["absorption"])
        out.append({
            "points": spent, "margin": margin, "hit": odds(margin),
            "per_hit": per_hit(damage, margin),
            "rounds": (C.group_size(raw(foe["name"])) * foe["health"] / mine
                       if mine else None),
        })
    return out


def survival(odds, foe, roll=52):
    """MANUAL: *Two ways to stay alive*. ONE character alone with the whole
    group already on him, the worst case the game offers, and the case armor
    has to be sized against. Not a party: `kill_in` is that one character
    clearing the group by himself.

    A stamina policy switching at level L spends `grants(52, 4)[L]` points on
    stamina and every later point on weapon skill, so the rows differ only in
    where the same budget went. They buy no dexterity at all, which is the
    comparison being made: a health pool against not being hit in the first
    place.
    """
    record = raw(foe["name"])
    atk, size = C.attacks_a_character(record), C.group_size(record)
    free = dict(C.grants(roll, 4))

    def stamina_policy(switch):
        """Health at 40, and the points left for weapon skill."""
        bought = free[switch] if switch > 1 else 0
        per_level = bought / (switch - 1) if switch > 1 else 0
        health, stamina = L.pct(roll, 25), 0.0
        for lvl in range(1, LEVEL):
            if switch > 1 and lvl <= switch:
                stamina += per_level
            health += L.pct(int(roll + C.PER_LEVEL * (lvl - 1) + stamina),
                            L.PCT_HEALTH_FROM_STAMINA)
        return free[LEVEL] - bought, health

    rows = []
    for label, switch in (("All to weapon skill", 0), ("Stamina through 15", 15),
                          ("Stamina through 20", 20)):
        skill, health = stamina_policy(switch)
        rows.append((Build(label, skill, 0, 0, ONE_HANDED, ARMOUR_SHIELD),
                     health))
    rows += [(b, HEALTH) for b in BUILDS]

    out = []
    for b, health in rows:
        mine = output(odds, b.damage, b.accuracy, foe["absorption"])
        kill = size * foe["health"] / mine if mine else float("inf")
        margin = foe["accuracy"] - b.absorption
        incoming = odds(margin) * per_hit(foe["damage"], margin) * size * atk
        die = health / incoming if incoming else float("inf")
        out.append({"policy": b.name, "health": health,
                    "absorption": b.absorption,
                    "hit_you": odds(margin),
                    "per_hit": per_hit(foe["damage"], margin),
                    "kill_in": kill, "die_in": die, "safety": die / kill})
    return out


def bosses(odds, names=("PALTIVAR", "CHAOTIC MINOTAUR", "BLAZIOS",
                        "TITAN LORD")):
    """MANUAL: *The four bosses*. A party of four against one of them; rounds
    to bring it down, and what each character takes a round meanwhile."""
    out = []
    for name in names:
        c = raw(name)
        atk = C.attacks_a_character(c)
        row = {"boss": name, "health": c["health"], "accuracy": c["accuracy"],
               "builds": {}}
        for b in BUILDS:
            mine = PARTY * output(odds, b.damage, b.accuracy, c["absorption"])
            margin = c["accuracy"] - b.absorption
            row["builds"][b.name] = {
                "rounds": c["health"] / mine if mine else None,
                "hit_you": odds(margin),
                "per_hit": per_hit(c["damage"], margin),
                "taken_a_round": odds(margin) * per_hit(c["damage"], margin) * atk,
            }
        out.append(row)
    return out


def caster(odds, foe, area_damage=350):
    """MANUAL: *A mage at level 40*. The same three rungs on a caster, whose
    accuracy is its casting skill. `area_damage` is Earthquake's record damage;
    one-rounding the group is what the rung is bought for."""
    natural = C.natural_attack(7, "casting", LEVEL)
    out = []
    for name, dexterity, casting in (("First strike", 117, 315),
                                     ("Rarely hit", 187, 245),
                                     ("Untouchable", 332, 100)):
        margin = natural + casting - foe["absorption"]
        absorption = ARMOUR_SHIELD + L.attribute_bonus(NATURAL_ATTR + dexterity)
        dealt = per_hit(area_damage, margin)
        out.append({"rung": name, "dexterity": dexterity, "casting": casting,
                    "margin": margin, "absorption": absorption,
                    "hit_you": odds(foe["accuracy"] - absorption),
                    "per_hit": per_hit(foe["damage"],
                                       foe["accuracy"] - absorption),
                    "area_damage": dealt,
                    "one_rounds": dealt >= foe["health"]})
    return out


def rung_at(target, odds, foe, budget=510, weapon=ONE_HANDED,
            armour=ARMOUR_SHIELD):
    """The cheapest build whose chance to be hit is at most `target`.

    The rarely-hit rung was named for one swing in four and priced under a flat
    roll, where margin 13 was 25%. Under the real roll it is 34%, so the rung
    has to be re-bought. Dexterity is raised to the first total that reaches the
    target, and what is left of the budget is split between weapon skill and
    strength by brute force rather than by the crossover rule: the rule is a
    derivative and the split here is a few points either side of it.
    """
    for dexterity in range(0, budget + 1):
        absorption = armour + L.attribute_bonus(NATURAL_ATTR + dexterity)
        if odds(foe["accuracy"] - absorption) <= target:
            break
    else:
        return None
    spare = budget - dexterity
    best = max(
        (Build("", spare - st, st, dexterity, weapon, armour)
         for st in range(spare + 1)),
        key=lambda b: output(odds, b.damage, b.accuracy, foe["absorption"]))
    return best


# --- the same policies, walked from level 15 to 40 -------------------------
#
# Everything above is a level-40 snapshot. A build is really a *policy* for
# spending points as they arrive, and whether the snapshot's verdict holds for
# the twenty-five levels before it is a separate question: the creatures gain
# absorption and accuracy on their own schedule, and the budget and the gold
# arrive on theirs.

POLICIES = ("Berserker", "Rarely hit", "Untouchable")


def build_at(policy, level, odds, target=0.266, share_to_armour=0.5):
    """The cheapest build following `policy` at `level`, or None if the rung is
    out of reach on that level's budget.

    Common to all three: dexterity first, to whatever the policy needs, and
    never less than first strike: turn order is a running cost every build
    pays. What is left goes to weapon skill and strength, split by brute force.
    """
    table = C.enemies_by_level()
    experience = L.experience_table(L.load())
    foe = table[level]
    budget = dict(C.grants(52, 4))[level]
    natural_attr = C.ROLL_CAP + C.PER_LEVEL * (level - 1)
    natural_skill = C.natural_attack(1, "slashing", level)
    two_handed = policy == "Berserker"
    armour = C.armor_afforded(level, experience, share_to_armour,
                              shield=not two_handed)
    weapon = C.weapon_afforded(level, experience, 0.2,
                               C.shop_weapons(two_handed=two_handed))

    def absorb(dexterity):
        return armour + L.attribute_bonus(natural_attr + dexterity)

    first_strike = C.first_strike_cost(level, table)
    need = first_strike
    if policy != "Berserker":
        aim = 0.0 if policy == "Untouchable" else target
        for dexterity in range(first_strike, budget + 1):
            if odds(foe["accuracy"] - absorb(dexterity)) <= aim:
                need = dexterity
                break
        else:
            return None                      # not reachable on this budget
    if need > budget:
        return None
    spare = budget - need

    def damage(strength):
        return weapon + L.attribute_bonus(natural_attr + strength)

    best = max(range(spare + 1),
               key=lambda st: output(odds, damage(st),
                                     natural_skill + spare - st,
                                     foe["absorption"]))
    return {
        "level": level, "policy": policy, "budget": budget,
        "skill": spare - best, "strength": best, "dexterity": need,
        "first_strike": first_strike, "armour": armour, "weapon": weapon,
        "accuracy": natural_skill + spare - best, "damage": damage(best),
        "absorption": absorb(need), "health": C.health_pool(52, level),
        "foe": foe,
    }


def career_table(policy, odds, levels=range(15, LEVEL + 1)):
    """What the policy actually delivers at every level it can be run at."""
    rows = []
    for level in levels:
        b = build_at(policy, level, odds)
        if b is None:
            rows.append({"level": level, "policy": policy, "reachable": False})
            continue
        foe, record = b["foe"], raw_by_level(level)
        size = C.group_size(record)
        atk = C.attacks_a_character(record)
        margin = foe["accuracy"] - b["absorption"]
        blow = per_hit(foe["damage"], margin)
        mine = PARTY * output(odds, b["damage"], b["accuracy"],
                              foe["absorption"])
        together = C.clear_group(mine, odds(margin) * blow, foe["health"],
                                 size, atk, True, arriving=size)[1]
        rows.append({
            "level": level, "policy": policy, "reachable": True,
            "creature": foe["name"], "group": size, "budget": b["budget"],
            "dexterity": b["dexterity"], "first_strike": b["first_strike"],
            "skill": b["skill"], "strength": b["strength"],
            "armour": b["armour"], "weapon": b["weapon"],
            "absorption": b["absorption"], "hit_you": odds(margin),
            "per_hit": blow, "worst_round": blow * size,
            "health": b["health"],
            "party_rounds": size * foe["health"] / mine if mine else None,
            "one_rounds": bool(mine) and mine >= foe["health"],
            "taken_together": together,
        })
    return rows


def raw_by_level(level):
    """The basis creature's record, or the nearest real one when the level is
    interpolated: `enemies_by_level` fills the gaps with a synthetic row."""
    name = C.enemies_by_level()[level]["name"]
    try:
        return raw(name)
    except KeyError:
        for step in range(1, 6):
            for near in (level - step, level + step):
                if near in C.enemies_by_level():
                    try:
                        return raw(C.enemies_by_level()[near]["name"])
                    except KeyError:
                        continue
        raise


def marginal(odds, foe, extra=15, builds=None):
    """STRATEGY: *What fifteen more do at level 40*. Where a build's next points
    are worth most, which is not always its own headline stat.

    `builds` defaults to the printed BUILDS, which are the pre-correction
    reference the ladder is pinned to. Pass `allocation`'s rungs to read the
    marginal point on the builds STRATEGY actually recommends.
    """
    record = raw(foe["name"])
    atk, size = C.attacks_a_character(record), C.group_size(record)
    out = []
    for b in (BUILDS if builds is None else builds):
        base = size * foe["health"] / (
            PARTY * output(odds, b.damage, b.accuracy, foe["absorption"]))
        row = {"build": b.name, "rounds": base}
        for field in ("skill", "strength"):
            grown = Build(b.name, b.skill + (extra if field == "skill" else 0),
                          b.strength + (extra if field == "strength" else 0),
                          b.dexterity, b.weapon, b.armour)
            mine = PARTY * output(odds, grown.damage, grown.accuracy,
                                  foe["absorption"])
            row[f"into_{field}"] = size * foe["health"] / mine
        taken = []
        for absorption in (b.absorption,
                           b.armour + L.attribute_bonus(
                               NATURAL_ATTR + b.dexterity + extra)):
            margin = foe["accuracy"] - absorption
            taken.append(odds(margin) * per_hit(foe["damage"], margin)
                         * size * atk)
        row["taken_now"], row["into_dexterity"] = taken
        out.append(row)
    return out


# --- the caster and the healer ---------------------------------------------
#
# A martial build splits its points two ways, hitting against staying alive. A
# caster splits them three, because intelligence is the pool and the pool is
# how many casts it gets, so `caster_schedule` searches both switches at once
# rather than assuming the fighter's answer transfers.

MAGE = 7
MONK = 4    # the healer: same shape, but the pool attribute is wisdom
SWITCHES = (0, 8, 12, 14, 18, 20, 24)
# Columns below 30 are left out on purpose. They hold the grid's highest single
# cells and its lowest ones, because starting dexterity early makes the spell
# the character can afford flip between one level and the next, and the career
# total then swings by a third on a one-level change to the policy. Those are
# spell-availability steps, not an optimum. Averaged down the intelligence
# switches, `dex from 35` wins on both its mean and its worst case.
DEX_FROM = (None, 40, 38, 35, 33, 30)


def caster_schedule(switches=SWITCHES, dex_froms=DEX_FROM):
    """STRATEGY: *the caster's two switches*. Creatures killed between rests
    over the whole career, for every combination of `intelligence through X`
    and `dexterity from Y`.

    Intelligence compounds, since a point adds to the pool at every training
    still to come, and casting does not, so buying the compounding one first is
    worth more than any ratio between them. That argues for a late switch, and
    on this measure alone the peak sits around 18.

    Read it with `dead_levels` beside it, which is the constraint that actually
    binds. A career sum rewards the endgame pool and says nothing about when
    the pool arrives, so it scores a caster that cannot one-cast anything from
    level 14 to 24 above one that can. The sum is not the objective.
    """
    rows = []
    for switch in switches:
        row = {"switch": switch, "kills": {}}
        for dex in dex_froms:
            r = C.career(MAGE, switch, "intelligence", "attack", dex_from=dex)
            row["kills"][dex] = r["career"]
        rows.append(row)
    return rows


def dead_levels(switches=SWITCHES, levels=range(12, LEVEL + 1),
                class_code=MAGE):
    """STRATEGY: *why the switch is early*. Levels at which no spell the caster
    owns kills a creature of its own level in one cast.

    Margin scales spell damage exactly as it scales a weapon's, so a caster
    that spends its early points on the pool has a large pool and a spell that
    lands for nothing. The fallback is Magic Attack at 9 damage, which is 38
    casts against a Black Dragon and not a fight anyone plays. This counts the
    levels where that is the best the character can do.
    """
    table = C.enemies_by_level()
    name = C.CLASSES[class_code].upper()
    out = []
    for switch in switches:
        detail = C.career(class_code, switch, "intelligence",
                          "attack")["detail"]
        dead = [lvl for lvl in levels
                if not any(C.landed(dmg, detail[lvl]["margin"])
                           >= table[lvl]["health"]
                           for dmg, _ in C.spell_options(name, lvl))]
        out.append({"switch": switch, "dead": dead, "count": len(dead),
                    "worst_run": _longest_run(dead)})
    return out


def _longest_run(levels):
    best = run = 0
    previous = None
    for lvl in levels:
        run = run + 1 if previous is not None and lvl == previous + 1 else 1
        previous, best = lvl, max(best, run)
    return best


def intelligence_years(switches=(0, 12, 18), levels=(12, 14, 16, 18, 20, 24)):
    """STRATEGY: *what the intelligence years cost*. Why the hit column does
    not show the bill.

    Hit rate saturates at 100% and then stops telling you anything, so a caster
    that has spent its early points on the pool looks identical to one that has
    not. The cost is in casts per kill instead: `dealt` against `foe_health` is
    how much of a creature one cast removes.
    """
    runs = {s: C.career(MAGE, s, "intelligence", "attack") for s in switches}
    out = []
    for level in levels:
        row = {"level": level,
               "foe_health": runs[switches[0]]["detail"][level]["foe_health"],
               "by_switch": {}}
        for s in switches:
            d = runs[s]["detail"][level]
            row["by_switch"][s] = {
                "hit": d["hit"], "dealt": d["dealt"],
                "casts": d["foe_health"] / d["dealt"] if d["dealt"] else None,
            }
        out.append(row)
    return out


def caster_rungs(odds, foe, budget=510, intelligence=78, area_damage=350):
    """STRATEGY: *the caster ladder has two rungs*. The same three stopping
    points on a caster, re-bought under the corrected roll.

    What a caster buys with the top rung is not what a martial buys. Dexterity
    comes out of casting, casting is the margin, and the margin scales the
    spell, so the third rung takes away the thing the build exists to do. The
    test is `one_rounds`: a group that dies on your turn never attacks at all.
    """
    natural = C.natural_attack(MAGE, "casting", LEVEL)
    spare = budget - intelligence
    out = []
    # The same three rungs `allocation` names, so the caster table and the
    # martial one can be read side by side.
    for name, dexterity in (("First strike", 112), ("Rarely hit", 212),
                            ("Untouchable", 332)):
        casting = spare - dexterity
        absorption = ARMOUR_SHIELD + L.attribute_bonus(NATURAL_ATTR + dexterity)
        margin = natural + casting - foe["absorption"]
        # Earthquake is an ordinary damage spell, so a creature carrying bit 13
        # takes half of it. The Black Dragon is one of the thirteen that do.
        dealt = per_hit(area_damage, margin) * C.resisted(
            C.BLOW_SPELL, C.foe_resistance(foe))
        out.append({"rung": name, "dexterity": dexterity, "casting": casting,
                    "margin": margin, "absorption": absorption,
                    "hit_you": odds(foe["accuracy"] - absorption),
                    "per_hit": per_hit(foe["damage"],
                                       foe["accuracy"] - absorption),
                    "area_damage": dealt,
                    "one_rounds": dealt >= foe["health"]})
    return out


# Great Heal: 500 restored for 100 magic, the best per-point single-target heal
# a monk or alchemist has. The healer's pool is what the party actually spends,
# so damage on the healer costs twice: once to take it and once to heal it.
GREAT_HEAL, GREAT_HEAL_COST = 500, 100


def healer_splits(odds, foe, budget=510, wisdom=120,
                  splits=((200, 190), (300, 90), (390, 0))):
    """STRATEGY: *the healer is built differently*. What each casting/dexterity
    split spends on keeping itself alive.

    Three Black Dragons all on the healer at once, which is the case the build
    exists to survive. The last column is the share of its own pool it burns
    per round healing itself, which is a round it does not spend healing anyone
    else. There is no front rank: the target picker rolls 0 to 3 and re-rolls
    only for empty or fallen slots, so the healer takes its share like
    everybody else.
    """
    record = raw(foe["name"])
    size, atk = C.group_size(record), C.attacks_a_character(record)
    pool = C.magic_pool(4, LEVEL, C.ROLL_CAP, C.ROLL_CAP + wisdom)
    out = []
    for casting, dexterity in splits:
        absorption = ARMOUR_SHIELD + L.attribute_bonus(NATURAL_ATTR + dexterity)
        margin = foe["accuracy"] - absorption
        taken = odds(margin) * per_hit(foe["damage"], margin) * size * atk
        cost = taken / GREAT_HEAL * GREAT_HEAL_COST
        out.append({"casting": casting, "dexterity": dexterity,
                    "absorption": absorption, "hit_you": odds(margin),
                    "taken": taken, "pool": pool,
                    "share_of_pool": cost / pool if pool else None,
                    "spent": casting + dexterity + wisdom})
    return out


def incapacitators(odds, floor=186):
    """STRATEGY: *the four that end a character's fight*, and what shutting
    them out costs at each level.

    None of the four carries PARTY ATTACK, so each picks one character a round
    but they arrive two and three at a time, and the healer is as likely as
    anyone to be the one picked. `floor` is the absorption that takes the worst
    of their accuracies to a negative margin.
    """
    experience = L.experience_table(L.load())
    out = []
    for level in (30, 35, 40):
        armour = C.armor_afforded(level, experience, 0.5, shield=True)
        natural = C.ROLL_CAP + C.PER_LEVEL * (level - 1)
        need = 0
        while armour + L.attribute_bonus(natural + need) < floor:
            need += 1
        out.append({"level": level, "armour": armour, "points": need})
    return out


def allocation(odds, foe):
    """STRATEGY: *the allocation, level by level*. Where each policy's 510
    points end up, on the corrected roll.

    The first fourteen levels are common to all four builds: charisma, first
    strike, and weapon skill with what is left. Nothing defensive is available
    there: armor is worth 69 absorption at level 14 and the cheapest immunity
    costs more than the whole budget.
    """
    table = C.enemies_by_level()
    grants = dict(C.grants(52, 4))
    common = {"charisma": 40,
              "first_strike_14": C.first_strike_cost(14, table),
              "budget_14": grants[14],
              "first_strike_40": C.first_strike_cost(40, table),
              "budget_40": grants[40]}
    common["skill_14"] = (common["budget_14"] - common["charisma"]
                          - common["first_strike_14"])
    # Dexterity comes from `stops`, so this table and the published one cannot
    # drift apart. 127 matches Paltivar's 265 with the natural 138 and a tie
    # goes to the party; 137 is the 50% band; 212 the 27% band; 332 reaches the
    # 241 absorption that Paltivar's 240 cannot beat. What is left goes to
    # weapon skill and strength, split by brute force.
    priced = {r["build"]: r["dexterity"] for r in stops(odds, foe)}
    rows = []
    for name, weapon, armour in (
            ("Berserker", TWO_HANDED, ARMOUR_2H),
            ("Half the time", ONE_HANDED, ARMOUR_SHIELD),
            ("Rarely hit", ONE_HANDED, ARMOUR_SHIELD),
            ("Untouchable", ONE_HANDED, ARMOUR_SHIELD)):
        dexterity = priced[name]
        spare = 510 - dexterity
        b = max((Build(name, spare - st, st, dexterity, weapon, armour)
                 for st in range(spare + 1)),
                key=lambda x: output(odds, x.damage, x.accuracy,
                                     foe["absorption"]))
        margin = foe["accuracy"] - b.absorption
        rows.append({"build": name, "skill": b.skill, "strength": b.strength,
                     "dexterity": b.dexterity, "absorption": b.absorption,
                     "accuracy": b.accuracy, "damage": b.damage,
                     "weapon": weapon, "spent": b.spent,
                     "hit_you": odds(margin),
                     "per_hit": per_hit(foe["damage"], margin)})
    return common, rows


# --- printing --------------------------------------------------------------

def _pct(x):
    return "--" if x is None else f"{x * 100:.0f}%"


def _num(x, places=1):
    return "--" if x is None else f"{x:.{places}f}"


def _blow(row):
    """Damage one landed hit does, shown only where it tells you something.

    At 0% it never lands and at 100% `taken a round` is already the same number
    times the group. In between the two diverge, and the per-hit figure is the
    one that says whether a round can kill you.
    """
    return "--" if row["hit_you"] in (0.0, 1.0) else f"{row['per_hit']:.0f}"


def report(odds, label, foe):
    print(f"\n{'=' * 78}\n{label}\n{'=' * 78}")

    size = C.group_size(raw(foe["name"]))
    print(f"\nThe ladder at level {LEVEL}, {size} x {foe['name'].title()}"
          f"\n(four of the build, focus-firing; damage columns are per"
          f" character)")
    print(f"{'':13}{'absorb':>7}{'hit you':>9}{'per hit':>9}{'worst rnd':>11}"
          f"{'party rnds':>12}{'1-rounds':>10}{'all three':>11}")
    for r in ladder(odds, foe):
        both = None if r["taken_together"] is None else r["taken_together"] / HEALTH
        worst = "--" if not r["hit_you"] else f"{r['per_hit'] * size:.0f}"
        one = "--" if r["party_rounds"] is None else ("yes" if r["one_rounds"]
                                                     else "no")
        print(f"{r['build']:13}{r['absorption']:>7.0f}{_pct(r['hit_you']):>9}"
              f"{_blow(r):>9}{worst:>11}{_num(r['party_rounds']):>12}"
              f"{one:>10}{_pct(both):>11}")

    print(f"\nWhat weapon skill buys, one character clearing the group alone")
    print(f"{'points':>8}{'margin':>8}{'hit':>7}{'per hit':>9}{'rounds':>9}")
    for r in skill_returns(odds, foe):
        print(f"{r['points']:>8}{r['margin']:>8.0f}{_pct(r['hit']):>7}"
              f"{r['per_hit']:>9}{_num(r['rounds']):>9}")

    print(f"\nTwo ways to stay alive. SOLO: one character, whole group on"
          f" him, nobody else swinging")
    print(f"{'policy':24}{'health':>8}{'absorb':>8}{'hit you':>9}"
          f"{'per hit':>9}{'kill in':>9}{'die in':>9}{'safety':>8}")
    for r in survival(odds, foe):
        print(f"{r['policy']:24}{r['health']:>8.0f}{r['absorption']:>8.0f}"
              f"{_pct(r['hit_you']):>9}{_blow(r):>9}"
              f"{r['kill_in']:>9.1f}{r['die_in']:>9.1f}{r['safety']:>7.1f}x")

    print(f"\nThe four bosses, party of four; per hit is what ONE character"
          f" takes")
    print(f"{'':30}" + "".join(f"{b.name:>26}" for b in BUILDS))
    print(f"{'boss':18}{'health':>7}{'acc':>5}"
          + "".join(f"{'rounds':>9}{'per hit':>9}{'odds':>8}" for b in BUILDS))
    for r in bosses(odds):
        cells = ""
        for b in BUILDS:
            cell = r["builds"][b.name]
            # Per hit is shown at 100% here too: with one attack a round it is
            # the damage taken, and the point of the column is what one blow
            # does to a 1,066 health pool.
            blow = "--" if not cell["hit_you"] else f"{cell['per_hit']:.0f}"
            cells += (f"{_num(cell['rounds']):>9}{blow:>9}"
                      f"{_pct(cell['hit_you']):>8}")
        print(f"{r['boss']:18}{r['health']:>7}{r['accuracy']:>5}{cells}")

    print(f"\nThe caster ladder")
    print(f"{'rung':14}{'dex':>5}{'casting':>9}{'margin':>8}{'absorb':>8}"
          f"{'hit you':>9}{'per hit':>9}{'area dmg':>10}{'one-rounds':>12}")
    for r in caster(odds, foe):
        print(f"{r['rung']:14}{r['dexterity']:>5}{r['casting']:>9}"
              f"{r['margin']:>8.0f}{r['absorption']:>8.0f}{_pct(r['hit_you']):>9}"
              f"{_blow(r):>9}{r['area_damage']:>10}"
              f"{'yes' if r['one_rounds'] else 'no':>12}")

    print(f"\nWhat fifteen more points do")
    print(f"{'build':13}{'into skill':>20}{'into strength':>20}"
          f"{'into dexterity':>24}")
    for r in marginal(odds, foe):
        skill = f"{r['rounds']:.1f} -> {r['into_skill']:.1f} rnds"
        strength = f"{r['rounds']:.1f} -> {r['into_strength']:.1f} rnds"
        dexterity = f"{r['taken_now']:.0f} -> {r['into_dexterity']:.0f} a round"
        print(f"{r['build']:13}{skill:>20}{strength:>20}{dexterity:>24}")


def careers(odds):
    print(f"\n{'=' * 78}\nThe same policies from level 15 to 40\n{'=' * 78}")
    for policy in POLICIES:
        print(f"\n{policy}, four of them; damage columns are per character")
        print(f"{'lvl':>4}{'creature':22}{'dex':>5}{'(fs)':>6}{'skill':>6}"
              f"{'str':>5}{'armr':>6}{'wpn':>5}{'absorb':>8}{'hit you':>9}"
              f"{'per hit':>8}{'worst':>7}{'% pool':>8}{'rnds':>6}"
              f"{'1-rnd':>7}{'lost fight':>11}")
        for r in career_table(policy, odds):
            if not r["reachable"]:
                print(f"{r['level']:>4}{'-- out of reach on this budget':22}")
                continue
            worst = "--" if not r["hit_you"] else f"{r['worst_round']:.0f}"
            share = "--" if not r["hit_you"] else \
                f"{r['worst_round'] / r['health'] * 100:.0f}%"
            print(f"{r['level']:>4}{r['creature'][:21]:22}{r['dexterity']:>5}"
                  f"{r['first_strike']:>6}{r['skill']:>6}{r['strength']:>5}"
                  f"{r['armour']:>6}{r['weapon']:>5}{r['absorption']:>8}"
                  f"{_pct(r['hit_you']):>9}"
                  f"{('--' if not r['hit_you'] else r['per_hit']):>8}"
                  f"{worst:>7}{share:>8}{r['party_rounds']:>6.1f}"
                  f"{('yes' if r['one_rounds'] else 'no'):>7}"
                  f"{r['taken_together'] / r['health'] * 100:>10.0f}%")


def builds(odds, foe):
    print(f"\n{'=' * 78}\nThe caster, the healer, and where the points go"
          f"\n{'=' * 78}")

    print("\nThe caster's two switches: creatures killed between rests,"
          " whole career")
    print(f"{'intelligence':>14}" + "".join(
        f"{('never' if d is None else f'dex from {d}'):>14}" for d in DEX_FROM))
    for row in caster_schedule():
        label = "none" if not row["switch"] else f"through {row['switch']}"
        print(f"{label:>14}" + "".join(
            f"{row['kills'][d]:>14.0f}" for d in DEX_FROM))

    print("\nLevels 12 to 40 with no one-cast kill available")
    print(f"{'intelligence':>14}{'dead levels':>13}{'longest run':>13}"
          f"{'  from':<6}")
    for r in dead_levels():
        label = "none" if not r["switch"] else f"through {r['switch']}"
        span = "" if not r["dead"] else f"  {r['dead'][0]} to {r['dead'][-1]}"
        print(f"{label:>14}{r['count']:>13}{r['worst_run']:>13}{span:<6}")

    print("\nWhat the intelligence years cost, one cast against one creature")
    switches = (0, 12, 18)
    print(f"{'lvl':>4}{'health':>8}" + "".join(
        f"{('all casting' if not s else f'switch {s}'):>22}" for s in switches))
    print(f"{'':4}{'':8}" + "".join(f"{'hit':>7}{'dealt':>7}{'casts':>8}"
                                    for _ in switches))
    for row in intelligence_years(switches):
        cells = ""
        for s in switches:
            c = row["by_switch"][s]
            cells += (f"{_pct(c['hit']):>7}{c['dealt']:>7.0f}"
                      f"{_num(c['casts']):>8}")
        print(f"{row['level']:>4}{row['foe_health']:>8.0f}{cells}")

    print("\nThe caster ladder, re-bought")
    print(f"{'rung':14}{'dex':>5}{'casting':>9}{'margin':>8}{'absorb':>8}"
          f"{'hit you':>9}{'per hit':>9}{'area dmg':>10}{'one-rounds':>12}")
    for r in caster_rungs(odds, foe):
        print(f"{r['rung']:14}{r['dexterity']:>5}{r['casting']:>9}"
              f"{r['margin']:>8.0f}{r['absorption']:>8.0f}"
              f"{_pct(r['hit_you']):>9}{_blow(r):>9}{r['area_damage']:>10}"
              f"{'yes' if r['one_rounds'] else 'no':>12}")

    print("\nThe healer's split: three Black Dragons all on the healer")
    print(f"{'casting':>9}{'dex':>6}{'absorb':>8}{'hit you':>9}"
          f"{'taken a round':>15}{'own pool a round':>18}")
    for r in healer_splits(odds, foe):
        print(f"{r['casting']:>9}{r['dexterity']:>6}{r['absorption']:>8.0f}"
              f"{_pct(r['hit_you']):>9}{r['taken']:>15.0f}"
              f"{_pct(r['share_of_pool']):>18}")

    print("\nThe healer's own dead levels: a monk buying wisdom")
    print(f"{'wisdom':>14}{'dead levels':>13}{'longest run':>13}{'  from':<6}")
    for r in dead_levels(class_code=MONK):
        label = "none" if not r["switch"] else f"through {r['switch']}"
        span = "" if not r["dead"] else f"  {r['dead'][0]} to {r['dead'][-1]}"
        print(f"{label:>14}{r['count']:>13}{r['worst_run']:>13}{span:<6}")

    print("\nShutting out the four that end a character's fight (absorption"
          " 186)")
    print(f"{'lvl':>4}{'armor gold affords':>20}{'dexterity points':>18}")
    for r in incapacitators(odds):
        print(f"{r['level']:>4}{r['armour']:>20.0f}{r['points']:>18}")

    rungs = [Build(r["build"], r["skill"], r["strength"], r["dexterity"],
                   r["weapon"], ARMOUR_2H if r["weapon"] == TWO_HANDED
                   else ARMOUR_SHIELD)
             for r in allocation(odds, foe)[1]]
    print("\nWhat fifteen more points do, on the recommended rungs")
    print(f"{'build':13}{'into skill':>20}{'into strength':>20}"
          f"{'into dexterity':>24}")
    for r in marginal(odds, foe, builds=rungs):
        skill = f"{r['rounds']:.1f} -> {r['into_skill']:.1f} rnds"
        strength = f"{r['rounds']:.1f} -> {r['into_strength']:.1f} rnds"
        dexterity = f"{r['taken_now']:.0f} -> {r['into_dexterity']:.0f} a round"
        print(f"{r['build']:13}{skill:>20}{strength:>20}{dexterity:>24}")

    common, rows = allocation(odds, foe)
    print(f"\nCommon to every build: charisma {common['charisma']} through"
          f" level 5, first strike {common['first_strike_14']} by 14,"
          f" weapon skill {common['skill_14']}")
    print(f"(budget is {common['budget_14']} at level 14 and"
          f" {common['budget_40']} at 40)")
    print(f"\nWhere the 510 end up")
    print(f"{'build':13}{'skill':>7}{'str':>6}{'dex':>6}{'absorb':>8}"
          f"{'acc':>6}{'damage':>8}{'hit you':>9}{'per hit':>9}{'spent':>7}")
    for r in rows:
        print(f"{r['build']:13}{r['skill']:>7}{r['strength']:>6}"
              f"{r['dexterity']:>6}{r['absorption']:>8.0f}{r['accuracy']:>6}"
              f"{r['damage']:>8.0f}{_pct(r['hit_you']):>9}{_blow(r):>9}"
              f"{r['spent']:>7}")


def main(argv):
    foe = C.enemies_by_level()[LEVEL]
    assert all(b.spent == 510 for b in BUILDS), \
        "a build stopped spending the budget exactly; fix it or the table lies"
    if "--compare" in argv:
        report(flat, "FLAT d56: the model MANUAL.md's tables were built on",
               foe)
    report(folded, "FOLDED d55: what the game does; see docs/combat.md", foe)
    if "--careers" in argv:
        careers(folded)
    if "--builds" in argv:
        builds(folded, foe)


if __name__ == "__main__":
    main(sys.argv[1:])
