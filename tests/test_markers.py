"""The legend marker table: which gold square on a map is which legend line.

The decode claims each record carries its own page and square in the same
coordinate system the map data uses. What makes that more than a story is that
it partitions cleanly and agrees with an experiment done a different way: the
an earlier method attributed 17 pages by taking their
markers away and watching the screen, and the records agree with all but one.
"""
import json
from pathlib import Path

import markers

ROOT = Path(__file__).resolve().parent.parent
WORLD = (ROOT / "game" / "WORLD.DAT").read_bytes()
PAGES = json.loads((ROOT / "data" / "map_pages.json").read_text())


def test_the_table_ends_where_the_labels_begin():
    recs = markers.read_markers(WORLD)
    assert len(recs) == 207
    # The byte after the last record is the start of the label strings, which
    # is why the table's length has to be found by shape rather than read.
    assert markers.read_labels(WORLD)[1] == "FLAGELL"


def test_labels_are_packed_strings_not_fixed_fields():
    labels = markers.read_labels(WORLD)
    # A 25-byte-field reading works for the first hundred and then drifts; the
    # drift shows up as the terminator marching into the text.
    assert labels[133] == "THAINE MAP 1"
    assert WORLD[0x3D3CCD + 133 * 25:0x3D3CCD + 134 * 25] != b"THAINE MAP 1".ljust(25, b"\0")


def test_every_group_falls_on_exactly_one_page():
    """A group is one legend; a legend belongs to one map."""
    seen = {}
    for m in markers.read_markers(WORLD):
        seen.setdefault(m["group"], set()).add((m["area"], m["level"]))
    assert seen, "no marker records decoded"
    spread = {g: v for g, v in seen.items() if len(v) > 1}
    assert not spread, f"groups spanning several slots: {spread}"


def test_the_records_place_most_of_the_printed_pages():
    marks = markers.by_page(WORLD, PAGES)
    printed = {p["title"] for p in PAGES if p.get("in_book")}
    assert len(marks.keys() & printed) >= 34, \
        "the records should place 35 of the 37 printed pages"
    # The maps the book leaves out take markers too, which is how they were
    # found: a legend line naming a place the book never shows.
    assert len(marks) > 35


def test_positions_land_inside_the_printed_page():
    """Every marker now has a square, because the page draws the whole row.

    It did not always: the page used to print cells 3..36, and the seven
    markers standing in the cropped columns (a ship at cell 0, an exit at
    cell 39) had nowhere to go, which is why some pages drew fewer gold
    squares than they had legend lines. Widening the page to the stored row
    gave all seven a square.
    """
    marks = markers.by_page(WORLD, PAGES)
    printed = {p["title"] for p in PAGES if p.get("in_book")}
    off = [(t, m["label"]) for t, ms in marks.items() if t in printed
           for m in ms if not m["shown"]]
    assert off == [], off


def test_numbering_reads_top_left_to_bottom_right():
    for marks in markers.by_page(WORLD, PAGES).values():
        order = [(m["row"], m["col"]) for m in marks]
        assert order == sorted(order)
        assert [m["n"] for m in marks] == list(range(1, len(marks) + 1))



def test_the_caption_is_field_three_not_the_record_index():
    """Reading the caption by the record's own position gives wrong captions.

    It is the trap this decode fell into: 138 labels and 207 markers looks like
    a shortfall, so fifteen pages came out with no captions at all. Field 3 is
    the index, 1..137, and markers share captions, because a place like
    KINGDOM OF BARIAG is a marker on several maps.
    """
    recs = markers.read_markers(WORLD)
    labels = markers.read_labels(WORLD)
    f3 = [m["field3"] for m in recs]
    # 1..137, and label 137 is the last one with text, so the reader keeps
    # walking past it into blanks, so the table's real length is the range.
    assert (min(f3), max(f3)) == (1, 137)
    assert labels[137] and not labels[138]
    assert len(set(f3)) < len(f3), "captions are shared, so this cannot be a bijection"

    # Every marker names a caption, so no page is left blank.
    marks = markers.by_page(WORLD, PAGES)
    assert all(m["label"] for ms in marks.values() for m in ms)


def test_the_captions_match_what_the_game_prints():
    """Checked in the emulator: clicking a marker prints its caption.

    ELFIN CITY was one of the pages the index reading left blank; clicking its
    six markers in reading order gives exactly these, and SEWERS OF BARIAG's
    single marker reads KINGDOM OF BARIAG, not the INTELLIGENCE = 85 that the
    record index suggested.
    """
    marks = markers.by_page(WORLD, PAGES)
    assert [m["label"] for m in marks["ELFIN CITY"]] == [
        "THAINE MAP 3", "MACKENZIE", "VISHAN'S STRONGHOLD",
        "BAXTER", "MALEIA", "ELFIN SEWER"]
    assert [m["label"] for m in marks["SEWERS OF BARIAG"]] == ["KINGDOM OF BARIAG"]


def test_unplaced_labels_name_a_real_slot():
    for u in markers.unplaced(WORLD, PAGES):
        assert 0 <= u["area"] < 7
        assert 0 <= u["level"] < 20
