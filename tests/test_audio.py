"""The two audio banks, and the tables that raise a sound.

What makes this more than a plausible reading of three byte ranges is that
every layout divides its section exactly and fills it with nothing left over.
The 24 song lengths reach the start of section 15 and the 141 sound lengths
reach its end, every slice opens on its own magic, and the ambient pointer
table ends on the `0xFFFF` the eighth pointer is followed by.
"""
import struct

import audio as A
import extract as EX
import items as IT
import links as L
import sections as S


def _u16(blob, at):
    return struct.unpack_from("<H", blob, at)[0]


def test_the_four_index_tables_run_end_to_end(directory):
    """The master directory ends where the song offsets begin, and each table
    reaches the next: 36 dwords from 0x2CF37, then 24, 24, 141 and 141."""
    assert S.MASTER_TABLE + 36 * 4 == A.SONG_OFFSETS
    assert A.SONG_OFFSETS + A.SONG_COUNT * 4 == A.SONG_LENGTHS
    assert A.SONG_LENGTHS + A.SONG_COUNT * 2 == A.SOUND_OFFSETS
    assert A.SOUND_OFFSETS + A.SOUND_COUNT * 4 == A.SOUND_LENGTHS


def test_every_slice_is_a_whole_file(directory):
    """Bank() asserts the magics and the contiguity as it reads; this is what
    those assertions come to on the two banks."""
    bank = A.Bank(directory)
    for n in range(1, A.SONG_COUNT + 1):
        assert bank.song(n)[:4] == A.CMF_MAGIC
    for n in range(1, A.SOUND_COUNT + 1):
        assert bank.sound(n)[:len(A.VOC_MAGIC)] == A.VOC_MAGIC
    assert bank.song(0) is None and bank.sound(0) is None
    assert bank.song(A.SONG_COUNT + 1) is None


def test_the_banks_fill_their_own_sections(directory):
    bank = A.Bank(directory)
    songs, sounds = directory[A.SONGS], directory[A.SOUNDS]
    assert sum(bank.song_lengths) == songs.size
    assert sum(bank.sound_lengths) == sounds.size
    assert bank.song_offsets[0] == songs.offset
    assert bank.sound_offsets[0] == sounds.offset


def test_the_magics_in_the_sections_match_the_offset_tables(directory):
    """The 24 CTMF magics in section 14 and the 141 VOC magics in section 15,
    with none missed and none left over."""
    bank = A.Bank(directory)
    for section, magic, table in ((A.SONGS, A.CMF_MAGIC, bank.song_offsets),
                                  (A.SOUNDS, A.VOC_MAGIC, bank.sound_offsets)):
        blob = directory[section].slice(directory.world)
        at, found = 0, []
        while (at := blob.find(magic, at)) >= 0:
            found.append(directory[section].offset + at)
            at += 1
        assert found == table


def test_every_song_carries_the_same_timing(directory):
    """48 ticks a quarter note, 96 clock ticks a second and a tempo of 120 on
    all 24, which agree with each other."""
    bank = A.Bank(directory)
    heads = [A.cmf_header(bank.song(n)) for n in range(1, A.SONG_COUNT + 1)]
    assert {h["ticks_per_quarter"] for h in heads} == {48}
    assert {h["ticks_per_second"] for h in heads} == {96}
    assert {h["tempo"] for h in heads} == {120}
    assert {h["divisor"] for h in heads} == {12428}
    assert {h["version"] for h in heads} == {0x0101}
    # No song names itself: the three string offsets are 0 on all 24.
    assert {h[name] for h in heads for name in ("title", "composer", "remarks")} == {0}


def test_the_instrument_block_is_where_the_header_says(directory):
    """40 bytes in on all 24, with the music block 16 x count past it."""
    bank = A.Bank(directory)
    for n in range(1, A.SONG_COUNT + 1):
        head = A.cmf_header(bank.song(n))
        assert head["instrument_block"] == 40
        assert head["music_block"] == 40 + A.CMF_INSTRUMENT * head["instrument_count"]
        assert len(A.cmf_instruments(bank.song(n))) == head["instrument_count"]


def test_every_voice_is_a_sine_pair(directory):
    """Both wave-select bytes are 0 on all 144 instruments in the bank, so the
    OPL2's other three waveforms go unused."""
    bank = A.Bank(directory)
    every = [i for n in range(1, A.SONG_COUNT + 1)
             for i in A.cmf_instruments(bank.song(n))]
    assert len(every) == 144
    assert {i[8] for i in every} == {0}
    assert {i[9] for i in every} == {0}
    # The last five bytes of the sixteen are zero on all of them.
    assert {b for i in every for b in i[11:]} == {0}


def test_every_event_stream_parses_end_to_end(directory):
    """Each closes on an FF 2F end-of-track landing on the file's own last
    byte, which cmf_track() asserts, and no other meta type appears."""
    bank = A.Bank(directory)
    for n in range(1, A.SONG_COUNT + 1):
        track = A.cmf_track(bank.song(n))
        assert track[-1]["kind"] == "end"
        assert sum(1 for e in track if e["kind"] == "end") == 1


def test_every_song_is_melodic(directory):
    """Controller 0x67 is CMF's rhythm switch: 24 songs set it, every one to
    0, so no song has percussion channels."""
    bank = A.Bank(directory)
    rhythm = [e for n in range(1, A.SONG_COUNT + 1)
              for e in A.cmf_track(bank.song(n))
              if e["kind"] == "control" and e["controller"] == A.CMF_RHYTHM_CONTROLLER]
    assert len(rhythm) == A.SONG_COUNT
    assert {e["value"] for e in rhythm} == {0}


def test_no_program_change_names_an_instrument_the_bank_lacks(directory):
    bank = A.Bank(directory)
    for n in range(1, A.SONG_COUNT + 1):
        blob = bank.song(n)
        count = A.cmf_header(blob)["instrument_count"]
        for event in A.cmf_track(blob):
            if event["kind"] == "program":
                assert event["instrument"] < count


def test_nine_voices_are_enough(directory):
    """23 songs use nine MIDI channels or fewer. Song 22 uses ten and never
    sounds more than nine at once, so a free-voice pool plays it."""
    bank = A.Bank(directory)
    widest = {}
    for n in range(1, A.SONG_COUNT + 1):
        sounding, most, used = set(), 0, set()
        for event in A.cmf_track(bank.song(n)):
            if event["kind"] == "on":
                sounding.add((event["channel"], event["note"]))
                used.add(event["channel"])
            elif event["kind"] == "off":
                sounding.discard((event["channel"], event["note"]))
            most = max(most, len({c for c, _ in sounding}))
        widest[n] = (len(used), most)
    assert [n for n, (used, _) in widest.items() if used > A.OPL_VOICES] == [22]
    assert max(most for _, most in widest.values()) == A.OPL_VOICES


def test_every_sound_is_one_uncompressed_block(directory):
    """No loops, no silence blocks, no stereo, no compression: the file's own
    size is 26 + 4 + block length + 1, which is the length table's entry."""
    bank = A.Bank(directory)
    for n in range(1, A.SOUND_COUNT + 1):
        blob = bank.sound(n)
        block = A.voc_block(blob)
        assert block["version"] == 0x010A
        assert blob[A.VOC_FIRST_BLOCK] == 26
        assert 26 + 4 + (block["samples"] + 2) + 1 == bank.sound_lengths[n - 1]
        assert len(A.voc_samples(blob)) == block["samples"]


def test_the_rates_are_creatives_own_time_constant(directory):
    """Fourteen distinct rate bytes appear, 9,009 to 22,222 Hz, and the bank
    runs 235 seconds."""
    bank = A.Bank(directory)
    blocks = [A.voc_block(bank.sound(n)) for n in range(1, A.SOUND_COUNT + 1)]
    rates = [b["rate"] for b in blocks]
    assert len(set(rates)) == 14
    assert min(rates) == 9009 and max(rates) == 22222
    assert round(sum(b["samples"] / b["rate"] for b in blocks)) == 235


def test_the_driver_is_ct_voice(directory):
    """Section 13 is Creative's CT-VOICE.DRV, and image 0x17CF8 hard-codes the
    length it reads rather than taking it from the directory."""
    bank = A.Bank(directory)
    blob = bank.driver()
    assert len(blob) == A.DRIVER_BYTES == 2493
    assert directory[A.DRIVER].size == A.DRIVER_BYTES
    assert blob[:3] == b"\xe9\x51\x07"


def test_section_3_gives_every_named_map_a_song(directory):
    """140 uint16, one per slot. The 54 slots the registry names all carry a
    song and the 86 it does not name all carry 0."""
    from registry import map_registry

    slots = A.map_songs(directory)
    named = {area * A.SLOTS_PER_AREA + level
             for area, level in map_registry(directory.world)}
    assert len(named) == 54
    assert {n for n, song in enumerate(slots) if song} == named
    assert all(1 <= slots[n] <= A.SONG_COUNT for n in named)


def test_the_slot_arithmetic_is_the_partys_own_position(directory):
    """Image 0x1534A resolves the slot from x and y, 40 by 24 cells a slot."""
    assert A.slot_of(0, 0) == 0
    assert A.slot_of(460, 46) == 1 * A.SLOTS_PER_AREA + 11
    assert A.slot_of(799, 167) == A.MAP_SLOTS - 1


def test_every_song_is_reachable(directory):
    """17 through section 3, the other 7 through the override or a direct
    call."""
    by_map = {s for s in A.map_songs(directory) if s}
    named = {A.MENU_SONG, A.RESTORATION_SONG, A.TITLE_SONG, A.OPENING_SONG,
             *A.ENDING_SONGS}
    assert len(by_map) == 17
    assert by_map | named == set(range(1, A.SONG_COUNT + 1))


def test_the_ambient_table_is_sixteen_halves_of_ten_slots(directory):
    """Eight areas, a day half and a night half, every delay 200 ticks."""
    areas = A.ambient(directory.exe)
    assert len(areas) == A.AMBIENT_AREAS
    for one in areas:
        for half in ("day", "night"):
            assert one[half]["delay"] == 200
            assert len(one[half]["slots"]) == A.AMBIENT_SLOTS
            assert all(0 <= s <= A.SOUND_COUNT for s in one[half]["slots"])
    # The eighth area is the Plane of Souls, and its five sounds are the
    # longest ambience in the game.
    plane = areas[7]
    assert [s for s in plane["day"]["slots"] if s] == [118, 119, 120, 121, 122]
    assert plane["night"]["slots"] == [0, 118, 0, 119, 0, 120, 0, 121, 0, 122]


def test_the_ambient_day_is_not_the_musics_day(directory):
    """Image 0x009C8 opens its day at 360 and image 0x1858F opens its own at
    420, so the two windows differ by half an hour."""
    assert A.AMBIENT_DAY == (360, 1140)
    assert A.MUSIC_DAY == (420, 1140)


def test_every_weapon_entry_names_a_sound(directory):
    """Section 9, 210 entries of 12 bytes, the sound at +0xA. 36 of the 210
    carry 0, which is the silence index 0 means everywhere."""
    sounds = A.weapon_sounds(directory)
    assert len(sounds) == 210
    assert all(0 <= s <= A.SOUND_COUNT for s in sounds)
    assert sum(1 for s in sounds if s == 0) == 36
    # The same table tools/items.py reaches through an item's own pointer.
    kit = IT.Items(directory)
    assert kit.pool + 0x1854 == directory[A.WEAPON_TABLE].offset


def test_the_dispatcher_decides_what_a_cast_sounds(directory):
    """Not a field of the record: the dispatcher at image 0x1C4E4 branches on
    record offset 72 and then on four bits of 76, and every one of the 107
    spells answers one of the 18 branches."""
    import spell_sounds as SS
    from disasm import Exe

    image = Exe("game/REGISTER.EXE")
    table = SS.plays(image)
    records = directory[S.SPELLS].records(directory.world, S.SPELL_RECORD)
    assert len(records) == 107
    assert all(SS.spell_branch(r, table) is not None for r in records)


def test_a_restorative_sounds_through_the_attack_table(directory):
    """Its branch never plays anything itself: image 0x1C5E1 hands offset 32
    to the lookup at image 0x0357E and drops the entry on the character's own
    animation slot, so what is heard is that entry's own sound beside the
    animation drawn over the portrait. All 19 name entry 18, whose sound is
    12."""
    import spell_sounds as SS
    from disasm import Exe
    import extract as EX

    image = Exe("game/REGISTER.EXE")
    table = SS.plays(image)
    attacks = EX.attack_table(directory.exe)
    records = directory[S.SPELLS].records(directory.world, S.SPELL_RECORD)
    rest = [r for r in records if _u16(r, A.SPELL_AFFECTS) & A.SPELL_RESTORATIVE]
    assert len(rest) == 19
    assert {_u16(r, 32) for r in rest} == {18}
    assert attacks[18]["sound"] == 12
    assert {SS.sound_of(r, table, attacks) for r in rest} == {12}
    # Offset 32 is an entry number only on that branch. Elsewhere it is a sound
    # index, and it runs to 126, which no 49-entry table could hold.
    body = [r for r in records if not _u16(r, A.SPELL_AFFECTS) & A.SPELL_RESTORATIVE]
    assert max(_u16(r, 32) for r in body) > len(attacks)
    assert len({SS.sound_of(r, table, attacks) for r in body}) > 10



def test_every_monster_and_attack_entry_names_a_sound(directory, data):
    """Enemy record 42 and 44, and the attack table's own +0."""
    for mob in data["enemies"]:
        for field in ("sound_hit", "sound_miss"):
            assert 0 <= mob[field] <= A.SOUND_COUNT
    for entry in EX.attack_table(directory.exe):
        assert 0 <= entry["sound"] <= A.SOUND_COUNT


def test_the_doors_and_pads_name_their_own_sounds(directory):
    """A door's sound plays on arrival and 65 of the 139 destinations are
    silent; a pad's is 43 on all 13 that teleport."""
    destinations = L.destinations(directory.exe)
    assert len(destinations) == 139
    quiet = sum(1 for one in destinations if not one["sound"])
    assert quiet == 65


def test_the_dawn_is_four_five_minute_windows(directory):
    """06:00, 06:30, 07:00 and 07:30, each with a bit that stops it
    repeating."""
    assert [at for at, _ in A.DAWN_WINDOWS] == [360, 390, 420, 450]
    assert len({bit for _, bit in A.DAWN_WINDOWS}) == 4
    assert A.DAWN_SOUND == 46
