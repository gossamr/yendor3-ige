"""The game's songs and sound effects, and everything that raises one.

Three sections of `WORLD.DAT` hold the audio and four index tables in
`REGISTER.EXE` address it ([audio.md](../docs/audio.md)). Section 13 is
Creative's CT-VOICE driver, section 14 is 24 CMF songs for the Sound Blaster's
FM chip, and section 15 is 141 VOC effects and spoken lines. Section 3 says
which song a map slot plays.

A song slice and a sound slice are each a whole file: the CMF carries its own
`CTMF` header and the VOC its own `Creative Voice File` header, so neither
needs a wrapper built round it.

What raises a sound is ten record fields, the ambient table, the dawn windows
and a literal at the call site. The tables here cover the first three; the
literals are named in `docs/audio.md`.

    python tools/audio.py                   # both banks, summarized
    python tools/audio.py --songs           # every song's header
    python tools/audio.py --sounds          # every sound's rate and length
    python tools/audio.py --ambient         # the eight areas, day and night
    python tools/audio.py --dump DIR        # .cmf, .voc and CT-VOICE.DRV
"""

from __future__ import annotations

import argparse
import struct

import sections as S

# DS:0 is image 0x1DDB0, which is file offset 0x21DB0, so a `DS:` offset and a
# file offset below name the same bytes once this is added.
DGROUP = 0x21DB0

# The four index tables, at their own file offsets. Both indices are 1-based:
# image 0x17C4B and image 0x17F0F each `dec bx` before scaling, so index 0 is
# silence and reaches neither table.
SONG_OFFSETS = 0x2CFC7          # DS:0xB217, uint32 into WORLD.DAT
SONG_LENGTHS = 0x2D027          # DS:0xB277, uint16
SOUND_OFFSETS = 0x2D057         # DS:0xB2A7, uint32
SOUND_LENGTHS = 0x2D28B         # DS:0xB4DB, uint16
SONG_COUNT = 24                 # written to DS:0x5460 at image 0x0F124
SOUND_COUNT = 141               # written to DS:0x5462 at image 0x0F12A

# Section 13, loaded whole by image 0x17CF8, which hard-codes the length.
DRIVER = 13
DRIVER_BYTES = 0x9BD
DRIVER_MAGIC = b"CT-VOICE\0"
DRIVER_MAGIC_AT = 3

SONGS = 14
SOUNDS = 15

# Section 3: one uint16 per map slot, a 1-based song number with 0 for
# silence. Image 0x1534A reads it, resolving the slot from the party's world
# position as `(y / 24) * 20 + (x / 40)`.
MAP_SONGS = 3
MAP_SLOTS = 140
SLOTS_PER_AREA = 20
BANDS_PER_AREA = 24
CELLS_PER_LEVEL = 40

# The songs a screen plays over whatever the map is playing. Image 0x1858F
# takes the override at DS:0x5430 where it is non-zero, and these are the two
# values written to it: 1 at image 0x0BEC8 and image 0x18467, 13 at image
# 0x019DC. Image 0x0BF5D and three others put it back to 0.
MENU_SONG = 1
RESTORATION_SONG = 13
# Songs a call site plays directly rather than through the override.
TITLE_SONG = 8                  # image 0x10DCF
OPENING_SONG = 24               # image 0x0531F
ENDING_SONGS = (9, 10, 11)      # images 0x1C2E3, 0x1BDBB, 0x1C0A9

# A song that ends is followed by this many timer ticks of silence and then
# the same choice again, which is what makes one repeat: the handler at image
# 0x0E950 counts DS:0x5408 down and sets the play bit at zero. CMF carries no
# loop of its own and the game asks SBFMDRV for none.
SONG_RETRY_TICKS = 20
TICKS_PER_SECOND = 1193182 / 65536      # the PC timer, 18.2 a second

# CMF, Creative's Music File: a header, a bank of OPL2 instruments and a
# MIDI-like event stream. The three fields the game reads are marked.
CMF_MAGIC = b"CTMF"
CMF_FIELDS = {
    "version": 0x04,
    "instrument_block": 0x06,   # read at image 0x1851B
    "music_block": 0x08,        # read at image 0x18547
    "ticks_per_quarter": 0x0A,
    "ticks_per_second": 0x0C,   # read at image 0x1852E
    "title": 0x0E,
    "composer": 0x10,
    "remarks": 0x12,
    "instrument_count": 0x24,   # read at image 0x1851F
    "tempo": 0x26,
}
CMF_CHANNELS_IN_USE = 0x14      # 16 bytes, one per MIDI channel
CMF_MIDI_CHANNELS = 16
CMF_INSTRUMENT = 16             # the SBI layout, of which the last five are 0
# Image 0x1853E hands SBFMDRV the timer divisor rather than the rate, and the
# divisor is the PIT's own input over the header's ticks per second.
PIT_HZ = 1193180

# The OPL2 has nine melodic voices. 23 of the 24 songs use nine MIDI channels
# or fewer; song 22 uses ten and never sounds more than nine at once, so a
# free-voice pool plays it.
OPL_VOICES = 9
# Controller 0x67 is CMF's rhythm-mode switch, and all 24 songs set it to 0.
CMF_RHYTHM_CONTROLLER = 0x67
CMF_VOLUME_CONTROLLER = 0x07

# VOC, Creative Voice File. Every one of the 141 is a single uncompressed
# type-1 block: no loops, no silence blocks, no stereo, no compression.
VOC_MAGIC = b"Creative Voice File\x1a"
VOC_FIRST_BLOCK = 0x14          # read at image 0x186A9; 26 on all 141
VOC_VERSION = 0x16
VOC_BLOCK_TYPE = 0x1A
VOC_BLOCK_LENGTH = 0x1B         # 24-bit little-endian, the data bytes plus 2
VOC_RATE_BYTE = 0x1E
VOC_COMPRESSION = 0x1F
VOC_SAMPLES = 0x20
VOC_DATA_BLOCK = 1
VOC_TERMINATOR = 0
# Creative's own time constant, integer division.
VOC_RATE_NUMERATOR = 1000000
VOC_RATE_BASE = 256

# The ambient loop, image 0x008B4. Image 0x009C8 takes the area word at
# DS:0xCF33, which a door destination and a teleport pad both carry at their
# own +0x0C, and reads that area's pointer out of the table at DS:0xEADB. The
# pointer names a day half of 22 bytes followed by a night half of 22.
AMBIENT_POINTERS = 0xEADB
AMBIENT_AREAS = 8
AMBIENT_HALF = 0x16
AMBIENT_SLOTS = 10
AMBIENT_END = 0xFFFF            # the word after the eighth pointer
# The night half is taken where the clock is outside this window, which is
# not the music's: image 0x1858F opens its day at 420.
AMBIENT_DAY = (360, 1140)
MUSIC_DAY = (420, 1140)

# Sound 46 is the dawn, and it is the one sound the clock fires by itself.
# Image 0x008DC tests four five-minute windows, each with a bit of DS:0xCF35
# that stops it repeating; the four clear when the clock passes midnight.
DAWN_SOUND = 46
DAWN_WINDOWS = ((360, 0x8000), (390, 0x4000), (420, 0x2000), (450, 0x1000))
DAWN_MINUTES = 5
# Image 0x008D1 skips all four where DS:0xCEF9 carries any of bits 13 to 15,
# one of which is the indoor flag, so the dawn is an outdoor sound.
DAWN_INDOORS = 0xE000

# Sounds the code names as a literal at its own call site rather than reading
# off a record. Each is read at the branch that plays it.
#
#   melee_miss  image 0x00E78 tests the damage the resolver at 0x1586F wrote.
#               Zero plays 35; anything else reads the hand weapon's own +0xA.
#   container   images 0x0294D and 0x02986, both behind the kind bit image
#               0x027AD reads, so only the barrel, chest and dresser are heard.
#   volley_fires  image 0x0C26C, once, after the four shot pictures are drawn
#               and before the shot steps its first band, with image 0x0C264
#               cutting whatever is playing short in front of it. A bow names
#               no sound of its own and there is no second picker: the four
#               missile item ids the picture picker at image 0x1B562 compares
#               against appear exactly once each in the image, the weapon
#               properties entry's +0xA is 0 on all 35 missile weapons, and the
#               volley never touches the projectile record. A monster's shot is
#               the one that varies, off enemy record 48.
#   shot_stopped  image 0x0C310, where the probe at image 0x02F93 answered 1 or
#               2 for the band the shot reached. 1 is a terrain of 2 to 99 or
#               200 to 299 and 2 is any object; 4 is a monster and goes to the
#               shots instead. Answer 3, which the view entry's own +6 bit
#               0x800 raises, and a shot that runs out of bands at image
#               0x0C2F4 are both silent.
#   shot_lands / shot_misses  image 0x0C35F, once per shooter resolved: 34
#               where DS:0x536E bit 0x200 stands and 35 where it does not.
#               Image 0x0C6BA raises that bit as the damage comes off the
#               monster's health and image 0x0C6F6 clears it before each shot.
#               The volley's own routine plays 10 and 76 as well, on the two
#               paths that throw an item rather than shoot: image 0x0C4A4 picks
#               between them on the item id in DS:0x5426, 76 for the FLAMING
#               OIL FLASK at DS:0x5464 and for the -1 at DS:0x544E, 10 for the
#               rest.
#   monster_dies  image 0x12CEF, inside the routine at image 0x12CA6 that frees
#               a dead monster's slot.
#   repair_mends / repair_destroys  the three-way at image 0x1C48B: a roll
#               under the first threshold destroys the piece and plays 8, at or
#               under the second mends it and plays 7, over it fails silently.
#   sheet_opens image 0x0CBB6 and six more, each followed by the panel routine
#               at image 0x1334C, which is what puts a screen up.
#   shop_deals  image 0x16863 and four more, the same pattern inside the
#               conversation and creation screens.
#   light_out   image 0x1A4D0 plays it on the next redraw where DS:0x5370 bit
#               0x40 stands, and image 0x0EBB9 raises that bit in the timer
#               handler as a countdown reaches its end, clearing it again as it
#               sounds. So it is a timed thing running out: a cast light or a
#               torch. Image 0x0FDE3 plays it on the same path.
#   character_picked  images 0x04B32 and 0x04C66, each beside a write of
#               DS:0x53D4, the handle slot every service on a body reads, the
#               second going on to redraw the four portraits at image 0x16C78.
#   party_falls image 0x1B4CD, in the routine image 0x15AC1 calls. Image
#               0x15A92 walks the four handle slots at DS:0xD0C9 and leaves the
#               moment it finds a character whose condition word does not carry
#               one of the bits 0x1C40, so it reaches the sound only where
#               every one of the four is held. The routine stops the song,
#               plays it, clears the combat words and zeroes 56 words, and
#               waits for it to finish before redrawing.
#   doorway     images 0x03451 and 0x034A9, the two arms of the move routine at
#               image 0x03447, which image 0x03276 calls only where the cell
#               being stepped onto carries a terrain between DS:0x5452 and
#               DS:0x5450, written as 200 and 299 at images 0x0F106 and
#               0x0F100. That is the doorway range (docs/map.md), so it is
#               walking through a doorway rather than every step.
#   mark / returns  MARK OR RETURN is the one spell carrying record 72 bit
#               0x20. Image 0x0CCEB reads the caster's own record at the offset
#               the spell's offset 64 names, which is 240, the mark slot, and
#               image 0x0CCFB raises panel 40 through the prompt dispatcher at
#               image 0x058F0, whose record at DS:0xE6B5 reads DO YOU WANT TO.
#               Answer 4 sets DS:0x536A bit 0x80 and plays 87, answer 6 leaves
#               it clear and plays 44, and image 0x1CA48 reads that bit to pick
#               between the two: set writes the party's place into the slot,
#               which is the mark, and clear reads it back, which is the return.
#   step_refused  image 0x032D5, twenty bytes before the step at image
#               0x032E9. The two classifiers write their answer into DS:0x53E0
#               and the step runs only on a pair of zeros; 2 is a terrain of 0
#               or 1, the edge of the map, and goes quiet, and everything else
#               is a wall or a blocking object and sounds (docs/map.md).
#   character_panel  images 0x03A98, 0x03F12 and four more, one per character.
#               Each takes its own key, reads that character's handle slot from
#               DS:0xD0C9 up, sets their bit in DS:0x536C, calls the panel
#               routine at image 0x1334C and then sounds. So it is the
#               character's own panel going up, which is the same item panel a
#               buy, a sell, a repair or an enhancement opens (docs/shops.md).
NAMED_SOUNDS = {
    "melee_miss": 35,
    "container": 14,
    "volley_fires": 6,
    "shot_stopped": 13,
    "shot_lands": 34,
    "shot_misses": 35,
    "monster_dies": 7,
    "repair_mends": 7,
    "repair_destroys": 8,
    "sheet_opens": 1,
    "shop_deals": 9,
    "light_out": 40,
    "character_panel": 15,
    "character_picked": 2,
    "step_refused": 13,
    "doorway": 5,
    "party_falls": 50,
    "mark": 87,
    "returns": 44,
}

# What each of the six world scripts sounds as it moves the party, read off the
# stretch of code that writes its own ambient area into DS:0xCF33. Script 3
# writes its area and plays nothing.
SCRIPT_SOUNDS = {1: 33, 2: 84, 3: 0, 4: 44, 5: 44, 6: 44}

# The terrain a doorway carries, which is what gates the sound above. Written
# at images 0x0F106 and 0x0F100 (docs/map.md).
DOORWAY_TERRAIN = (200, 299)

# The ENHANCED LENS, which image 0x0B6AC sounds before writing area 3.
LENS_SOUND = 43

# The one sound the game insists on: image 0x18648 hands index 3 to the PC
# speaker where sound is off, an 1,800 Hz tone gated for 4 timer ticks.
REFUSAL_SOUND = 3
REFUSAL_HZ = 1800
REFUSAL_TICKS = 4
# The click each of the two runtime toggles plays as it is pressed, at images
# 0x0E6B8 and 0x0E728.
TOGGLE_SOUND = 4
# What a wrapper waits where sound is off, so a fight keeps its pacing either
# way: images 0x0C6D8 and 0x1D91F.
SILENT_WAIT_TICKS = 6

# DS:0xCF63, the one word that says what is available and what is on. Bit 1
# gates every music entry and bit 3 every sound entry; each toggle turns its
# bit off unconditionally and back on only where the driver bit is set.
AUDIO_WORD = {"fm_driver": 0, "music_on": 1, "ct_voice": 2, "sound_on": 3,
              "no_fm_driver": 6, "ct_voice_refused": 7}

# The ten record fields that hold a sound index, by where each lives. The
# address beside each is the instruction that loads it.
RECORD_SOUNDS = {
    "monster_hit": ("enemy record", 42, "0x01053"),
    "monster_miss": ("enemy record", 44, "0x0109E"),
    "monster_shot": ("enemy record", 48, "0x123AA"),
    "attack": ("attack table entry", 0, "0x0095F"),
    "door": ("door destination", 0x06, "0x0553B"),
    "pad": ("teleport pad", 0x0E, "0x0AC0D"),
    "spell_cast": ("spell record", 34, "0x1CCF5"),
    "spell_land": ("spell record", 32, "0x1CD8C"),
    "spell_miss": ("spell record", 40, "0x1D0DE"),
    "weapon": ("weapon properties entry", 0x0A, "0x00EB5"),
}

# The weapon properties table: section 9, 12 bytes an entry, the sound at
# +0xA. tools/items.py reads the same table through the item record's own
# pointer; this is the whole table, since a blow reads the entry rather than
# the item.
WEAPON_TABLE = 9
WEAPON_ENTRY = 12
WEAPON_SOUND = 0x0A

# The sound a cast plays, on every one of the 107 records. The 19 restoratives
# are the records whose word 72 carries either of these bits (docs/spells.md),
# and all 19 hold 18 at offset 32.
SPELL_SOUND = 32
SPELL_AFFECTS = 72
SPELL_RESTORATIVE = 0xC000


def _u16(blob: bytes, at: int) -> int:
    return struct.unpack_from("<H", blob, at)[0]


class Bank:
    """The four index tables, and the slices they name.

    Both banks are 1-based, as the game's own indices are. Index 0 is silence
    and answers None.
    """

    def __init__(self, d: S.Directory):
        self.d = d
        self.world = d.world
        self.song_offsets = list(struct.unpack_from(
            f"<{SONG_COUNT}I", d.exe, SONG_OFFSETS))
        self.song_lengths = list(struct.unpack_from(
            f"<{SONG_COUNT}H", d.exe, SONG_LENGTHS))
        self.sound_offsets = list(struct.unpack_from(
            f"<{SOUND_COUNT}I", d.exe, SOUND_OFFSETS))
        self.sound_lengths = list(struct.unpack_from(
            f"<{SOUND_COUNT}H", d.exe, SOUND_LENGTHS))
        self.verify()

    def verify(self) -> None:
        """The three checks docs/audio.md asks the extraction to assert."""
        for n, at in enumerate(self.song_offsets, start=1):
            assert self.world[at:at + len(CMF_MAGIC)] == CMF_MAGIC, \
                f"song {n} at {at:#x} does not open CTMF"
        for n, at in enumerate(self.sound_offsets, start=1):
            assert self.world[at:at + len(VOC_MAGIC)] == VOC_MAGIC, \
                f"sound {n} at {at:#x} does not open a VOC header"
        songs, sounds = self.d[SONGS], self.d[SOUNDS]
        assert self.song_offsets[0] == songs.offset
        assert self.sound_offsets[0] == sounds.offset
        for table, lengths, end in ((self.song_offsets, self.song_lengths, songs.end),
                                    (self.sound_offsets, self.sound_lengths, sounds.end)):
            reach = [at + size for at, size in zip(table, lengths)]
            assert reach[:-1] == table[1:], "a slice does not reach the next"
            assert reach[-1] == end, f"the last slice ends at {reach[-1]:#x}, not {end:#x}"

    def song(self, n: int) -> bytes | None:
        """Song `n`, 1-based, as a whole `.CMF` file."""
        if not 1 <= n <= SONG_COUNT:
            return None
        at = self.song_offsets[n - 1]
        return self.world[at:at + self.song_lengths[n - 1]]

    def sound(self, n: int) -> bytes | None:
        """Sound `n`, 1-based, as a whole `.VOC` file."""
        if not 1 <= n <= SOUND_COUNT:
            return None
        at = self.sound_offsets[n - 1]
        return self.world[at:at + self.sound_lengths[n - 1]]

    def driver(self) -> bytes:
        """Section 13, Creative's `CT-VOICE.DRV`, as image 0x17CF8 loads it."""
        at = self.d[DRIVER].offset
        blob = self.world[at:at + DRIVER_BYTES]
        assert blob[DRIVER_MAGIC_AT:DRIVER_MAGIC_AT + len(DRIVER_MAGIC)] == DRIVER_MAGIC
        return blob


def cmf_header(blob: bytes) -> dict:
    """A song's header, by the name `docs/audio.md` gives each field."""
    assert blob[:4] == CMF_MAGIC
    head = {name: _u16(blob, at) for name, at in CMF_FIELDS.items()}
    head["channels_in_use"] = list(
        blob[CMF_CHANNELS_IN_USE:CMF_CHANNELS_IN_USE + CMF_MIDI_CHANNELS])
    head["divisor"] = PIT_HZ // head["ticks_per_second"]
    return head


def cmf_instruments(blob: bytes) -> list[bytes]:
    """The bank of sixteen-byte instruments the song's own header names."""
    head = cmf_header(blob)
    at = head["instrument_block"]
    return [blob[at + i * CMF_INSTRUMENT:at + (i + 1) * CMF_INSTRUMENT]
            for i in range(head["instrument_count"])]


def cmf_events(blob: bytes) -> bytes:
    """The event stream, from the music block to the end of the file."""
    return blob[cmf_header(blob)["music_block"]:]


# The event stream is MIDI with running status. All 24 songs close on an
# `FF 2F` end-of-track meta event landing on the file's own last byte, and no
# other meta type appears.
MIDI_NOTE_OFF = 0x80
MIDI_NOTE_ON = 0x90
MIDI_CONTROLLER = 0xB0
MIDI_PROGRAM = 0xC0
MIDI_PITCH_BEND = 0xE0
MIDI_META = 0xFF
MIDI_SYSEX = 0xF0
MIDI_END_OF_TRACK = 0x2F
# The two status bytes that carry one data byte rather than two.
MIDI_ONE_BYTE = (MIDI_PROGRAM, 0xD0)


def _varlen(blob: bytes, at: int) -> tuple[int, int]:
    value = 0
    while True:
        byte = blob[at]
        at += 1
        value = (value << 7) | (byte & 0x7F)
        if not byte & 0x80:
            return value, at


def cmf_track(blob: bytes) -> list[dict]:
    """The event stream as a list, each event with the tick it falls on.

    A note, a controller and a program change come out under their own names;
    everything else comes out raw. The parse asserts that the stream closes on
    its end-of-track and that nothing follows it, which is what says the whole
    file has been read.
    """
    events = cmf_events(blob)
    at, tick, status, out = 0, 0, 0, []
    while at < len(events):
        delta, at = _varlen(events, at)
        tick += delta
        if events[at] & 0x80:
            status = events[at]
            at += 1
        kind, channel = status & 0xF0, status & 0x0F
        if status == MIDI_META:
            meta, at = events[at], at + 1
            length, at = _varlen(events, at)
            at += length
            assert meta == MIDI_END_OF_TRACK, f"meta {meta:#x}, not end of track"
            assert at == len(events), f"{len(events) - at} bytes past end of track"
            out.append({"tick": tick, "kind": "end"})
            break
        if kind == MIDI_SYSEX:
            length, at = _varlen(events, at)
            at += length
            continue
        first, at = events[at], at + 1
        if kind in MIDI_ONE_BYTE:
            out.append({"tick": tick, "kind": "program", "channel": channel,
                        "instrument": first})
            continue
        second, at = events[at], at + 1
        if kind == MIDI_NOTE_ON and second:
            out.append({"tick": tick, "kind": "on", "channel": channel,
                        "note": first, "velocity": second})
        elif kind in (MIDI_NOTE_OFF, MIDI_NOTE_ON):
            out.append({"tick": tick, "kind": "off", "channel": channel,
                        "note": first})
        elif kind == MIDI_CONTROLLER:
            out.append({"tick": tick, "kind": "control", "channel": channel,
                        "controller": first, "value": second})
        elif kind != MIDI_PITCH_BEND:
            out.append({"tick": tick, "kind": "other", "status": status})
    return out


def cmf_seconds(blob: bytes) -> float:
    """How long a song runs, its last tick over its own ticks a second."""
    track = cmf_track(blob)
    return track[-1]["tick"] / cmf_header(blob)["ticks_per_second"]


def voc_block(blob: bytes) -> dict:
    """The one type-1 block a sound is: its rate, and where its samples are.

    The rate is Creative's own time constant, `1000000 / (256 - byte)` under
    integer division. Samples are unsigned 8-bit mono.
    """
    assert blob[:len(VOC_MAGIC)] == VOC_MAGIC
    first = _u16(blob, VOC_FIRST_BLOCK)
    assert blob[first] == VOC_DATA_BLOCK, f"block type {blob[first]}, not sound data"
    length = blob[first + 1] | blob[first + 2] << 8 | blob[first + 3] << 16
    at = first + 6
    count = length - 2
    assert blob[at - 1] == 0, "compressed, which none of the 141 are"
    assert blob[at + count] == VOC_TERMINATOR, "no terminator block"
    return {"rate": VOC_RATE_NUMERATOR // (VOC_RATE_BASE - blob[at - 2]),
            "at": at, "samples": count,
            "version": _u16(blob, VOC_VERSION)}


def voc_samples(blob: bytes) -> bytes:
    """The unsigned 8-bit mono samples, with the header and terminator off."""
    block = voc_block(blob)
    return blob[block["at"]:block["at"] + block["samples"]]


def map_songs(d: S.Directory) -> list[int]:
    """Section 3: the 1-based song each of the 140 map slots plays, 0 silent."""
    section = d[MAP_SONGS]
    assert section.size == MAP_SLOTS * 2, f"section 3 is {section.size} bytes"
    return list(struct.unpack_from(f"<{MAP_SLOTS}H", d.world, section.offset))


def slot_of(x: int, y: int) -> int:
    """The map slot a world position falls in, as image 0x1534A resolves it."""
    return (y // BANDS_PER_AREA) * SLOTS_PER_AREA + (x // CELLS_PER_LEVEL)


def ambient(exe: bytes) -> list[dict]:
    """The eight areas' lists, each a day half and a night half.

    A half is a delay in timer ticks and then ten slots, and the player steps
    the cursor one slot per firing, spending a zero slot in silence.
    """
    at = DGROUP + AMBIENT_POINTERS
    pointers = struct.unpack_from(f"<{AMBIENT_AREAS + 1}H", exe, at)
    assert pointers[AMBIENT_AREAS] == AMBIENT_END, "the pointer table does not end"
    out = []
    for area, pointer in enumerate(pointers[:AMBIENT_AREAS], start=1):
        halves = {}
        for name, half in (("day", 0), ("night", 1)):
            base = DGROUP + pointer + AMBIENT_HALF * half
            words = struct.unpack_from(f"<{AMBIENT_SLOTS + 1}H", exe, base)
            halves[name] = {"delay": words[0], "slots": list(words[1:])}
        out.append({"area": area, **halves})
    return out


def weapon_sounds(d: S.Directory) -> list[int]:
    """The sound each of the 210 weapon properties entries lands with."""
    section = d[WEAPON_TABLE]
    assert section.size % WEAPON_ENTRY == 0
    return [_u16(d.world, section.offset + e * WEAPON_ENTRY + WEAPON_SOUND)
            for e in range(section.size // WEAPON_ENTRY)]


# Which sound a spell plays is the cast dispatcher's business rather than a
# field of the record, so [spell_sounds.py](spell_sounds.py) reads it: the
# branch decides, and on a restorative offset 32 names an attack table entry
# whose own sound plays beside the animation drawn over the portrait.

def seconds(bank: Bank, n: int) -> float:
    """How long sound `n` runs, its sample count over its own rate."""
    block = voc_block(bank.sound(n))
    return block["samples"] / block["rate"]


def _summary(bank: Bank, d: S.Directory) -> None:
    songs = [cmf_header(bank.song(n)) for n in range(1, SONG_COUNT + 1)]
    blocks = [voc_block(bank.sound(n)) for n in range(1, SOUND_COUNT + 1)]
    ticks = sum(1 for h in songs if h["ticks_per_second"] == songs[0]["ticks_per_second"])
    print(f"{SONG_COUNT} songs, {d[SONGS].size:,} bytes; "
          f"{sum(h['instrument_count'] for h in songs)} instruments; "
          f"{ticks} of {SONG_COUNT} at {songs[0]['ticks_per_second']} ticks a second")
    print(f"{SOUND_COUNT} sounds, {d[SOUNDS].size:,} bytes, "
          f"{sum(b['samples'] / b['rate'] for b in blocks):.0f} seconds; "
          f"{len(set(b['rate'] for b in blocks))} distinct rates, "
          f"{min(b['rate'] for b in blocks):,} to {max(b['rate'] for b in blocks):,} Hz")
    print(f"driver {len(bank.driver()):,} bytes")
    slots = map_songs(d)
    print(f"{sum(1 for s in slots if s)} of {MAP_SLOTS} map slots carry a song, "
          f"{len(set(s for s in slots if s))} songs between them")
    weapons = weapon_sounds(d)
    print(f"{len(weapons)} weapon entries, {len(set(weapons))} sounds between them")


def _songs(bank: Bank) -> None:
    print(f"{'#':>3} {'offset':>9} {'bytes':>7} {'instr':>5} {'chan':>4} "
          f"{'ticks/s':>7} {'seconds':>7}")
    for n in range(1, SONG_COUNT + 1):
        blob = bank.song(n)
        head = cmf_header(blob)
        used = sum(1 for c in head["channels_in_use"] if c)
        print(f"{n:3d} {bank.song_offsets[n - 1]:#09x} {len(blob):7,} "
              f"{head['instrument_count']:5d} {used:4d} {head['ticks_per_second']:7d} "
              f"{cmf_seconds(blob):7.1f}")


def _sounds(bank: Bank) -> None:
    print(f"{'#':>4} {'offset':>9} {'bytes':>7} {'rate':>7} {'seconds':>7}")
    for n in range(1, SOUND_COUNT + 1):
        block = voc_block(bank.sound(n))
        print(f"{n:4d} {bank.sound_offsets[n - 1]:#09x} "
              f"{bank.sound_lengths[n - 1]:7,} {block['rate']:7,} "
              f"{block['samples'] / block['rate']:7.2f}")


def _ambient(exe: bytes) -> None:
    for area in ambient(exe):
        for half in ("day", "night"):
            one = area[half]
            print(f"area {area['area']} {half:5s} delay {one['delay']:4d}  "
                  f"{' '.join(f'{s:3d}' for s in one['slots'])}")


def _dump(bank: Bank, where: str) -> None:
    from pathlib import Path

    out = Path(where)
    (out / "songs").mkdir(parents=True, exist_ok=True)
    (out / "sounds").mkdir(parents=True, exist_ok=True)
    for n in range(1, SONG_COUNT + 1):
        (out / "songs" / f"{n:02d}.cmf").write_bytes(bank.song(n))
    for n in range(1, SOUND_COUNT + 1):
        (out / "sounds" / f"{n:03d}.voc").write_bytes(bank.sound(n))
    (out / "CT-VOICE.DRV").write_bytes(bank.driver())
    print(f"{SONG_COUNT} songs, {SOUND_COUNT} sounds and the driver under {out}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("game", nargs="?", default="game")
    p.add_argument("--songs", action="store_true")
    p.add_argument("--sounds", action="store_true")
    p.add_argument("--ambient", action="store_true")
    p.add_argument("--dump", metavar="DIR")
    args = p.parse_args()

    d = S.load(args.game)
    bank = Bank(d)
    if args.songs:
        _songs(bank)
    if args.sounds:
        _sounds(bank)
    if args.ambient:
        _ambient(d.exe)
    if args.dump:
        _dump(bank, args.dump)
    if not (args.songs or args.sounds or args.ambient or args.dump):
        _summary(bank, d)


if __name__ == "__main__":
    main()
