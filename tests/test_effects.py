"""Every animation the game draws over a target, against the bytes."""
from __future__ import annotations

import collections
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import effects as EF  # noqa: E402
import items as I  # noqa: E402
import pictures as P  # noqa: E402
import sections as S  # noqa: E402
from disasm import Exe  # noqa: E402

GAME = ROOT / "game"
pytestmark = pytest.mark.skipif(not (GAME / "WORLD.DAT").exists(),
                                reason="needs a copy of the game in game/")


@pytest.fixture(scope="module")
def directory():
    return S.load(GAME)


@pytest.fixture(scope="module")
def image():
    return Exe(GAME / "REGISTER.EXE")


@pytest.fixture(scope="module")
def runs(directory):
    return P.read_runs(directory.exe, (GAME / "PICTURES.VGA").stat().st_size)


def test_every_frame_exists_in_its_own_run(directory, image, runs):
    """A picture number is worth nothing unless the run it names holds it."""
    rows = (EF.spell_effects(directory, image) + EF.attack_effects(directory)
            + EF.struck_effects())
    for row in rows:
        for n in row["frames"]:
            assert 0 <= n < runs[row["run"]].count, row


def test_thirty_five_spells_draw_something(directory, image):
    rows = EF.spell_effects(directory, image)
    assert len(rows) == 35
    kinds = {r["kind"] for r in rows}
    assert kinds == {"bolt", "area", "burst", "rain"}


def test_a_burst_is_two_groups_of_three(directory, image):
    for row in EF.spell_effects(directory, image):
        if row["kind"] == "burst":
            assert len(row["frames"]) == 2 * EF.BURST_FRAMES


def test_the_rain_cycles_five_frames_over_a_ground(directory, image):
    rain = [r for r in EF.spell_effects(directory, image) if r["kind"] == "rain"]
    assert rain, "four rain spells and one unused row carry one"
    for row in rain:
        # the ground, then the cycle
        assert row["frames"][0] == 47 or row["frames"][0] == 48
        assert len(row["frames"]) == 6


def test_a_recolor_pair_names_two_ramps(directory, image):
    """Each byte is a source group in the high nibble and a target in the low,
    so both have to be one of the sixteen ramps."""
    for row in EF.spell_effects(directory, image):
        for source, target in row["recolor"].items():
            assert 0 <= source < 16 and 0 <= target < 16, row


def test_poison_recolors_three_ramps_to_green(directory, image):
    poison = next(r for r in EF.spell_effects(directory, image)
                  if r["name"] == "POISON ARROW")
    assert poison["recolor"] == {1: 9, 5: 9, 12: 9}


def test_the_tint_table_reads_to_43(image):
    """The 82 pixel routines are four shapes, and every tint a spell names is
    one that reads."""
    import tints as TI
    rows = TI.tints(image)
    read = {n: r for n, r in rows.items() if "unread" not in r}
    assert max(read) == 43
    assert {r["kind"] for r in read.values()} == {
        "flicker", "shade", "group", "group and shade"}
    # 2 to 5 are the four shades and 6 to 19 the fourteen groups.
    assert [read[n]["delta"] for n in (2, 3, 4, 5)] == [-8, -4, 4, 8]
    assert [read[n]["group"] for n in range(6, 20)] == list(range(14))


def test_a_tint_shades_inside_its_own_group(image):
    import tints as TI
    rows = TI.tints(image)
    assert TI.paint(rows[4], 0x30) == 0x34
    assert TI.paint(rows[4], 0x3E) == 0x3F          # clamped at the top
    assert TI.paint(rows[2], 0x31) == 0x30          # and at the foot
    assert TI.paint(rows[4], 0xD3) == 0xD3          # the twinkling ramp is left
    assert TI.paint(rows[7], 0x35) == 0x15          # a group keeps the shade
    assert TI.paint(rows[1], 0x35, roll=2) == 0xFF  # the flicker drops it


def test_a_rain_steps_thirty_five_times(directory, image):
    """Offset 40 is the loop count on this branch, not a sound and not the
    cycle's own length."""
    for row in EF.spell_effects(directory, image):
        if row["kind"] == "rain":
            assert row["steps"] == 35


def test_a_splat_has_a_corner_for_each_of_the_six_drawing_modes(directory):
    places = EF.struck_places()
    assert sorted(places) == [9, 10, 11, 12, 13, 14]
    # The three wide places share a row and the three tall ones share another.
    assert {y for mode, (_, y) in places.items() if mode < 12} == {34}
    assert {y for mode, (_, y) in places.items() if mode >= 12} == {8}


def test_the_struck_ladder_is_three_rungs(directory):
    assert [r["frames"][0] for r in EF.struck_effects()] == list(EF.STRUCK)
    assert EF.STRUCK_BANDS == (10, 30)


def _plates(pics, runs, at, w, h, sex):
    """Every body of that sex under a piece's own corner (tools/pictures.py)."""
    body_run = runs[6]
    x, y = at
    return [bytes(P.picture(pics, body_run, n)[(y + row) * body_run.width + x + col]
                  for row in range(h) for col in range(w))
            for n in range(sex, 18, 2)]


def _kept(cut):
    return sum(1 for v in cut if v != P.TRANSPARENT)


def test_a_head_piece_is_drawn_onto_the_plate(directory, runs):
    """A helmet covers the hair, so it was drawn straight onto the body, and
    what is not helmet is the plate showing through."""
    pics = (GAME / "PICTURES.VGA").read_bytes()
    it = I.Items(directory)
    body_run, head_run = runs[6], runs[7]
    head = next(p for p in it.doll() if p["name"] == "LEATHER HELMET")
    ramp = [P.ground_ramp(P.picture(pics, body_run, sex), body_run.width)
            for sex in (0, 1)]

    for picture, sex in ((head["male"], 0), (head["female"], 1)):
        raw = P.picture(pics, head_run, picture)
        plates = _plates(pics, runs, head["at"], head_run.width, head_run.height, sex)
        cut = P.without_plate(raw, head_run.width, plates, ramp[sex])
        assert _kept(cut) < _kept(raw) / 4, "most of a head piece is the plate"
        # Nothing of the stone survives either sex's subtraction.
        assert not any(v != P.TRANSPARENT and v >> 4 in (ramp[0], ramp[1])
                       for v in cut)
        # Which of the nine the piece was drawn over is not recorded, so the
        # answer most of them give is it. A body whose hair shares a color
        # with the helmet eats pixels the rest keep, and stands alone.
        one = [_kept(P.without_plate(raw, head_run.width, [plate], ramp[sex]))
               for plate in plates]
        assert min(one) < _kept(cut)


def test_a_helmet_drawn_on_no_plate_keeps_every_pixel(directory, runs):
    """The four winged helms were drawn on nothing, so the plate takes none of
    them: a rule reading the ground off the sprite ate their visors."""
    pics = (GAME / "PICTURES.VGA").read_bytes()
    body_run, head_run = runs[6], runs[7]
    ramp = P.ground_ramp(P.picture(pics, body_run, 0), body_run.width)
    helm = P.picture(pics, head_run, 145)
    cut = P.without_plate(helm, head_run.width,
                          _plates(pics, runs, (12, 49), head_run.width,
                                  head_run.height, 0), ramp)
    assert _kept(cut) > _kept(helm) * 0.9


def test_a_helmet_drawn_in_the_stones_own_ramp_keeps_it(directory, runs):
    """The dragon skin helm's horns are filled with the stone's own ramp, and
    a flood from outside leaves them: the helmet's outline walls them in."""
    pics = (GAME / "PICTURES.VGA").read_bytes()
    body_run, head_run = runs[6], runs[7]
    it = I.Items(directory)
    piece = next(p for p in it.doll() if p["name"] == "DRAGON SKIN HELMET")
    for picture, sex in ((piece["male"], 0), (piece["female"], 1)):
        ramp = P.ground_ramp(P.picture(pics, body_run, sex), body_run.width)
        cut = P.without_plate(
            P.picture(pics, head_run, picture), head_run.width,
            _plates(pics, runs, piece["at"], head_run.width, head_run.height, sex),
            ramp)
        assert sum(1 for v in cut if v != P.TRANSPARENT and v >> 4 == 3), \
            "the horns keep their fill"


def test_a_body_piece_is_drawn_onto_the_plate(directory, runs):
    """A hood is cut out of the plate the same way a helmet is, and the block
    of stone over the shoulders comes off with the subtraction."""
    pics = (GAME / "PICTURES.VGA").read_bytes()
    it = I.Items(directory)
    body_run = runs[6]
    piece = next(p for p in it.doll() if p["name"] == "ROBES")
    ramp = P.ground_ramp(P.picture(pics, body_run, 1), body_run.width)
    raw = P.picture(pics, body_run, piece["female"])
    plates = _plates(pics, runs, piece["at"], body_run.width, body_run.height, 1)
    cut = P.without_plate(raw, body_run.width, plates)
    # The block sits over the head, where the robe itself draws nothing, and
    # the subtraction takes all 176 pixels of it.
    over_head = lambda d: sum(1 for at, v in enumerate(d)
                              if v != P.TRANSPARENT and at // body_run.width < 60)
    assert over_head(raw) == 176
    assert over_head(cut) == 0
    # Everything it takes anywhere is stone or outline: 299 of the alcove's
    # own ramp and 68 of the black the figure is drawn around.
    assert sorted(collections.Counter(a >> 4 for a, b in zip(raw, cut)
                                      if a != b).items()) == [(0, 68), (ramp, 299)]


def test_a_body_piece_takes_no_flood(directory, runs):
    """CLOTHES' male tunic is drawn in the stone's own ramp and stands against
    the outside, so a flood from the transparent pixels empties it."""
    pics = (GAME / "PICTURES.VGA").read_bytes()
    it = I.Items(directory)
    body_run = runs[6]
    piece = next(p for p in it.doll() if p["name"] == "CLOTHES")
    ramp = P.ground_ramp(P.picture(pics, body_run, 0), body_run.width)
    raw = P.picture(pics, body_run, piece["male"])
    plates = _plates(pics, runs, piece["at"], body_run.width, body_run.height, 0)
    assert _kept(P.without_plate(raw, body_run.width, plates)) > _kept(raw) * 0.85
    assert _kept(P.without_plate(raw, body_run.width, plates, ramp)) < _kept(raw) / 2


def test_an_enchanted_piece_sparkles_in_the_turning_ramp(directory, runs):
    """A `+N` form shares one picture, and what it adds over the plain form is
    pixels of the ramp the game turns on its own timer."""
    pics = (GAME / "PICTURES.VGA").read_bytes()
    it = I.Items(directory)
    by_name = {p["name"]: p for p in it.doll()}
    for plain, enchanted, least in (("LEATHER HELMET", "LEATHER HELMET +1", 1),
                                    ("LEATHER ARMOR", "LEATHER ARMOR +1", 1)):
        a, b = by_name[plain], by_name[enchanted]
        assert a["male"] != b["male"]
        # Every +N form of a piece draws the one picture.
        for n in range(2, 6):
            assert by_name[f"{plain} +{n}"]["male"] == b["male"]
        run = runs[a["run"]]
        sparkle = lambda pic: sum(1 for v in P.picture(pics, run, pic)
                                  if 0xD0 <= v < 0xE0)
        assert sparkle(a["male"]) == 0
        assert sparkle(b["male"]) >= least


def test_the_paper_doll_covers_every_worn_item(directory, runs):
    it = I.Items(directory)
    doll = it.doll()
    assert len(doll) == 164
    by_slot = {}
    for piece in doll:
        by_slot[piece["slot"]] = by_slot.get(piece["slot"], 0) + 1
    assert by_slot == {"head": 35, "body": 60, "feet": 35, "hands": 34}


def test_both_sexes_of_every_piece_exist_and_differ(directory, runs):
    """The female form is the male plus one, and no pair is the same picture."""
    pics = (GAME / "PICTURES.VGA").read_bytes()
    it = I.Items(directory)
    for piece in it.doll():
        run = runs[piece["run"]]
        assert piece["female"] == piece["male"] + 1
        assert 0 <= piece["male"] and piece["female"] < run.count, piece
        male = P.picture(pics, run, piece["male"])
        female = P.picture(pics, run, piece["female"])
        assert male != female, piece
        assert any(v != P.TRANSPARENT for v in male), piece


def test_the_body_slot_draws_from_run_six_and_the_rest_from_run_seven(directory):
    it = I.Items(directory)
    for piece in it.doll():
        assert piece["run"] == (6 if piece["slot"] == "body" else 7)

def test_a_base_body_is_a_whole_panel_before_the_ground_comes_off(directory, runs):
    """The eighteen are the figure standing in the game's own stone alcove, so
    every pixel of the frame is opaque until the ground is cut."""
    pics = (GAME / "PICTURES.VGA").read_bytes()
    run = runs[I.BODY_RUN]
    for n in range(I.BODY_PICTURES):
        raw = P.picture(pics, run, n)
        assert P.TRANSPARENT not in raw, n


def test_cutting_the_ground_leaves_one_figure_and_no_holes(directory, runs):
    """A flood from the border, not a ramp test: body 6 wears the ground's own
    ramp and a plain test takes 312 pixels of its clothing away."""
    pics = (GAME / "PICTURES.VGA").read_bytes()
    run = runs[I.BODY_RUN]
    width, height = run.width, run.height
    for n in range(I.BODY_PICTURES):
        cut = P.without_ground(P.picture(pics, run, n), width)
        kept = sum(1 for v in cut if v != P.TRANSPARENT)
        # every figure comes out about the same size, and none is emptied
        assert 1400 < kept < 1800, (n, kept)
        # nothing is cut out of the middle: the top two rows go entirely
        assert set(cut[:2 * width]) == {P.TRANSPARENT}, n


def test_a_worn_piece_carries_no_ground_of_its_own(directory, runs):
    """The 164 were sprites already, which is why only the bodies are cut."""
    pics = (GAME / "PICTURES.VGA").read_bytes()
    it = I.Items(directory)
    for piece in it.doll():
        run = runs[piece["run"]]
        raw = P.picture(pics, run, piece["male"])
        assert P.TRANSPARENT in raw, piece
        opaque = sum(1 for v in raw if v != P.TRANSPARENT)
        assert opaque < len(raw) // 2, piece


def test_the_doll_draws_six_icon_boxes_beside_the_figure(directory):
    """The six slots wearing no picture each draw their item's icon in a box,
    and the table at DS:0x6494 is where those boxes are."""
    boxes = I.Items(directory).doll_boxes()
    assert list(boxes) == ["missile", "container", "hand", "shield",
                           "ring", "ring 2"]
    assert [b["box"] for b in boxes.values()] == [10, 11, 12, 13, 14, 15]
    assert boxes["missile"]["at"] == [0, 64] and boxes["missile"]["size"] == [16, 16]
    assert boxes["shield"]["at"] == [40, 103]
    # The two rings take an 8 by 8 box, and the other four a 16 by 16.
    for slot, box in boxes.items():
        assert box["size"] == ([8, 8] if slot.startswith("ring") else [16, 16])
        # Every box stands inside the figure's own 56 by 136 frame.
        assert box["at"][0] + box["size"][0] <= 56
        assert box["at"][1] + box["size"][1] <= 136


def test_a_two_handed_weapon_is_laid_at_the_shields_box(directory):
    """Image 0x1611B reads the shield box's own entry rather than a corner of
    its own, so the weapon goes where the shield's icon would."""
    it = I.Items(directory)
    index = it.doll_index()
    assert index["two_handed"]["at"] == it.doll_boxes()["shield"]["at"] == [40, 103]
    assert index["two_handed"]["run"] == 7
    # The other five boxes are the game's own panel layout, so the figure the
    # export writes carries none of them.
    assert "boxes" not in index
