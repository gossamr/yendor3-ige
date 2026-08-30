"""The British-spelling check, and the tree it guards.

Unlike the rest of the suite this reads no game file: the checker reads
committed text, and the tree is the fixture. Two things are asserted. That the
tree is clean, which is the point of the check. And that the stem list does
not fire on American words that begin the same way, which is the point of this
file: a check with false positives is a check somebody switches off, and the
lookaheads that prevent them are easy to lose when a stem is added.
"""
import spelling_check as SC

# American words that begin with a British stem on the list. Each one is a
# false positive the lookaheads exist to prevent.
INNOCENT = [
    "analysis", "analyst", "catalyst", "paralysis", "emphasis",
    "optimism", "optimistic", "specialist", "realistic", "realism",
    "organism", "organist", "modernism", "finalist", "generalist",
    "characteristic", "rationalist", "centralist",
    "totally", "cancellation", "greyhound",
    "four", "noise", "premise", "feature", "our", "hour", "practice",
]

# The forms the list is there to catch, with what each should become.
GUILTY = {
    "armour": "armor",
    "armourShare": "armorShare",
    "share_to_armour": "share_to_armor",
    "RANGED_RECOLOUR_BYTES": "RANGED_RECOLOR_BYTES",
    "recoloured": "recolored",
    "Behaviour": "Behavior",
    "neighbour": "neighbor",
    "greyed": "grayed",
    "GREY_BIT": "GRAY_BIT",
    "paralyse": "paralyze",
    "analysed": "analyzed",
    "serialisable": "serializable",
    "recognises": "recognizes",
    "optimise": "optimize",
    "penalised": "penalized",
    "modelling": "modeling",
    "totalled": "totaled",
    "labelled": "labeled",
    "towards": "toward",
    "offence": "offense",
    "whilst": "while",
    "analogue": "analog",
}


def found(text):
    """(word, replacement) for every hit in a one-line string."""
    return [(w, fix) for _, w, fix, _ in SC.hits_in_text(text)]


def test_the_tree_holds_no_british_spellings():
    bad = [f"{p.relative_to(SC.ROOT)}:{n}: {w} -> {fix}"
           for p in SC.tracked([]) for n, w, fix, _ in SC.hits(p)]
    assert bad == []


def test_american_words_that_start_like_a_british_stem_are_left_alone():
    for word in INNOCENT:
        assert found(word) == [], word


def test_every_stem_on_the_list_is_caught_and_corrected():
    for word, fix in GUILTY.items():
        hit = found(word)
        assert len(hit) == 1, f"{word} matched {hit}"
        assert word.replace(hit[0][0], hit[0][1]) == fix


def test_the_replacement_keeps_the_case_it_found():
    assert found("armour")[0][1] == "armor"
    assert found("Armour")[0][1] == "Armor"
    assert found("ARMOUR")[0][1] == "ARMOR"


def test_the_game_keeps_its_own_spelling():
    """Text quoted out of the game keeps the game's own spelling. SPECTRE is a
    monster and SABRE an item, both used as keys into the game's own data."""
    assert found('"SPECTRE": [') == []
    assert found('assert item == "SABRE"') == []
    # Only in the caps the game writes them in. The English word is still a hit.
    assert found("the spectre of a regression") == [("spectre", "specter")]


def test_the_checker_exempts_itself_and_this_file():
    """Both name the words they are about, so both always match themselves."""
    for name in ("tools/spelling_check.py", "tests/test_spelling_check.py"):
        assert name in SC.SKIP
        assert SC.ROOT / name not in SC.tracked([])
    assert len(SC.SKIP) == 2, "an exemption stops the check covering the tree"
