"""The introduction, and the three talking heads it is the only player of.

Nothing here is a table either. The five scenes are hand-written code, so what
fixes the reading is that every constant is a byte string that either is at the
address it was read from or is not: `intro.check_intro` asserts each one, and
the tests below hold the counts this project states. The sounds are the other
side of it, since [docs/audio.md](../docs/audio.md) reaches 51 to 75 and 83
through these call sites and no other.
"""
import intro as I


def test_the_five_scenes_run_in_the_order_their_routines_do(directory):
    one = I.intro(directory.exe)
    assert [s["scene"] for s in one["scenes"]] == [1, 2, 3, 4, 5]
    assert [s["at"] if "at" in s else None for s in one["scenes"]] == [None] * 5


def test_every_scene_constant_is_in_the_image_it_was_read_from(directory):
    I.check_intro(directory.exe)


def test_the_four_stills_come_out_of_the_full_screen_run(directory):
    """Run 0 is the 318 x 198 run the menu and the assembly are painted into."""
    scenes = I.intro(directory.exe)["scenes"]
    assert [s["run"] for s in scenes] == [0, 0, 0, 0, 3]
    assert [s.get("picture") for s in scenes[:4]] == [8, 9, 10, 11]


def test_the_zoom_walks_a_rectangle_25_frames(directory):
    zoom = I.intro(directory.exe)["scenes"][3]["zoom"]
    assert zoom["picture"] == 12 and zoom["over"] == 11
    assert zoom["frames"] == 25
    assert zoom["from"] == [6, 4, 0x9D, 0x62]
    assert zoom["step"] == [0x0C, 8, -6, -4]


def test_the_three_heads_are_the_only_path_to_sounds_67_to_75(directory):
    """Except 71, which scene 5 plays on its own between two of them."""
    heads = I.heads(directory.exe)
    assert len(heads) == 3
    spoken = [n for h in heads
              for n in range(h["firstSound"], h["firstSound"] + h["sounds"])]
    assert spoken == [67, 68, 69, 70, 72, 73, 74, 75]
    assert 71 in I.sounds_played(directory.exe)


def test_every_head_carries_the_words_of_the_lines_it_speaks(directory):
    """The caption is what the routine prints where sound is switched off, so
    these three are the only spoken content the game writes down."""
    heads = I.heads(directory.exe)
    assert [len(h["caption"]) for h in heads] == [2, 3, 5]
    assert heads[0]["caption"][0].startswith('"ALTHOUGH THE APPEARANCE OF PALTIVAR')
    assert heads[2]["caption"][-1] == 'BE DONE."'
    for one in heads:
        assert one["quiet"] > 0
        assert one["picturesPerSound"] > 0


def test_the_intro_plays_every_sound_docs_audio_credits_to_it(directory):
    """51 to 66 over the two story pages, 83 as the world comes up, and 67 to
    75 across scene 5."""
    played = I.sounds_played(directory.exe)
    assert played == list(range(51, 67)) + [83] + list(range(67, 76))
    assert len(set(played)) == len(played)


def test_the_two_songs_are_the_ones_the_scenes_start(directory):
    scenes = I.intro(directory.exe)["scenes"]
    assert scenes[3]["song"] == 10
    assert [b["song"] for b in scenes[4]["beats"] if "song" in b] == [11]


def test_scene_five_is_nine_beats_of_cycles_heads_and_one_sound(directory):
    beats = I.intro(directory.exe)["scenes"][4]["beats"]
    assert len(beats) == 9
    assert [b.get("picture") for b in beats if "picture" in b] == [40, 45, 50, 73]
    assert sum(1 for b in beats if "head" in b) == 3


def test_scene_five_opens_on_the_panel_that_names_zamora(directory):
    caption = I.intro(directory.exe)["scenes"][4]["caption"]
    assert caption == ["YOU SPEAK WITH ZAMORA AT HIS HOME", "NEAR THE ATHANEUM..."]
