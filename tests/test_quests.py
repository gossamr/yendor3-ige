"""The three quest tables, and the writers and readers assembled from them.

Nothing here is on a clue-book page either. What fixes the readings is that
each table tiles its own terminator exactly: the gate table's 35 records end at
a word of `0xFFFF` where the destination table ends, the kill table's 23 end at
a zero key, and every flag number all three hold falls in 1 to 224. The world
scripts are immediates rather than a table, so `quests.check_world_scripts` holds
each one to the bytes at the image address it was read from.
"""
import quests as Q


def test_the_gate_table_tiles_to_its_terminator(directory):
    """35 records of 22 bytes, starting where the 139 destination records end."""
    gates = Q.gates(directory.exe)
    assert len(gates) == 35
    end = Q.DGROUP + Q.GATE_TABLE_AT + len(gates) * Q.GATE_RECORD
    assert Q._u16(directory.exe, end) == Q.GATE_END


def test_every_gate_names_a_destination_and_a_flag_in_range(directory):
    for gate in Q.gates(directory.exe):
        assert 1 <= gate["destination"] <= 139
        assert 1 <= gate["flag"] <= Q.FLAG_COUNT


def test_the_gates_reach_thirteen_of_the_fourteen_flag_words(directory):
    """Flags 19 to 218, and no gate names the first word."""
    flags = [gate["flag"] for gate in Q.gates(directory.exe)]
    assert min(flags) == 19 and max(flags) == 218
    assert len({(f - 1) // 16 for f in flags}) == 13
    assert all(f > 16 for f in flags)


def test_thirteen_gates_carry_a_password_and_one_carries_an_item(directory):
    gates = Q.gates(directory.exe)
    passwords = [g["password"] for g in gates if g["password"]]
    assert passwords == ["NOBLEMAN", "GAUNTLET", "COMPASSION", "PATRIARCH",
                         "PARCHMENT", "RUSE", "GEMSTONE", "CALANTHA", "ALLIANCE",
                         "TIMBER", "SOLITAIRE", "DELIA", "DRAGONSKIN"]
    keyed = [g for g in gates if g["itemId"]]
    assert len(keyed) == 1
    assert keyed[0]["destination"] == 58 and keyed[0]["itemId"] == 374
    assert keyed[0]["flag"] == 121


def test_a_password_gate_raises_prompt_26_and_asks_for_it(directory):
    """`+0x06` holds 26 on all thirteen, and the destination record's own
    `0x8000` is what sends the refusal to the password branch."""
    for gate in Q.gates(directory.exe):
        if gate["password"]:
            assert gate["prompt"] == Q.PASSWORD_PROMPT
            assert gate["asksPassword"]
        else:
            assert gate["prompt"] is None


def test_the_flag_resolver_counts_bits_down_from_the_high_one(directory):
    """Image 0x17AFE: flag 16 is the last bit of the first word, not the first
    bit of the second."""
    assert Q.flag_of(Q.FLAG_WORDS_AT, 0x8000) == 1
    assert Q.flag_of(Q.FLAG_WORDS_AT, 0x0001) == 16
    assert Q.flag_of(Q.FLAG_WORDS_AT + 2, 0x8000) == 17
    assert Q.flag_of(Q.FLAG_WORDS_AT + 26, 0x0001) == Q.FLAG_COUNT


def test_the_kill_table_tiles_to_a_zero_key(directory):
    kills = Q.kills(directory)
    assert len(kills) == 23
    end = Q.DGROUP + Q.KILL_TABLE_AT + len(kills) * Q.KILL_RECORD
    assert Q._u16(directory.exe, end) == 0


def test_the_kill_records_ascend_by_spawn_id_and_by_flag(directory):
    kills = Q.kills(directory)
    assert [k["spawnId"] for k in kills] == sorted(k["spawnId"] for k in kills)
    assert [k["flags"][0] for k in kills] == sorted(k["flags"][0] for k in kills)


def test_every_kill_names_one_flag_and_one_monster_that_stands_somewhere(directory):
    for record in Q.kills(directory):
        assert len(record["flags"]) == 1
        assert 1 <= record["flags"][0] <= Q.FLAG_COUNT
        assert record["name"]
        assert record["x"] is not None and record["y"] is not None


def test_the_last_two_kills_are_blazios_and_paltivar(directory):
    """Flags 223 and 224 are the ending, and the numbering follows the game's
    own order through the regions."""
    kills = Q.kills(directory)
    assert kills[-2]["name"] == "BLAZIOS" and kills[-2]["flags"] == [223]
    assert kills[-1]["name"] == "PALTIVAR" and kills[-1]["flags"] == [224]


def test_the_cell_events_place_the_six_scripts_the_handlers_answer_for(directory):
    scripts = Q.world_scripts(directory)
    assert [s["script"] for s in scripts] == [1, 2, 3, 4, 5, 6]
    assert [(s["x"], s["y"]) for s in scripts] == [
        (40, 62), (69, 50), (487, 32), (603, 44), (352, 68), (635, 136)]


def test_every_script_constant_is_in_the_image_it_was_read_from(directory):
    """The landing is three `mov word ptr` immediates in the step handler and
    the object is a `mov ax` immediate in the drawing dispatch."""
    Q.check_world_scripts(directory.exe)


def test_the_scripts_draw_the_objects_the_drawing_dispatch_answers(directory):
    assert [s["object"] for s in Q.world_scripts(directory)] == [210, 223, 224, 231, 212, 250]


def test_two_scripts_draw_their_object_on_a_flag(directory):
    """Cell (40, 62) takes object 210 while flag 5 is clear and cell (69, 50)
    takes object 223 once flag 27 is set, which image 0x0B704 tests a second
    time inside the view."""
    by = {s["script"]: s for s in Q.world_scripts(directory)}
    assert by[1]["objectFlag"] == -5
    assert by[2]["objectFlag"] == 27
    assert all(by[n]["objectFlag"] == 0 for n in (3, 4, 5, 6))


def test_the_plane_of_souls_is_entered_and_left_on_one_flag(directory):
    by = {s["script"]: s for s in Q.world_scripts(directory)}
    assert by[5]["writes"] == [157] and by[5]["needsFlag"] == 145
    assert by[6]["writes"] == [-157]
    assert by[6]["destroys"]["first"] == 383 and by[6]["destroys"]["last"] == 385
    assert by[6]["marksCarried"] == {"item": 387, "flag": 158}


def test_the_drain_swaps_a_ring_of_invisibility_for_a_copper_ring_of_armor(directory):
    by = {s["script"]: s for s in Q.world_scripts(directory)}
    assert by[4]["swap"]["from"] == 198 and by[4]["swap"]["to"] == 205
    assert by[4]["swap"]["message"] == ["THE RINGS", "HAVE BEEN", "DRAINED."]


def test_223_of_the_224_flags_are_used(people):
    """Flag 58 is the one nothing names, and it is a gap inside a run rather
    than the end of one."""
    counts = Q.summary(people)
    assert counts["used"] == 223
    assert counts["unused"] == [58]


def test_two_flags_are_written_and_never_read_and_none_the_other_way(people):
    """Killing the WASP QUEEN sets flag 6 and NPC 133's TOUCH CROWN sets flag
    212. A flag read and never written would be a hole in the reading."""
    counts = Q.summary(people)
    assert counts["writtenNeverRead"] == [6, 212]
    assert counts["readNeverWritten"] == []


def test_the_armorer_is_the_whole_mechanism_in_one_record(people):
    """PAY 3,000 is offered while flag 63 is clear and sets it, and BUY ARMOR,
    SELL ITEMS and FINISHED all want it set."""
    row = Q.flag_writers_and_readers(people)[62]
    assert row["flag"] == 63
    assert "NPC 31 PAY 3,000" in row["writtenBy"]
    assert sum(1 for r in row["readBy"] if r.startswith("offers NPC 31")) == 3


def test_killing_king_slator_silences_four_people(people):
    """NPCs 127, 128, 129 and 131 all fall silent on flag 206."""
    row = Q.flag_writers_and_readers(people)[205]
    assert row["flag"] == 206
    silent = [r for r in row["readBy"] if r.endswith("silent")]
    assert silent == ["NPC 127 silent", "NPC 128 silent",
                      "NPC 129 silent", "NPC 131 silent"]


def test_three_items_have_a_handler_and_each_one_is_in_the_image(directory):
    """Image 0x0B490 dispatches USE on the JEWELED PORTAL KEY, the ENHANCED
    LENS and the ORB OF ZAMORA, and nothing else."""
    Q.check_item_handlers(directory.exe)
    assert [u["item"] for u in Q.item_handlers(directory.exe)] == [374, 382, 631]


def test_the_lens_opens_the_plane_of_souls_from_one_cell(directory):
    lens = Q.item_handlers(directory.exe)[1]
    assert lens["standAt"] == {"x": 352, "y": 67, "facing": "south"}
    assert lens["writes"] == [145]
    assert lens["message"] == ["UNLOCKED"]


def test_the_orb_wants_one_item_from_each_of_the_five_kingdoms(directory):
    """The SCEPTER OF BARIAG, the AMULET OF OBVERSIA, the SWORD OF SLATOR, the
    CROWN OF EURON and the GEMSTONE OF YENDOR, and it destroys all five."""
    orb = Q.item_handlers(directory.exe)[2]
    assert orb["wants"] == [214, 300, 523, 548, 630]
    assert orb["destroys"] == orb["wants"]
    assert orb["needsFlag"] == 223
    assert orb["opensNpc"] == 140
    assert orb["to"] == {"x": 660, "y": 132, "facing": "north"}


def test_the_travel_guard_is_the_three_weapons_of_light(directory):
    guard = Q.travel_guard(directory.exe)
    assert guard["flag"] == 157
    assert (guard["first"], guard["last"]) == (383, 385)
    assert guard["refusal"] == ["YOU CAN NOT", "USE THAT", "HERE!"]


def test_every_handler_writes_the_area_word_the_ambience_reads(directory):
    """`DS:0xCF33` picks which ambient list a place runs (docs/audio.md), and
    a handler that lands the party writes it by hand where a door takes it out
    of its destination record. Script 5 is the only writer of area 8, the Plane
    of Souls."""
    areas = {s["script"]: s["area"] for s in Q.world_scripts(directory)}
    assert areas == {1: 2, 2: 4, 3: 5, 4: 5, 5: 8, 6: 2}
    assert Q.item_handlers(directory.exe)[2]["area"] == 3


def test_the_boots_that_spare_a_character_from_a_tile_are_in_the_image(directory):
    """Image 0x0ADAC compares the feet word of a character record against the
    RED DRAGON SKIN BOOTS, on a pad record carrying bit 0 (docs/map.md)."""
    Q.check_tiles(directory.exe)
    assert Q.shod_against_tiles(directory.exe) == 629


def test_the_ending_is_a_song_two_pages_and_twelve_spoken_lines(directory):
    """Image 0x05290 is what flag 224 sends the main loop to. It plays song 24
    over two run 0 pictures and speaks the last twelve sounds of the bank."""
    one = Q.ending(directory.exe)
    assert one["song"] == 24 and one["run"] == 0
    assert [page["picture"] for page in one["pages"]] == [13, 14]
    spoken = [step["sound"] for page in one["pages"]
              for step in page["speaks"] if "sound" in step]
    assert spoken == list(range(130, 142))


def test_every_ending_constant_is_in_the_image_it_was_read_from(directory):
    Q.check_ending(directory.exe)
