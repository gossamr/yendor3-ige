# Music and sound

The game's audio is three sections of `WORLD.DAT`, a fourth section that says which song a map plays, and four index tables in `REGISTER.EXE`. Section 13 is Creative's CT-VOICE driver, section 14 is 24 CMF songs for the Sound Blaster's FM chip, and section 15 is 141 VOC sound effects and spoken lines. This document records settled findings only. [world-dat.md](world-dat.md) indexes the sections.

The evidence is **code** and **shape**, in the classifiers [README.md](README.md) defines. Every address given is an instruction that reads the field, and every layout divides its section exactly and fills it with nothing left over. No claim below rests on hearing a sound.

## The four index tables

All four sit in `REGISTER.EXE`'s data segment. `DS:0` is image `0x1DDB0`, which is file offset `0x21DB0`, so the file offset and the `DS:` offset in the table below name the same bytes.

| Table | File offset | `DS:` | Entries | Entry | Read by |
|---|---|---|---|---|---|
| song offsets | `0x2CFC7` | `0xB217` | 24 | uint32, byte offset into `WORLD.DAT` | `0x17C5A` |
| song lengths | `0x2D027` | `0xB277` | 24 | uint16, bytes | `0x17C6A`, `0x1877B` |
| sound offsets | `0x2D057` | `0xB2A7` | 141 | uint32, byte offset into `WORLD.DAT` | `0x17F1E` |
| sound lengths | `0x2D28B` | `0xB4DB` | 141 | uint16, bytes | `0x17F2E`, `0x1882F` |

The four run end to end and begin where the master directory ends: 36 dwords from `0x2CF37` reach `0x2CFC7`, the song offsets reach `0x2D027`, the song lengths `0x2D057`, the sound offsets `0x2D28B` and the sound lengths `0x2D3A5`.

**Both indices are 1-based.** Image `0x17C4B` builds a song's read request and image `0x17F0F` a sound's; each does `dec bx`, then `shl bx, 1` for the length table and a second `shl bx, 1` for the offset table. Index 0 means silence and never reaches either table ([Playing a song](#playing-a-song), [Playing a sound](#playing-a-sound)).

**The counts are in the executable too.** Image `0x0F124` writes 24 into `DS:0x5460` and image `0x0F12A` writes 141 into `DS:0x5462`. Those are the loop counts the two buffer sizers walk, and they match the tables' own extents: the song offsets are the 24 `CTMF` magics in section 14, and the sound offsets are the 141 `Creative Voice File\x1a` magics in section 15, in both cases with no magic left over and none missed.

**The lengths agree with the offsets.** Every song's length is the distance to the next song's offset, and song 24's length reaches exactly the start of section 15. Every sound's length is the distance to the next sound's offset, and sound 141's length ends exactly at section 15's end, `0x3C2030`.

## Section 13, the CT-VOICE driver

Section 13 is `0x00970DA`, 2,493 bytes, and it is Creative's `CT-VOICE.DRV`: the bytes open `E9 51 07` then `CT-VOICE\0Creative Sound Blaster Card`, and carry the 1989-1990 Creative Technology copyright string. The game loads it whole into a block of its own and enters it at offset 0.

Image `0x17CF8` builds that read request, and it is the only audio load that goes to the master directory rather than to an index table: it takes the offset from the dword at `DS:0xB1BB`, which is master entry 13, and hard-codes the length as `0x9BD`, which is 2,493.

## Section 14, the songs

24 CMF files, `0x0097A97` to `0x00BAEBA`, 144,419 bytes. CMF is Creative's Music File, a MIDI-like event stream plus a bank of OPL2 instrument definitions, which the resident `SBFMDRV.COM` plays on the Sound Blaster's FM chip.

Every one of the 24 has the same header shape. The fields the game reads are marked.

| Offset | Size | Field | Value across all 24 |
|---|---|---|---|
| `0x00` | 4 | magic | `CTMF` |
| `0x04` | 2 | version, minor then major | `01 01`, so 1.1 |
| `0x06` | 2 | instrument block offset, **read at `0x1851B`** | 40 |
| `0x08` | 2 | music block offset, **read at `0x18547`** | `40 + 16 x instruments` |
| `0x0A` | 2 | ticks per quarter note | 48 |
| `0x0C` | 2 | clock ticks per second, **read at `0x1852E`** | 96 |
| `0x0E` | 2 | title offset | 0 |
| `0x10` | 2 | composer offset | 0 |
| `0x12` | 2 | remarks offset | 0 |
| `0x14` | 16 | channel in use, one byte per MIDI channel | 0 or 1 |
| `0x24` | 2 | instrument count, **read at `0x1851F`** | 4 to 10 |
| `0x26` | 2 | basic tempo | 120 |

The instrument block is `16 x count` bytes at offset 40, and the event stream runs from the music block offset to the end of the file. No song names itself: the three string offsets are zero on all 24.

**The event stream is MIDI with running status**, and all 24 parse end to end: each one closes on an `FF 2F` end-of-track meta event landing on the file's own last byte, with no bytes before or after it. That is the whole of what the stream contains.

- **One meta event.** `FF 2F` appears 24 times, once per song, and no other meta type appears at all. No song changes tempo.
- **Two controllers.** `0x07`, channel volume, 886 times; `0x67`, CMF's rhythm-mode switch, 24 times and always with a value of 0. Every song is therefore melodic, with no percussion channels.
- **Timing is uniform.** All 24 carry 48 ticks per quarter note, 96 clock ticks per second and a basic tempo of 120, which agree with each other. A tick is 1/96 second on every song, and the whole bank runs 1,963 seconds.
- **Program changes are always in range**, and no song sets a program the instrument block does not hold.

**The instrument block is the SBI layout**, sixteen bytes of which the last five are zero on all 144 instruments in the bank: modulator and carrier characteristic, then scaling and output level, attack and decay, sustain and release, wave select, then one feedback and connection byte. **Both wave-select bytes are 0 on all 144**, so every voice in the game is a pure sine pair and the OPL2's other three waveforms go unused.

**Nine voices are enough.** 23 of the songs use MIDI channels 0 to 8 or fewer. Song 22 uses ten, channels 0 to 9, with 238 of its 4,935 note-ons on channel 9. Pairing its note-ons against its note-offs shows **never more than nine channels sounding at once**, so the tenth part is time-shared rather than a tenth voice, and a free-voice pool plays it on the OPL2's nine.

The 24, with the maps section 3 gives each one and the call site of each song section 3 never names:

| # | Offset | Bytes | Instruments | Channels | Where it plays |
|---|---|---|---|---|---|
| 1 | `0x0097a97` | 5,357 | 4 | 5 | main menu (`0x0BEC8`, `0x18467` set the override) |
| 2 | `0x0098f84` | 6,942 | 4 | 4 | ATHANEUM |
| 3 | `0x009aaa2` | 7,728 | 7 | 8 | YENDOR, KINGDOM OF YENDOR, CASTLE OF YENDOR |
| 4 | `0x009c8d2` | 5,636 | 4 | 8 | THAINE MAP 2, THAINE MAP 3, THAINE MAP 5, THAINE MAP 6, THAINE MAP 7, THAINE MAP 8, THAINE MAP 9, THAINE MAP 10 |
| 5 | `0x009ded6` | 8,738 | 6 | 6 | KINGDOM OF BARIAG, CASTLE OF BARIAG LEVEL 1, CASTLE OF BARIAG LEVEL 2 |
| 6 | `0x00a00f8` | 2,821 | 6 | 7 | COPPER MINE, PRISON, ACOKNIGHT'S CAVE LEVEL 1, IRON MINE, SILVER MINE, CAVE OF ICE, DUNGEON OF SLATOR LEVEL 1, UNDERGROUND TUNNEL |
| 7 | `0x00a0bfd` | 3,842 | 6 | 6 | SEWERS OF BARIAG, NUORE MINE, ACOKNIGHT'S CAVE LEVEL 2, ELFIN SEWER, DUNGEON OF SLATOR LEVEL 2, GOLD MINE |
| 8 | `0x00a1aff` | 1,246 | 7 | 7 | title splash (`0x10DCF`) |
| 9 | `0x00a1fdd` | 5,373 | 6 | 7 | ending (`0x1C2E3`) |
| 10 | `0x00a34da` | 2,648 | 5 | 5 | ending (`0x1BDBB`) |
| 11 | `0x00a3f32` | 1,188 | 4 | 4 | ending (`0x1C0A9`) |
| 12 | `0x00a43d6` | 7,347 | 9 | 9 | DELIA'S ISLAND, KEEP |
| 13 | `0x00a6089` | 5,156 | 8 | 8 | Restoration (`0x019DC` sets the override) |
| 14 | `0x00a74ad` | 10,918 | 6 | 7 | KINGDOM OF OBVERSIA, CASTLE OF OBVERSIA, TOWER OF OBVERSIA, LABYRINTH |
| 15 | `0x00a9f53` | 10,661 | 6 | 7 | DWARVEN HOMELAND MAP 1, DWARVEN HOMELAND MAP 2 |
| 16 | `0x00ac8f8` | 5,938 | 6 | 6 | DWARVEN HOMELAND MAP 3, CAVE OF FIRE, DWARVEN HOMELAND MAP 4 |
| 17 | `0x00ae02a` | 6,963 | 5 | 6 | THAINE MAP 4, THE HOLY ORDER, THE WAY OF THE ORDER |
| 18 | `0x00afb5d` | 1,104 | 5 | 5 | THE PLANE OF SOULS |
| 19 | `0x00affad` | 8,740 | 8 | 8 | ELFIN CITY, VISHAN'S STRONGHOLD LEVEL 1, VISHAN'S STRONGHOLD LEVEL 2 |
| 20 | `0x00b21d1` | 4,231 | 5 | 5 | KINGDOM OF SLATOR, CASTLE OF SLATOR LEVEL 1, CASTLE OF SLATOR LEVEL 2 |
| 21 | `0x00b3258` | 4,578 | 6 | 6 | KINGDOM OF EURON, CASTLE OF EURON |
| 22 | `0x00b443a` | 19,938 | 10 | 10 | THAINE MAP 1 |
| 23 | `0x00b921c` | 4,720 | 5 | 5 | QUARTZ CHAMBER |
| 24 | `0x00ba48c` | 2,606 | 6 | 6 | narrated opening (`0x0531F`) |

## Section 15, the sounds

141 VOC files, `0x00BAEBA` to `0x03C2030`, 3,174,774 bytes, which is 73% of `WORLD.DAT`. Every one has the same shape, and the header constants are identical across all 141.

| Offset | Size | Field | Value across all 141 |
|---|---|---|---|
| `0x00` | 20 | magic | `Creative Voice File\x1A` |
| `0x14` | 2 | offset of the first block, **read at `0x186A9`** | 26 |
| `0x16` | 2 | version | `0x010A`, so 1.10 |
| `0x18` | 2 | version complement | `0x1129` |
| `0x1A` | 1 | block type | 1, sound data |
| `0x1B` | 3 | block length, 24-bit little-endian | data bytes + 2 |
| `0x1E` | 1 | sample rate byte | 145 to 211 |
| `0x1F` | 1 | compression | 0, 8-bit PCM |
| `0x20` | n | samples, unsigned 8-bit mono | |
| | 1 | terminator block, type 0 | `0x00` |

So a file is one type-1 block and nothing else: no loops, no silence blocks, no marker blocks, no stereo, no compression. The sample count is the block length minus 2, and the file's total size is `26 + 4 + block length + 1`, which equals the length table's entry on all 141.

**The rate is `1000000 / (256 - rate byte)` Hz**, Creative's own time-constant formula, integer division. Fourteen distinct rate bytes appear. 179 (12,987 Hz) covers 87 of the files and 180 (10,000 Hz) another 18; the extremes are 145 (9,009 Hz) on one file and 211 (22,222 Hz) on eleven.

The bank runs 235 seconds in total, from 0.07 seconds on sound 17 to 3.94 on sound 57. Length does not sort by index: sounds 18 to 33 run 0.4 to 3.1 seconds, with sound 17 at 0.07 seconds in front of them and sound 34 at 0.28 behind. The long ones are of two kinds, and only the code separates them. The opening and the ending play consecutive runs of them over a still picture, and the ambient table below spends others one at a time on a timer.

## Section 3, the map's song

Section 3 is `0x0083DD0`, 280 bytes: **140 uint16, one per map slot, each a 1-based song number with 0 for silence.** The 54 slots the map registry names all carry a song, and the 86 it does not name all carry 0, with nothing left over either way ([map.md](map.md) covers the registry).

Image `0x1534A` reads it. The slot comes from the party's world position, `DS:0xCF75` for x and `DS:0xCF77` for y, since the 140 slots are one 800 by 168 grid of 40 by 24 cells:

    slot = (y / 24) * 20 + (x / 40)          integer division, image 0x1534A to 0x15365

The routine keeps the last slot it resolved in `DS:0x0F42` and returns at once where the slot has not changed. Otherwise it reads that slot's word and plays it. Its two callers are image `0x10050`, the tail of the map window build, and image `0x0D696`, so the song is re-picked whenever the window is rebuilt, which a door and a step both do. Image `0x0DE90` zeroes `DS:0x0F42` to force the next call through.

The read goes through the same request block as everything else, with the record size taken from `DS:0x5494`, which image `0x0F18A` sets to 2, and the base offset from the master directory's own entry 3 at `DS:0xB193`. So the word for slot n is at `0x0083DD0 + 2n`.

## Extracting the audio

Every offset below comes out of the two files, and nothing here needs the game run. `master` is the 36-dword directory at `exe[0x2CF37]` that [world-dat.md](world-dat.md) describes. [tools/audio.py](../tools/audio.py) reads all of it, and `python tools/audio.py --dump DIR` writes the 24 `.CMF`, the 141 `.VOC` and the driver out as files.

    exe   = REGISTER.EXE
    world = WORLD.DAT

    song_offsets  = 24  uint32 at exe[0x2CFC7]
    song_lengths  = 24  uint16 at exe[0x2D027]
    sound_offsets = 141 uint32 at exe[0x2D057]
    sound_lengths = 141 uint16 at exe[0x2D28B]

    song n  (1..24)  = world[song_offsets[n-1]  : + song_lengths[n-1]]    # a whole .CMF
    sound n (1..141) = world[sound_offsets[n-1] : + sound_lengths[n-1]]   # a whole .VOC

    driver = world[master[13] : + 0x9BD]                                  # CT-VOICE.DRV

    map_song[slot] = uint16 at world[master[3] + 2 * slot]                # slot 0..139, master[3] = 0x0083DD0

Two more sound indices live in the files rather than in the code, and an extractor that wants the whole trigger map needs both:

    weapon_sound[e] = uint16 at world[0x08E632 + 12*e + 0xA]               # e = 0..209, section 9
    ambient[a][half][k] = uint16 at exe[0x21DB0 + p + 0x16*half + 2 + 2*k] # a = 0..7, half = 0|1, k = 0..9
      where p  = uint16 at exe[0x21DB0 + 0xEADB + 2*a]
      and   the delay in ticks is the word at exe[0x21DB0 + p + 0x16*half]

A song slice and a sound slice are each a complete file: the CMF carries its own `CTMF` header and the VOC its own `Creative Voice File` header, so neither needs a wrapper built round it. To turn a sound into samples without a VOC reader, given its offset `o`:

    block_length = world[o+0x1B] | world[o+0x1C] << 8 | world[o+0x1D] << 16
    rate         = 1000000 // (256 - world[o+0x1E])
    samples      = world[o+0x20 : o+0x20 + block_length - 2]        # unsigned 8-bit mono

That holds on all 141 because every one is a single uncompressed type-1 block.

Three checks the extraction should assert, all of which hold on this copy: the 24 song slices each start with `CTMF`, the 141 sound slices each start with `Creative Voice File\x1A`, and the 141 slices are contiguous and end exactly at section 15's end.

## The two drivers

`SW.BAT` loads `SBFMDRV.COM` before the game when `BLASTER` is set in the environment, and unloads it with `/U` afterward ([running.md](running.md)). The game finds it, loads CT-VOICE itself, and talks to each through its own entry.

**Image `0x18620` is the whole setup**, called once from image `0x0EEB1`. It clears the low four bits of `DS:0xCF63`, parses `BLASTER`, and then calls the music half and the sound half unless the command line turned one off.

**Parsing `BLASTER`, image `0x18868`.** It asks DOS for the variable named by the string `BLASTER=` at `DS:0x0FB2` and copies the value to `DS:0x9926`. It then scans for `A` or `a` and reads the three characters after it as hex digits, `(d0 << 8) + (d1 << 4) + d2` with each digit taken as its character minus `'0'`, into `DS:0x53BE`. It scans again for `I` or `i` and reads one character into `DS:0x53BC`. Missing variable, missing `A` or missing `I` all set bits 14 and 15 of `DS:0xCF63` and abandon audio for the run. Only digits parse. A letter would give a wrong value, and no Sound Blaster base address carries one.

**Finding the FM driver, image `0x1871A`.** It walks interrupt vectors `0x80` to `0xBE`, 63 of them, counting in `DS:0x0FC7`. A vector whose handler begins `0xCF`, an `iret`, is skipped as unclaimed. Any other is accepted when the five bytes at offset `0x103` of its segment are `FMDRV`, which is the signature at file offset 3 of `SBFMDRV.COM`. The vector number then goes into `cs:[0x3B6]`, which **is the operand byte of the `int 0` at image `0x18865`**: the call gate is self-modifying, and image `0x18865` is every SBFMDRV call the game makes. Failing to find it clears bits 0 and 1 of `DS:0xCF63` and sets bit 6.

**Loading CT-VOICE, image `0x187B3`.** It allocates `0x9C` paragraphs, reads section 13 into it, and keeps the segment in both `DS:0xFA02` and the far pointer `DS:0xFA00`, whose offset stays 0. Every CT-VOICE call is `lcall [0xFA00]` with the function in `bx`.

The CT-VOICE calls the game makes:

| `bx` | Argument | What the game does with it |
|---|---|---|
| 1 | `ax` = base I/O address from `BLASTER` | `0x187ED` |
| 2 | `ax` = interrupt number from `BLASTER` | `0x187F7` |
| 3 | | `0x187FB`; a non-zero `ax` back means the card did not answer, which sets bit 15 of `DS:0xCF63` and clears bits 2 and 3 |
| 4 | `ax` = 1 | `0x18819` |
| 5 | `es:di` = `DS:0x0F2E` | `0x18828`, the status word the driver keeps non-zero while a sound plays |
| 6 | `es:di` = the VOC's first block | `0x186B1`, plays it |
| 8 | | `0x186E5` and `0x185D4`, cuts a sound short |
| 9 | | `0x185DE`, at teardown, before the block is freed |

And these SBFMDRV calls, all through image `0x18865`:

| `bx` | Argument | What the game does with it |
|---|---|---|
| 1 | `dx:ax` = `DS:0x0F2C` | `0x18769`, the status byte the driver keeps non-zero while a song plays |
| 2 | `dx:ax` = the song's instrument block, `cx` = its instrument count | `0x18527` |
| 3 | `ax` = `0xFFFF` | `0x18614`, at teardown |
| 4 | `ax` = `1193180 / clock ticks per second`, so 12,428 on every song | `0x1853E` |
| 6 | `dx:ax` = the song's music block | `0x1854E` |
| 7 | | `0x186F7`, stops the song |
| 8 | | `0x1876F` and `0x1860B` |

**Two buffers, each sized from the length tables.** Image `0x18778` walks all 24 song lengths for the largest, 19,938, shifts it right four times and adds 2 paragraphs, and allocates 1,248 paragraphs for the song buffer, whose segment goes to `DS:0x4404`. Image `0x1882C` does the same over the 141 sound lengths for the largest, 51,205, and allocates 3,202 paragraphs for the sound buffer, at `DS:0x53DE`. The music sizer compares signed and shifts with `sar`; the sound sizer compares unsigned and shifts with `shr`, which it has to, since 51,205 does not fit a signed word.

**A song or a sound is read straight into its buffer at offset 0.** The request block is `DS:0x96C2`: `+0` the file handle, `+2` the destination segment, `+4` the destination offset, `+6` the byte count, `+8` a record index, `+0xA` and `+0xC` a 32-bit base offset. Image `0x039ED` seeks to `+6 x +8 + the base` and image `0x03997` reads. For a song and a sound the count is the length-table entry, the index is 0 and the base is the offset-table entry, so the seek lands on the file itself.

## What turns audio off

`DS:0xCF63` is the one word that says what is available and what is on.

| Bit | Meaning | Set by | Cleared by |
|---|---|---|---|
| 0 | FM driver found | `0x187A8` | `0x1873A`, `0x18620` |
| 1 | music on | `0x187A8`, `0x0C034`, `0x0E6D4` | `0x1873A`, `0x18620`, `0x0C021`, `0x0E6CA` |
| 2 | CT-VOICE loaded | `0x18859` | `0x1880D`, `0x18620` |
| 3 | sound on | `0x18859`, `0x0C05C`, `0x0E70F` | `0x1880D`, `0x18620`, `0x0C049`, `0x0E705` |
| 6 | FM driver not found | `0x1873F` | `0x187AD` |
| 7 | CT-VOICE refused to start | | `0x1885E` |
| 14, 15 | no usable `BLASTER` | `0x1887D` | |

Bit 1 gates every music entry and bit 3 gates every sound entry. Each toggle turns its bit off unconditionally and back on only where the matching driver bit is set, so a machine with no card cannot switch either on.

**`/NOM` and `/NOS` skip the setup rather than the playing.** The command-line parser at image `0x01E56` sets bit 1 of `DS:0x536E` for `/NOM` and bit 0 for `/NOS` ([patching.md](patching.md)). Image `0x18631` tests bit 1 before calling the music half and bit 0 before the sound half, so with either switch the driver is never found, the buffer is never allocated and the `DS:0xCF63` bit stays clear.

**Two runtime toggles.** Image `0x0E6A8` toggles music and image `0x0E6F0` toggles sound, each drawing `OFF` or `ON` beside itself and playing sound 4 as its click. Turning music off stops the song at once; turning it on calls the map-song entry. Image `0x0C014` and image `0x0C041` are the same pair reached by key, on the screen whose loop is at image `0x0BF44`.

**With sound off, one effect survives on the PC speaker.** Image `0x18648` returns without playing when bit 3 is clear, except for index 3, which it hands to image `0x01528`: that loads PIT channel 2 with the divisor `1193182 / 1800`, an 1,800 Hz tone, gates the speaker on through port `0x61`, waits 4 timer ticks and gates it off again. Index 3 is the refusal beep, and it is the only sound the game insists on.

**Elsewhere, silence is spent as time.** Image `0x0A67C` waits `ax` timer ticks through `int 1Ah`, 18.2 to the second. The two sound wrappers call it rather than returning early: image `0x0C6D8` and image `0x1D91F` each wait 6 ticks where sound is off, so a fight keeps its pacing either way ([combat.md](combat.md)).

## Playing a song

**Image `0x184CC` plays the song in `ax`.** It returns at once where `DS:0xCF63` bit 1 is clear. It stores the number in `DS:0x0F40`, which is what is playing now, and returns where that number is 0. It then returns where `DS:0x0F2C` is non-zero, so **a song starts only when nothing is playing**: the call does not interrupt. Otherwise it reads the song into the buffer at `DS:0x4404` and hands SBFMDRV the instrument block, the timer divisor and the music block.

**Image `0x186EB` stops the song.** It calls SBFMDRV function 7, zeroes `DS:0x0F40`, arms the retry below and clears `DS:0x5370` bit 4.

**Image `0x18556` is the entry the main loop polls**, from image `0x150E3` on every pass of the input loop, and from image `0x0BB84`, image `0x0C039` on the music toggle, image `0x1B83E`, image `0x019E7` and image `0x1846A`. It does one of three things:

- Nothing, where music is off or `DS:0x0F2C` says a song is still playing.
- Play, where `DS:0x5370` bit 4 is set.
- Arm the retry otherwise: `DS:0x5408` takes 20 and `DS:0x540C` bit 9 goes up.

**The retry is what makes a song repeat.** The timer handler at image `0x0E950` decrements `DS:0x5408` once per tick while `DS:0x540C` bit 9 is set, and on reaching zero clears that bit and sets `DS:0x5370` bit 4. So a song that ends is followed by 20 ticks of silence, about 1.1 seconds, and then the same choice again. CMF carries no loop of its own and the game asks SBFMDRV for none.

**Which song, image `0x1858F`.** The override at `DS:0x5430` wins where it is non-zero. Otherwise the choice is the arrival pair, `DS:0xCF31` by default and `DS:0xCF2F` where the clock at `DS:0xCF7F` is between 420 and 1140 minutes, which is 07:00 to 19:00. A zero at that point plays nothing, and so does a clear `DS:0x536A` bit 13.

**The arrival pair is dead in the shipped data.** A door writes its destination record's `+0x08` into `DS:0xCF2F` and `+0x0A` into `DS:0xCF31` at image `0x0557B`, and a teleport pad writes its own `+0x10` and `+0x12` at image `0x0AC6C` ([map.md](map.md)). Both words are 0 on all 139 destination records and on all 19 pads, and seven further sites zero them. So no map has a day song and a night song, image `0x1858F` always falls through to the override, and image `0x0FE74`, which stops the music on arrival where what is playing matches either word, never fires.

**What actually plays on a map is section 3**, through image `0x1534A`, which calls image `0x184CC` directly rather than going through image `0x18556`. The override and the map song therefore coexist: the override holds a screen's own song, and stepping onto a new slot plays that slot's song over it.

The override is written 1 at image `0x0BEC8` and image `0x18467` for the main menu, 13 at image `0x019DC` for Restoration, and 0 at image `0x0BF5D`, `0x0C0EB`, `0x0C11C` and `0x0EF0A` on the way back out. Restoration is reached by F8, scan code `0x42`, at image `0x0BBC9`, and by image `0x006AE`.

Every one of the 24 songs is reachable: 17 are named by section 3 and the other 7 by the override or by a direct call.

## Playing a sound

**Image `0x18648` plays the sound in `ax`.** Where `DS:0xCF63` bit 3 is clear it plays nothing, except for index 3 on the PC speaker. Otherwise it reads the sound into the buffer at `DS:0x53DE` and calls CT-VOICE function 6 with `es:di` pointing at the file's own first block, `es:[0x14]` bytes in. It does not wait: the driver plays from the buffer under interrupt, and `DS:0x0F2E` stays non-zero until it finishes.

That has two consequences the callers handle by hand.

- **Image `0x184B4` waits for the current sound to end.** It spins on `DS:0x0F2E` and answers ZF set where sound is on, ZF clear where it is off. 21 sites call it, usually to hold a frame until the effect stops.
- **Image `0x186D8` cuts the current sound short**, through CT-VOICE function 8. Five sites call it, all of them about to start a different sound.

Three wrappers sit in front of image `0x18648`, and each has something to put in a sound's place where sound is off.

| Wrapper | Argument | Substitute |
|---|---|---|
| `0x0C6D8` | sound index in `ax`, ignored where 0 | 6 ticks |
| `0x1D91F` | sound index in `ax`, ignored where 0 | 6 ticks |
| `0x1C13C` | a 14-byte block in `si`, below | cycles the pictures for the block's own `+0xC` ticks |

Image `0x1C13C` is the ending's talking head. Its block is 14 bytes:

    +0x00 uint16  first sound index    +0x08 uint16  pictures cycled per sound
    +0x02 uint16  first picture        +0x0A uint16  lines of that caption
    +0x04 uint16  caption address      +0x0C uint16  ticks, used only with sound off
    +0x06 uint16  sounds to play

The three blocks are the only path to sounds 67 to 75, except 71. Each caption is the spoken line's own text, which is what ties the long sounds to speech rather than to effects: `DS:0x935C` begins `"ALTHOUGH THE APPEARANCE OF PALTIVAR IS IMMINENT,`.

| At | Sounds | First picture | Caption | Pictures | Lines | Ticks |
|---|---|---|---|---|---|---|
| `DS:0x597C` | 67 to 70 | 40 | `DS:0x935C` | 5 | 2 | 120 |
| `DS:0x598A` | 72 | 73 | `DS:0x93C2` | 7 | 3 | 180 |
| `DS:0x5998` | 73 to 75 | 73 | `DS:0x9440` | 7 | 5 | 280 |

## The ambient loop

**A place makes noise on its own, on a timer, out of a ten-slot list.** Image `0x008B4` is the whole of it, and the main loop at image `0x000A2` calls it whenever the timer has raised `DS:0x5372` bit 1. That is a second countdown in the same handler the music retry uses, on `DS:0x540A` and `DS:0x540C` bit 8 rather than `DS:0x5408` and bit 9.

**Image `0x009C8` picks the list.** It takes the area word at `DS:0xCF33`, which both a door destination and a teleport pad carry at their own `+0x0C`, and reads entry `area - 1` of the pointer table at `DS:0xEADB`, which holds eight pointers and then `0xFFFF`. The pointer names a **day half of 22 bytes followed by a night half of 22**, and the routine adds `0x16` to reach the night half where the clock at `DS:0xCF7F` is outside 360 to 1140 minutes, which is 06:00 to 19:00. That window is not the music's: image `0x1858F` opens its day at 420.

Each half is a delay word then ten sound slots:

    +0x00 uint16  ticks between sounds
    +0x02 uint16  slot 0
    ...
    +0x14 uint16  slot 9

The player reads the slot the cursor at `DS:0x0FDB` names, plays it where it is not 0, and steps the cursor by 2 until it passes `base + 0x12`, when it goes back to the base. It then copies the delay into `DS:0x540A` and sets `DS:0x540C` bit 8, and the timer handler at image `0x0E97F` counts that down and raises `DS:0x5372` bit 1 again. Every one of the sixteen halves holds a delay of 200 ticks, which is 11 seconds, so the list steps about five times a minute and a zero slot spends a step in silence.

Arriving anywhere restarts the list. Image `0x00999` is the same routine with the cursor put back to the base. Its twelve call sites are the door handler at image `0x05536`, the teleport pad at image `0x0AC20`, seven in the script-cell range from image `0x0B6B7` to image `0x0BAAD`, and images `0x0D558`, `0x0D6A0` and `0x0DF0F`.

**The eighth area is the Plane of Souls.** Areas 1 to 7 are the values the 139 door destinations carry. Image `0x0BA31` is the only writer of 8, and it puts the party at (604, 123), which is map slot 115 ([map.md](map.md) names it). Its five sounds are 2.1 to 3.8 seconds each, the longest ambience in the game.

| Area | Half | At | Delay | The ten slots |
|---|---|---|---|---|
| 1 | day | `DS:0xeaed` | 200 | 16, 0, 17, 0, 18, 0, 19, 0, 0, 20 |
| 1 | night | `DS:0xeb03` | 200 | 22, 0, 26, 0, 22, 22, 45, 26, 28, 0 |
| 2 | day | `DS:0xeb19` | 200 | 30, 16, 19, 0, 30, 17, 0, 18, 0, 19 |
| 2 | night | `DS:0xeb2f` | 200 | 26, 22, 0, 28, 29, 30, 45, 22, 0, 29 |
| 3 | day | `DS:0xeb45` | 200 | 23, 27, 22, 26, 0, 23, 27, 0, 22, 27 |
| 3 | night | `DS:0xeb5b` | 200 | 22, 0, 23, 26, 0, 27, 0, 27, 23, 0 |
| 4 | day | `DS:0xeb71` | 200 | 23, 0, 24, 0, 25, 0, 27, 0, 24, 0 |
| 4 | night | `DS:0xeb87` | 200 | 22, 0, 23, 0, 26, 0, 23, 0, 22, 0 |
| 5 | day | `DS:0xeb9d` | 200 | 31, 0, 23, 21, 0, 25, 0, 27, 0, 23 |
| 5 | night | `DS:0xebb3` | 200 | 27, 23, 0, 31, 25, 0, 27, 25, 0, 31 |
| 6 | day | `DS:0xebc9` | 200 | 21, 24, 0, 25, 0, 27, 0, 21, 27, 0 |
| 6 | night | `DS:0xebdf` | 200 | 22, 21, 0, 22, 23, 0, 23, 25, 0, 24 |
| 7 | day | `DS:0xebf5` | 200 | 95, 0, 30, 0, 18, 0, 30, 0, 95, 30 |
| 7 | night | `DS:0xec0b` | 200 | 30, 0, 45, 0, 28, 45, 30, 0, 22, 29 |
| 8 | day | `DS:0xec21` | 200 | 118, 0, 119, 0, 120, 0, 121, 0, 122, 0 |
| 8 | night | `DS:0xec37` | 200 | 0, 118, 0, 119, 0, 120, 0, 121, 0, 122 |

**Sound 46 is the dawn, and it is the one sound the clock fires by itself.** Image `0x008DC` loads it and then tests four five-minute windows, each with a bit of `DS:0xCF35` that stops it repeating: 06:00 at bit 15, 06:30 at bit 14, 07:00 at bit 13 and 07:30 at bit 12. A window that has not fired today plays 46 in place of the list's next slot. Image `0x008D1` skips all four where `DS:0xCEF9` carries any of bits 13 to 15, one of which is the indoor flag the view shades by ([view.md](view.md)), so the dawn is an outdoor sound. The four bits clear when the clock passes 1,440 minutes, at image `0x0EC23` on the ordinary advance and image `0x0D4AB` when a rest carries the party past midnight.

## What raises a sound

Ten record fields hold a sound index, the ambient table above holds 160 slots, and every other call names an index as a literal. The addresses below are the instruction that loads the field, not the call that follows it.

[tools/sound_sites.py](../tools/sound_sites.py) reads the call sites out of the executable rather than off this page: 172 far calls reach the six audio entries, of which 119 play a sound, 101 of those hand it a literal over 42 distinct sounds, and the other 18 take a value the routine worked out, which is one of the fields below.

| Field | Where | Played by |
|---|---|---|
| enemy record 42 | section 29 | `0x01053`, `0x01105`, `0x080C7` on the clue book's own page |
| enemy record 44 | section 29 | `0x0109E` |
| enemy record 48 | section 29 | `0x123AA`, off the projectile record's `+0x14`, when the shot lands ([combat.md](combat.md)) |
| attack table `+0` | `DS:0x96DA`, 12 bytes per entry | `0x0095F`, `0x0360B`, `0x0AEB9` |
| door destination `+0x06` | `DS:0xBA95`, 18 bytes per record | `0x0553B` |
| teleport pad `+0x0E` | `DS:0xB71F`, 20 bytes per record | `0x0AC0D`, `0x0AC25` |
| spell record 34 | section 31 | `0x1CCF5`, `0x1CD5E`, `0x1CF2B`, `0x1D3E0`, `0x1D80B` through `0x1D91F`, and `0x1D2AD` direct |
| spell record 32 | section 31 | `0x1CD8C`, `0x1D146`, `0x1D2E9`, `0x1D36E`, `0x1D4E0`, `0x1D5C6`, all through `0x1D91F`. Every family reaches one of the six, the restoratives at `0x1D146` |
| spell record 40 | section 31 | `0x1D0DE` through `0x1D91F` |
| weapon properties entry `+0xA` | section 9, 12 bytes per entry ([items.md](items.md)) | `0x00EB5`, when a melee blow lands |

### What a cast plays, which is the dispatcher's rather than the record's

A spell's sound is not a field of its record. The dispatcher at image `0x1C4E4` branches on record offset 72 and then on four bits of record 76, and the branch decides. The record being cast sits in a buffer at `DS:0x5DA6`, which is what makes the dispatcher readable: `DS:0x5DEE` is its offset 72, `DS:0x5DF2` its 76, `DS:0x5DC6` its 32 and `DS:0x5DC8` its 34. Eighteen branches cover all 107 records with none left over, and [tools/spell_sounds.py](../tools/spell_sounds.py) walks them.

| Record and bit | Spells | Plays |
|---|---|---|
| 72 `0x8000`, `0x4000` | 19 | the attack table entry offset 32 names |
| 72 `0x2000`, `0x1000` | 39 | record offset 34 |
| 72 `0x0100`, 76 `0x0008`/`0x0002`/`0x0004`/`0x0001` | 38 | record offset 32 |
| 72 `0x0080`, `0x0008` | 4 | 44 |
| 72 `0x0001`, `0x0040` | 2 | 11 |
| 72 `0x0010`, `0x0004` | 2 | 51, 79 |
| 72 `0x0020`, `0x0002` | 2 | nothing |

**A restorative sounds through the attack table.** Its branch plays nothing itself. Image `0x1C5E1` hands offset 32 to the lookup at image `0x0357E`, which answers a far pointer to an attack table entry, and stores that pointer on the character's own animation slot at `DS:0x0F4A`, twenty bytes each and four of them. What is heard is the entry's own `+0`, beside the animation its `+2` draws over the healed character's portrait. All 19 restoratives name entry 18, whose sound is 12 and whose animation is 2. The same lookup read the same way is image `0x0AEB9` on the monster's side.

**Offset 32 is two things.** On that branch it is an entry number, and all 19 restoratives hold 18, inside the 49 the table has. On every other branch it is a sound index, and across the other 88 records it reaches 126, which no 49-entry table could hold. The overloading is settled from both sides.

**A cast that does nothing is silent.** Image `0x1CCE7` tests the damage the applier at image `0x1D93D` wrote into `DS:0x0F34` and `DS:0x0F36` and leaves without a sound where it is zero, so immunity and a failed roll both come out quiet. There is no miss sound.

### The literals, read off the branch that plays them

Most of the 101 literal sites say only that a sound is played there. These say which sound covers which branch, because the instruction that picks between them is in the same window.

| Sound | Raised by | Read at |
|---|---|---|
| 1 | a screen going up, before the panel routine draws it | `0x0CBB6` and six more |
| 2 | one of the four portraits taken, beside a write of `DS:0x53D4` | `0x04B32`, `0x04C66` |
| 5 | the party stepping, either arm of the move routine | `0x03451`, `0x034A9` |
| 6 | a party volley leaving, once | `0x0C26C` |
| 7 | a monster's slot freed as it dies | `0x12CEF` |
| 8 / 7 | a repair destroying the piece / mending it | `0x1C48B`'s three-way |
| 9 | a service paid for | `0x16863` and four more |
| 10 / 76 | a thrown item landing, by its own id | `0x0C4A4`, `0x0C4E5` |
| 13 | a step a wall or a blocking object refused, and a shot one stopped | `0x032D5`, `0x0C310` |
| 14 | a container with a lid | `0x0294D`, `0x02986` |
| 15 | the item panel a shop service opens | `0x03A98` and five more |
| 34 / 35 | a shot that came off the monster's health / one that did not | `0x0C35F` |
| 35 | a blow in hand to hand that missed, and a thrown item leaving | `0x00E89`, `0x0C675` |
| 40 | a cast light or a torch running out | `0x1A4D0`, raised at `0x0EBB9` |
| 43, 33, 84, 44 | the lens, and the world scripts by their own area | `0x0B6AC` to `0x0BB3D` |

**Sound 5 is the step because `DS:0x0E9A` is the key.** It is written with 72, 75, 77 and 80, which are the four arrow scan codes, and image `0x03447` compares it against `0x48` to tell a forward step from the rest. Each arm sounds before adding its own delta to `DS:0xCF75` and `DS:0xCF77`.

**Sound 13 is the refusal because it stands in front of the step.** Image `0x032D5` is twenty bytes before the step at image `0x032E9`. The two classifiers write into `DS:0x53E0` and the step runs only on a pair of zeros; 2 is a terrain of 0 or 1, the edge of the map, and goes quiet, and everything else sounds ([map.md](map.md)).

**Only one effect sounds at a time.** CT-VOICE plays out of a single buffer, so a second sound cannot overlap the first: image `0x186D8` cuts the current one short at five sites and image `0x184B4` waits it out at twenty-one.

**The projectile picks a picture and not a sound.** A party shot is drawn as one of five pictures, chosen from the missile weapon's own item id, and every one of the five sounds the same. Three readings say so and none of them needs the game run.

- **The picker sets no sound.** Image `0x1B547` writes the picture number into `DS:0x0FC3` and the blitter's rectangle into `DS:0x5438`, `DS:0x5434` and `DS:0x543A`, and returns. Nothing else.
- **There is no second picker.** The four ids it compares against, 484, 269, 525 and 535, occur as an instruction immediate exactly once each in the whole image, at `0x1B562`, `0x1B56B`, `0x1B574` and `0x1B57A`. Every other byte pair matching one of them decodes as something else.
- **Every sound in the routine is an immediate.** Reading `0x0C13E` to `0x0C980` end to end, the nine calls that reach a sound entry are handed 6, 13, 34, 35, 10, 76 and the wrapper's own argument, all of them `mov ax, imm16` in the instruction stream. No record, no table and no `DS:0x0FC3`. The routine never touches the projectile record at `DS:0xA5A6` either, which is the record a monster's shot takes its sound out of.

So a SLING, a LONG BOW, a CROSSBOW, a FIRE BOW and an ICE BOW all play 6. What the weapon picks is the picture and the damage. The weapon's own properties entry `+0xA`, which a landed melee blow reads, is 0 on all 35 missile weapons against 174 of the table's 210 entries that name one, so that field is not a second source either.

**A monster's shot is the one that varies.** Image `0x12579` copies enemy record 48 into the projectile record's `+0x14`, one of four at `DS:0xA5A6`, and image `0x123AA` walks the four and plays the first that is not zero. 13 monsters carry one, with 7 distinct sounds between them.

**Sound 35 is a miss in hand to hand, and it pairs with the weapon's own sound.** Image `0x00E73` calls the resolver at `0x1586F` and image `0x00E78` tests the damage it wrote into `DS:0x0F36`. Zero takes the branch that plays 35 at image `0x00E89`. Anything else takes the branch that reads the acting character's hand weapon out of record offset `0x142`, resolves its properties entry through image `0x0F44C`, and plays that entry's own `+0xA` at image `0x00EBC`, skipping where the entry holds 0. So a character's blow is the same pair a monster's is, records 42 and 44 against a weapon field and one literal.

**Sound 14 is a container with a lid.** Images `0x0294D` and `0x02986` both load 14, and both stand behind a test of `DS:0x5890` bit 1, which is the kind bit image `0x027AD` reads to raise WHO WILL OPEN against WHO WILL SEARCH ([map.md](map.md)). Kind 1 is the barrel, the chest and the dresser; the other eleven drawings open in silence.

**A volley's sounds are 6, 13, 34 and 35.** Image `0x0C13E` is the whole of it, reached from `S` at image `0x0067F`, which sets `DS:0x536E` bit `0x100` in front of the call and clears it after.

- **6 as it leaves.** Image `0x0C264` cuts whatever is playing short and image `0x0C26C` plays 6, once, after the four shot pictures are drawn at image `0x0C21B` and before the first band.
- **The bands are silent.** Image `0x0C276` sets the party's own cell without probing it, and every band further out is drawn and then handed to the probe at image `0x02F93`. The probe writes its answer into `DS:0x53E0`.
- **13 where the shot stopped.** Answer 1, a terrain of 2 to 99 or 200 to 299, and answer 2, any object, both reach image `0x0C310`. Answer 3, which the view entry's own `+6` bit `0x800` raises, and a shot that runs out of bands at image `0x0C2F4`, are silent.
- **34 or 35 per shooter resolved.** Answer 4 is a monster, and image `0x0C35F` plays 34 where `DS:0x536E` bit `0x200` stands and 35 where it does not. Image `0x0C6BA` raises that bit as the damage comes off the monster's health and image `0x0C6F6` clears it in front of each shot. Every shooter the volley collected is heard: image `0x0C316` opens each pass with a three-tick wait, so four bows are four sounds and not one.

**Sounds 10 and 76 are a thrown item, not a bow.** The same routine takes two other paths, and both carry an item id in `DS:0x5426` rather than a bow: image `0x1AFF9` calls it with neither bit set, and image `0x006A6` calls it with `DS:0x5370` bit `0x1000` set, which is hand to hand. Image `0x0C5C8` draws the item's own quarter of the throw picture, telling the four apart by id against 63 and 61, which are the BLUE and GOLD POTION, and against the 60 image `0x0F130` writes into `DS:0x5464`, which is the FLAMING OIL FLASK. It plays 35 at image `0x0C675` as the item leaves. What it lands with is the same comparison read again at images `0x0C4A4` and `0x0C4E5`: 76 at image `0x0C518` for the flask and for the -1 image `0x0F0FA` writes into `DS:0x544E`, and 10 at images `0x0C4BB`, `0x0C4F7` and `0x0C5BF` for anything else.

**Offset 32 is a sound on all 107 records, the restoratives included.** The spell being cast sits in a buffer at `DS:0x5DA6`, so `DS:0x5DC6` is its offset 32 and `DS:0x5DC8` its 34, and neither word is ever written: they are read straight out of the record. Image `0x1D146` reads `DS:0x5DC6` and hands it to the wrapper at image `0x1D91F`, and the same branch goes on to read `DS:0x5DCC`, which is offset 38, the restorative's own maximum ([spells.md](spells.md)). So a heal, a cure, a resurrection and a restoration each play offset 32 as much as a damaging spell does, and all 19 hold **18** there, which makes 18 the one sound every restorative shares. The other 88 hold 30 distinct values between them, all in range.

Offsets 34 and 40 split by family, and only there. On the 19 restoratives 34 is an amount of health, 10 for HEAL and 9,999 for PERFECT HEALTH, and 40 is a mask that runs past the 141 the bank holds, so neither is a sound on those records. On the other 88 both are, every non-zero value of 34 falling inside 1 to 141 and every non-zero value of 40 but 208, 219 and 225. Which branch raises either is unread.

The door's sound plays on arrival and 65 of the 139 destinations are silent. The pad's is 43 on all 13 pads that teleport and 0 on the six that only refuse a rest.

### The bank

Offsets are into `WORLD.DAT`, bytes are the length-table entry, and seconds is the sample count over the rate. The last column names each source: a record field, `ambient` for a slot of the table above, `dawn` for the clock windows, and the image address of every call that plays the index as a literal. A run played by a loop is credited to the loop's own call site: `0x1BD0F` plays 51 to 53, `0x1BD34` plays 54 to 58, `0x1BD88` plays 59 to 66, and the three talking-head blocks at `0x1C062`, `0x1C09F` and `0x1C0C7` play 67 to 70, 72, and 73 to 75.

| # | Offset | Bytes | Rate | Seconds | Raised by |
|---|---|---|---|---|---|
| 1 | `0x00baeba` | 2,551 | 12,987 | 0.19 | `0x0889f`, `0x0cbb6`, `0x0d1e2`, `0x0d3ed`, `0x0d435`, `0x0d855`, `0x0da0b` |
| 2 | `0x00bb8b1` | 3,510 | 10,000 | 0.35 | `0x00272`, `0x04b32`, `0x04c66` |
| 3 | `0x00bc667` | 2,698 | 12,987 | 0.21 | attack table; `0x056f7`, `0x085a7`, `0x09522`, `0x0be29`, `0x0be56`, `0x0c0af`, `0x0c9ac`, `0x0cc3b`, `0x0d3c5`, `0x0db9e`, `0x19a13`, `0x1ac5c`, `0x1b96a`, `0x1c7f2`, `0x1c952`, `0x1db83`, `0x1db9d` |
| 4 | `0x00bd0f1` | 1,950 | 18,181 | 0.11 | `0x0da62`, `0x0dba8`, `0x0e6b8`, `0x0e728`, `0x1acb7`, `0x1b983` |
| 5 | `0x00bd88f` | 12,852 | 12,987 | 0.99 | `0x03451`, `0x034a9` |
| 6 | `0x00c0ac3` | 6,465 | 14,925 | 0.43 | monster shot; spell 32; `0x0c26c` |
| 7 | `0x00c2404` | 6,713 | 14,084 | 0.47 | spell 40; `0x01fa5`, `0x0204f`, `0x02072`, `0x061fc`, `0x09597`, `0x0a091`, `0x12cef`, `0x1c4bd` |
| 8 | `0x00c3e3d` | 2,344 | 12,987 | 0.18 | spell 32; spell 34; `0x1c495` |
| 9 | `0x00c4765` | 1,728 | 11,111 | 0.15 | `0x04087`, `0x14335`, `0x163a7`, `0x16863`, `0x16888`, `0x172da`, `0x17329` |
| 10 | `0x00c4e25` | 7,532 | 14,925 | 0.50 | `0x0c4bb`, `0x0c4f7`, `0x0c5bf` |
| 11 | `0x00c6b91` | 9,067 | 13,157 | 0.69 | attack table; `0x19aad`, `0x1ace9`, `0x1cbc8`, `0x1cc6f` |
| 12 | `0x00c8efc` | 26,647 | 22,222 | 1.20 | attack table; spell 34 |
| 13 | `0x00cf713` | 1,935 | 12,987 | 0.15 | spell 34; `0x032d5`, `0x0c310` |
| 14 | `0x00cfea2` | 2,060 | 12,987 | 0.16 | `0x02950`, `0x02989` |
| 15 | `0x00d06ae` | 2,118 | 12,987 | 0.16 | spell 40; `0x03a98`, `0x03b27`, `0x03f12`, `0x03fc9`, `0x03fe9`, `0x0402e` |
| 16 | `0x00d0ef4` | 24,327 | 12,987 | 1.87 | ambient |
| 17 | `0x00d6dfb` | 1,002 | 12,987 | 0.07 | ambient |
| 18 | `0x00d71e5` | 29,335 | 12,987 | 2.26 | ambient; attack table |
| 19 | `0x00de47c` | 28,088 | 12,987 | 2.16 | ambient |
| 20 | `0x00e5234` | 33,539 | 12,987 | 2.58 | ambient |
| 21 | `0x00ed537` | 37,758 | 12,987 | 2.90 | ambient |
| 22 | `0x00f68b5` | 28,735 | 12,987 | 2.21 | ambient |
| 23 | `0x00fd8f4` | 21,504 | 12,987 | 1.65 | ambient |
| 24 | `0x0102cf4` | 23,985 | 12,987 | 1.84 | ambient |
| 25 | `0x0108aa5` | 32,739 | 12,987 | 2.52 | ambient |
| 26 | `0x0110a88` | 5,340 | 12,987 | 0.41 | ambient |
| 27 | `0x0111f64` | 24,287 | 16,129 | 1.50 | ambient |
| 28 | `0x0117e43` | 31,747 | 12,987 | 2.44 | ambient |
| 29 | `0x011fa46` | 30,097 | 12,987 | 2.31 | ambient |
| 30 | `0x0126fd7` | 31,951 | 12,987 | 2.46 | ambient |
| 31 | `0x012eca6` | 35,340 | 12,987 | 2.72 | ambient |
| 32 | `0x01376b2` | 33,660 | 12,987 | 2.59 | door |
| 33 | `0x013fa2e` | 39,697 | 12,987 | 3.05 | door; `0x0b7c7` |
| 34 | `0x014953f` | 3,670 | 13,157 | 0.28 | attack table; spell 32; spell 34; `0x0c35f` |
| 35 | `0x014a395` | 2,098 | 13,157 | 0.16 | monster miss; spell 40; weapon; `0x00e89`, `0x0c35f`, `0x0c675` |
| 36 | `0x014abc7` | 13,076 | 16,129 | 0.81 | monster hit; monster miss |
| 37 | `0x014dedb` | 3,668 | 12,987 | 0.28 | weapon |
| 38 | `0x014ed2f` | 5,573 | 11,111 | 0.50 | monster hit; weapon |
| 39 | `0x01502f4` | 3,190 | 12,987 | 0.24 | weapon |
| 40 | `0x0150f6a` | 2,408 | 12,987 | 0.18 | attack table; monster hit; monster miss; monster shot; spell 32; spell 34; `0x0fde3`, `0x1a4d0` |
| 41 | `0x01518d2` | 4,593 | 15,151 | 0.30 | weapon |
| 42 | `0x0152ac3` | 12,059 | 17,241 | 0.70 | monster hit; monster miss |
| 43 | `0x01559de` | 10,644 | 12,987 | 0.82 | attack table; door; monster hit; monster miss; pad; spell 32; spell 34; `0x0b6ac` |
| 44 | `0x0158372` | 16,706 | 12,987 | 1.28 | door; `0x0b9af`, `0x0ba6b`, `0x0bb3d`, `0x0cdd1`, `0x1c679`, `0x1cb0e` |
| 45 | `0x015c4b4` | 35,168 | 20,000 | 1.76 | ambient |
| 46 | `0x0164e14` | 23,169 | 13,157 | 1.76 | dawn |
| 47 | `0x016a895` | 3,612 | 12,987 | 0.28 | monster hit; monster miss |
| 48 | `0x016b6b1` | 12,978 | 12,987 | 1.00 | attack table; monster shot; spell 32; spell 34 |
| 49 | `0x016e963` | 2,376 | 13,157 | 0.18 | weapon |
| 50 | `0x016f2ab` | 49,694 | 12,987 | 3.82 | `0x1b4cd` |
| 51 | `0x017b4c9` | 28,215 | 12,987 | 2.17 | `0x1bd0f`, `0x1c6f5` |
| 52 | `0x0182300` | 34,384 | 12,987 | 2.65 | spell 32; `0x1bd0f` |
| 53 | `0x018a950` | 38,425 | 12,987 | 2.96 | `0x1bd0f` |
| 54 | `0x0193f69` | 32,812 | 12,987 | 2.52 | `0x1bd34` |
| 55 | `0x019bf95` | 31,123 | 12,987 | 2.39 | spell 32; `0x1bd34` |
| 56 | `0x01a3928` | 48,504 | 12,987 | 3.73 | spell 32; spell 34; `0x1bd34` |
| 57 | `0x01af6a0` | 51,205 | 12,987 | 3.94 | spell 32; `0x1bd34` |
| 58 | `0x01bbea5` | 32,770 | 12,987 | 2.52 | attack table; spell 32; spell 34; `0x1bd34` |
| 59 | `0x01c3ea7` | 27,044 | 12,987 | 2.08 | `0x1bd88` |
| 60 | `0x01ca84b` | 36,327 | 12,987 | 2.79 | `0x1bd88` |
| 61 | `0x01d3632` | 39,690 | 12,987 | 3.05 | `0x1bd88` |
| 62 | `0x01dd13c` | 14,478 | 12,987 | 1.11 | attack table; `0x1bd88` |
| 63 | `0x01e09ca` | 43,120 | 12,987 | 3.32 | spell 32; spell 34; `0x1bd88` |
| 64 | `0x01eb23a` | 32,812 | 12,987 | 2.52 | `0x1bd88` |
| 65 | `0x01f3266` | 27,892 | 12,987 | 2.15 | `0x1bd88` |
| 66 | `0x01f9f5a` | 28,260 | 12,987 | 2.17 | `0x1bd88` |
| 67 | `0x0200dbe` | 35,432 | 12,987 | 2.73 | `0x1c062` |
| 68 | `0x0209826` | 36,661 | 12,987 | 2.82 | spell 32; `0x1c062` |
| 69 | `0x021275b` | 36,580 | 12,987 | 2.81 | `0x1c062` |
| 70 | `0x021b63f` | 48,828 | 12,987 | 3.76 | `0x1c062` |
| 71 | `0x02274fb` | 29,697 | 12,987 | 2.28 | `0x1c084` |
| 72 | `0x022e8fc` | 34,226 | 12,987 | 2.63 | `0x1c09f` |
| 73 | `0x0236eae` | 19,120 | 12,987 | 1.47 | `0x1c0c7` |
| 74 | `0x023b95e` | 34,496 | 12,987 | 2.65 | `0x1c0c7` |
| 75 | `0x024401e` | 23,218 | 12,987 | 1.79 | `0x1c0c7` |
| 76 | `0x0249ad0` | 14,426 | 11,111 | 1.30 | attack table; monster shot; spell 32; spell 34; spell 40; `0x0c518` |
| 77 | `0x024d32a` | 5,999 | 12,987 | 0.46 | weapon |
| 78 | `0x024ea99` | 12,790 | 12,987 | 0.98 | monster hit; monster miss |
| 79 | `0x0251c8f` | 5,119 | 11,111 | 0.46 | `0x1c8bb` |
| 80 | `0x025308e` | 6,237 | 13,157 | 0.47 | monster hit; monster miss |
| 81 | `0x02548eb` | 5,204 | 12,987 | 0.40 | monster hit; monster miss; spell 32; spell 34 |
| 82 | `0x0255d3f` | 15,968 | 12,987 | 1.23 | monster hit; monster miss; spell 40 |
| 83 | `0x0259b9f` | 49,368 | 12,987 | 3.80 | `0x1bdd0` |
| 84 | `0x0265c77` | 42,969 | 19,230 | 2.23 | door; `0x0b861` |
| 85 | `0x0270450` | 15,626 | 12,987 | 1.20 | spell 32; spell 34 |
| 86 | `0x027415a` | 17,359 | 11,111 | 1.56 | attack table; monster hit; monster miss; monster shot; spell 32; spell 34; spell 40 |
| 87 | `0x0278529` | 8,316 | 12,987 | 0.64 | `0x0cdbf` |
| 88 | `0x027a5a5` | 15,250 | 22,222 | 0.68 | monster hit; monster miss |
| 89 | `0x027e137` | 14,560 | 22,222 | 0.65 | monster hit |
| 90 | `0x0281a17` | 5,490 | 12,987 | 0.42 | monster miss |
| 91 | `0x0282f89` | 14,268 | 22,222 | 0.64 | monster hit; monster miss; spell 32; spell 34 |
| 92 | `0x0286745` | 9,899 | 12,987 | 0.76 | monster hit; monster miss; spell 32; spell 34; weapon |
| 93 | `0x0288df0` | 19,144 | 12,987 | 1.47 | spell 32; spell 34; spell 40 |
| 94 | `0x028d8b8` | 47,558 | 22,222 | 2.14 | `0x10e8e` |
| 95 | `0x029927e` | 21,925 | 13,157 | 1.66 | ambient |
| 96 | `0x029e823` | 3,509 | 11,111 | 0.31 | weapon |
| 97 | `0x029f5d8` | 12,039 | 22,222 | 0.54 | weapon |
| 98 | `0x02a24df` | 3,920 | 22,222 | 0.17 | monster hit; monster miss; weapon |
| 99 | `0x02a342f` | 21,667 | 12,987 | 1.67 | monster hit; monster miss; spell 32; spell 34; spell 40 |
| 100 | `0x02a88d2` | 22,208 | 22,222 | 1.00 | monster shot; spell 32; spell 34; `0x1b483` |
| 101 | `0x02adf92` | 19,544 | 22,222 | 0.88 | attack table |
| 102 | `0x02b2bea` | 22,806 | 12,987 | 1.75 | monster hit; monster miss |
| 103 | `0x02b8500` | 6,748 | 13,157 | 0.51 | monster hit; weapon |
| 104 | `0x02b9f5c` | 8,045 | 14,084 | 0.57 | monster hit; weapon |
| 105 | `0x02bbec9` | 23,988 | 22,222 | 1.08 | monster hit; monster miss |
| 106 | `0x02c1c7d` | 37,215 | 13,157 | 2.83 | spell 32 |
| 107 | `0x02caddc` | 8,955 | 13,157 | 0.68 | `0x1ca37` |
| 108 | `0x02cd0d7` | 49,963 | 12,987 | 3.84 | spell 32 |
| 109 | `0x02d9402` | 5,693 | 13,157 | 0.43 | monster hit; weapon |
| 110 | `0x02daa3f` | 4,349 | 11,111 | 0.39 | monster hit; weapon |
| 111 | `0x02dbb3c` | 22,222 | 13,157 | 1.69 | spell 32 |
| 112 | `0x02e120a` | 10,804 | 9,009 | 1.20 | spell 34 |
| 113 | `0x02e3c3e` | 10,006 | 13,157 | 0.76 | weapon |
| 114 | `0x02e6354` | 14,384 | 14,084 | 1.02 | monster hit; monster miss |
| 115 | `0x02e9b84` | 25,448 | 22,222 | 1.14 | attack table; monster hit; monster miss; spell 32; spell 34 |
| 116 | `0x02efeec` | 13,063 | 15,151 | 0.86 | monster hit; monster miss; monster shot; spell 32 |
| 117 | `0x02f31f3` | 49,966 | 12,987 | 3.84 | door |
| 118 | `0x02ff521` | 49,908 | 12,987 | 3.84 | ambient |
| 119 | `0x030b815` | 33,062 | 12,987 | 2.54 | ambient |
| 120 | `0x031393b` | 27,416 | 12,987 | 2.11 | ambient |
| 121 | `0x031a453` | 31,095 | 12,987 | 2.39 | ambient |
| 122 | `0x0321dca` | 44,107 | 12,987 | 3.39 | ambient |
| 123 | `0x032ca15` | 3,764 | 12,987 | 0.29 | monster hit; monster miss |
| 124 | `0x032d8c9` | 28,599 | 11,111 | 2.57 | spell 32 |
| 125 | `0x0334880` | 3,998 | 12,987 | 0.31 | monster hit; monster miss |
| 126 | `0x033581e` | 42,535 | 13,157 | 3.23 | spell 32 |
| 127 | `0x033fe45` | 14,450 | 12,987 | 1.11 | monster hit; monster miss |
| 128 | `0x03436b7` | 11,615 | 11,111 | 1.04 | monster hit; monster miss |
| 129 | `0x0346416` | 20,512 | 11,111 | 1.84 | monster hit; monster miss |
| 130 | `0x034b436` | 39,792 | 12,987 | 3.06 | `0x05356` |
| 131 | `0x0354fa6` | 49,572 | 12,987 | 3.81 | `0x05364` |
| 132 | `0x036114a` | 23,337 | 12,987 | 1.79 | `0x05372` |
| 133 | `0x0366c73` | 49,200 | 12,987 | 3.79 | `0x05388` |
| 134 | `0x0372ca3` | 47,783 | 12,987 | 3.68 | `0x0539e` |
| 135 | `0x037e74a` | 23,607 | 12,987 | 1.82 | `0x053ac` |
| 136 | `0x0384381` | 39,887 | 12,987 | 3.07 | `0x053ef` |
| 137 | `0x038df50` | 25,528 | 12,987 | 1.96 | `0x053fd` |
| 138 | `0x0394308` | 46,123 | 13,157 | 3.50 | `0x05413` |
| 139 | `0x039f733` | 42,576 | 13,157 | 3.23 | `0x05429` |
| 140 | `0x03a9d83` | 49,563 | 13,157 | 3.76 | `0x0543f` |
| 141 | `0x03b5f1e` | 49,426 | 13,157 | 3.75 | `0x05455` |

## Nothing is unreached

**All 141 sounds are named by something.** The reachable set is the union of the ten record fields, the ambient table, the dawn and the literals at the 119 call sites. It covers 1 to 141 with nothing left over. All 24 songs are reachable too, 17 of them through section 3 and 7 through the override or a direct call.

**Neither bank is named anywhere.** No string in the executable gives a sound or a song a title, so the tables above say when each is played and not what it is. The nearest thing to a name is a caption: the three talking-head blocks pair each spoken run with the text of the line, so sounds 67 to 70 and 72 to 75 are the only ones whose content is written down in the game's own data.
