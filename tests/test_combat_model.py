"""Pins for the numbers the strategy chapters quote.

Every figure the manual gives as a recommendation came out of `combat_model`,
and each one drifted at least once while it was being worked out, and the point
budget, the armor ceiling, the level a breakpoint falls on. These tests are
not checking arithmetic; they are checking that the arithmetic still lands
where the prose says it does.
"""

from __future__ import annotations

import collections
import re
import struct
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import combat_model as cm  # noqa: E402
import labels  # noqa: E402
import levels as lv  # noqa: E402


@pytest.fixture(scope="module")
def enemies():
    return cm.enemies_by_level()


@pytest.fixture(scope="module")
def experience():
    return lv.experience_table(lv.load(ROOT / "game" / "REGISTER.EXE"))


# --- The monsters ---------------------------------------------------------


def test_breakpoints_are_the_eight_the_manual_names(enemies):
    """Regular monsters only: the boss levels 11, 22, 28 and 36 drop out."""
    got = [s["level"] for s in cm.breakpoints(enemies) if s["level"] <= cm.LEVEL_CAP]
    assert got == [4, 10, 18, 26, 29, 30, 39, 40]


def test_level_39_is_the_largest_step(enemies):
    steps = {s["level"]: s["jump"] for s in cm.breakpoints(enemies)}
    assert steps[39] == 20
    assert max(steps.values()) == steps[39]


def test_the_table_is_one_real_monster_not_a_field_by_field_worst(enemies):
    """A build has to survive what the level can throw at it, not the median --
    but the row must describe something the player can actually meet."""
    rows = [e for e in json.loads((ROOT / "data" / "enemies.json").read_text())
            if e["listed"] and e["level"] == 40]
    regular = [e for e in rows if not e["food"]]
    worst = max(regular, key=lambda e: e["experience"])
    assert worst["name"] == "BLACK DRAGON" == enemies[40]["name"]
    for field in ("absorption", "accuracy", "damage", "health"):
        assert enemies[40][field] == worst[field]
    # and it is not the field-by-field worst: the Titan Lord hits harder
    assert enemies[40]["damage"] < max(e["damage"] for e in rows)


def test_bosses_are_the_monsters_carrying_food(enemies):
    """Ten of the 71, and they are exactly the named individuals."""
    rows = [e for e in json.loads((ROOT / "data" / "enemies.json").read_text())
            if e["listed"]]
    assert {e["name"] for e in rows if e["food"]} == {
        "WASP QUEEN", "KING BARIAG", "PIXIE LEADER", "ACOKNIGHT",
        "QUEEN OBVERSIA", "VISHAN", "KING SLATOR", "TITAN LORD",
        "CHAOTIC MINOTAUR", "BLAZIOS"}
    # the Titan Lord is back when bosses are asked for
    assert cm.enemies_by_level(bosses=True)[40]["name"] == "TITAN LORD"


def test_missing_levels_are_interpolated_not_dropped(enemies):
    # No monster carries level 12, 23, 24, 43 or 44.
    assert 12 in enemies
    assert enemies[11]["absorption"] < enemies[12]["absorption"] < enemies[13]["absorption"]


# --- The character ---------------------------------------------------------


def test_every_blend_caps_at_sixty():
    """Weights sum to 100 and rolls stop at 60, so no skill starts above 60."""
    for skill in ("projectile", "slashing", "bashing", "polearm"):
        for class_code in range(1, 10):
            base = cm.natural_attack(class_code, skill, 1)
            assert base <= cm.ROLL_CAP + 5, (skill, class_code, base)


def test_attack_ceilings_at_level_forty():
    assert cm.natural_attack(1, "slashing", 40) == 143     # fighter
    assert cm.natural_attack(7, "casting", 40) == 148      # mage, the highest
    assert cm.natural_attack(9, "projectile", 40) == 138   # marksman
    assert cm.natural_attack(9, "slashing", 40) == 133     # ...and its melee


def test_casting_beats_every_weapon_skill():
    best = {c: cm.best_attack(c, 40)[1] for c in range(1, 10)}
    assert max(best.values()) == best[7] == best[4] == 148


def test_health_matches_the_manuals_table():
    assert cm.health_pool(52, 1) == 13
    assert cm.health_pool(52, 10) == 175
    assert cm.health_pool(52, 20) == 412
    assert cm.health_pool(52, 40) == 1066


def test_budget_lands_on_the_charisma_chapters_totals():
    """497 to 524 free points, after buying charisma to 100 and stopping."""
    assert cm.budget(45, 5)[40] == 497
    assert cm.budget(60, 3)[40] == 524


def test_dexterity_buys_absorption_at_five_to_one():
    assert cm.absorption(0, 72) == 0          # nothing at or below the threshold
    assert cm.absorption(0, 77) == 1
    assert cm.absorption(0, 122) == 10
    # and the natural +2 a level supplies 13 by level 40 from a 60 roll
    assert cm.absorption(0, cm.ROLL_CAP + 2 * 39) == 13


# --- The armor ceiling ----------------------------------------------------
#
# The constants in the module are the thing that was wrong for most of a
# session, so this rebuilds them from WORLD.DAT rather than trusting them.

ITEM_BASE, ITEM_REC, ITEM_FIELDS, NAME_LEN = 0x083EE8, 58, 19, 13
ITEM_POOL, ITEM_SECTION_SIZE = 0x8D71E, 36598
# Category word at record +12, from the equip dispatch at 0x04237.
SHIELD, RING, WORN = 0x0800, 0x0400, 0x0200
# Worn sub-slot, from the properties word at +2 and the dispatch at 0x0431d.
# Only these four are tested there, so 0x2000, a fifth slot word the record
# carries, can never be filled. Robes and cloaks are 0x4000: body armor.
WORN_SLOTS = {0x8000: "head", 0x4000: "body", 0x1000: "feet", 0x0800: "hands"}
PLUS = re.compile(r"^(.*?) \+ ?(\d+)$")


def _wearables():
    world = (ROOT / "game" / "WORLD.DAT").read_bytes()
    out = []
    for i in range(ITEM_SECTION_SIZE // ITEM_REC):
        rec = world[ITEM_BASE + i * ITEM_REC:ITEM_BASE + (i + 1) * ITEM_REC]
        name = " ".join(
            p for p in (rec[ITEM_FIELDS + k * NAME_LEN:
                            ITEM_FIELDS + k * NAME_LEN + NAME_LEN - 1]
                        .split(b"\0")[0].decode("latin1")
                        .translate(labels.CHARSET).strip()
                        for k in range(3)) if p)
        category = struct.unpack_from("<H", rec, 12)[0]
        if not name or not category & (SHIELD | RING | WORN):
            continue
        offset = struct.unpack_from("<H", rec, 0)[0]
        absorb = world[ITEM_POOL + offset]
        value = int(rec[5:8].hex())
        if not absorb or not value:      # value 0 is quest loot, not a purchase
            continue
        if category & SHIELD:
            slot = "shield"
        elif category & RING:
            slot = "ring"
        else:
            flags = struct.unpack_from("<H", world, ITEM_POOL + offset + 2)[0]
            slot = WORN_SLOTS.get(flags & 0xD800)
        if slot is None:
            continue
        m = PLUS.match(name)
        out.append((slot, int(m.group(2)) if m else 0, absorb, name))
    return out


def _best_set(enchanted: bool) -> int:
    best: dict[str, int] = {}
    rings: list[int] = []
    for slot, plus, absorb, _ in _wearables():
        if not enchanted and plus:
            continue
        if slot == "ring":
            rings.append(absorb)
        else:
            best[slot] = max(best.get(slot, 0), absorb)
    # Two ring slots, but only one Ring of Invisibility a character: Yardley
    # makes four from one copper bar, one per party member.
    return sum(best.values()) + sum(sorted(rings, reverse=True)[:2])


def test_armour_ceiling_is_one_item_per_slot():
    """Not the eight highest numbers: four body armors cannot be worn at once."""
    assert _best_set(enchanted=False) == cm.UNENCHANTED[0] == 111
    assert _best_set(enchanted=True) == cm.ENCHANTED[0] == 161


def test_there_are_four_worn_slots_and_no_cloak():
    """Robes and cloaks compete with plate; they do not add to it."""
    worn = {name: slot for slot, _, _, name in _wearables()}
    for name in ("ROBES", "CLOTHES", "FIGHTER'S CLOTHING", "MAGICIAN'S CLOAK",
                 "ROYAL PLATE ARMOR"):
        assert worn[name] == "body"
    assert set(WORN_SLOTS.values()) == {"head", "body", "feet", "hands"}


def test_no_ring_can_be_enchanted():
    """So the two ring slots contribute the same 45 either way."""
    assert not any(plus for slot, plus, _, _ in _wearables() if slot == "ring")


def test_the_plain_set_arrives_before_the_enchanted_one(experience):
    """Gold, not slots, is what gates absorption, and it gates it late."""
    afforded = {L: cm.armor_afforded(L, experience, 0.5) for L in (10, 17, 25, 35)}
    assert afforded[10] < cm.UNENCHANTED[0]
    assert afforded[17] >= cm.UNENCHANTED[0]
    assert afforded[25] < cm.ENCHANTED[0]
    assert afforded[35] == cm.ENCHANTED[0]


# --- The fight -------------------------------------------------------------


def test_a_margin_of_55_is_where_missing_stops():
    assert cm.hit_odds(54) < 1.0
    assert cm.hit_odds(55) == 1.0
    # ...but damage keeps climbing, which is why 55 is not a wall
    assert cm.landed(250, 110) > cm.landed(250, 55)


def test_overkill_is_not_credited(enemies):
    """A cast that could kill twice over still kills once."""
    foe = enemies[40]
    modest = cm.Encounter(level=40, accuracy=400, damage=foe["health"],
                          absorption=999, health=1000, pool=1000, cost=100)
    huge = cm.Encounter(level=40, accuracy=400, damage=foe["health"] * 10,
                        absorption=999, health=1000, pool=1000, cost=100)
    assert modest.kills_per_rest(foe) == huge.kills_per_rest(foe)


def test_absorption_at_their_accuracy_ends_the_incoming_damage(enemies):
    foe = enemies[40]
    assert cm.expected(foe["damage"], foe["accuracy"], foe["accuracy"] - 1) > 0
    assert cm.expected(foe["damage"], foe["accuracy"], foe["accuracy"]) <= 1


# --- The healing economy ---------------------------------------------------
#
# The build advice turns on which heal is efficient for how many wounded, and
# on which monsters can take a character out of a fight. Both are read from
# data/spells.json and data/enemies.json rather than asserted.

import json  # noqa: E402


def _spells():
    return {s["name"]: s for s in json.loads(
        (ROOT / "data" / "spells.json").read_text())}


def test_party_heal_is_the_worst_single_target_heal():
    """8.9 health a mana across four, 2.2 on one, the whole basis for mixing."""
    sp = _spells()
    per_target = {n: min(sp[n]["amount"], 1066) / sp[n]["mp"]
                  for n in ("HEAL", "IMPROVE HEALTH", "PARTY HEAL",
                            "RESTORE HEALTH", "GREAT HEAL")}
    assert min(per_target, key=per_target.get) == "PARTY HEAL"
    assert max(per_target, key=per_target.get) == "GREAT HEAL"
    party = sp["PARTY HEAL"]
    assert party["scope"] == "all"
    assert party["amount"] * 4 / party["mp"] > per_target["GREAT HEAL"]


def test_party_heal_beats_great_heal_at_three_wounded():
    sp = _spells()
    party = sp["PARTY HEAL"]["amount"] / sp["PARTY HEAL"]["mp"]
    great = sp["GREAT HEAL"]["amount"] / sp["GREAT HEAL"]["mp"]
    assert 2 * party < great < 3 * party


def test_only_monk_and_alchemist_heal_inside_the_early_window():
    """Party Heal at 9 for them, 16 for everyone else: the window shuts at 15."""
    got = {c["class"]: c["level"]
           for c in _spells()["PARTY HEAL"]["classes"]}
    assert got["MONK"] == got["ALCHEMIST"] == 9
    assert all(v >= 16 for k, v in got.items()
               if k not in ("MONK", "ALCHEMIST"))


def test_a_monk_cannot_cast_party_heal_often_at_level_nine():
    """176 mana buys three casts, which is what makes wisdom the early buy."""
    pool = cm.magic_pool(4, 9, cm.ROLL_CAP, cm.ROLL_CAP)
    assert pool // _spells()["PARTY HEAL"]["mp"] == 3


INCAPACITATING = {"PARALYZE", "FROZEN", "STONING"}


def test_four_monsters_can_incapacitate_and_186_absorption_stops_them():
    rows = [e for e in json.loads((ROOT / "data" / "enemies.json").read_text())
            if e["listed"]]
    bad = [e for e in rows
           if set(e["attacks"] or []) & INCAPACITATING]
    assert len(bad) == 4
    assert max(e["accuracy"] for e in bad) == 185      # the ICE DWARF
    # a margin below zero never reaches the block that applies the condition
    assert cm.hit_odds(185 - 186) == 0.0


# --- Shop weapons versus the weapons of Light ------------------------------


def test_the_weapons_of_light_are_not_shop_stock():
    """They alone have no enchanted series, and they disintegrate on leaving."""
    items = json.loads((ROOT / "data" / "items.json").read_text())
    light = [i for i in items if i["name"].endswith("OF LIGHT")
             and i["category"] == "WEAPONS"]
    assert len(light) == 3
    assert all(not i["variants"] for i in light)
    assert all(int(i["fields"]["damage"]) == 250 for i in light)
    assert all(i["fields"]["damage"] != "250"
               for i in items
               if i["category"] == "WEAPONS" and i["variants"])


def test_the_best_buyable_weapon_reaches_thirty(experience):
    """Every strategy figure rests on 30, not on the 250 a quest lends you.

    40 exists (the 2-Handed Sword, War Hammer and Halberd all reach it at
    +10), but all three are two-handed, and carrying one costs the shield.
    """
    assert cm.weapon_afforded(40, experience) == 30
    assert cm.weapon_afforded(10, experience) < 20
    assert max(d for d, _, _ in cm.shop_weapons()) == 30
    assert max(d for d, _, _ in cm.shop_weapons(two_handed=True)) == 40


def test_the_absorption_bonus_steps_on_multiples_of_five():
    """Round-to-nearest puts the steps at 75, 80, 85, not at exact fifths.

    `pct` adds half the divisor before dividing, so an excess of 3 already
    reaches 1. Stopping on an exact division (dexterity 77, 82, 87) pays two
    points for absorption the multiple of five already bought.
    """
    steps = [d for d in range(73, 140)
             if cm.absorption(0, d) != cm.absorption(0, d - 1)]
    assert all(d % 5 == 0 for d in steps), steps
    assert steps[:4] == [75, 80, 85, 90]
    # the exact-division values cost two points for nothing
    for exact in (77, 82, 87):
        assert cm.absorption(0, exact) == cm.absorption(0, exact - 2)


def test_every_build_lands_its_dexterity_on_a_step():
    """A build that stops one to four points past a step has wasted them.

    138 is the natural dexterity of a level-40 character who rolled 60, so the
    manual's point totals have to carry it to a multiple of five.
    """
    natural = cm.ROLL_CAP + 2 * 39
    for build, points in (("self-sufficient", 142), ("untouchable", 372),
                          ("healer", 132), ("untouched by the median", 152),
                          ("untouched by the worst", 177),
                          ("untouched by Paltivar", 252)):
        assert (natural + points) % 5 == 0, (build, natural + points)


def test_the_ladder_tops_out_at_paltivars_accuracy():
    """Nothing swings above 240, so 241 absorption is the last useful point."""
    rows = [e for e in json.loads((ROOT / "data" / "enemies.json").read_text())
            if e["listed"]]
    hardest = max(e["accuracy"] for e in rows)
    assert hardest == 240
    natural = cm.ROLL_CAP + 2 * 39
    # 252 points reaches it; the next step up buys nothing
    assert cm.absorption(177, natural + 252) == hardest + 1
    assert cm.expected(400, hardest, cm.absorption(177, natural + 252)) == 0
    assert cm.expected(400, hardest, cm.absorption(177, natural + 372)) == 0


def test_strength_pays_once_the_margin_passes_the_crossover(experience):
    """The optimum split sits on margin == 5 x (weapon + strength bonus).

    Strength is worth buying for any build spending heavily on a weapon skill,
    because a 30-damage weapon cannot absorb a margin of 380.
    """
    foe = cm.enemies_by_level()[40]
    weapon = cm.weapon_afforded(40, experience)
    natural_skill = cm.natural_attack(1, "slashing", 40)
    natural_attr = cm.ROLL_CAP + 2 * 39

    def output(budget, strength_points):
        acc = natural_skill + budget - strength_points
        bonus = cm.absorption(0, natural_attr + strength_points)
        return cm.expected(weapon + bonus, acc, foe["absorption"])

    best = max(range(511), key=lambda s: output(510, s))
    assert 130 <= best <= 145                      # the berserker's split
    assert output(510, best) > output(510, 0) * 1.1  # worth more than a tenth
    # and the optimum lands on the crossover
    bonus = cm.absorption(0, natural_attr + best)
    margin = natural_skill + 510 - best - foe["absorption"]
    assert abs(margin - 5 * (weapon + bonus)) <= 10
    # a small attack budget stays below the crossover and wants little
    assert max(range(259), key=lambda s: output(258, s)) < 30


# --- Encounters ------------------------------------------------------------


def _listed():
    return [e for e in json.loads((ROOT / "data" / "enemies.json").read_text())
            if e["listed"]]


def test_group_bits_take_only_three_of_eight_combinations():
    """Which is what identifies them as a size rather than three flags."""
    seen = {e["masks"]["w96"] & cm.GROUP_BITS for e in _listed()}
    assert seen == {0x0000, 0xC000, 0xA000}
    sizes = collections.Counter(cm.group_size(e) for e in _listed())
    assert sizes == {3: 46, 2: 20, 1: 5}


def test_the_solo_monsters_are_the_five_named():
    assert {e["name"] for e in _listed() if cm.group_size(e) == 1} == {
        "MIMIC", "FROST DWARF TOWER", "FIRE DWARF TOWER", "ALLIGATOR",
        "CROCODILE"}


def test_party_attack_multiplies_what_one_character_takes():
    """Three Black Dragons put three attacks on every character, not three
    between them.

    The two rates are four apart and it matters which one a caller wants.
    `attacks_the_party` is the party-wide total; `attacks_a_character` is what
    `clear_group` takes, and mixing them up overstates damage taken fourfold.
    """
    by_name = {e["name"]: e for e in _listed()}
    dragon = by_name["BLACK DRAGON"]
    assert cm.group_size(dragon) == 3
    assert cm.attacks_the_party(dragon) == 12     # 3 monsters x all four
    assert cm.attacks_a_character(dragon) == 1.0  # one swing each, every round
    ghoul = by_name["GHOUL"]
    assert cm.group_size(ghoul) == 3
    assert cm.attacks_the_party(ghoul) == 3       # 3 monsters, one target each
    assert cm.attacks_a_character(ghoul) == 0.25  # spread over the four slots
    # The party-wide figure is always four times the per-character one, which
    # is exactly the size of the error if the two are confused.
    for monster in _listed():
        assert (cm.attacks_the_party(monster)
                == 4 * cm.attacks_a_character(monster) * cm.group_size(monster))


def test_arrival_rate_is_the_whole_of_tactical_play():
    """The same fight, won without a scratch or lost, on when they close."""
    # a party killing one monster a round, acting first, against three of
    # them; attacks_each is one monster's swings at one character, which is 1
    # for the PARTY ATTACK monsters this models.
    singly = cm.clear_group(output=700, incoming=100, monster_health=635,
                            size=3, attacks_each=1, first=True, arriving=1)
    together = cm.clear_group(output=700, incoming=100, monster_health=635,
                              size=3, attacks_each=1, first=True, arriving=3)
    assert singly[0] == together[0] == 3      # same rounds either way
    assert singly[1] == 0                     # each dies before it swings
    assert together[1] == 300                 # against a pool of 1,066 at 40


def test_acting_second_costs_a_round_of_damage():
    first = cm.clear_group(700, 100, 635, 3, 1, True, arriving=3)
    second = cm.clear_group(700, 100, 635, 3, 1, False, arriving=3)
    assert second[1] > first[1]


# --- the manual's tables ---------------------------------------------------

def test_the_ladder_builds_all_spend_the_same_budget():
    """`tools/ladder.py` is where MANUAL.md's tables come from. Its three
    builds are only comparable if each spends the whole 510 points a charisma
    roll of 52 pays out, so that is asserted rather than assumed."""
    import ladder

    assert [b.spent for b in ladder.BUILDS] == [510, 510, 510]
    # And 510 is what the budget actually is, net of the 40 into charisma.
    income = sum(cm.budget(52, 40).values()) // 1
    assert ladder.BUILDS[0].spent + 40 <= income


def test_the_ladder_uses_the_per_character_attack_rate():
    """The factor-of-four trap, pinned at the call site rather than the
    definition: what one Black Dragon puts on one character is 1, so three of
    them cost a berserker about half its health and not twice it."""
    import ladder

    foe = cm.enemies_by_level()[40]
    assert foe["name"] == "BLACK DRAGON"
    rows = {r["build"]: r for r in ladder.ladder(ladder.folded, foe)}
    health = ladder.HEALTH
    assert rows["Berserker"]["taken_singly"] == 0           # each dies first
    assert 0.4 < rows["Berserker"]["taken_together"] / health < 0.6
    assert rows["Untouchable"]["taken_together"] == 0


def test_the_roll_moves_defence_and_leaves_offence_alone():
    """Every level-40 build sits far past the margin where the hit chance
    saturates, so correcting the roll cannot touch a single offensive column --
    which is why the ladder's ordering survived the correction."""
    import ladder

    foe = cm.enemies_by_level()[40]
    flat = {r["build"]: r for r in ladder.ladder(ladder.flat, foe)}
    fold = {r["build"]: r for r in ladder.ladder(ladder.folded, foe)}
    for name in ("Berserker", "Rarely hit", "Untouchable"):
        assert flat[name]["party_rounds"] == fold[name]["party_rounds"]
    # Defensively the berserker sits at margin 54 and the untouchable below
    # zero, so both ends of the ladder barely move; only the rung in the middle
    # of the band does, and it moves by a third.
    assert abs(flat["Berserker"]["hit_you"] - fold["Berserker"]["hit_you"]) < 0.01
    assert flat["Untouchable"]["hit_you"] == fold["Untouchable"]["hit_you"] == 0
    assert fold["Rarely hit"]["hit_you"] / flat["Rarely hit"]["hit_you"] > 1.3


def test_the_tables_carry_the_unmultiplied_blow():
    """An expectation hides the thing that kills you: 34% of 42 and 100% of 14
    are the same number a round and not the same fight. Every table that quotes
    a chance to be hit also quotes what one landed hit does."""
    import ladder

    foe = cm.enemies_by_level()[40]
    rows = {r["build"]: r for r in ladder.ladder(ladder.folded, foe)}
    # Three Black Dragons at 34% deal 42 apiece, so a round where all three
    # land is 126, three times the 43 the expectation reports.
    rarely = rows["Rarely hit"]
    assert rarely["per_hit"] == 42
    assert round(rarely["taken_a_round"]) == 43
    assert rarely["per_hit"] * 3 > 2 * rarely["taken_a_round"]
    # And the build that is never hit has no blow to report.
    assert rows["Untouchable"]["hit_you"] == 0


def test_the_rarely_hit_rung_has_to_be_re_bought():
    """The rung is named for one swing in four and was priced when margin 13
    was 25%. Under the real roll that margin is 34%, so it costs more."""
    import ladder

    foe = cm.enemies_by_level()[40]
    printed = ladder.BUILDS[1]
    assert printed.dexterity == 187
    assert round(ladder.folded(foe["accuracy"] - printed.absorption), 3) == 0.344

    rebought = ladder.rung_at(0.266, ladder.folded, foe)
    assert rebought.dexterity == 212          # 25 more, and the budget still 510
    assert rebought.spent == printed.spent == 510
    # A quarter exactly is unreachable: the fold makes each step 2/64 wide in
    # that band, so 26.6% and 23.4% straddle it by the same margin.
    assert ladder.folded(8) > 0.25 > ladder.folded(7)


def test_the_level_forty_verdict_does_not_hold_for_the_whole_career():
    """The ladder is a snapshot, and the three rungs move under it.

    Immunity to the monster *at your level* is what is out of reach before 15,
    not immunity in general, which is the pivot the manual already names. The
    berserker is the only policy whose position gets worse every level, and the
    rarely-hit rung is nearly free early and costs two fifths of the budget at
    the top.
    """
    import ladder

    assert ladder.build_at("Untouchable", 14, ladder.folded) is None
    assert ladder.build_at("Untouchable", 15, ladder.folded) is not None

    rows = {r["level"]: r for r in ladder.career_table("Berserker",
                                                       ladder.folded)}
    assert all(rows[lvl]["one_rounds"] for lvl in rows)     # at every level
    assert rows[15]["hit_you"] < 0.5 < rows[40]["hit_you"]  # and worse each time

    hit = {r["level"]: r for r in ladder.career_table("Rarely hit",
                                                      ladder.folded)}
    assert hit[16]["hit_you"] == 0                # armor alone covers it
    assert hit[16]["dexterity"] < 30 < 200 < hit[40]["dexterity"]
    # a fifth of the budget at 15, two fifths of it at 40
    assert hit[15]["dexterity"] / hit[15]["budget"] < 0.25
    assert hit[40]["dexterity"] / hit[40]["budget"] > 0.4


def test_a_lethal_spell_is_required_before_a_cheap_one():
    """`kills_per_rest` scores a fractional kill per cast, so without a filter
    the cheapest spell in the list wins by being cast hundreds of times.

    Magic Attack at 9 damage and 2 magic is 38 casts against a Black Dragon and
    was scoring 27 kills a rest against it. The career walk prefers spells that
    kill in one cast and falls back to the rest only where none does.
    """
    table = cm.enemies_by_level()
    detail = cm.career(7, 11, "intelligence", "attack")["detail"]
    for level in (16, 20, 30, 40):
        d = detail[level]
        assert cm.landed(d["spell"], d["margin"]) >= table[level]["health"]


def test_buying_the_pool_too_long_leaves_nothing_that_kills():
    """Margin scales spell damage exactly as it scales a weapon's, so a caster
    that keeps buying intelligence ends with a large pool and an inert spell.

    This is the constraint the career sum hides: summed kills between rests
    peak at a switch around 18, which is a caster that cannot one-cast anything
    of its own level from 12 to 24.
    """
    import ladder

    dead = {r["switch"]: r for r in ladder.dead_levels()}
    assert dead[8]["count"] == 0
    assert dead[12]["count"] < dead[18]["count"] < dead[24]["count"]
    assert dead[18]["worst_run"] >= 13

    grid = {r["switch"]: r["kills"] for r in ladder.caster_schedule()}
    assert grid[18][35] > grid[12][35]        # the sum prefers the dead build


def test_resistance_is_a_floor_of_half_and_never_compounds():
    """The check leaves on the first bit that matches, so two matches halve
    once rather than quartering. Blazios is the only monster carrying two
    resistance bits and no blow matches both, so this guards the code rather
    than a case that arises today."""
    assert cm.resisted(cm.BLOW_SPELL, 0x2000) == 0.5
    assert cm.resisted(cm.BLOW_SHOT, 0x8000) == 0.5
    assert cm.resisted(0xA000, 0xE000) == 0.5          # two matches, still half
    assert cm.resisted(cm.BLOW_SPELL, 0x8000) == 1.0   # wrong kind


def test_a_melee_swing_carries_no_word_so_nothing_halves_it():
    """Image 0x00E73 resolves a swing and 0x00EC8 subtracts it with nothing in
    between. Bit 14 is the one physical bit no blow sets; if it is ever pinned
    down as the melee bit, MELEE_RESISTED is the single switch."""
    for word in (0x8000, 0x4000, 0x2000, 0xE000):
        assert cm.resisted(cm.BLOW_MELEE, word) == 1.0


def test_the_level_forty_basis_monster_halves_spell_damage():
    """The Black Dragon carries bit 13, which is why a single caster no longer
    one-rounds a group of them however much casting it has bought."""
    import ladder

    foe = cm.enemies_by_level()[40]
    assert cm.foe_resistance(foe) == 0x2000
    assert cm.resisted(cm.BLOW_SPELL, cm.foe_resistance(foe)) == 0.5
    assert not any(r["one_rounds"] for r in ladder.caster_rungs(ladder.folded, foe))


def test_a_caster_cannot_dodge_resistance_by_spell_choice():
    """59 of the 70 listed damage spells carry bit 13. The ones that do not are
    weak enough that picking them is not a strategy."""
    import json

    spells = json.loads((cm.ROOT / "data" / "spells.json").read_text())
    damage = [s for s in spells if s.get("listed") and s.get("damage")]
    resisted = [s for s in damage if cm.spell_blow(s) & cm.BLOW_SPELL]
    assert len(resisted) / len(damage) > 0.8
    escapes = [s for s in damage if not cm.spell_blow(s)]
    assert max(s["damage"] for s in escapes) < 50


def test_the_extracted_resistance_fields_match_the_record():
    """`foe_resistance` reads the extractor's booleans; this checks them
    against offset 102 of the record they came from, so a change to either
    side shows up here rather than quietly moving a table."""
    from_record = cm.resistances()
    if not from_record:
        pytest.skip("no game/WORLD.DAT to cross-check against")
    rebuilt = cm._from_extract()
    for name, fields in from_record.items():
        if name not in rebuilt:
            continue
        want = fields["resistance"] & (cm.BLOW_SPELL | cm.BLOW_SHOT | cm.BIT_14)
        assert rebuilt[name] == want, name


def test_immunity_is_not_a_strong_resistance():
    """Resistance halves; immunity takes the damage to nothing, and only for
    the one damage type. They are separate words on the record and separate
    mechanics, and the extractor's `resist_magic` merges them because the
    game's own page prints them on one row."""
    import json

    spells = json.loads((cm.ROOT / "data" / "spells.json").read_text())
    fire = next(s for s in spells
                if s.get("damage") and "FIRE" in (s.get("element") or []))
    plain = next(s for s in spells
                 if s.get("damage") and not s.get("element"))
    dwarf = {"name": "FIRE DWARF"}
    assert cm.immune_to(dwarf, fire)        # nothing at all
    assert not cm.immune_to(dwarf, plain)   # an elementless spell is untouched
    # And immunity does not appear in the resistance word.
    assert not cm.foe_resistance(dwarf) & cm.BLOW_SPELL


def test_a_damage_type_immunity_narrows_the_list_rather_than_disarming():
    """39 of the 70 damage spells carry no element, so no damage-type immunity
    reaches them. A caster always has something to throw."""
    import json

    spells = json.loads((cm.ROOT / "data" / "spells.json").read_text())
    damage = [s for s in spells if s.get("listed") and s.get("damage")]
    elementless = [s for s in damage if not s.get("element")]
    assert len(elementless) > len(damage) / 2
