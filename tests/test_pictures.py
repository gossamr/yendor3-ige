"""The picture runs in PICTURES.VGA, and the monster art read out of them.

The run table is checked against the file it describes, ten runs that tile the
whole 17 MB with no gap and no remainder, and the monster art against
the game's own clue-book screens, which is the only check that can tell a
plausible decode from a right one.
"""
import base64
import json
from pathlib import Path

import pytest

import extract
import pictures as P
import pngutil
import tiles

ROOT = Path(__file__).resolve().parent.parent
PICS = ROOT / "game" / "PICTURES.VGA"
SHOTS = ROOT / "tmp" / "monsters"


def runs(directory):
    return P.read_runs(directory.exe, PICS.stat().st_size)


def test_the_ten_runs_tile_the_whole_file(directory):
    size = PICS.stat().st_size
    rs = runs(directory)
    assert len(rs) == P.COUNT
    assert rs[0].base == 0
    for a, b in zip(rs, rs[1:]):
        assert a.base + a.count * a.size == b.base, f"{a} does not meet {b}"
    last = rs[-1]
    assert last.base + last.count * last.size == size


def test_every_run_is_a_whole_number_of_pictures(directory):
    for run in runs(directory):
        assert run.width * run.height == run.size
        assert run.count > 0


def test_the_last_run_is_the_map_tile_bank(directory):
    """tools/tiles.py reads the map's artwork as 64-byte tiles counted from
    the head of the file. That block is run 9, arrived at from the other
    direction, so the two must agree on where it starts."""
    run = runs(directory)[9]
    assert (run.width, run.height) == (tiles.TILE, tiles.TILE)
    assert run.base == tiles.BANK_ALIGN + tiles.BLOCK * tiles.TILE_BYTES


def test_a_monster_names_a_picture_that_exists(directory):
    pics = PICS.read_bytes()
    rs = runs(directory)
    for e in extract.extract_enemies(directory):
        run = P.monster_run(rs, e["masks"]["w96"])
        assert e["sprite"] + P.FRAMES <= run.count, e["name"]


def test_recoloring_moves_a_ramp_and_leaves_the_shade(directory):
    raw = bytes([0x00, 0x2F, 0xA3, P.TRANSPARENT])
    assert P.recolored(raw, {2: 5, 10: 1}) == bytes([0x00, 0x5F, 0x13, P.TRANSPARENT])
    assert P.grayed(raw) == bytes([0x00, 0x0F, 0x03, P.TRANSPARENT])


def test_the_monsters_drawn_gray_are_the_three_the_bit_names(directory):
    off, bit = P.GRAY_BIT
    gray = {e["name"] for e in extract.extract_enemies(directory)
            if e["masks"][f"w{off}"] >> bit & 1}
    assert gray == {"GHOST", "SPECTRE", "PHASE TITAN"}


def test_the_art_reproduces_the_games_own_monster_screens(directory):
    """The proof of the whole chain: run, picture number, palette, recolor
    and the gray bit. Each capture is one step of an animation the clue book
    runs, so the monster's ten pictures are all candidates; a page caught
    mid-refresh shows two steps at once and matches neither exactly.

    Measured: 64 of 71 exact, and no monster below 0.53.
    """
    if not any(SHOTS.glob("*.png")):
        pytest.skip(f"no monster captures in {SHOTS.relative_to(ROOT)}; "
                    "run tools/capture_monsters.js")
    import verify_monsters as V

    pics = PICS.read_bytes()
    rs = runs(directory)
    palette = tiles.palette(directory, extract.MONSTER_PALETTE)
    slot = {}
    for i, c in enumerate(palette):
        slot.setdefault(bytes(c), i)

    listed = sorted((e for e in extract.extract_enemies(directory) if e["listed"]),
                    key=lambda e: e["name"])
    exact = seen = 0
    for n, e in enumerate(listed):
        shot = SHOTS / f"m{n:02d}.png"
        if not shot.exists():
            continue
        seen += 1
        sw, sh, rgb = pngutil.read(str(shot))
        index = [slot.get(rgb[i * 3:i * 3 + 3], -1) for i in range(sw * sh)]
        swaps = {s["from"]: s["to"] for s in e["recolor"]}
        best = 0.0
        for f in range(P.FRAMES):
            run, raw = P.monster(pics, rs, e["sprite"], e["masks"]["w96"],
                                  e["masks"]["w98"], swaps, f)
            hit, total = V.compare(rgb, sw, sh, raw, run.width, index,
                                   V.ANCHOR[run.index])
            if total:
                best = max(best, hit / total)
        assert best > 0.5, f"{e['name']} matches its own screen only {best:.3f}"
        exact += best == 1.0
    if seen:
        assert exact >= seen * 0.85, f"only {exact} of {seen} exact"


def test_every_listed_monster_gets_a_picture(directory):
    pics = PICS.read_bytes()
    enemies = extract.extract_enemies(directory)
    art = extract.monster_art(directory, pics, enemies)
    assert set(art) == {e["name"] for e in enemies if e["listed"]}
    for name, a in art.items():
        assert a["src"].startswith("data:image/png;base64,"), name
        png = base64.b64decode(a["src"].split(",", 1)[1])
        assert png[:8] == b"\x89PNG\r\n\x1a\n", name
        # The declared size has to be the picture's own, or the panel scales it.
        w, h = int.from_bytes(png[16:20], "big"), int.from_bytes(png[20:24], "big")
        assert (w, h) == (a["width"], a["height"]), name


def test_the_art_is_cropped_to_the_monster(directory):
    """A picture is mostly empty, and storing the empty part costs bytes the
    panel carries on every load."""
    pics = PICS.read_bytes()
    rs = runs(directory)
    enemies = extract.extract_enemies(directory)
    art = extract.monster_art(directory, pics, enemies)
    for e in enemies:
        if not e["listed"]:
            continue
        run = P.monster_run(rs, e["masks"]["w96"])
        a = art[e["name"]]
        assert a["width"] <= run.width and a["height"] <= run.height, e["name"]
    total = sum(len(a["src"]) for a in art.values())
    assert total < 300_000, f"{total} bytes of art is more than the panel should carry"
