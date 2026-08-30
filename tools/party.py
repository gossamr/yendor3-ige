"""Mixed parties: what each composition actually delivers, level by level.

`tools/ladder.py` models four characters of one build, which is a comparison of
*builds* and not a party anyone fields. This models the compositions a player
actually chooses between. The point is not that one wins: it is that the three
roles buy different things and the mix decides which constraint binds.

    python tools/party.py            # every composition at level 40
    python tools/party.py --careers  # the same from 15 to 40

## The three roles

**Martial**: unlimited output, single target, focus-fired with the rest.
Spends its 510 points on the `Rarely hit` rung by default; `--berserker`
switches it. Costs nothing per fight and so never runs out.

**Caster**: an area spell hits every engaged monster at once, so its output
scales with the group where a martial's does not. Mage: charisma, then
intelligence 78 for the pool, then first strike, then casting. Bounded by magic
points, and by nuore, which is a second currency the party shares.

**Healer**: deals nothing worth counting. Its contribution is a pool that
converts to health at a fixed rate, and the question it answers is how many
fights the party sustains rather than how fast it wins one.

## What is modeled, and what is not

A round is: the party acts (all four outrun every regular monster once first
strike is bought), then whatever is still alive swings. Casters spend their
spell every round they act. Martials focus-fire, and overkill is not carried
between monsters within a round.

Monsters are all engaged from the start, the lost-control case. The other
bound, one arrival a round, is uninteresting here: any composition that
one-rounds a group takes nothing at all under it.

Not modeled: the caster's own miss years, positional restrictions (`when` is
respected, so a hand-to-hand-only spell is not used at range but the choice of
where to stand is not), condition attacks, and item effects.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import combat_model as C
import ladder as LD
import levels as L

PARTY = 4
HEAL_PER_MANA = 100 * 4 / 45     # Party Heal: 100 to all four for 45 magic
GREAT_HEAL_PER_MANA = 500 / 100  # the concentrated alternative

# Nuore is the second currency every spell spends, all 98 of them, with no
# free cast anywhere in the list. Monsters drop it and a shop sells it at ten
# gold a unit in lots of ten.
#
# It is NOT carried inventory. The party's nuore is a single counter at
# DS:0xcf99, alongside gold at 0xcf91 and food at 0xcf95: the steal attacks
# subtract from it (image 0x037ac), a spell's cost subtracts from it (0x0d34e),
# and the panel prints it (0x1720e). Nine references in the whole image and not
# one of them weighs it, so the four units the NUORE *item* record carries are
# the weight of a purchased stack and not a cap on the counter. An earlier pass
# here concluded carry capacity was the binding constraint on a caster party;
# that was wrong, and this note is why.
NUORE_PRICE = 10                 # gold a unit; SUPPLIES_PER_UNIT is the lot size

MAGE, MONK = 7, 4
CASTER_INT = 78                  # the pool the schedule buys before splitting
HEALER_WIS = 120

# The spellblades: classes that carry both a weapon skill and a spell list.
# Paladin and Marksman blend half an attribute into magic against a full
# caster's whole one, so their pool is about half the size before any points
# are spent. Alchemist and Druid are 75/25 blends and are full casters that
# happen to have a weapon skill.
SPELLBLADES = {
    "paladin": (6, "PALADIN", "slashing", C.WIS),
    "marksman": (9, "MARKSMAN", "projectile", C.INT),
    "druid": (8, "DRUID", "slashing", C.INT),
    "alchemist": (5, "ALCHEMIST", "bashing", C.WIS),
}


def _spells():
    return json.loads((C.ROOT / "data" / "spells.json").read_text())


def best_spell(class_name: str, level: int, area: bool, margin=None,
               targets=1, by="damage"):
    """The spell of that kind a class should be casting by `level`.

    `by="damage"` takes the biggest, which is what buys tempo: ending a fight
    a round earlier is a round of incoming damage nobody takes. `by="efficiency"`
    takes the most damage per magic point, which is what buys fights per rest.
    They are not the same spell and usually not close: at level 40 a mage's
    Earthquake delivers 8.1 damage a point and its Finger of Flame, learned
    twenty-two levels earlier, delivers 20.3.
    """
    best, best_score = None, -1.0
    for s in _spells():
        if not s.get("listed") or not s.get("damage"):
            continue
        levels = [c["level"] for c in s.get("classes", [])
                  if c["class"] == class_name]
        if not levels or min(levels) > level:
            continue
        is_area = (s.get("scope") == "all"
                   and s.get("target") in ("monsters", "visible monsters"))
        if is_area != area:
            continue
        if s.get("when") == "out of hand to hand":   # inert once engaged
            continue
        if by == "efficiency" and margin is not None:
            per = LD.per_hit(s["damage"], margin) * targets
            score = per / s["mp"] if s["mp"] else 0
        else:
            score = s["damage"]
        if score > best_score:
            best, best_score = s, score
    return best


# The two families the game names for itself, from the spell AFFECTS
# enumeration. A spell whose target is a family only lands on that family.
FAMILY_INSECT, FAMILY_UNDEAD = 9, 13


def _affects(spell, foe):
    """Whether this spell can be thrown at this monster at all."""
    target = (spell.get("target") or "").lower()
    if "undead" not in target and "insect" not in target:
        return True
    want = FAMILY_UNDEAD if "undead" in target else FAMILY_INSECT
    try:
        return LD.raw_by_level(foe.get("level", 0)).get("family") == want
    except (KeyError, TypeError):
        return False


class Member:
    """One character: what it adds to a round and what it spends doing it."""

    def __init__(self, role, level, odds, foe, martial_policy="Rarely hit",
                 casting_share=1.0, spell_choice="damage", casters=1):
        self.role, self.level, self.odds, self.foe = role, level, odds, foe
        # A weapon swing is free and single-target. A spell costs magic and
        # nuore and may hit the whole group. Keeping them in one field is how
        # single-target spells came to be cast for nothing.
        self.weapon = 0.0            # free, single target
        self.spell_damage = 0.0      # per target, costed
        self.spell_targets = 1
        self.cost = self.pool = self.nuore = 0.0
        self.spell = None
        natural_attr = C.ROLL_CAP + C.PER_LEVEL * (level - 1)
        budget = dict(C.grants(52, 4))[level]
        armour = C.armor_afforded(level, L.experience_table(L.load()), 0.5)

        if role == "martial":
            build = LD.build_at(martial_policy, level, odds)
            if build is None:
                build = LD.build_at("Berserker", level, odds)
            self.absorption = build["absorption"]
            self.weapon = LD.output(odds, build["damage"], build["accuracy"],
                                    foe["absorption"])
            return

        # Both casting roles pay first strike out of the same budget.
        strike = C.first_strike_cost(level, C.enemies_by_level())
        self.absorption = armour + L.attribute_bonus(natural_attr + strike)
        spent = min(budget, strike)

        if role == "caster":
            attr = min(CASTER_INT, budget - spent)
            spent += attr
            self.pool = C.magic_pool(MAGE, level, C.ROLL_CAP + attr, C.ROLL_CAP)
            casting = C.natural_attack(MAGE, "casting", level) + budget - spent
            margin = casting - foe["absorption"]
            group = C.group_size(LD.raw_by_level(level))
            # Area and single-target compete. Against a group the area spell
            # wins by the group size; against a solitary monster they compete
            # head to head, and a single-target spell is usually the cheaper
            # way to kill it.
            # How many of these are in the party changes which spell is right:
            # four casters clear a group with four cheap spells where one needs
            # an expensive one, so the cheap spell is only correct in numbers.
            self._pick_spell("MAGE", level, odds, foe, margin, group,
                             spell_choice, casters)
        elif role == "healer":
            attr = min(HEALER_WIS, budget - spent)
            self.pool = C.magic_pool(MONK, level, C.ROLL_CAP, C.ROLL_CAP + attr)
        else:                                            # a spellblade
            self._spellblade(role, level, odds, foe, budget, spent,
                             natural_attr, casting_share)

    def _pick_spell(self, class_name, level, odds, foe, margin, group,
                    spell_choice, casters=1):
        """Choose from every spell castable in melee, by simulating each.

        `damage` takes the biggest, which minimises rounds. `efficiency` takes
        the cheapest spell that still clears the group in the *same* number of
        rounds: efficiency alone is degenerate, because damage per magic point
        is maximised by the level-1 Magic Attack, which would need twenty-three
        casts and twenty-three rounds of standing there being hit.

        `out of hand to hand` spells are excluded throughout: they are inert
        once a monster has closed, which rules out the mage's two most
        efficient area spells, Finger of Flame and Power Surge.
        """
        options = []
        for spell in _spells():
            if not spell.get("listed") or not spell.get("damage"):
                continue
            levels = [c["level"] for c in spell.get("classes", [])
                      if c["class"] == class_name]
            if not levels or min(levels) > level:
                continue
            if spell.get("when") == "out of hand to hand":
                continue
            # Some spells name a family rather than a monster: TURN UNDEAD
            # reads `undeads` and a dragon is not one, so it cannot be thrown
            # at the group being modeled. Without this the picker chose it and
            # collected 765 a target for a spell that would do nothing.
            if not _affects(spell, foe):
                continue
            # Immunity is not resistance: a monster immune to the spell's
            # damage type takes nothing from it, so the spell is not an option
            # at all rather than a halved one.
            if C.immune_to(foe, spell):
                continue
            targets = (group if spell.get("scope") == "all"
                       and spell.get("target") in ("monsters",
                                                   "visible monsters") else 1)
            # A monster that resists this kind of spell halves what lands.
            per = (odds(margin) * LD.per_hit(spell["damage"], margin)
                   * C.resisted(C.spell_blow(spell), C.foe_resistance(foe)))
            if per <= 0:
                continue
            # Rounds for `casters` of these to clear the group, and what that
            # costs. Overkill on a single target is not carried.
            killed_a_round = min(targets, group) * per * casters
            rounds = max(1, -(-group * foe["health"] // max(1, killed_a_round)))
            options.append((rounds, spell["mp"] * rounds * casters,
                            per, targets, spell))
        if not options:
            return
        fewest = min(r for r, *_ in options)
        if spell_choice == "efficiency":
            pick = min((o for o in options if o[0] == fewest), key=lambda o: o[1])
        else:
            pick = max(options, key=lambda o: o[2] * o[3])
        _r, _c, per, targets, spell = pick
        self.spell_damage, self.spell_targets = per, targets
        self.cost = spell["mp"]
        self.nuore = spell.get("nuore") or 0
        self.spell = spell["name"]

    def _spellblade(self, role, level, odds, foe, budget, spent, natural_attr,
                    casting_share=1.0):
        """A hybrid at a stated split, rather than an optimised one.

        `casting_share` is the fraction of the remaining budget given to the
        magic side; of that, the first 78 points go to the magic attribute (the
        pool) exactly as the caster schedule spends them, and the rest to
        casting. What is left goes to weapon skill, with strength taken to the
        crossover.

        There is no single right objective to optimise here, since per-round
        output says all-casting and the pool says otherwise, so the splits are shown
        and the reader picks. That is the whole question about spellblades.
        """
        code, name, skill, attribute = SPELLBLADES[role]
        experience = L.experience_table(L.load())
        weapon = C.weapon_afforded(level, experience, 0.2, C.shop_weapons())
        spare = budget - spent
        magic_side = int(spare * casting_share)
        attr = min(CASTER_INT, magic_side)
        casting = magic_side - attr
        martial = spare - magic_side

        self.pool = C.magic_pool(
            code, level,
            C.ROLL_CAP + (attr if attribute == C.INT else 0),
            C.ROLL_CAP + (attr if attribute == C.WIS else 0))

        strength = max(range(martial + 1), key=lambda st: LD.output(
            odds, weapon + L.attribute_bonus(natural_attr + st),
            C.natural_attack(code, skill, level) + martial - st,
            foe["absorption"]))
        # A shot is the one physical blow that carries a word, so a monster
        # with bit 15 halves the marksman's bow and nobody else's hand weapon.
        shot = C.resisted(C.BLOW_SHOT if skill == "projectile" else C.BLOW_MELEE,
                          C.foe_resistance(foe))
        self.weapon = shot * LD.output(
            odds, weapon + L.attribute_bonus(natural_attr + strength),
            C.natural_attack(code, skill, level) + martial - strength,
            foe["absorption"])

        group = C.group_size(LD.raw_by_level(level))
        margin = C.natural_attack(code, "casting", level) + casting \
            - foe["absorption"]
        self._pick_spell(name, level, odds, foe, margin, group, "damage")
        if self.cost > self.pool:            # cannot afford a single cast
            self.spell_damage, self.cost, self.nuore = 0.0, 0.0, 0.0
            self.spell = None
        self.split = (attr, casting, martial)


def spellblade_splits(role, level, odds, shares=(0.0, 0.25, 0.5, 0.75, 1.0)):
    """One hybrid at every split, with what each buys."""
    foe = C.enemies_by_level()[level]
    out = []
    for share in shares:
        m = Member(role, level, odds, foe, casting_share=share)
        casts = int(m.pool // m.cost) if m.cost else 0
        group = C.group_size(LD.raw_by_level(level))
        out.append({
            "role": role, "share": share, "split": m.split,
            "swing": m.weapon, "area": m.spell_damage,
            "area_total": m.spell_damage * m.spell_targets,
            "pool": m.pool, "cost": m.cost, "casts": casts,
            "spell": m.spell,
            "round_one": max(m.weapon,
                             m.spell_damage * m.spell_targets if casts else 0),
        })
    return out


SPELLBLADE_COMPOSITIONS = [
    ("4 paladins", ("paladin",) * 4),
    ("3 paladins + healer", ("paladin",) * 3 + ("healer",)),
    ("2 paladins + 2 martials", ("paladin", "paladin", "martial", "martial")),
    ("2 marksmen + caster + healer",
     ("marksman", "marksman", "caster", "healer")),
    ("2 druids + martial + healer", ("druid", "druid", "martial", "healer")),
    ("2 alchemists + martial + healer",
     ("alchemist", "alchemist", "martial", "healer")),
]

COMPOSITIONS = [
    ("4 martials", ("martial",) * 4),
    ("3 martials + healer", ("martial",) * 3 + ("healer",)),
    ("2 martials + caster + healer", ("martial", "martial", "caster", "healer")),
    ("martial + 2 casters + healer", ("martial", "caster", "caster", "healer")),
    ("3 casters + healer", ("caster",) * 3 + ("healer",)),
    ("4 casters", ("caster",) * 4),
]


def fight(members, foe, size, attacks_each, odds):
    """Run one engagement with everything already closed.

    Order inside a round: whoever has an area spell acts first and one at a
    time, because an area spell is worth most while every monster is at full
    health, and because the next caster should not spend a spell on a group
    that is already dead. Then the weapons focus-fire what is left. A hybrid
    casts only when the spell would out-damage its own swing across the
    monsters still standing.

    Returns rounds, damage one character takes, and the magic and nuore the
    party spent.
    """
    monsters = [float(foe["health"])] * size
    mana = {i: m.pool for i, m in enumerate(members)}
    taken, rounds, magic, nuore = 0.0, 0, 0.0, 0.0

    def alive():
        return [i for i, h in enumerate(monsters) if h > 0]

    while alive() and rounds < 50:
        rounds += 1
        for i, m in enumerate(members):
            standing = alive()
            if not standing:
                break
            hits = min(m.spell_targets, len(standing))
            cast = (m.spell_damage and mana[i] >= m.cost
                    and m.spell_damage * hits > m.weapon)
            if cast:
                mana[i] -= m.cost
                magic += m.cost
                nuore += m.nuore
                for j in standing[:hits]:
                    monsters[j] -= m.spell_damage
            elif m.weapon:
                monsters[standing[0]] -= m.weapon
        standing = alive()
        if not standing:
            break
        margin = foe["accuracy"] - members[0].absorption
        taken += (len(standing) * odds(margin)
                  * per_hit_taken(foe, margin) * attacks_each)
    return rounds, taken, magic, nuore


def per_hit_taken(foe, margin):
    return LD.per_hit(foe["damage"], margin)


def evaluate(name, roles, level, odds, martial_policy="Rarely hit",
             spell_choice="damage"):
    foe = C.enemies_by_level()[level]
    record = LD.raw_by_level(level)
    size = C.group_size(record)
    attacks_each = C.attacks_a_character(record)
    casters = sum(1 for r in roles if r not in ("martial", "healer"))
    members = [Member(r, level, odds, foe, martial_policy,
                      spell_choice=spell_choice, casters=max(1, casters))
               for r in roles]

    # Damage taken is per character, and every character has the same
    # absorption only if they bought the same dexterity; take the martial's if
    # there is one, since it is the build the ladder prices.
    front = next((m for m in members if m.role == "martial"), members[0])
    ordered = [front] + [m for m in members if m is not front]
    rounds, taken, magic, nuore = fight(ordered, foe, size, attacks_each, odds)

    dropped = LD.raw_by_level(level).get("nuore", 0) * size

    healer = next((m for m in members if m.role == "healer"), None)
    caster_pool = sum(m.pool for m in members if m.spell_damage)
    party_damage = taken * PARTY
    fights_by_magic = caster_pool / magic if magic else float("inf")
    fights_by_health = (float("inf") if not party_damage else
                        (C.health_pool(52, level) * PARTY
                         + (healer.pool * HEAL_PER_MANA if healer else 0))
                        / party_damage)
    return {
        "party": name, "level": level, "rounds": rounds,
        "monster": foe["name"], "group": size,
        "taken": taken, "health": C.health_pool(52, level),
        "one_rounds": rounds <= 1,
        "magic_a_fight": magic, "nuore_a_fight": nuore,
        "nuore_dropped": dropped, "nuore_net": dropped - nuore,
        "gold_to_cover": max(0.0, nuore - dropped) * NUORE_PRICE,
        "caster_pool": caster_pool,
        "healer_pool": healer.pool if healer else 0,
        "fights_per_rest": min(fights_by_magic, fights_by_health),
        "limited_by": ("magic" if fights_by_magic < fights_by_health
                       else "health"),
    }


def report(level, odds, martial_policy="Rarely hit", spell_choice="damage"):
    foe = C.enemies_by_level()[level]
    print(f"\nLevel {level}: {C.group_size(LD.raw_by_level(level))} x "
          f"{foe['name'].title()}, all engaged. Martials on the "
          f"'{martial_policy}' rung; casters picking their spell by"
          f" {spell_choice}.")
    print(f"{'composition':30}{'rounds':>8}{'1-rnd':>7}{'taken/char':>12}"
          f"{'% pool':>8}{'magic/fight':>13}{'fights/rest':>13}{'limit':>8}")
    for name, roles in COMPOSITIONS:
        r = evaluate(name, roles, level, odds, martial_policy, spell_choice)
        fights = ("--" if r["fights_per_rest"] == float("inf")
                  else f"{r['fights_per_rest']:.1f}")
        print(f"{r['party']:30}{r['rounds']:>8}"
              f"{('yes' if r['one_rounds'] else 'no'):>7}"
              f"{r['taken']:>12.0f}{r['taken'] / r['health'] * 100:>7.0f}%"
              f"{r['magic_a_fight']:>13.0f}{fights:>13}{r['limited_by']:>8}")


def careers(odds, martial_policy="Rarely hit"):
    for name, roles in COMPOSITIONS:
        print(f"\n{name}")
        print(f"{'lvl':>4}{'monster':22}{'rounds':>8}{'1-rnd':>7}"
              f"{'taken/char':>12}{'% pool':>8}{'fights/rest':>13}{'limit':>8}")
        for level in range(15, 41):
            r = evaluate(name, roles, level, odds, martial_policy)
            fights = ("--" if r["fights_per_rest"] == float("inf")
                      else f"{r['fights_per_rest']:.1f}")
            print(f"{level:>4}{r['monster'][:21]:22}{r['rounds']:>8}"
                  f"{('yes' if r['one_rounds'] else 'no'):>7}"
                  f"{r['taken']:>12.0f}{r['taken'] / r['health'] * 100:>7.0f}%"
                  f"{fights:>13}{r['limited_by']:>8}")


BOSSES = ("PALTIVAR", "CHAOTIC MINOTAUR", "BLAZIOS", "TITAN LORD")


def boss_report(level, odds, martial_policy="Rarely hit"):
    """Bosses are where compositions differ. Regular groups die in one round to
    anything with a caster in it and cost a martial party one per cent of its
    health, so they separate nothing; a boss has 2,000 to 3,400 health, cannot
    be one-rounded, and carries PARTY ATTACK, so it swings at every character
    every round for as long as the fight lasts.
    """
    print(f"\nThe four bosses at level {level}, one of each, party of four."
          f"\nMartials on the '{martial_policy}' rung; casts are what the"
          f" party spends bringing it down.")
    print(f"{'composition':30}" + "".join(f"{b.title()[:9]:>21}" for b in BOSSES))
    print(f"{'':30}" + "".join(f"{'rnds':>6}{'taken':>8}{'magic':>7}"
                               for _b in BOSSES))
    for name, roles in COMPOSITIONS + SPELLBLADE_COMPOSITIONS:
        cells = ""
        for boss in BOSSES:
            c = LD.raw(boss)
            members = [Member(r, level, odds, c, martial_policy) for r in roles]
            front = next((m for m in members if m.role == "martial"), members[0])
            ordered = [front] + [m for m in members if m is not front]
            rounds, taken, magic, _n = fight(
                ordered, c, 1, C.attacks_a_character(c), odds)
            cells += f"{rounds:>6}{taken:>8.0f}{magic:>7.0f}"
        print(f"{name:30}{cells}")


def spellblade_report(level, odds):
    print(f"\nSpellblades at level {level}: one character at every split.\n"
          f"The group is {C.group_size(LD.raw_by_level(level))} x "
          f"{C.enemies_by_level()[level]['name'].title()}, "
          f"{C.group_size(LD.raw_by_level(level)) * C.enemies_by_level()[level]['health']:.0f}"
          f" health between them.")
    # Swing is one hit on one monster, so the spell is printed per target
    # beside it. `x group` is the same cast totalled over everything engaged,
    # which is the spell's real advantage but not a like-for-like number.
    print(f"{'class':11}{'to magic':>9}{'attr':>6}{'casting':>9}{'weapon':>8}"
          f"{'swing':>8}{'spell/target':>14}{'x group':>9}{'pool':>7}"
          f"{'casts':>7}  spell")
    for role in SPELLBLADES:
        for r in spellblade_splits(role, level, odds):
            attr, casting, weapon = r["split"]
            print(f"{role:11}{r['share'] * 100:>8.0f}%{attr:>6}{casting:>9}"
                  f"{weapon:>8}{r['swing']:>8.0f}{r['area']:>14.0f}"
                  f"{r['area_total']:>9.0f}"
                  f"{r['pool']:>7.0f}{r['casts']:>7}  {r['spell'] or '--'}")
        print()


def main(argv):
    policy = "Berserker" if "--berserker" in argv else "Rarely hit"
    if "--bosses" in argv:
        boss_report(40, LD.folded, policy)
    elif "--spellblades" in argv:
        spellblade_report(40, LD.folded)
    elif "--careers" in argv:
        careers(LD.folded, policy)
    else:
        report(40, LD.folded, policy)
        print()
        for name, roles in SPELLBLADE_COMPOSITIONS:
            r = evaluate(name, roles, 40, LD.folded, policy)
            fights = ("--" if r["fights_per_rest"] == float("inf")
                      else f"{r['fights_per_rest']:.1f}")
            print(f"{r['party']:30}{r['rounds']:>8}"
                  f"{('yes' if r['one_rounds'] else 'no'):>7}"
                  f"{r['taken']:>12.0f}{r['taken'] / r['health'] * 100:>7.0f}%"
                  f"{r['magic_a_fight']:>13.0f}{fights:>13}"
                  f"{r['limited_by']:>8}")


if __name__ == "__main__":
    main(sys.argv[1:])
