"""The section directory is the foundation: if it is misread, every table
below it decodes as garbage, so these assertions are deliberately strict.
"""
import sections as S


def test_files_are_the_expected_build(directory):
    assert len(directory.exe) == 202_676
    assert len(directory.world) == 4_350_901


def test_directory_covers_world_dat_exactly(directory):
    secs = directory.sections
    assert secs[0].offset == 0x083400
    # Sections are contiguous and the last one ends at EOF, which is what makes
    # the final table entry usable as an end marker.
    for a, b in zip(secs, secs[1:]):
        assert a.end == b.offset
    assert secs[-1].end == len(directory.world)


def test_offsets_are_ascending_and_in_range(directory):
    for s in directory.sections + directory.restoration:
        assert 0 <= s.offset < len(directory.world)
        assert s.size >= 0


def test_record_sizes_divide_evenly(directory):
    assert directory[S.ENEMIES].size == 7738
    assert directory[S.ENEMIES].size % S.ENEMY_RECORD == 0
    assert directory[S.ENEMIES].size // S.ENEMY_RECORD == 73

    assert directory[S.SPELLS].size == 8560
    assert directory[S.SPELLS].size // S.SPELL_RECORD == 107

    wt = directory.rest(S.WALKTHROUGH)
    assert wt.size // S.WALKTHROUGH_PAGE == 33
    assert S.WALKTHROUGH_COLS * S.WALKTHROUGH_ROWS == S.WALKTHROUGH_PAGE


def test_known_section_offsets(directory):
    """Offsets confirmed by inspecting the data they point at."""
    assert directory[S.ENEMIES].offset == 0x417075
    assert directory[S.SPELLS].offset == 0x41B5BF
    assert directory.rest(S.WALKTHROUGH).offset == 0x3C90A2


def test_audio_index_tables_still_where_the_handoff_says(directory):
    """The CMF and VOC index tables were located in an earlier session. They
    are not used by the extractor, but if they moved this is a different build
    and nothing else here can be trusted either."""
    import struct
    cmf = struct.unpack_from("<I", directory.exe, 0x2CFC7)[0]
    voc = struct.unpack_from("<I", directory.exe, 0x2D057)[0]
    assert 0 < cmf < len(directory.world)
    assert 0 < voc < len(directory.world)
    assert directory.world[voc:voc + 19] == b"Creative Voice File"


def test_spell_text_section_is_whole_lines(directory):
    st = directory.spell_text_section()
    assert st.offset == 0x3D57E1
    assert st.size % S.SPELL_TEXT_BLOCK == 0
    assert st.size % S.SPELL_TEXT_COLS == 0
    assert st.size // S.SPELL_TEXT_COLS == 360
