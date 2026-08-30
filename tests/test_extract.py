"""Decoder tests, anchored on facts that can be checked without trusting the
decoder: names the game prints, numbers its own prose quotes, and orderings
that follow from the game's difficulty curve.
"""
import base64
import collections
import json
import re
from pathlib import Path

import pytest

import extract
import labels
import sections as S
import tiles

ROOT_TOOLS = Path(__file__).resolve().parent.parent / "tools"
OBSERVED = Path(__file__).resolve().parent.parent / "observed"


def observed(name: str) -> dict:
    """One transcription of the game's screens, or a skip where it is not kept.

    The transcriptions are the game's content and are not distributed, so a
    tree without them skips the tests that check the decode against them.
    """
    path = OBSERVED / name
    if not path.exists():
        pytest.skip(f"no {name}; the screen transcriptions are not distributed")
    return json.loads(path.read_text())


def observed_items() -> dict:
    """The 170 captured F5 pages, keyed by decoded name.

    Every row is decoded, and these are what the decode is checked against.
    The capture is keyed by the name as the record stores it, apostrophes and
    all ("MAGE~S CHAIN MAIL ARMOR"), so the keys go through the game's charset
    here to meet the decoded names.
    """
    return {key.translate(labels.CHARSET): value
            for key, value in observed("observed_items.json")["items"].items()}


# --- enemies ---------------------------------------------------------------

def test_enemy_count_and_sentinel(directory, data):
    # 73 records, of which record 0 is zero-filled and is dropped.
    assert directory[S.ENEMIES].size // S.ENEMY_RECORD == 73
    assert len(data["enemies"]) == 72
    first = directory[S.ENEMIES].records(directory.world, S.ENEMY_RECORD)[0]
    assert first == bytes(S.ENEMY_RECORD)


def test_first_monsters_are_the_known_ones(data):
    assert [e["name"] for e in data["enemies"][:3]] == [
        "WASP", "CENTIPEDE", "WASP QUEEN"]
    assert data["enemies"][-1]["name"] == "PURPLE DRAGON"


def test_names_are_clean_ascii(data):
    for e in data["enemies"]:
        assert e["name"] == e["name"].strip()
        assert all(0x20 <= ord(c) < 0x7F for c in e["name"])


def test_two_field_names_are_joined(data):
    """The record splits names across two 13-byte fields so two-word names
    fit; both halves must survive into the output."""
    names = {e["name"] for e in data["enemies"]}
    assert "FROST DWARF TOWER" in names
    assert "SKELETAL WARRIOR" in names


def test_stats_verified_against_the_running_game(data):
    """These exact numbers were read off the game's F2 screen under emulation.
    Two monsters three orders of magnitude apart, so the mapping cannot be a
    coincidence of scale."""
    by = {e["name"]: e for e in data["enemies"]}
    aco = by["ACOKNIGHT"]
    assert (aco["health"], aco["accuracy"], aco["dexterity"],
            aco["absorption"], aco["damage"]) == (175, 110, 115, 48, 87)
    bla = by["BLAZIOS"]
    assert (bla["health"], bla["accuracy"], bla["dexterity"],
            bla["absorption"], bla["damage"]) == (2900, 235, 260, 165, 390)


def test_stats_rise_with_difficulty(data):
    by = {e["name"]: e for e in data["enemies"]}
    wasp, boss = by["WASP"], by["PALTIVAR"]
    for stat in ("health", "accuracy", "dexterity", "absorption", "damage"):
        assert wasp[stat] < boss[stat], stat
    assert wasp["health"] == 9
    assert boss["health"] == 3400


def test_family_groups_monsters_that_belong_together(data):
    """The family code is what the game's INSECT / UNDEAD flags key off."""
    by = {e["name"]: e["family"] for e in data["enemies"]}
    insects = ["WASP", "CENTIPEDE", "WASP QUEEN", "PRAYING MANTIS", "MILLIPEDE"]
    assert len({by[n] for n in insects}) == 1
    undead = ["GHOST", "GHOUL", "SKELETON", "WIGHT", "SPECTRE"]
    assert len({by[n] for n in undead}) == 1
    assert by["WASP"] != by["GHOST"]


def test_rewards_are_packed_bcd(data):
    """Rewards are stored as decimal digits, not integers: WASP's 15 experience
    is the bytes 00 00 00 15, and PALTIVAR's 1,000,000 is 01 00 00 00. All four
    figures were checked against the game's screen for every monster."""
    by = {e["name"]: e for e in data["enemies"]}
    assert (by["WASP"]["experience"], by["WASP"]["gold"]) == (15, 30)
    assert by["ACOKNIGHT"]["experience"] == 1_000
    assert by["ACOKNIGHT"]["gold"] == 3_000
    assert by["ACOKNIGHT"]["food"] == 4
    assert by["ACOKNIGHT"]["nuore"] == 40
    assert by["PALTIVAR"]["experience"] == 1_000_000
    assert by["BLAZIOS"]["gold"] == 3_000_000


def test_no_reward_field_decodes_to_an_invalid_bcd(data):
    for e in data["enemies"]:
        for field in ("experience", "gold", "food", "nuore"):
            assert e[field] is not None, f"{e['name']}.{field}"
            assert e[field] >= 0


def test_resistance_is_a_level_not_a_flag(data):
    """Bits 15 and 14 of the resistance word never appear together, so they are
    a two-level scale. The game prints the same word for both, so the level is
    carried through rather than flattened."""
    by = {e["name"]: e for e in data["enemies"]}
    # Bits 15 and 14 both print on the game's PHYSICAL DAMAGE row and answer
    # different damage types: ACOKNIGHT's 15 is the type a shot carries,
    # BLAZIOS's 14 a type nothing carries.
    assert by["ACOKNIGHT"]["resist_physical"] and by["ACOKNIGHT"]["resist_shot"]
    assert by["BLAZIOS"]["resist_physical"] and not by["BLAZIOS"]["resist_shot"]
    assert not by["WASP"]["resist_physical"]
    assert sum(1 for e in data["enemies"] if e["resist_shot"]) == 13
    assert sum(1 for e in data["enemies"] if e["resist_physical"]) == 22


# Where the game's own F2 renderer calls its two helpers, one call a row: ten
# for IMMUNE and two for RESISTANT. Each passes the row's mask in ax and the
# row's label in bx.
EFFECT_ROWS = [0x7D98, 0x7DAD, 0x7DC2, 0x7DD7, 0x7DEC, 0x7E01,
               0x7E16, 0x7E2B, 0x7E40, 0x7E55, 0x7E6A, 0x7E9C]


def test_the_effect_rows_come_from_the_games_own_masks():
    """The twelve rows of the monster page are twelve calls, and each carries
    the mask it prints for. Reading them says what every bit of the immunity
    and resistance words is filed under, which is stronger than matching our
    decode against screenshots of the result, because it is the rule rather
    than an instance of it.
    """
    exe = _exe()
    rows = []
    for at in EFFECT_ROWS:
        mask = label = None
        for ins in exe.disasm(exe.aligned_start(at, 40), 40):
            if ins.address >= at:
                break
            if ins.mnemonic == "mov" and ins.op_str.startswith("ax, "):
                mask = int(ins.op_str.split(", ")[1], 0)
            if ins.mnemonic == "mov" and ins.op_str.startswith("bx, "):
                label = int(ins.op_str.split(", ")[1], 0)
        text = exe.data[extract.L.DGROUP + label:][:24]
        rows.append((text.split(b"\x00")[0].decode("latin1").rstrip(":"), mask))

    immunity, resistance = rows[:10], rows[10:]
    assert [name for name, _ in rows] == list(extract.L.EFFECTS)
    # Every immunity row is one bit, and it is the bit we decode it as.
    for name, mask in immunity:
        assert bin(mask).count("1") == 1, name
        bit = mask.bit_length() - 1
        assert extract.IMMUNITY_BITS[bit] == name, (name, bit)
    # The two resistance rows are not one bit each.
    assert dict(resistance) == {"MAGIC DAMAGE": extract.RESIST_MAGIC_ROW,
                                "PHYSICAL DAMAGE": extract.RESIST_PHYSICAL_ROW}


def test_a_resistance_bit_is_worth_what_sets_it(directory, data):
    """A resistance halves the blow when the blow's own word carries the same
    bit, so what a bit is worth is decided by what sets it. A spell's word is
    the upper bits of its record 76 and takes three values across all 107; a
    shot's is built from the weapon and is 0x8000, or 0x8800 from an enchanted
    one; a melee swing builds no word at all."""
    import items as I
    import struct

    masks = {struct.unpack_from("<H", rec, 76)[0] & 0xFE00
             for rec in directory[S.SPELLS].records(directory.world, S.SPELL_RECORD)}
    assert masks == {0x0000, 0x0200, 0x2000}
    assert extract.RESIST_MAGIC_ROW & 0x2000 in masks
    assert extract.RESIST_UNMATCHED not in masks
    assert extract.RESIST_SHOT not in masks   # a spell is never a shot

    # The bit a shot sets from the weapon's flag word, 0x400, is carried by no
    # weapon and no ammunition, so a shot's word is only ever 0x8000 or,
    # where the weapon is enchanted, 0x8800.
    items = I.Items(directory)
    weapons = [items.properties(rec) for i, rec in enumerate(items.records, 1)
               if items.names[i - 1] and items.table_of(rec) == "weapon"]
    assert weapons and not any(I._u16(p, 2) & 0x400 for p in weapons)
    assert {bool(I._u16(p, 8)) for p in weapons} == {True, False}

    unmatched = {e["name"] for e in data["enemies"] if e["resist_unmatched"]}
    assert len(unmatched) == 9 and "KING BARIAG" in unmatched


def test_magic_resistance_comes_from_either_source(data):
    """Four monsters are shown RESISTANT to magic on the strength of the
    immunity word alone, with nothing set in the resistance word."""
    by = {e["name"]: e for e in data["enemies"]}
    for n in ("BLAZIOS", "CHAMELEON MAN", "FIRE DWARF", "SORCERER"):
        assert by[n]["resist_magic"], n
        assert by[n]["masks"] is not None
    assert not by["WASP"]["resist_magic"]


def test_damage_type_immunities_are_named(data):
    """Solved from the game's screens: fire, cold, electric and power sit in
    the low bits of the immunity word."""
    by = {e["name"]: e for e in data["enemies"]}
    assert "FIRE" in by["FIRE GIANT"]["immune"]
    assert "COLD" in by["FROST GIANT"]["immune"]
    assert set(by["BLAZIOS"]["immune"]) == {"FIRE", "ELECTRIC", "POWER"}
    # Nothing is immune to physical damage, only resistant to it.
    assert not any("PHYSICAL DAMAGE" in e["immune"] for e in data["enemies"])


def test_the_placeholder_record_is_flagged_unlisted(data):
    """The game leaves "NOT USED" out of its own list; pinning that down is what
    aligned the alphabetical screen order to the table order."""
    by = {e["name"]: e for e in data["enemies"]}
    assert by["NOT USED"]["listed"] is False
    assert sum(1 for e in data["enemies"] if e["listed"]) == 71


def test_ranged_stats(data):
    """Only 13 monsters have ranged attacks; for the rest the game leaves the
    rows blank, so they decode to None rather than 0."""
    by = {e["name"]: e for e in data["enemies"]}
    assert (by["BANDIT"]["ranged_accuracy"], by["BANDIT"]["ranged_damage"]) == (92, 60)
    assert by["ACOKNIGHT"]["ranged_accuracy"] is None
    assert sum(1 for e in data["enemies"] if e["ranged_accuracy"]) == 13


def test_special_attacks_are_decoded_not_only_observed(data):
    """The two record bits, plus the conditions from the attack id's table.

    This used to assert that FUNGUS decoded to PARTY ATTACK alone, with its
    three conditions available only as a screen reading. They are decoded now,
    so the weaker expectation would hide the stronger result.
    """
    by = {e["name"]: e for e in data["enemies"]}
    assert by["ACOKNIGHT"]["attacks"] == ["PARTY ATTACK"]
    assert by["CROCODILE"]["attacks"] == ["BREAK SHIELD"]
    assert by["FUNGUS"]["attacks"] == ["PARTY ATTACK", "SICK", "POISON", "DISEASE"]


def test_condition_immunities_match_the_game(data):
    """Ground truth: the game's own F2 screen shows ACOKNIGHT as IMMUNE to
    exactly POISON, DISEASE, PARALYSIS, FREEZING, HEXING and CURSING, and
    BLAZIOS as immune to none of them."""
    by = {e["name"]: e for e in data["enemies"]}
    assert set(by["ACOKNIGHT"]["immune"]) == {
        "POISON", "DISEASE", "PARALYSIS", "FREEZING", "HEXING", "CURSING"}
    # BLAZIOS is immune to no *condition*, only to damage types.
    conditions = {"POISON", "DISEASE", "PARALYSIS", "FREEZING", "HEXING", "CURSING"}
    assert set(by["BLAZIOS"]["immune"]) & conditions == set()


def test_all_undead_share_the_undead_immunity_word(data):
    """Every undead is immune to all six conditions and nothing else, which is
    what being undead should mean and corroborates the bit order."""
    by = {e["name"]: e for e in data["enemies"]}
    conditions = {"POISON", "DISEASE", "PARALYSIS", "FREEZING", "HEXING", "CURSING"}
    for n in ("GHOST", "GHOUL", "SKELETON", "WIGHT", "SPECTRE",
              "SKELETAL WARRIOR"):
        assert set(by[n]["immune"]) == conditions, n


def test_frost_and_fire_monsters_carry_the_right_immunity(data):
    by = {e["name"]: e for e in data["enemies"]}
    for n in ("FROST GIANT", "SNOW GIANT", "ICE DWARF", "FROST DWARF"):
        assert "COLD" in by[n]["immune"] and "FIRE" not in by[n]["immune"], n
    for n in ("FIRE GIANT", "FIRE DWARF", "FIRE MANTIS", "BLAZIOS"):
        assert "FIRE" in by[n]["immune"] and "COLD" not in by[n]["immune"], n


def test_unconfirmed_fields_are_not_given_real_names(data):
    """Guard against a future refactor quietly promoting a guess to a name."""
    e = data["enemies"][0]
    assert set(e["unknown"]).issubset({f"u{o}" for o in extract.ENEMY_UNKNOWN})
    assert all(k.startswith("u") for k in e["unknown"])
    # The reward bytes are decoded now, so they must no longer be listed as
    # unknown; a regression that re-added them would be silently wrong.
    for off in (76, 77, 78, 79, 82, 83, 86, 87, 88, 89, 90, 91):
        assert off not in extract.ENEMY_UNKNOWN


# --- spells ----------------------------------------------------------------

def test_spell_count_and_known_names(data):
    assert len(data["spells"]) == 107
    assert [s["name"] for s in data["spells"][:4]] == [
        "HEAL", "MAGIC ATTACK", "SLING SHOT", "COLD SLASH"]


def test_every_spell_has_a_description(data):
    for s in data["spells"]:
        # A handful of table slots are placeholders named ERROR; they still
        # carry text, so the pairing must hold for all 107.
        assert s["description"], s["name"]


def test_description_index_is_contiguous(directory):
    """The (start_line, count) pairs must tile the description stream without
    gaps or overlap, which is what proves the index was read correctly."""
    import struct
    idx = directory.rest(extract.SPELL_TEXT_INDEX)
    pairs = struct.unpack_from(f"<{idx.size // 2}H", directory.world, idx.offset)
    assert (pairs[0], pairs[1]) == (0, 0)  # sentinel
    n = directory[S.SPELLS].size // S.SPELL_RECORD
    expected = 1
    for i in range(1, n + 1):
        start, count = pairs[i * 2], pairs[i * 2 + 1]
        assert start == expected, f"pair {i} starts at {start}, expected {expected}"
        assert count > 0
        expected = start + count
    total = directory.spell_text_section().size // S.SPELL_TEXT_COLS
    assert expected <= total


def test_known_descriptions(data):
    by = {s["name"]: s["description"] for s in data["spells"]}
    assert by["HEAL"] == (
        "THIS SPELL WILL RESTORE 10 HEALTH POINTS TO A SINGLE PLAYER.")
    assert by["SLING SHOT"].startswith("LIKE THE EFFECTS OF A POWERFUL SLING")


def test_charset_substitutions_applied(data):
    """The game has no apostrophe glyph (uses '~') and writes fractions with a
    backslash. Neither may survive into the JSON."""
    blob = " ".join(s["description"] for s in data["spells"])
    assert "~" not in blob
    assert "\\" not in blob
    assert any("'" in s["name"] for s in data["spells"])  # MINER'S LIGHT I


DAMAGE_IN_PROSE = re.compile(r"\bUP TO (\d+)\s+POINTS|\b(\d+) POINTS OF")


def test_damage_field_matches_the_numbers_the_prose_quotes(data):
    """The strongest available proof that the damage column is the damage
    column: each spell's own description names its damage figure."""
    checked = mismatched = 0
    for s in data["spells"]:
        m = DAMAGE_IN_PROSE.search(s["description"])
        if not m:
            continue
        checked += 1
        if int(m.group(1) or m.group(2)) != s["damage"]:
            mismatched += 1
    assert checked >= 60
    # ERADICATE's text says 400 where its record says 480, a discrepancy in
    # the game's own content, not in the decode. Allow exactly that one.
    assert mismatched <= 1


def test_the_discrepancies_in_the_games_own_spell_data(data):
    """The five places a spell's prose and its record disagree, or one clue
    book page disagrees with another. Pinned so a later pass does not "fix"
    one into a wrong decode; `docs/spells.md` lists them.

    SWORD OF ICE and the FIERY SPEAR contradiction have tests of their own.
    """
    by = {s["name"]: s for s in data["spells"]}
    assert by["ERADICATE"]["damage"] == 480          # the prose says 400
    assert "400" in by["ERADICATE"]["description"]
    assert by["HARDY PARTY"]["amount"] == 600        # the prose says 650
    assert "650" in by["HARDY PARTY"]["description"]
    # Offset 22 is the lowest of a spell's class levels on 95 of the 98.
    off = {s["name"] for s in data["spells"] if s["listed"] and s["classes"]
           and s["level"] != min(c["level"] for c in s["classes"])}
    assert off == {"DISEASE CLOUD", "FIERY SPEAR", "MINER'S LIGHT I"}


def test_non_damaging_spells_have_zero_damage(data):
    by = {s["name"]: s["damage"] for s in data["spells"]}
    for name in ("HEAL", "CURE POISON", "MINER'S LIGHT I"):
        assert by[name] == 0, name


def test_spell_costs_decoded_from_the_record(data):
    """MP and nuore were solved against the game's own F3 screen for every
    spell the clue book lists, and match exactly at these offsets."""
    import json
    from pathlib import Path
    printed = observed("observed_spells.json")
    by = {s["name"]: s for s in data["spells"]}
    checked = 0
    for name, seen in printed.items():
        spell = by[name]
        assert spell["mp"] == seen["mp"], f"{name}: MP"
        assert spell["nuore"] == seen["nuore"], f"{name}: nuore"
        checked += 1
    assert checked >= 95


def test_affects_and_when_reproduce_every_screen(data):
    """The AFFECTS and WHEN rows, decoded rather than read.

    The F3 printer builds them out of four words of the record (72, 76, 30
    and 70), and `extract.spell_affects` walks its branches in the same
    order. That makes the 98 captured screens the check on the decode instead
    of its source: every one of them, exactly, including the nine spells whose
    AFFECTS row the printer leaves blank.
    """
    seen = observed("observed_spells.json")
    by = {s["name"]: s for s in data["spells"]}
    blank = 0
    for name, screen in seen.items():
        spell = by[name]
        target, reach = screen["target"], None
        for _, phrase in extract.SPELL_REACH:
            if target and target.endswith(" " + phrase):
                target, reach = target[: -len(phrase) - 1], phrase
                break
        assert (spell["scope"], spell["target"], spell["reach"], spell["when"]) \
            == (screen["scope"], target, reach, screen["when"]), name
        blank += screen["target"] is None
    assert len(seen) == 98 and blank == 9


def test_which_records_the_book_lists_comes_out_of_the_list_registry(data):
    """`listed` is read, not inferred from which screens a capture reached.

    The registry at `ds:0xf6a8` that holds the six item categories holds the
    clue book's other sections too: list 2 the monsters, list 3 the spells.
    Both agree with the walks: the 71 monsters the F2 section pages through,
    and the 98 spells the F3 section does, which are the ones the capture run
    photographed.
    """
    seen = observed("observed_spells.json")
    assert {s["name"] for s in data["spells"] if s["listed"]} == set(seen)
    assert [e["name"] for e in data["enemies"] if not e["listed"]] == ["NOT USED"]


def test_every_listed_spell_has_casting_classes(data):
    listed = [s for s in data["spells"] if s["listed"]]
    assert len(listed) == 98
    for s in listed:
        # Up to six now: the decode is not limited to the three rows the
        # clue book's page has room to print.
        assert 1 <= len(s["classes"]) <= 6, s["name"]
        for c in s["classes"]:
            assert c["class"] in ("MONK", "ALCHEMIST", "PALADIN",
                                  "MAGE", "DRUID", "MARKSMAN"), s["name"]
            assert 1 <= c["level"] <= 40, (s["name"], c)
            assert c["source"] in (None, "TRAINING", "SCROLL"), (s["name"], c)


def test_spell_targeting_is_classified(data):
    """Single-target versus area, and what it acts on."""
    by = {s["name"]: s for s in data["spells"]}
    assert by["HEAL"]["scope"] == "one"
    assert by["HEAL"]["target"] == "character"
    assert by["ACID RAIN"]["scope"] == "all"
    assert by["ACID RAIN"]["target"] == "visible monsters"
    # Reach is split out of the AFFECTS row so it does not repeat the WHEN row.
    assert by["COLD SLASH"]["target"] == "monster"
    assert by["COLD SLASH"]["reach"] == "in hand to hand"
    # Offset 74 is the element, in the same bit layout as the enemy immunity
    # word, and that shared vocabulary is the point: the game tests one against
    # the other, so "cold" here matches "immune to cold" there.
    by = {s["name"]: s for s in data["spells"]}
    for name, element in [("FIREBALL", ["FIRE"]), ("COLD SLASH", ["COLD"]),
                          ("LIGHTNING BOLT", ["ELECTRIC"]), ("POWER SURGE", ["POWER"]),
                          ("POISON CLOUD", ["POISON"]), ("DISEASE CLOUD", ["DISEASE"]),
                          ("CRITICAL WOUNDS", [])]:
        assert by[name]["element"] == element, name
    # SWORD OF ICE promises in prose that cold-immune monsters are spared, but
    # carries no element bit, so in game they are not. A bug in the game's data,
    # recorded here so a future change does not "fix" it into a wrong decode.
    assert "COLD" in by["SWORD OF ICE"]["description"].upper()
    assert by["SWORD OF ICE"]["element"] == []
    # An element is only ever set on something that deals damage.
    for s in data["spells"]:
        if s["listed"] and s["element"]:
            assert s["damage"], s["name"]
            assert set(s["element"]) <= set(extract.IMMUNITY_BITS.values()), s["name"]

    # Offset 34 is an amount whose meaning follows the effect: health restored
    # for a heal, but the dexterity bonus on FEET OF FEATHERS. It is exposed raw
    # alongside the family flag rather than as a decoded "healing" field.
    by_name = {s["name"]: s for s in data["spells"]}
    for name, amount in [("HEAL", 10), ("IMPROVE HEALTH", 50), ("PARTY HEAL", 100),
                         ("RESTORE HEALTH", 200), ("GREAT HEAL", 500),
                         ("PERFECT HEALTH", extract.SPELL_HEAL_ALL)]:
        assert by_name[name]["amount"] == amount, name
        assert by_name[name]["restorative"], name
        assert not by_name[name]["damage"], name
    # Nothing that does damage is in the restorative family.
    for s in data["spells"]:
        if s["listed"] and s["damage"]:
            assert not s["restorative"], s["name"]

    for s in data["spells"]:
        if s["listed"]:
            reaches = [phrase for _, phrase in extract.SPELL_REACH]
            assert s["reach"] in (None, *reaches), s["name"]
            assert not any((s["target"] or "").endswith(p)
                           for p in reaches), s["name"]
            assert s["scope"] in (None, "one", "all"), s["name"]
            assert s["when"] in (None, "anytime", "in hand to hand",
                                 "out of hand to hand"), s["name"]


def test_placeholder_spells_carry_no_observations(data):
    """The clue book omits the ERROR placeholders, as it omits NOT USED from
    the monster list."""
    for s in data["spells"]:
        if s["name"] == "ERROR":
            assert not s["listed"] and s["classes"] == []


# --- items -----------------------------------------------------------------

def test_item_table_geometry(directory):
    """631 records of 58 bytes: 19 field bytes then three 13-byte name fields."""
    size = next(s.size for s in directory.sections if s.offset == extract.ITEM_BASE)
    assert size % extract.ITEM_RECORD == 0
    assert size // extract.ITEM_RECORD == 631
    assert (extract.ITEM_FIELD_BYTES
            + extract.ITEM_NAME_FIELDS * extract.ITEM_NAME_LEN) == extract.ITEM_RECORD


def test_item_names_span_all_three_fields(data):
    """A name runs across the three fields: "BROKEN" + "BO STICK" is one item."""
    names = {i["name"] for i in data["items"]}
    assert "BROKEN BO STICK" in names
    assert "ARMORED BOOTS" in names
    for item in data["items"]:
        assert item["name"] == item["name"].strip()
        assert item["name"].isprintable()


def test_item_value_and_weight_decoded(data):
    """Checked against the game's own F5 pages.

    Base value is packed BCD over three bytes, five digits because the SCEPTER
    OF BARIAG costs 10,000, and weight is a uint16 of tenths, which
    it has to be: the ANVIL OF LIGHT weighs 50.0 and would overflow a byte.
    """
    by = {i["name"]: i for i in data["items"]}
    for name, value, weight in [("ARMORED BOOTS", 250, 4.5),
                                ("CHAIN MAIL ARMOR", 2000, 9.0),
                                ("2-HANDED SWORD", 10000, 9.0),
                                ("BLACK POTION", 200, 0.5),
                                ("ANVIL OF LIGHT", None, 50.0)]:
        if value is not None:
            assert by[name]["value"] == value, name
        assert by[name]["weight"] == weight, name
    # Crown of Euron really does have no price, and the game prints no line.
    assert by["CROWN OF EURON"]["value"] == 0


def test_item_value_and_weight_match_every_screen(data):
    """Not a sample: every figure the clue book printed has to agree."""
    printed = observed_items()
    by = {i["name"]: i for i in data["items"]}
    checked = 0
    for name, seen in printed.items():
        fields = seen["fields"]
        item = by[name]
        if fields.get("base value"):
            want = float(fields["base value"].replace(",", ""))
            assert item["value"] == want, name
            checked += 1
        if fields.get("weight"):
            assert item["weight"] == float(fields["weight"]), name
            checked += 1
    assert checked >= 300


def test_absorption_comes_from_the_properties_table(data):
    """Bytes 0-1 point into a second table whose first byte is the absorption.

    Only reported where the game prints an ABSORPTION line: the pool is shared
    and its blocks are not a fixed shape, so that byte means something else for
    a potion. Where both exist they agree exactly.
    """
    by = {i["name"]: i for i in data["items"]}
    agreed = 0
    for name, seen in observed_items().items():
        shown = seen["fields"].get("absorption")
        if shown:
            assert by[name]["absorption"] == int(shown), name
            agreed += 1
        else:
            assert by[name]["absorption"] is None, name
    assert agreed == 38


def test_enchanted_variants_are_folded_into_the_base_item(data):
    """The book puts a series behind a selector; the record lists each separately.

    Two things this guards, both of which leaked items into the list as if they
    were their own:

    * the digits are not always one: enhancement runs to **+10**, and nine
      items reach it;
    * the series does not always stop at +8, so the fold has to cover the whole
      range rather than a guessed ceiling.
    """
    by = {i["name"]: i for i in data["items"]}
    assert "CLOTHES +1" not in by
    assert not [n for n in by if extract.PLUS.match(n)], "an enchanted form leaked"

    tens = [i for i in data["items"] if any(v["plus"] == 10 for v in i["variants"])]
    assert len(tens) == 9
    assert extract.MAX_PLUS == 10

    boots = by["ARMORED BOOTS"]
    assert [v["plus"] for v in boots["variants"]] == list(range(1, 9))
    assert all(v["value"] >= boots["value"] for v in boots["variants"])
    assert by["CLOTHES"]["variants"] and len(by["CLOTHES"]["variants"]) == 2

    # The stray space in `RUBY MORNING STAR + 2` used to leave a hole in that
    # weapon's series; the optional space in PLUS closes it.
    assert [v["plus"] for v in by["RUBY MORNING STAR"]["variants"]] == list(range(1, 9))


def test_the_book_categories_come_out_of_the_executable(data, directory):
    """The book's filing is six lists of item ids in REGISTER.EXE, one per
    category the F5 menu opens, read through the pointer table at ds:0xf6a8.

    They are not a sample: between them the six lists hold exactly the 170
    items whose pages were captured, and every one of those pages agrees on
    which category it belongs to.
    """
    import items as I

    lists = I.Items(directory).categories()
    assert sorted(lists) == sorted(set(extract.ITEM_CATEGORIES)
                                   - {"ATTRIBUTE ENHANCERS", "TRANSPORTATIONS"})
    assert sum(len(ids) for ids in lists.values()) == 170

    listed = [i for i in data["items"] if i["listed"]]
    assert len(listed) == 170
    captured = observed_items()
    for item in listed:
        assert item["category"] == captured[item["name"]]["category"]
    unlisted = [i for i in data["items"] if not i["listed"]]
    assert unlisted and all(i["category"] is None for i in unlisted)


def _as_read(value):
    """A decoded row as the screen reader would have read it off the page.

    The reader joins the runs on a row without knowing the gaps between them,
    and it only keeps the inks the values are printed in, so the trailing
    PERCENT and MINUTES never reached the capture. Comparing on spaces removed,
    and as a prefix, is what those two facts leave.
    """
    if isinstance(value, float):
        text = f"{value:.1f}"
        return text.lstrip("0") if value < 1 else text
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def test_every_captured_item_page_is_reproduced(data):
    """The strong form of the check: each row of each captured F5 page, against
    the row the decode produces for it. 650 rows over 170 pages."""
    by = {i["name"]: i for i in data["items"]}
    checked = 0
    for name, seen in observed_items().items():
        item = by[name]
        page = dict(item["fields"], **{"base value": item["value"],
                                       "weight": item["weight"],
                                       "absorption": item["absorption"]})
        for row, captured in seen["fields"].items():
            if captured is None:
                continue
            decoded = page.get(row)
            # The book prints one row per effect; the reader kept the first,
            # because a continuation row carries no caption to key it by.
            if isinstance(decoded, list):
                decoded = decoded[0] if decoded else None
            assert decoded is not None, f"{name}: nothing decoded for {row}"
            want = captured.replace(" ", "")
            got = _as_read(decoded).replace(" ", "")
            assert got.startswith(want), f"{name} {row}: {captured!r} vs {decoded!r}"
            checked += 1
    assert checked == 650


def test_fits_in_is_the_containers_word(data):
    """Three bits of record word 14, and when none is set the item is either a
    container itself or something that can only be passed between characters."""
    by = {i["name"]: i for i in data["items"]}
    assert by["CLOTHES"]["fields"]["fits in"] == "BACKPACK BOX BAG"
    assert by["CHAIN MAIL ARMOR"]["fields"]["fits in"] == "BACKPACK"
    assert by["BACKPACK"]["fields"]["fits in"] == "CHARACTER PANEL"
    assert by["SWORD OF LIGHT"]["fields"]["fits in"] == "ANY PANEL"
    # Every item has one, including the 134 the book never indexes.
    assert all(i["fields"].get("fits in") for i in data["items"])


def test_adds_and_protections_come_from_the_effects_table(data):
    """Record word 2 points at a 16-byte entry: up to four (character-record
    offset, amount) pairs. The offset is what names the row (0x20 to 0x30 are
    the nine condition words, 0x3c up are the attributes and the skills), and
    the two renderers split the entry on exactly that boundary.

    The decode carries every row; the captures only ever showed the first.
    """
    by = {i["name"]: i for i in data["items"]}
    assert by["SWORD OF LIGHT"]["fields"]["adds"] == [
        "10 STRENGTH", "10 DEXTERITY", "30 SLASHING"]
    assert by["PARALYSIS PROTECTION RING"]["fields"]["protections"] == [
        "50 PARALYZE", "60 FROZEN", "40 STONING"]
    assert by["CROWN OF EURON"]["fields"]["adds"] == ["10 CASTING"]

    # An effect names a field of the character record, so every name it can
    # print is one the executable's own field tables hold.
    named = {row.split(maxsplit=1)[1]
             for i in data["items"]
             for key in ("adds", "protections")
             for row in i["fields"].get(key, [])}
    assert named <= {"STRENGTH", "DEXTERITY", "STAMINA", "INTELLIGENCE",
                     "WISDOM", "CHARISMA", "SLASHING", "BASHING", "POLEARM",
                     "CASTING", "DISEASE", "POISON", "SICKNESS", "STONING",
                     "FROZEN", "PARALYZE", "CURSING", "HEXING", "JINXING"}


def test_every_item_that_is_equipped_names_its_slot(data):
    """Record word 12 picks the slot the equip dispatch routes to, and for the
    worn category the armor entry's word at 2 picks one of four. The partition
    is clean: nothing carries the worn bit and no worn bit."""
    by = {i["name"]: i for i in data["items"]}
    for name, slot in [("ROYAL PLATE ARMOR", "BODY"),
                       ("ROYAL PLATE HELMET", "HEAD"),
                       ("ROYAL PLATE BOOTS", "FEET"),
                       ("ROYAL PLATE GLOVES", "HANDS"),
                       ("GOLD SHIELD", "SHIELD"),
                       ("RING OF INVISIBILITY", "RING"),
                       ("2-HANDED SWORD", "HAND WEAPON"),
                       ("SLING", "MISSILE WEAPON"),
                       ("TORCH", None)]:
        assert by[name]["slot"] == slot, name
    armor = [i for i in data["items"] if i["category"] == "ARMOR / RINGS"]
    assert all(i["slot"] for i in armor)


def test_a_magic_scroll_names_the_spell_it_teaches(data):
    """Its misc properties entry is `10 00 00 26 <spell id> 00 00 00`, the same
    shape for all 26, and the id is 1-based into the spell table. Every one of
    them lands on a spell whose name the scroll's own name contains."""
    spells = {s["name"] for s in data["spells"]}
    scrolls = [i for i in data["items"] if i["category"] == "MAGIC SCROLLS"]
    assert len(scrolls) == 26
    for scroll in scrolls:
        assert scroll["spell"] in spells, scroll["name"]
        # "SCROLL OF ACID RAIN" and "FIREBALL SCROLL" both name their spell.
        assert scroll["spell"] in scroll["name"], scroll["name"]
    assert all(i["spell"] is None for i in data["items"]
               if i["category"] != "MAGIC SCROLLS")


def test_the_decode_reaches_the_items_the_capture_never_did(data):
    """134 of the 304 items have no F5 page, and the capture left them with a
    name and nothing else. They have their rows now."""
    unlisted = [i for i in data["items"] if not i["listed"]]
    assert len(unlisted) == 134
    assert all(i["fields"] for i in unlisted)
    by = {i["name"]: i for i in data["items"]}
    assert by["GOLD CHEST KEY"]["fields"]["fits in"] == "BACKPACK BOX BAG"
    assert by["LIT TORCH"]["fields"]["duration"] == "0 MINUTES"


def test_attribute_enhancers_are_rules_not_items(data):
    """That category has no item list; the clue book gives it one rules page,
    and the page is six rows of constants in the code at image 0x06f2f."""
    rules = data["enhancers"]
    assert len(rules) == 6
    assert [r["kind"] for r in rules] == ["SCROLLS", "PARCHMENTS", "WANDS",
                                          "RODS", "GEMS", "STONES"]
    # Attribute and skill enhancers come in matched pairs, 3 / 5 / 7.
    assert [r["amount"] for r in rules] == [3, 3, 5, 5, 7, 7]
    assert [r["raises"] for r in rules] == ["ATTRIBUTE", "SKILL"] * 3
    assert not any(i["category"] == "ATTRIBUTE ENHANCERS" for i in data["items"])


def test_transportations_are_not_items(data):
    """The eighth category lists three things that appear nowhere in the 631
    item records. They are a four-entry table in the executable, of which the
    book prints three: the FLYING RUG is in the game but not in the book."""
    transports = data["transports"]
    assert [t["name"] for t in transports] == ["PEGASUS", "GIANT EAGLE",
                                               "MAGIC DRAGON"]
    names = {i["name"] for i in data["items"]}
    assert not names & {t["name"] for t in transports}
    assert [t["value"] for t in transports] == [10000, 30000, 70000]
    assert [t["uses"] for t in transports] == [1, 2, 4]
    # Only the dragon is nocturnal, which is what its TIME row says.
    assert [t["when"] for t in transports] == ["ANYTIME", "ANYTIME",
                                               "BETWEEN 7P.M. AND 7A.M."]


# --- walkthrough -----------------------------------------------------------

def test_walkthrough_shape(data):
    pages = data["walkthrough"]
    assert len(pages) == 33
    assert all(len(p["rows"]) == S.WALKTHROUGH_ROWS for p in pages)


def test_walkthrough_page_boundaries(data):
    pages = data["walkthrough"]
    assert pages[0]["rows"][0] == "1. ATHANEUM"
    # Every page ends with its own footer, which is what proves the 1275-byte
    # page stride and the 51-column row width are both right.
    for i, p in enumerate(pages, start=1):
        assert p["rows"][-1].strip() == f"{i} OF 33"


def test_walkthrough_is_printable_text(data):
    for p in data["walkthrough"]:
        for row in p["rows"]:
            assert all(0x20 <= ord(c) < 0x7F for c in row)


def test_walkthrough_section_index(data):
    idx = extract.walkthrough_sections(data["walkthrough"])
    assert len(idx) == 50
    assert idx[0] == {"n": 1, "title": "ATHANEUM", "page": 1}
    assert idx[-1]["title"] == "QUARTZ CHAMBER"
    assert [s["n"] for s in idx] == sorted(s["n"] for s in idx)


# --- name tables -----------------------------------------------------------

def test_map_names(data):
    maps = data["maps"]
    assert len(maps) == 37
    assert maps[0] == "DWARVEN HOMELAND"
    assert "QUARTZ CHAMBER" in maps
    assert "ACOKNIGHT'S CAVE" in maps  # '~' substitution applied here too


def test_legend_labels(data):
    legend = data["legend"]
    # 138 labels, not the 250 the directory entry's length would suggest: that
    # entry runs to the start of the next one, and the labels stop well short.
    assert len(legend) == 138
    assert legend[-1] == "THAINE MAP 5"
    # Slot 0 is a developer column ruler that shipped in the data; its length
    # is itself the proof that the record holds 25 visible characters.
    assert legend[0] == extract.LEGEND_RULER
    assert len(extract.LEGEND_RULER) == extract.LEGEND_RECORD - 1
    assert "FLAGELL" in legend
    assert "SAXON'S SHIP TO THAINE" in legend
    # Everything past the labels is the spell-text index and the descriptions.
    # Striding 26 bytes over those yields plausible-looking fragments, which is
    # exactly why the run has to be cut rather than trusted to the length.
    for label in legend:
        assert label == label.strip()
        assert "." not in label, label


def test_map_tile_grids_are_decoded(data):
    """A page's grid comes out of WORLD.DAT.

    A cell is a uint16 at base + band*3200 + level*160 + col*4, and the ids on
    a page are few: Acoknight's Cave Level 1 uses four (wall, two floor
    variants, one feature). That the grid is right is measured elsewhere, by
    drawing the page from the files and diffing it against the game's own
    (`fidelity` in `tools/pack_maps.py`).
    """
    import sys
    sys.path.insert(0, "tools")
    import registry
    import solve_maps as SM

    world = Path("game/WORLD.DAT").read_bytes()
    slots = registry.map_registry(world)
    assert len(slots) == 54
    for (area, level) in slots:
        assert 0 <= area < 7           # 0x83400 / 76800 = 7 area blocks
        assert 0 <= level < 20
        grid = SM.read_grid(world, area * SM.AREA_STRIDE, level)
        assert len(grid) == 24
        assert all(len(row) == 34 for row in grid)

    cave = next(s for s, t in slots.items() if t == "ACOKNIGHT'S CAVE LEVEL 1")
    assert cave == (2, 12)
    grid = SM.read_grid(world, cave[0] * SM.AREA_STRIDE, cave[1])
    assert len({v for row in grid for v in row}) == 4


def test_map_pages_carry_no_mouse_pointer(data):
    """The game draws its own pointer wherever the mouse sits.

    It landed in the middle of three pages before the capture learned to park
    it in the title strip that gets cropped away. These two skin tones are the
    pointer's own, taken from the pixels a re-capture removed; a page that
    picked it up would carry them in its palette.
    """
    pointer = {"#cb8669", "#ba7561"}
    for page in data["map_pages"]:
        assert not (pointer & set(page["palette"])), page["title"]


def test_map_pages_are_drawn_not_shipped(data):
    """A page ships as its tile grid plus the tiles it is drawn with.

    No bitmap: the grid comes out of WORLD.DAT and the panel draws it, which is
    what makes a page reproducible at any size rather than photographed. The
    markers the game paints over the tiles come as their own small layer.
    """
    pages = data["map_pages"]
    # Every slot the registry names is packed, and all of them the same way --
    # out of the game's files. 37 of the 54 also have a capture, which is used
    # to measure fidelity and for nothing else.
    # (was: 36 have a capture whose slot the registry agrees with; 16 more pack
    # artwork, and two are held back because the captures have never shown some
    # of their tiles.
    assert sum(1 for p in pages if p.get("in_book")) == 37
    assert len(pages) == 54
    titles = [p["title"] for p in pages]
    assert len(set(titles)) == len(titles), "a page was packed twice"
    assert "ACOKNIGHT'S CAVE LEVEL 1" in titles
    # The level numbers are learned glyphs, not counted positions: a page that
    # fails to open leaves a hole, and counting would renumber past it.
    assert "CASTLE OF BARIAG LEVEL 2" in titles
    booked = [p["title"] for p in pages if p.get("in_book")]
    areas = {t.split(" LEVEL ")[0].split(" MAP ")[0] for t in booked}
    known = {m.replace("~", "'") for m in data["maps"]}
    assert areas <= known, areas - known
    # The rest are titled by their storage slot, because nothing in the file
    # names them: neither map name table has an entry, so a real-looking title
    # here would be invented. The legend the page carries is what identifies it.
    # Every page is titled by the game's own registry, so no page carries an
    # invented name and none is titled by its storage slot.
    import sys
    sys.path.insert(0, "tools")
    import pack_maps as P
    registry = P.map_registry(Path("game/WORLD.DAT").read_bytes())
    for page in pages:
        assert registry[(page["area"], page["level"])] == page["title"], page["title"]


def test_the_registry_names_every_slot_the_book_prints():
    """The registry is checked against the book, and against a walk.

    36 of its 54 entries are pages the clue book prints, and the title it gives
    matches the one read off the game's own frame for every one of them, two
    independent routes to the same string. The 18 it names that the book does
    not print include area 2 level 1, which is where walking through Athaneum's
    Exit to Yendor door lands: the registry calls it YENDOR.
    """
    import json as _json
    import sys
    sys.path.insert(0, "tools")
    import pack_maps as P

    world = Path("game/WORLD.DAT").read_bytes()
    registry = P.map_registry(world)
    assert len(registry) == 54
    assert registry[(2, 1)] == "YENDOR"

    book = {(g["area"], g["level"]): g["title"]
            for g in []}
    agree = [k for k, v in book.items() if registry.get(k) == v]
    assert len(agree) == len(book), \
        [(k, book[k], registry.get(k)) for k in book if registry.get(k) != book[k]]
    # Areas 0 and 6 hold no maps at all, which the variety heuristic that
    # preceded the registry got wrong for four slots.
    assert not [k for k in registry if k[0] in (0, 6)]


def test_every_page_has_the_same_shape(data):
    for page in data["map_pages"]:
        # 40, not the book's 34: a stored row is 40 cells and the three at
        # each end are real squares the clue book crops. Markers stand on them.
        assert (page["cols"], page["rows"], page["tile"]) == (40, 24, 8)
        assert page["palette"] and all(c.startswith("#") for c in page["palette"])
        assert len(base64.b64decode(page["grid"])) == 40 * 24
        assert len(base64.b64decode(page["tiles"])) % (8 * 8) == 0
        for r, c, _ in page["overlay"]:
            assert 0 <= r < 24 and 0 <= c < 40, page["title"]



def test_the_panel_ships_no_map_bitmaps():
    """The images it used to carry are gone; it draws the pages instead."""
    assert not Path("web/maps").exists()



# --- end-to-end ------------------------------------------------------------

def test_build_writes_all_json(tmp_path):
    payload = extract.build("game", tmp_path)
    for key in ("enemies", "spells", "walkthrough", "maps", "legend",
                "labels", "restoration"):
        assert (tmp_path / f"{key}.json").is_file(), key
    assert payload["labels"]["effects"][0] == "POISON"


# --- monster level and special attacks -------------------------------------


def test_monster_level_runs_one_to_forty_five(data):
    levels = {c["name"]: c["level"] for c in data["enemies"]}
    assert levels["WASP"] == 1
    assert levels["CENTIPEDE"] == 1
    assert levels["PALTIVAR"] == 45
    assert levels["NOT USED"] == 0


def test_level_orders_the_monsters_the_way_their_stats_do(data):
    """Every other stat is grown from the level, so they move together."""
    live = [c for c in data["enemies"] if c["listed"]]
    # Rank correlation rather than monotonicity: monsters at the same level
    # are tuned against each other, so neighbors swap. What must hold is that
    # the field tracks the stats across the whole table, and a wrong offset does
    # not score 0.95 by accident.
    def rank(vals):
        order = sorted(range(len(vals)), key=lambda i: vals[i])
        out = [0] * len(vals)
        for r, i in enumerate(order):
            out[i] = r
        return out

    a = rank([c["level"] for c in live])
    b = rank([c["absorption"] for c in live])
    n = len(a)
    rho = 1 - 6 * sum((x - y) ** 2 for x, y in zip(a, b)) / (n * (n * n - 1))
    assert rho > 0.95, f"level vs absorption rho = {rho:.3f}"


def test_special_attacks_decode_exactly_as_the_game_prints_them(data):
    """The whole point: read from the table, not from the screens.

    `attacks` comes from the monster's attack id and the table the printer
    indexes with it. `observed_attacks.json` is what
    `tools/capture_monsters.js` read off the game's own F2 pages. They have to
    agree for every monster the book lists, which is what makes the id a
    decode rather than a guess, and it is the only thing that file is for.
    """
    seen = observed("observed_attacks.json")
    mismatched = [c["name"] for c in data["enemies"]
                  if c["listed"]
                  and sorted(c["attacks"]) != sorted(seen.get(c["name"], []))]
    assert mismatched == []
    # ...and it is not vacuous: 30 of the 71 monsters carry one.
    assert sum(1 for c in data["enemies"] if c["attacks"]) == 30


def test_monsters_sharing_an_attack_id_share_their_attacks(data):
    import collections

    # PARTY ATTACK and BREAK SHIELD come from other bits, so ignore those.
    conditions = collections.defaultdict(set)
    for c in data["enemies"]:
        rest = tuple(sorted(a for a in c["attacks"]
                            if a not in ("PARTY ATTACK", "BREAK SHIELD")))
        conditions[c["attack_id"]].add(rest)
    assert all(len(v) == 1 for v in conditions.values()), conditions
    # ...and it is not vacuous: several ids are shared.
    shared = sum(1 for v in collections.Counter(
        c["attack_id"] for c in data["enemies"]).values() if v > 1)
    assert shared >= 3


def test_the_ranged_fields_are_set_for_exactly_the_ranged_monsters(data):
    """Five fields describe the shot and all five agree on who has one: the
    picture, the sound, the attack id, and the accuracy and damage the clue
    book prints. A monster with any of them has all of them."""
    ranged = {c["name"] for c in data["enemies"] if c["ranged"]}
    assert len(ranged) == 13
    for c in data["enemies"]:
        shooting = c["name"] in ranged
        assert bool(c["ranged_accuracy"]) == shooting, c["name"]
        assert bool(c["ranged_damage"]) == shooting, c["name"]
        if shooting:
            assert c["ranged"]["picture"] and c["ranged"]["sound"], c["name"]
            assert c["ranged"]["attack_id"], c["name"]


def test_a_shot_names_a_picture_the_projectile_run_holds(data, directory):
    """The picture is an index into PICTURES.VGA run 1, and seven values serve
    all thirteen shooters, three of which fire the same arrows."""
    import pictures as P

    pics = ROOT_TOOLS.parent / "game" / "PICTURES.VGA"
    run = P.read_runs(directory.exe, pics.stat().st_size)[extract.PROJECTILE_RUN]
    pictures = {c["ranged"]["picture"] for c in data["enemies"] if c["ranged"]}
    assert len(pictures) == 7
    assert all(0 < n < run.count for n in pictures), pictures


def test_how_often_a_monster_shoots_is_one_of_five_figures(data):
    """The AI rolls against a threshold picked by the highest of four bits of
    word 98. Only shooters carry one, and the three that cannot move carry the
    highest."""
    chances = {c["name"]: c["ranged"]["chance"]
               for c in data["enemies"] if c["ranged"]}
    assert set(chances.values()) <= set(extract.RANGED_CHANCE_BITS.values()) | {
        extract.RANGED_CHANCE_DEFAULT}
    assert {n for n, p in chances.items() if p == 90} == {
        "FUNGUS", "FROST DWARF TOWER", "FIRE DWARF TOWER"}


def test_only_the_creeping_fungus_recolours_its_shot(data):
    """Twelve monsters carry the bit that turns the shot's recolour list on;
    one of them has a list to apply, and it is the recoloured fungus."""
    lists = {c["name"]: c["ranged"]["recolour"]
             for c in data["enemies"] if c["ranged"] and c["ranged"]["recolour"]}
    assert lists == {"CREEPING FUNGUS": [{"from": 4, "to": 3}]}


def test_every_monster_animates_one_way_or_the_other(data):
    """Two bits of word 96 choose between running the walk cycle in a loop and
    running it back and forth. Every monster the game lists carries exactly
    one; the third bit, which stops the animation, is carried by none."""
    walks = collections.Counter(c["walk"] for c in data["enemies"] if c["listed"])
    assert walks == collections.Counter({"loop": 48, "bounce": 23})


def test_xref_finds_the_instruction_that_reads_a_known_field():
    """The technique the record was decoded with, held to a case whose answer
    is already known: the monster's sprite is record 26, so the draw loop's
    read of it is a reference to `[si+0x4c]`. A superset disassembly of a
    real-mode image is mostly noise, and this is what says the filter still
    keeps the signal."""
    import xref

    hits = {addr for addr, _, _ in xref.find(_exe(), 0x4C, ("si",))}
    # image 0x80b0 sets the attack frame from it, 0x153c4 walks the cycle.
    assert {0x080B0, 0x153C4} <= hits
    assert len(hits) < 40, "the filter is letting noise through"


def test_a_decode_is_read_through_its_anchor_not_from_near_it():
    """Reading a 16-bit image from a guessed address is how a decode goes
    wrong. `test word ptr [0x5df2], 0x8000` at image 0x1d72f, read from one
    byte in, becomes `push es / pop bp / add byte ptr [bx+si+0x874], al` --
    and the guard it applies on the instruction after it disappears without
    leaving a hole. That is a resistance bit looking unconditional when it is
    not."""
    exe = _exe()
    # The instruction after the guard is a real boundary, and backing up from
    # it lands on the guard rather than inside it.
    start = exe.aligned_start(0x1D737)
    assert start is not None
    stream = {i.address for i in exe.disasm(start, 40)}
    assert {0x1D72F, 0x1D737} <= stream
    # A byte inside an instruction is not, and says so rather than decoding.
    assert exe.aligned_start(0x1D730) is None


def _exe():
    import disasm

    return disasm.Exe(ROOT_TOOLS.parent / "game" / "REGISTER.EXE")


def test_every_map_has_a_cell_the_party_could_stand_on(directory, data):
    """A map dropped onto is a map with an arrival cell, and that cell has to
    pass what the step itself passes: image 0x02EEA on the terrain word and
    0x02F13 on the object word. On a map that is mostly water, mostly-anything
    is water, so the rule has to be the game's rather than a guess about which
    id is the ground.
    """
    import pack_maps

    for page in data["map_pages"]:
        band, cell = page["arrive"]
        assert pack_maps.walkable(directory.world, page["area"], page["level"],
                                  band, cell), page["title"]
    assert len(data["map_pages"]) == 54


def test_the_walkable_rule_leaves_the_water_out(directory):
    """The check that would have caught the guess this replaced: the sea around
    DELIA'S ISLAND is drawn, and most of that map is sea."""
    import pack_maps
    import solve_maps as SM
    import struct

    area, level = 4, 6
    world = directory.world
    walk = [(b, c) for b in range(SM.ROWS) for c in range(40)
            if pack_maps.walkable(world, area, level, b, c)]
    drawn = [(b, c) for b in range(SM.ROWS) for c in range(40)
             if tiles.drawn(world, area, level, b, c)]
    assert len(drawn) > 2 * len(walk), "the island should be the smaller part"
    sea = struct.unpack_from("<H", world, area * SM.AREA_STRIDE
                             + level * SM.LEVEL_STRIDE)[0]
    assert not pack_maps.walkable(world, area, level, 0, 0), f"sea id {sea} walkable"


def test_only_the_torch_pair_carries_a_duration(directory, data):
    """What a carried slot's second word is for depends on the item, and two
    kinds of item need it set: a light source, where it is how much is left to
    burn, and a container, where it points at the contents. Everything else
    sits in a slot as an id beside a zero. This pins both sets, because a third
    kind appearing is what would make handing an item over wrong again."""
    import items as I

    items = I.Items(directory)
    duration, container = [], []
    for i, name in enumerate(items.names, 1):
        if not name:
            continue
        category = I._u16(items.records[i - 1], I.CATEGORY)
        if category & 0x1000:
            duration.append(name)
        if category & I.IS_CONTAINER:
            container.append(name)
    assert duration == ["TORCH", "LIT TORCH"]
    assert container == ["BAG", "BOX", "BACKPACK"]
    # And the panel agrees: those are the only items whose page prints one.
    assert {i["name"] for i in data["items"] if "duration" in (i["fields"] or {})} \
        == {"TORCH", "LIT TORCH"}


def test_an_enchanted_item_carries_its_own_id(data):
    """A base item folds its +1..+10 forms in as variants, and each keeps the
    id the game knows it by, which is the base's plus the enchantment, on all
    327 of them, though the id is read rather than computed."""
    by_id = {i["id"]: i for i in data["items"]}
    seen = 0
    for item in data["items"]:
        for v in item["variants"]:
            assert v["id"] == item["id"] + v["plus"], item["name"]
            assert v["id"] not in by_id, "a variant is also listed on its own"
            seen += 1
    assert seen == 327


def test_a_steal_takes_a_fixed_sum(data):
    """Offsets 92-95 are a packed-BCD amount in the same form as the four
    rewards, and only the three monsters whose special attack is STEAL GOLD
    carry one."""
    stolen = {c["name"]: c["steal"] for c in data["enemies"] if c["steal"]}
    stealers = {c["name"] for c in data["enemies"]
                if "STEAL GOLD" in c["attacks"]}
    assert set(stolen) == stealers
    assert stolen == {"THIEF": 100, "ELF ASSASSIN": 1000,
                      "FROST DWARF TOWER": 1000}


def test_sprite_groups_monsters_that_share_artwork(data):
    """The draw loop sets the current frame from this field, so monsters with
    the same value are drawn the same, which is what the groups look like."""
    import collections

    by = collections.defaultdict(set)
    for c in data["enemies"]:
        by[c["sprite"]].add(c["name"])
    assert by[0] >= {"WASP", "WASP QUEEN"}
    assert by[70] == {"FROST GIANT", "SNOW GIANT", "FIRE GIANT"}
    assert {"EMERALD DRAGON", "BLACK DRAGON", "PURPLE DRAGON"} <= by[140]
    # Far fewer sprites than monsters: the apparent purpose of the field.
    assert len(by) < len(data["enemies"]) / 2


def test_sound_is_an_index_into_the_executables_voc_table(data):
    import struct

    exe = Path("game/REGISTER.EXE").read_bytes()
    entries = 0
    while True:
        a = struct.unpack_from("<I", exe, 0x2D057 + entries * 4)[0]
        b = struct.unpack_from("<I", exe, 0x2D057 + (entries + 1) * 4)[0]
        if not a < b < 30_000_000:
            break
        entries += 1
    assert entries >= 140

    sounds = [c[k] for c in data["enemies"] for k in ("sound_hit", "sound_miss")]
    sounds += [c["ranged"]["sound"] for c in data["enemies"] if c["ranged"]]
    assert max(sounds) <= entries
    # The two towers are the only monsters with nothing to say in melee, and
    # they are the two that never enter it.
    silent = {c["name"] for c in data["enemies"]
              if c["listed"] and not c["sound_hit"] and not c["sound_miss"]}
    assert silent == {"FROST DWARF TOWER", "FIRE DWARF TOWER"}
    # A monster with a weapon swishes when it misses, whatever it sounds like
    # when it connects: fifteen of them share one miss sound.
    misses = collections.Counter(c["sound_miss"] for c in data["enemies"]
                                 if c["listed"] and c["sound_miss"])
    assert misses.most_common(1) == [(35, 15)]


def test_the_decoded_fields_are_no_longer_offered_as_unknown(data):
    gone = {"u26", "u32", "u42", "u44", "u46", "u48", "u54", "u56", "u58",
            "u60", "u62", "u70", "u72", "u74", "u80", "u84", "u92", "u94"}
    for c in data["enemies"]:
        assert not (gone & set(c["unknown"])), sorted(gone & set(c["unknown"]))


def test_recolour_is_a_terminated_list_of_distinct_substitutions(data):
    """Six bytes, each a (color, replacement) pair, stopping at a zero byte.

    Neither property is guaranteed by the bytes being *something*: if these
    were counts or coordinates, some list would run past a zero and some would
    replace the same color twice. Across every monster that carries one,
    neither happens, which is the evidence that they are substitutions.
    """
    carrying = [c for c in data["enemies"] if c["recolour"]]
    assert len(carrying) == 32
    for c in carrying:
        froms = [p["from"] for p in c["recolour"]]
        assert len(set(froms)) == len(froms), c["name"]
        assert all(0 <= p["to"] <= 15 for p in c["recolour"]), c["name"]
        assert 1 <= len(c["recolour"]) <= 6


def test_recolour_needs_its_flag(data):
    """Bit 2 of word 96 is what turns the substitution on."""
    for c in data["enemies"]:
        if c["recolour"]:
            assert c["masks"]["w96"] & 4, c["name"]


def test_a_shared_sprite_is_told_apart_by_its_recolouring(data):
    """Which is what the pair of fields is for: one drawing, several monsters."""
    by = {c["name"]: c for c in data["enemies"]}
    giants = ["FROST GIANT", "SNOW GIANT", "FIRE GIANT"]
    assert len({by[n]["sprite"] for n in giants}) == 1
    assert by["FROST GIANT"]["recolour"] == []
    assert by["SNOW GIANT"]["recolour"] != by["FIRE GIANT"]["recolour"]

    assert by["SLIME"]["sprite"] == by["PURPLE SLIME"]["sprite"]
    assert by["SLIME"]["recolour"] == []
    assert by["PURPLE SLIME"]["recolour"] == [{"from": 9, "to": 1}]


# --- when each class learns a spell -----------------------------------------


def test_the_class_rows_reproduce_every_screen(data):
    """The decode is checked against all 98 pages the clue book prints.

    Three tables settle it, in the order the printer asks them: the two spells
    a class starts with, the class's training row, and the spell's scroll mask.
    The book has room for three class rows and prints the first three, so the
    comparison is against that prefix, and it is exact for every spell.
    """
    import json as _json

    printed = observed("observed_spells.json")
    checked = 0
    for s in data["spells"]:
        seen = printed.get(s["name"])
        if not seen:
            continue
        want = [{"class": c["class"], "level": c["level"], "source": c["source"]}
                for c in seen["classes"]]
        got = [{"class": c["class"], "level": c["level"], "source": c["source"]}
               for c in s["classes"]][:3]
        assert got == want, s["name"]
        checked += 1
    assert checked == 98


def test_the_decode_finds_rows_the_f3_page_cannot_print(data):
    """F3 holds three class rows; the tables hold 22 more."""
    import json as _json

    printed = observed("observed_spells.json")
    extra = sum(len(s["classes"]) - len(printed[s["name"]]["classes"])
                for s in data["spells"] if s["name"] in printed)
    assert extra == 22


def test_the_class_lists_confirm_the_rows_f3_could_not_show(data):
    """And the book does print them, on F4, the other way round.

    F3 lists a spell's classes and has room for three; F4 lists a class's
    spells and has no such limit, so it is the check on the 22 rows F3 hides.
    Read back by `tools/read_class_spells.py` from its own capture.

    Five of the six agree exactly. The sixth is one spell: the Druid page
    includes FIERY SPEAR, which no table grants, not the class's level-1
    pair, not its training row, and the spell's scroll mask is zero. F3's own
    page for that spell lists only the Marksman. The disagreement is the
    game's, so it is pinned here rather than smoothed over.
    """
    import collections
    import json as _json

    book = observed("observed_class_spells.json")
    decoded = collections.defaultdict(set)
    for spell in data["spells"]:
        for row in spell["classes"]:
            decoded[row["class"]].add(spell["name"])

    for klass, listed in book.items():
        if klass == "DRUID":
            assert set(listed) - decoded[klass] == {"FIERY SPEAR"}
            assert decoded[klass] - set(listed) == set()
        else:
            assert set(listed) == decoded[klass], klass


def test_the_spell_level_is_what_a_scroll_asks_for(data):
    """Offset 22 is the spell's own level, exact on every scroll row."""
    checked = 0
    for s in data["spells"]:
        scroll = [r for r in s["classes"] if r["source"] == "SCROLL"]
        if not scroll:
            continue
        # One level per spell, shared by every class that learns it that way.
        assert len({r["level"] for r in scroll}) == 1, s["name"]
        assert s["level"] == scroll[0]["level"], s["name"]
        checked += 1
    assert checked >= 23


def test_level_one_spells_are_free_and_need_no_route(data):
    for s in data["spells"]:
        for r in s["classes"]:
            if r["source"] is None:
                assert r["level"] == 1, (s["name"], r)


def test_every_scroll_spell_has_a_scroll_to_learn_it_from(data):
    """The item table corroborates the SCROLL route, spell for spell.

    The clue book marks some (class, spell) rows SCROLL rather than TRAINING,
    and the argument that this means "learn it from a magic scroll item" came
    from the game's own wording. A scroll's misc properties entry carries the
    spell's id, so the check is a field rather than a naming convention --
    which matters, because SCROLL OF BLINDING is named for its effect and
    would not match on name.

    Three spells have a scroll item and no SCROLL row, which fits: every class
    that can cast them also trains them, so the book shows the training route.
    """
    scrolls = [i for i in data["items"] if i["category"] == "MAGIC SCROLLS"]
    teaches = {i["spell"] for i in scrolls}
    assert len(scrolls) == 26 and len(teaches) == 26
    assert "BLIND" in teaches                       # SCROLL OF BLINDING

    need = {s["name"] for s in data["spells"]
            if any(c["source"] == "SCROLL" for c in s["classes"])}
    assert len(need) == 23
    assert need <= teaches, sorted(need - teaches)
    assert teaches - need == {"ARMS OF GIANTS", "FIREBALL", "JUMP OVER"}




def test_the_book_pages_still_reproduce_exactly(data):
    """Widening the page and adding the object layer must not disturb the 37.

    Inside the window the clue book actually prints, a packed page is the
    game's own pixels, which is the check that the decode is right rather than
    merely plausible, and it has to keep holding as the margins are filled in.
    """
    for page in data["map_pages"]:
        if not page.get("in_book"):
            continue
        assert page["cols"] == 40
        # The overlay never lands outside the page it belongs to.
        for r, c, _ in page["overlay"]:
            assert 0 <= r < page["rows"] and 0 <= c < page["cols"], page["title"]


def test_every_clue_book_page_reproduces_the_game_exactly(data):
    """Pages drawn from the files are measured against the game's own frames.

    Fidelity skips the cells the game paints a legend marker over, and counts a
    cell as matching under any phase of the fire ramp, because a still catches
    one. What is left is a real difference: eight cells over three pages, none
    of them looked into.
    """
    booked = [p for p in data["map_pages"] if p.get("in_book")]
    assert len(booked) == 37
    if all(p["fidelity"] is None for p in booked):
        pytest.skip("no map captures in tmp/maps4; run tools/capture_maps.js")
    exact = [p for p in booked if p["fidelity"] == 1]
    assert len(exact) >= 34, sorted(
        (p["fidelity"], p["title"]) for p in booked if p["fidelity"] != 1)
    assert all(p["fidelity"] > 0.99 for p in booked)
    # A page with no capture makes no claim rather than claiming zero.
    assert all(p.get("fidelity") is None for p in data["map_pages"]
               if not p.get("in_book"))


def test_every_capture_sits_on_the_slot_the_registry_names():
    """`map_locations.json` is fitted by search; the registry is read.

    The search once put two captures on one slot, and the registry says which
    is right. Only pack_maps guarded against that, so every other reader of the
    file inherited the error, so this holds the file itself to the registry.
    """
    import json as _json
    import sys
    sys.path.insert(0, "tools")
    import registry
    import solve_maps as SM

    ROOT = Path(__file__).resolve().parent.parent
    world = (ROOT / "game" / "WORLD.DAT").read_bytes()
    names = registry.map_registry(world)
    locs = _json.loads(registry.INDEX.read_text())

    # The file records only which capture shows which map; the slot is read
    # from the registry, so a capture cannot sit on the wrong one. What can
    # still go wrong is a title the registry does not name, or two captures of
    # the same map, both of which would land two pages on one slot.
    assert all(set(l) == {"title", "shot", "score"} for l in locs), \
        "map_locations.json should carry no slot of its own"
    titles = [l["title"] for l in locs]
    assert len(set(titles)) == len(titles), "two captures name the same map"
    for title in titles:
        assert title in set(names.values()), title
    slots = [(c["area"], c["level"]) for c in registry.captures(world)]
    assert len(set(slots)) == len(slots)
