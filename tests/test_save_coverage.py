"""The save layout has a row for every offset the code names.

`tools/save_coverage.py` reads every offset of `REGISTER.EXE` as if an
instruction began there and buckets each roster access by the offset it names.
`tools/save_map.py` holds the layout. The two answer different questions, so
holding them to each other catches the drift that matters: an offset the
executable reads through a displacement and the layout has no row for.

The counts below are what `docs/saves.md` prints. They move when a row is
added, and the failure is the reminder to move the document with it.
"""

from __future__ import annotations

import pytest

import save_coverage as C
import saves as S
from disasm import Exe

# What `docs/saves.md` says is left, header slot and character record.
HEADER_UNNAMED, CHARACTER_UNNAMED = 190, 92

# The three displacements the sweep finds that belong to another struct
# entirely: `[si+0x70]` inside a monster pass, `[bp+0x71]` on a stack frame,
# and `[bx+0x108]` on the attack table at `DS:0x96DA`. `docs/saves.md` reads
# each of them where it names the 92.
OTHER_STRUCTS = {112, 113, 264}


@pytest.fixture(scope="module")
def swept():
    return C.scan(Exe())


def test_every_header_offset_the_code_names_has_a_row(swept):
    character, header = swept
    named = C.named("header")
    touched = {off for off, sites in header.items()
               if any(hit[3] >= C.WINDOW // 3 for hit in sites)}
    assert sorted(touched - set(named)) == []


def test_the_character_offsets_left_over_belong_to_another_struct(swept):
    character, header = swept
    named = C.named("character")
    touched = {off for off, sites in character.items()
               if any(hit[3] >= C.WINDOW // 3 for hit in sites)}
    assert sorted(touched - set(named)) == sorted(OTHER_STRUCTS)


def test_the_counts_are_what_the_document_prints():
    assert S.ROSTER_SLOT - len(C.named("header")) == HEADER_UNNAMED
    assert S.ROSTER_SLOT - len(C.named("character")) == CHARACTER_UNNAMED


def test_the_sweep_finds_the_fields_the_layout_already_names(swept):
    """The sweep's recall, so a change that blinds it fails here.

    A field reached by adding a constant to the pointer first names no
    displacement and is not found: the spell book at 202, which image `0x17B27`
    reaches by adding `0xCA`, is the shape of that.
    """
    character, header = swept
    found = 0
    for which, swept_one in (("header", header), ("character", character)):
        for off in C.named(which):
            if any(hit[3] >= C.WINDOW // 3 for hit in swept_one.get(off, [])):
                found += 1
    assert found >= 150
