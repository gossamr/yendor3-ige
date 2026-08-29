"""The map palette and tile bank, read from the game's files.

What these hold is that map artwork is *in* the files and can be decoded from
them. They deliberately do not claim a page can be drawn from the files alone:
a tile id does not determine the tile, and the last test is what measures that.
"""
import json
from pathlib import Path

import pytest

import pngutil
import markers as _markers
import solve_maps as SM
import tiles

ROOT = Path(__file__).resolve().parent.parent
SHOTS = ROOT / "tmp" / "maps4"
import registry as _registry
LOCS = _registry.captures((ROOT / "game" / "WORLD.DAT").read_bytes())


def need_shots():
    """Three tests below compare against the game's own map screens.

    `tools/capture_maps.js` writes them into tmp/, which is not committed, so
    a fresh clone has nothing to compare against and is told so rather than
    dividing by a count of zero.
    """
    if not any(SHOTS.glob("*.png")):
        pytest.skip(f"no map captures in {SHOTS.relative_to(ROOT)}; "
                    "run tools/capture_maps.js")


def test_the_palette_section_holds_seven_vga_palettes(directory):
    section = directory.sections[tiles.PALETTES]
    assert section.size == 7 * tiles.PALETTE_BYTES
    raw = directory.world[section.offset:section.offset + section.size]
    assert max(raw) <= 63, "a byte above 63 would not be a 6-bit DAC value"


def test_the_map_palette_opens_with_a_gray_ramp(directory):
    pal = tiles.palette(directory)
    ramp = pal[:9]
    assert all(p[0] == p[1] == p[2] for p in ramp), ramp
    assert [p[0] for p in ramp] == sorted(p[0] for p in ramp)


def test_tiles_the_game_drew_are_found_in_the_bank_exactly(directory):
    """The palette's proof: decode the bank with it and the game's own blocks
    turn up, pixel for pixel. A wrong palette would match nothing."""
    need_shots()
    pics = (ROOT / "game" / "PICTURES.VGA").read_bytes()
    pal = tiles.palette(directory)
    index = tiles.index(pics, pal)

    hits = misses = 0
    for loc in LOCS:
        shot = SHOTS / loc["shot"]
        if not shot.exists():
            continue
        grid = SM.read_grid(directory.world, loc["base"], loc["level"])
        objects = SM.read_objects(directory.world, loc["base"], loc["level"])
        skip = SM.marker_mask(str(shot))
        w, _, rgb = pngutil.read(str(shot))
        for r in range(SM.ROWS):
            for c in range(SM.COLS):
                if objects[r][c] or skip[r][c]:
                    continue
                block = b"".join(
                    rgb[((SM.Y0 + r * 8 + y) * w + SM.X0 + c * 8) * 3:
                        ((SM.Y0 + r * 8 + y) * w + SM.X0 + c * 8) * 3 + 24]
                    for y in range(8))
                if index.get(block):
                    hits += 1
                else:
                    misses += 1
    # Measured: 20,045 of 21,540. The rest are cells the capture shows with
    # something else over them that neither the object layer nor the marker
    # mask accounts for.
    assert hits / (hits + misses) > 0.9, f"{hits} found, {misses} not"


def test_a_tile_id_settles_the_tile_it_draws(directory):
    """A cell's terrain id picks one tile, on a page, nearly always.

    Measured over cells with no object and no legend marker on them: the id
    settles which block is drawn in 96% of (page, id) groups. What remains is
    a handful of ids that draw two different tiles on one page.
    """
    need_shots()
    one = total = 0
    for loc in LOCS:
        shot = SHOTS / loc["shot"]
        if not shot.exists():
            continue
        grid = SM.read_grid(directory.world, loc["base"], loc["level"])
        objects = SM.read_objects(directory.world, loc["base"], loc["level"])
        skip = SM.marker_mask(str(shot))
        w, _, rgb = pngutil.read(str(shot))
        seen: dict[int, set] = {}
        for r in range(SM.ROWS):
            for c in range(SM.COLS):
                if objects[r][c] or skip[r][c]:
                    continue
                seen.setdefault(grid[r][c], set()).add(b"".join(
                    rgb[((SM.Y0 + r * 8 + y) * w + SM.X0 + c * 8) * 3:
                        ((SM.Y0 + r * 8 + y) * w + SM.X0 + c * 8) * 3 + 24]
                    for y in range(8)))
        for blocks in seen.values():
            total += 1
            one += len(blocks) == 1
    assert total > 200
    assert one / total > 0.9, f"the id settles only {one/total:.0%} of groups"


def test_pages_render_from_the_files_as_the_game_drew_them(directory):
    """The whole claim, end to end.

    Nothing here reads a capture except to check the answer: the artwork comes
    out of PICTURES.VGA, the palette out of WORLD.DAT, and which tile each cell
    takes out of the tables in tiles.py. The captures are the check, not the
    source.

    Each cell is allowed any phase of the fire ramp, because a still of the map
    catches the rotation wherever it happened to be.
    """
    need_shots()
    pics = (ROOT / "game" / "PICTURES.VGA").read_bytes()
    exe = (ROOT / "game" / "REGISTER.EXE").read_bytes()
    world = directory.world
    phases = [tiles.cycled(tiles.palette(directory), n) for n in range(4)]

    total = exact = unknown = 0
    for loc in LOCS:
        shot = SHOTS / loc["shot"]
        if not shot.exists():
            continue
        area, level = loc["area"], loc["level"]
        grid = SM.read_grid(world, loc["base"], level)
        objects = SM.read_objects(world, loc["base"], level)
        marked = {(m["row"], m["col"]) for m in _markers.read_markers(world)
                  if (m["area"], m["level"]) == (area, level)}
        w, _, rgb = pngutil.read(str(shot))
        for r in range(SM.ROWS):
            for c in range(SM.COLS):
                if (r, c) in marked:
                    continue        # the game paints a legend marker over it
                total += 1
                bit = tiles.drawn(world, area, level, r, c + SM.COL0)
                theirs = b"".join(
                    rgb[((SM.Y0 + r * 8 + y) * w + SM.X0 + c * 8) * 3:
                        ((SM.Y0 + r * 8 + y) * w + SM.X0 + c * 8) * 3 + 24]
                    for y in range(8))
                got = None
                for pal in phases:
                    got = tiles.cell(pics, pal, exe, grid[r][c], objects[r][c], bit)
                    if got is None or got == theirs:
                        break
                if got is None:
                    unknown += 1
                elif got == theirs:
                    exact += 1

    assert unknown == 0
    assert exact / total > 0.99, f"{exact} of {total} cells match"
