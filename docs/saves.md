# The save file

`CURGAME` and every `SAVGAMEn` are 81,037 bytes and share one format. Settled findings only.

The Evidence column uses the classifiers [README.md](README.md) defines. **measured** here means [tools/save_probe.js](../tools/save_probe.js) played a scripted session and copied `CURGAME` after every step, and [tools/save_map.py](../tools/save_map.py) named the offsets that moved between two copies. **screens** means a save was put back on the emulated disk and read off the game's own F1 to F5 pages.

**Saving is a file copy.** SAVE writes the roster and the monster block into `CURGAME` first, reads it back from 5,000 to 68,557, and writes all 81,037 bytes to `SAVGAMEn`. The two files then compare equal byte for byte.

**`CURGAME` is a random access record store, not a memory dump.** The game seeks into it and writes single records as they change, which is a hundred bytes when the party crosses a row of the world, or one byte when a door opens. The file can therefore be read while the game is being played, and most of a fresh file is zeros.

## The section table

`DS:0xB167` (image `0x28F17`, file `0x2CF17`) is a table of `uint32` file offsets: seven for `CURGAME`, then a zero. The next dword is `0x83400`, the first entry of `WORLD.DAT`'s master directory, which [tools/sections.py](../tools/sections.py) reads at file `0x2CF37`. The two tables abut, so this one is addressed from that one.

A file is held in a 14-byte handle followed by its name. The handle for `CURGAME` is at `DS:0x967A`, for `PICTURES.VGA` at `DS:0x9690`, for `SAVGAMEX` at `DS:0x96AB` and for `WORLD.DAT` at `DS:0x96C2`. The `X`, at `DS:0x96C0`, is overwritten with the slot digit.

**There are six slots.** `DS:0x6FEC` is the list the disk panel draws: six 27-byte rows, each a digit, a NUL and a 25-character caption, shipped as `- EMPTY -` and overwritten with the name typed at a save. Image `0x0DA82` takes a row's first byte for the filename digit, so the slots are `SAVGAME1`–`SAVGAME6`, and image `0x0E0B8` has one branch per digit from `1` to `6`. The seventh row is zeros.

| Offset | Field |
|---|---|
| 0 | DOS file handle, `0xFFFF` when closed |
| 2, 4 | buffer segment and offset |
| 6 | record length |
| 8 | record number |
| 10 | section base, `uint32` |
| 14 | the name, NUL terminated |

The seek is at image `0x039ED`:

    file offset = [handle+10] + [handle+8] * [handle+6]

`mul`, `add`, `INT 21h AH=42h AL=00`. Reading is `0x03997` and writing `0x039C2`, both `INT 21h` with the handle's own buffer and length.

One stub per section points the handle at the right table entry and sets the record length. Section 1's length is not an immediate: the stub copies it from `DS:0x5492`, which holds 100.

| # | Stub (image) | Base | Size | Record | Count | What |
|---|---|---|---|---|---|---|
| 0 | `0x17E64` | 0 | 5,000 | 5,000 | 1 | the roster |
| 1 | `0x17EDC` | 5,000 | 16,800 | 100 | 168 | the seen grid |
| 2 | `0x17EF6` | 21,800 | 44,064 | 34 | 1,296 | containers |
| 3 | `0x17EA1` | 65,864 | 1,059 | 1 | 1,059 | bundles the chest path has finished |
| 4 | `0x17E82` | 66,923 | 1,008 | 1 | 1,008 | items handed over, a bit each |
| 5 | `0x17EC0` | 67,931 | 626 | 1 | 626 | which monsters are still on the map |
| 6 | `0x17E46` | 68,557 | 12,480 | 12,480 | 1 | the monsters on the map |

[tools/saves.py](../tools/saves.py) reads the offsets out of the executable rather than restating them, and [tests/test_saves.py](../tests/test_saves.py) reads each record length back out of its stub's bytes.

NEW GAME rebuilds all seven sections from zeros, at image `0x151E4` to `0x15348`, which is where the record counts come from. Section 1 uses `cx = 0xA8`. Section 2 uses `cx = 0x10`, writing 2,754 bytes at a time. Section 6 uses `ax = 0x122C`, which is the spawn table's own address.

## Section 0, the roster

Ten 500-byte slots. Slot 0 is a header, slots 1–5 are the created characters and 6–9 the four the game ships. `WORLD.DAT 0x41D72F`, the `PRE-CREATED PARTY` section, holds the same 5,000 bytes as a template.

**`CURGAME`'s roster is written but never read.** KEEP CHARACTER writes the 5,000 bytes immediately, and SAVE writes them again. The only reads of `CURGAME` belong to the save routine, and they start at offset 5,000. Every launch truncates `CURGAME` and rewrites all 81,037 bytes, and NEW GAME does the same, both from the `WORLD.DAT` template. A character kept at the menu therefore survives a relaunch only if it is written into that template, which is what [tools/keep_characters.py](../tools/keep_characters.py) and the cabinet's **Keep characters** button do, for slots 1 to 5.

**Only two routines fill the roster.** Image `0x15130` reads it from `WORLD.DAT` section 32, the template: NEW GAME, and the launch rebuild. Image `0x0DC0C` reads it from a `SAVGAMEn` and writes the same bytes on to `CURGAME`: LOAD. Everything in the header slot travels with the characters, the container allocator's two words included.

### The header slot

The first bytes ship holding `PRE-CREATED PARTY`, and the name typed at a save slot is written over them.

| Offset | Field | Evidence |
|---|---|---|
| 150 | facing: `0x8000` north, `0x4000` south, `0x2000` west, `0x1000` east | code, `0x112D6`; measured, one turn a step |
| 152 | the party's x, in cells across the whole world grid | measured; the trainer writes it and the party arrives there |
| 154 | the party's y | measured, the same way |
| 156 | the day, advanced by clock wrapping | measured, across a wrap |
| 162 | the clock, in minutes, 0 to 1,439 | measured, one step at a time |
| 180 | gold, packed BCD, four bytes | screens: the F5 purse |
| 184 | food, the same | screens: the F5 purse |
| 188 | nuore, the same | screens: the F5 purse |
| 310 | the sky ramp: 32 colors of three six-bit components | measured; shape: 96 bytes, every component 63 or below |
| 492 | the roster slots that are playing, four words, 0 for an empty place | measured, against the party assembled |

The facing values are the ones the look-ahead dispatch at image `0x112D6` tests, where `0x8000` steps `y` back and `0x4000` steps it on, `0x1000` steps `x` on and anything else steps it back.

The world is one grid, seven areas of 24 bands down by twenty levels of 40 cells across, so `x = level * 40 + cell` and `y = area * 24 + band`, and a map is one `(area, level)` block of that grid. The cabinet's trainer writes those two words to put a party on a named map. It takes the cell from `arrive` in `data/map_pages.json`, which is the drawn cell nearest the middle of that map, because a cell whose bit at `0x3C4F02` is clear is not part of the map at all.

The template's own fields state where a new game starts: x 460, y 46, facing north, clock 540. That is area 1 level 11, which the map registry names `ATHANEUM` ([map.md](map.md)), and 09:00.

**Gold, food and nuore are party-wide**, and are what the game's F5 panel prints. All three are **packed BCD, most significant byte first**: 3,557 gold reads `00 00 35 57`. It is the encoding [items.md](items.md) records on the item table's BASE VALUE. A new game starts with none of the three.

A step costs the clock 2 or 3 minutes and a rest about 483. The clock wraps at 1,440 and the day at 156 advances with the wrap. The sky ramp is rewritten as the clock moves: blue to white by day, near black at night, with every component 63 or below, as a VGA palette entry requires.

### The character record

500 bytes, at the same displacements the code uses. The roster sits at `DS:0xCEDD` in the running game, so slot 1 begins at `DS:0xD0D1`, which is where [monsters.md](monsters.md) puts a character struct: record offset N is `[si+N]`.

| Offset | Field | Evidence |
|---|---|---|
| 0 | name, NUL terminated | screens: F1 |
| 14 | class | screens: F1; code, `0x04CC3` |
| 16 | sex, 1 or 2 | screens: F1 |
| 22 | level | screens: F1 |
| 24 | experience, packed BCD, four bytes | screens: F1 |
| 28 | conditions, the word the cure prices are read from | code, `0x092B1`; screens: F1 |
| 60–110 | the live block, 26 words, below | screens: F1, every field |
| 124–174 | the same 26 words again, holding the maximum | screens: F1, and the pair below |
| 280 | weight carried, in tenths | code, `0x05C44`; shape: `10 x` strength |
| 282–313 | the eight panel slots, four bytes each | code, `0x0437E`, see [items.md](items.md) |
| 314, 318, 322, 326, 330, 334, 338 | missile, container, hand, shield, two rings, worn | code, `0x04237`, see [items.md](items.md) |

The live block, in the order the F1 sheet prints it:

| From 60 | Field | From 60 | Field |
|---|---|---|---|
| +0 | strength | +28 | survival |
| +2 | dexterity | +30 | projectile |
| +4 | stamina | +32 | slashing |
| +6 | intelligence | +34 | bashing |
| +8 | wisdom | +36 | polearm |
| +10 | charisma | +38 | casting |
| +12 | shot accuracy | +40 | mapping |
| +14 | shot damage | +42 | navigate |
| +16 | accuracy | +44 | bartering |
| +18 | damage | +46 | repair |
| +20 | absorption | +48 | thievery |
| +22 | health | +50 | linguistic |
| +24 | magic | | |
| +26 | weight capacity, in tenths | | |

The four combat words are the ones [tools/fight_probe.js](../tools/fight_probe.js) writes, at `0x48`, `0x4A`, `0x4C` and `0x4E`. The ACC and DAM rows of the sheet are the hand pair, and the shot pair is not printed there. The block at 124 is the maximum column. Health and magic differ from the live copy whenever the party is hurt or has cast, and the attributes and skills do not. Every field in both blocks, and the purse, agree with what the game prints on F1 to F5 for a save loaded back into it.

An item with no equipment slot, or whose slot is already taken, is placed in the first panel slot whose id is zero. [items.md](items.md) holds the slot masks and the equipment offsets. The second word of a slot is the item's own state, which for a container is its record number in section 2.

## Section 1, the seen grid

One bit per cell of the world, in the same geometry as the clue book's tables at `WORLD.DAT 0x3C4F02`: 7 areas of 24 bands, and a band is 20 levels of 40 cells, so 5 bytes to a level and 100 to a band.

    seen(x, y) = save[5000 + y*100 + x//8] >> (7 - x%8) & 1

with `x` and `y` counting across the whole world, so `area = y // 24` and `level = x // 40`. This is the marker at image `0x11268`, which divides `x` by 8, adds the row buffer's address, and ORs in `0x80 >> (x % 8)`. Its caller at `0x11361` first sets `0x8000` in the map cell's own word 6, so the bit is written once per cell rather than on every look.

What a party lights is two rows of three: its own cell and the two beside it, and the same three one step ahead. The dispatch at `0x112D6` marks the cell in front and then the party's own, and each of those marks itself and its two neighbors across. A row is written back to the file as it is marked, so walking a corridor writes one record a step.

## Section 2, containers

1,296 records of 34 bytes: a word, then eight four-byte entries. The reader at image `0xB323` walks the entries from record offset 2 and passes the first word of each to the item loader (`lcall 0x0F44C`), so an entry begins with an item id.

A character reaches its own by number: the id of the container item is at character offset 318 and this record number at 320. Every panel slot works the same way, since a slot's second word is the item's state and a container's state is its record here. All 1,296 are empty in a fresh game.

## Sections 3 and 4, bundles and what has been taken from them

`WORLD.DAT` section 10 is **1,000 records of 26 bytes**, and the low four hundred of them are bundles of loot: eight item ids at words 2 to 9 and a gold amount at word 10. Past about record 400 the section holds something else, text among it.

A record is a **bundle** rather than a chest, because a chest is only one of the ways the game hands one over.

* **Section 4 gives each bundle one byte, and each of its eight item slots one bit of that byte.** The bit is set when the item is handed over, by whichever route it leaves the bundle. A bit is never set where the record holds no item.
* **Section 3's bank 0 gives each bundle one bit**, set by the chest path alone. A bundle can therefore carry the section-4 byte without the bit.

The two are read together at image `0x2452` and `0x2576` into adjacent bytes, `DS:0x588E` for section 4 and `DS:0x588F` for section 3, with the record itself copied to `DS:0x5890`.

### Section 3 is banked

The table has **two entry points**, and they index section 3 differently.

| Entry | Section 3 index | Section 4 |
|---|---|---|
| image `0x252E` | the record number | the record number |
| image `0x25CB` | the record number **+ `DS:0xF48`** | not touched |

`DS:0xF48` is written once at startup, at image `0x0F076`, with the constant **1,008**, which is the size of section 4 and also one bit bank of section 3. Nothing else writes it, and only `0x25D3` reads it. Section 3 is therefore banked. A thousand bundles need 126 bytes, and the 1,059 bytes of section 3 have room for eight such banks.

Image `0x10BDA` decides which entry an object is recorded through, using a flag in the map object that names it. `[si+2] & 0x8000` takes the first entry and `& 0x4000` takes the second, and the object's number is at `[si+4]` in both cases. Three further bits (`0x1000`, `0x800` and `0x400`) are other kinds of object with no bit array at all. `0x800` is a monster, gated on a section 5 flag tested at image `0x10CC3` ([encounters.md](encounters.md)). Both entries are followed by `test [0x588F], al`, so the bit is read as "this one has already been dealt with".

The second entry has no per-item bits at all, so whatever reaches a bundle that way is recorded by its bank-1 bit alone.

## Section 5, which monsters are still on the map

626 bytes, so 5,008 flags, with a set / clear / test triple at image `0x127B4`, `0x1276B` and `0x127FB`, each taking the flag number in `ax`. The flag number is a **spawn id**: the 1,862 monsters the maps place are numbered 1 to 1,862, and each one's bit says whether it is still standing on its cell. [encounters.md](encounters.md) has the whole chain.

Set means the monster is not standing on its cell. Until it is killed it is in one of the eighty slots section 6 holds instead. Opening the Athaneum's south gate sets flags 37 and then 36, which are the two centipedes on adjacent cells of Yendor, where that gate leads: they come off the map as the party sees them. Death frees the slot at image `0x12CA6` and leaves the flag set, and nothing else clears it, so a killed monster does not return.

Nothing found reads the remaining 3,146 flags.

## Section 6, the monsters on the map

12,480 bytes written from `DS:0x122C`, which is the spawn table: 80 monster structs of 156 bytes each, the same ones [monsters.md](monsters.md) describes. A monster's name sits at struct offset `0x32`.

This is the one section that the game does not keep up to date as it plays. It is written to `CURGAME` only by the save itself, so `CURGAME` carries the copy made at launch until the first save.

## Reading one

    .venv/bin/python tools/saves.py SAVGAME1        # parse against this model
    .venv/bin/python tools/saves.py --layout        # the sections

[tools/save_probe.js](../tools/save_probe.js) plays a scripted session and copies `CURGAME` after every step. [tools/save_map.py](../tools/save_map.py) compares consecutive copies and names the offsets that moved. `--load=DIR` with `--start=load` puts save files on the emulated disk and opens one of them, so a save made elsewhere can be read on the game's own screens. F1 to F4 are the character sheets, and F5 is gold, food and nuore.

    bun tools/save_probe.js --out=tmp/save-probe/walk --steps='south:<<;open: ;out:^'
    bun tools/save_probe.js --out=tmp/sheets --load=tmp/saves --start=load \
        --slot=5 --steps='c1:!f1;w:..;c2:!f2;w:..'
