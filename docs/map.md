# Map format

How the game stores its maps: the grid, the object layer, the tile artwork, the maps the clue book leaves out, the legend markers, and where each door leads. Settled findings only.

## Where the map data lives

Searching for a wall bitmask the size of the map region finds nothing, which is why this was first reached by tracing rather than by looking. There *is* one -- see the per-area table below, but it is a twentieth of the size searched for, because it is indexed by level inside a band rather than laid out per map.

The data is reached by tracing. `dosboxNode` runs the emulator in-process, and js-dos takes the path of its wasm shim from `emulators.wdosboxJs`, so a copy of that shim with one hook in `FS.read` ([tools/trace_fs.js](../tools/trace_fs.js)) records every byte range the game touches, timestamped. [tools/trace_map_load.js](../tools/trace_map_load.js) opens map pages with that tracer running and reports what each load read. Observed, not inferred:

Opening one clue-book map reads, every time:

| What | Where | Size |
|---|---|---|
| A shared table | `WORLD.DAT` `0x3D34FD` | 3,023 B, identical for every map |
| The map name lists | `WORLD.DAT` ~`0x83500` | three reads, the F1 list itself |
| **The area's own region** | `WORLD.DAT`, per area | **76,800 B, in 24 chunks of 3,200** |
| **A per-area grid table** | `WORLD.DAT` `0x3C4F02 + k x 2400` | **2,400 B, 24 rows of 100** |
| Tile graphics | `PICTURES.VGA`, per map | runs of 64-byte tiles (a "1,087-byte block" is 1,088 = 17 of them) |

The 76,800-byte regions are contiguous and sit in the **unindexed head of `WORLD.DAT`**, before the first section directory entry at `0x83400`. That is why nothing in the directory ever pointed at them. ACOKNIGHT'S CAVE reads `0x25800` and ATHANEUM reads `0x12C00`, and the spacing between them is exactly 76,800.

The 2,400-byte tables at `0x3C4F02` hold **one bit per cell**, as 5 bytes by 20 levels by 24 bands, which is 40 bits to a row. A level with no map holds five zero bytes in every band. A level with a map reads `ff` across, with partial bytes where individual cells differ.

    bit(area, level, band, cell) =
        world[0x3C4F02 + area*2400 + band*100 + level*5 + cell//8]
        >> (7 - cell % 8)  & 1

Bands run before levels, and the eight bits of a byte run from high to low across the row. `cell` counts from 0 over the full 40, so a drawn column c is cell c + 3. The bit picks a cell's tile together with its terrain id, which *The tile bank* below describes.

## What the region's chunks draw

[tools/probe_map_data.js](../tools/probe_map_data.js) blanks a byte range in `WORLD.DAT` before boot, opens a map page, and diffs the frame against a clean capture. On ACOKNIGHT'S CAVE LEVEL 1:

| Blanked | What changed on screen |
|---|---|
| chunk 0 (3,200 B at `0x25800`) | **exactly rows y 8–15**, x 24–295 |
| chunk bytes 0–1800 | nothing |
| bytes 1800–1900 | nothing |
| bytes 1900–1950 | x 24–63 (5 tiles) |
| bytes 1950–2000 | x 64–159 (12 tiles) |
| bytes 2000–2200 | x 160–295 (17 tiles) |

So **chunk *i* draws the 8-pixel band at y = 8 + 8*i**, and 24 chunks cover y 8 to 199. The map is **34 tiles wide by 24 tall, 8x8 pixels each, at x 24, y 8**. Only bytes 1900 to 2200 of each 3,200-byte chunk feed the visible page, and the first 1,800 do not. That fits a region serving more than one level, since ACOKNIGHT'S CAVE LEVEL 1 and LEVEL 2 read the same region.

## The map format

Tracing showed which bytes are read, and changing them showed what those bytes do. A stored map is a **40 x 24 grid of 8x8 tiles**, and the clue book prints 34 of those columns, at (24, 8). A tile id is a uint16.

    tile(band, cell) = uint16 at  base + band*3200 + level*160 + cell*4

- A **row is 40 cells of 4 bytes** (160 B). The clue book prints cells 3..36 and crops three at each end, but **all 40 are real squares**. Markers stand on them (Dwarven Homeland Map 1's ship is at cell 0), and the panel draws the whole row. Reading only the book's window cost three columns off every side of every map, and left seven legend lines with no square to sit on.
- A **3,200-byte chunk holds that row for 20 levels**, which is why blanking one chunk blanks exactly one 8-pixel band (y = 8 + 8*band) across the full width. Levels sit end to end along the band, so **level n+1 is literally the next 40 cells**: east-west adjacency between maps is the storage layout, not a lookup, and two neighboring maps abut exactly.
- An **area is 24 chunks = 76,800 bytes**, so 20 levels of a 40 x 24 map.
- **`0x83400 / 76800 = 7` exactly.** The map slots fill the unindexed head of `WORLD.DAT`, seven areas holding 140 slots, which is why nothing in the section directory ever pointed at them.

Ids are few to a page: Acoknight's Cave Level 1 uses four (6 = wall, 322/323 = a floor dither pair, 327 = one feature). A page reads the artwork it needs from `PICTURES.VGA` a tile at a time.

Rebuilt from the grid and the two files, **30,048 of 30,057 cells match the game's own rendering** across the 37 pages the clue book prints, 34 of them exactly.

[tools/pack_maps.py](../tools/pack_maps.py) writes each page to `data/map_pages.json` as its grid plus the 8x8 tiles it uses.

The residual on a correct page is the **markers**, meaning the yellow squares and NPC dots that the game draws on top. Those come from the other table found here. The 2,000 bytes before the legend labels at `0x3D3CCD` are **250 marker records of 8 bytes, one record per label**. Blanking them moves only marker pixels, and that is the shape that attributes a legend label to its map.

A marker cell never matches its id's artwork, because the marker is drawn over it. Which cells those are is in the marker records: each carries an area, level, row and column.

## The object layer

A cell is **four bytes holding two layers**:

    cell(band, cell) = (uint16 terrain, uint16 object)   at base + band*3200
                                                            + level*160 + cell*4

**The object word names its own artwork**, with no dependence on the terrain beneath it or on which map it is: all 128 object ids draw one tile each. The tile is composited over the terrain, its `0xff` pixels leaving the terrain showing, and an object whose tile has no transparent pixel replaces the cell outright.

An object covering more than one cell **repeats its id in each cell it occupies**. There is no size, extent or anchor field, and no cell without a record of its own: every cell it holds draws its tile independently. Object 145 on Acoknight's Cave Level 1 holds cells (8,18) and (8,19), and both draw tile 268616.

Fidelity is measured by drawing a page from the files and diffing it against the game's own, skipping the cells a legend marker is painted over and counting a cell as matching under any phase of the fire ramp.

## Which ids the picture file accepts

Ids **0 to 340** load. An id of 341 or above aborts before anything is drawn, printing `Problem with PICTURE.VGA.`, which is one of a table of `$`-terminated DOS error strings at image `0x18934`. The id is therefore validated against `PICTURES.VGA` at load time, and the accepted range is a property of that file.

The families that draw anything are the ones real maps use: roughly 0..33, 100..103, 200..208 and 300..340. Everything between draws the page's empty tile.

A page is 40 cells by 24 and the book prints 34 of the columns, so writing `0, 1, 2, ...` across it and opening it makes the game draw its whole id-to-artwork table in one boot. That is what `tmp/probe_tiles.js` does, and [tools/read_tiles.py](../tools/read_tiles.py) reads it back.

A cell draws only where its bit is set, so the sweep sets them. Once set, the three margin cells at either end of a row draw as well, carrying id 0, and they draw first: the first artwork a page needs is whatever id 0 draws, not whatever the sweep starts with.

## The tile bank in PICTURES.VGA

**A tile is 64 bytes: an 8x8 block of palette indices, one byte a pixel, row major.** `0xff` means transparent: the pixel underneath shows through.

They sit in a **flat bank** that starts at byte 20 of `PICTURES.VGA` and runs in 64-byte units to the end of the file, 269,079 units in total. The last 576 of those are the file's tenth and last run of pictures, which is the run that holds 8x8 art. See [pictures.md](pictures.md). A run of **145 non-blank tiles at 268503 to 268647**, at the head of that run, holds the map's artwork. It does not hold only the map's artwork. The same run carries interface art, including the portrait panel arrows and frames, so membership of the run does not make a tile a map tile.

    tile n  =  PICTURES.VGA[20 + n*64 : 20 + n*64 + 64]
    pixel   =  palette[index]              index != 0xff
               whatever is underneath      index == 0xff

A read that the tracer reports as 1,087 bytes is **1,088 bytes, which is 17 tiles**, because the tracer reports an inclusive end. Every observed read is a whole number of tiles.

**A cell draws one or two of them.** The cell's four bytes are `(uint16 terrain, uint16 object)`, with terrain first and object second. The terrain word picks a tile from the bank. A non-zero object word picks a sprite that is drawn over that tile, and the sprite's `0xff` pixels leave the terrain showing through. That is the whole of how a map page is drawn.

The order is settled by where the objects land. Reading the object as the word *before* the terrain draws each object one cell to the right of where the game puts it, and the object flag then agrees with the test "this cell's picture differs from its terrain's" on 76.6% of cells. Reading the object as the word *after* the terrain raises that agreement to 85.6%.

Compositing both out of the files reproduces **30,048 of 30,057 cells exactly** (marker cells excluded), and **34 of the 37 pages entirely**.

- **The palette is in `WORLD.DAT`.** Section 12 is 5,376 bytes: seven 768-byte VGA palettes of 6-bit DAC values, and the map screen draws with the first. [tools/tiles.py](../tools/tiles.py) reads it.
- **Indices 220-223 are a fire ramp the game rotates.** The four colors are `(207,93,0)`, `(223,146,36)`, `(239,195,73)` and `(255,243,69)`, and they cycle through those four indices: all four rotations appear across the clue-book captures, one phase to a page. The palette as stored holds `(255,243,109)` at index 223, which is the ramp at rest and not one of the four. So a tile drawn with these indices matches a still frame only under the phase that frame caught, and 224-231 is a blue ramp of the same shape.
- **63 of the 145 are fully opaque and 82 carry transparency.** A tile with a transparent pixel can only be drawn over something else, so terrain comes from the opaque tiles and sprites come from the rest. That divides the run by what a tile *can* be, rather than by what uses it. **52 are reached by a map**, counting terrain and objects together, and the remainder include the interface art. [tools/tile_sheet.py](../tools/tile_sheet.py) draws all 145 as one sheet.
- **An id chooses its tile outright**, with no area and no slot involved, as the next section describes. The cell's own bit in the table at `0x3C4F02` decides only whether the terrain draws at all. Where that bit is clear, the cell draws tile 19, which is the empty one, whatever its id.
- **An object's tile need not be transparent anywhere.** A solid one replaces its cell outright rather than sitting over it, so transparency distinguishes what a tile *can* be, not what an object is.
- **An object covering more than one cell repeats its id in each.** There is no size, extent or anchor field: the id is written into every cell it occupies and each of those cells draws the object's tile on its own terms. Object 145 on Acoknight's Cave Level 1 holds cells (8,18) and (8,19), and both draw tile 268616.

## From an id to a tile

The lookup is in `REGISTER.EXE`, static data loaded at startup and never re-read: no file access precedes a page's tile reads. [tools/tiles.py](../tools/tiles.py) reads it.

**An id is split by a hundred:**

    family = id / 100        index = id % 100

which is why the ids real maps use fall in 0..33, 100..103, 200..208 and 300..340. Each family has a `(base, last index)` descriptor, and the base points at an array of records, and the picture number is one of the fields they hold:

| | Descriptors | Record | Picture at |
|---|---|---|---|
| terrain | `DS:0x0002` | 12 bytes | `+0x0A` |
| object | `DS:0xC8E7` | 10 bytes | `+0x08` |

An index past its family's last falls back to the first record of the first family, which is what every id no map uses draws. An object whose picture is zero draws nothing.

The routines are at image `0x0BC98` for terrain and `0x0BCDB` for object. The map renderer calls them at `0x194F5`, one after the other, taking `[si]` as the cell's terrain and `[si+2]` as its object.

Read straight from the file, the rule reproduces **341 of 341 terrain ids** and **123 of the 128 object ids** that an earlier pixel probe had recovered. The five it differs on are ones the probe reported incorrectly, because the probe had attributed a legend marker's tile to them.

## How a page is loaded, and what the game caches

The game **reads each tile individually**, at `20 + tile * 64`. That is a 63-byte read landing exactly on a tile boundary, followed by 1,024 bytes. Booting a page that carries every id from 0 to 340 reads exactly the 36 distinct tiles that the rule predicts, with nothing extra and nothing missing.

In memory it keeps a **per-page tile cache** of 36 six-byte records:

    uint16  block index, or 0xFFFF for an empty slot
    uint16  0x017F        the buffer's segment
    uint16  offset        stepping 0x40, one tile a slot

Keyed by block index, in first-use order: an id is resolved before a record is written, and two ids sharing a tile produce one entry. [tools/read_cache.py](../tools/read_cache.py) finds it in a memory dump and [tools/verify_tiles.py](../tools/verify_tiles.py) holds the file's lookup to it.

Two rules fix what "first use" means:

- **Tile 20 belongs to the map screen**, not to any id. It is cached after every page's terrain, including pages where no id draws it.
- **The margin cells draw, and they draw first.** A row is 40 cells and the book prints 34, so the three cells at either end carry id 0. The first tile cached is therefore whatever id 0 draws.

## The map registry

`WORLD.DAT 0x83400` is **840 bytes: six per slot, for all 140**. It sits immediately after the map region, which ends exactly there (7 areas x 76,800 = 537,600 = `0x83400`). Each record is four ASCII characters and a uint16:

    bytes 0..3   the title's suffix, space padded
    bytes 4..5   high byte a flag, low byte an index into the name table

The low byte indexes the name table. The suffix qualifies the name:

    "0"           no suffix     ATHANEUM
    "1".."9"      LEVEL n       CASTLE OF BARIAG LEVEL 2
    "01".."010"   MAP n         THAINE MAP 10

**A zero name index means the slot holds no map.** 54 of the 140 slots hold a map, and areas 0 and 6 hold none at all.

- **Which slots are maps.**
- **What each one is called.** The clue book prints 36 of the 54, and for every one of those the registry's title is the string the game itself prints on the page. The other 18 it names too: THAINE MAP 2 through 10, YENDOR, TOWER OF OBVERSIA, THE HOLY ORDER, VISHAN'S STRONGHOLD LEVEL 1 and 2, UNDERGROUND TUNNEL, THE WAY OF THE ORDER, THE PLANE OF SOULS and CASTLE OF SLATOR LEVEL 2.
- **Which slot a page belongs to.** `fit_maps` scored CASTLE OF SLATOR LEVEL 2 onto area 3 level 14, which the registry calls SILVER MINE, two pages on one slot. The registry arbitrates, and the capture belongs to Silver Mine.
- **That two levels of one place share a name.** Both levels of Castle of Bariag carry index 9, and both levels of Vishan's Stronghold carry 23. The suffix is what separates them, which is why the name table holds 37 places for 54 maps.

Ten Thaine maps, spread across three areas at levels 6 to 9, are the reason the overworld looked like one page in a list of 37.

A second per-slot table is located immediately after the name tables, at `0x83dd0`: 280 bytes, **two per slot**, nonzero on exactly the 54 slots the registry names. What its value means is not settled.

## The legend markers, and which gold square belongs to which line

Each clue-book map draws gold squares and prints a legend beside it, and nothing on the page states which square belongs to which line. The marker table does.

The square itself is **bank tile 268523**, a gold bevel with no transparent pixel, so it replaces the cell it lands on rather than sitting over it. It belongs to the map screen and not to any id: it is loaded on every page, including pages where no cell draws it, which is why a marker cell never matches its id's artwork however right the grid is. `0x3D34FD` holds **207 eight-byte records**, one per legend line, and two of its four fields are positions in exactly the coordinate system the map data uses:

    field 1 = level * 40 + cell     a level's row is 40 cells wide
    field 2 = area  * 24 + row      an area is 24 bands
    field 3 = the caption's index in the label table

So a record names its own page *and* its own square. [tools/markers.py](../tools/markers.py) decodes it, and `data/map_marks.json` carries the result. The panel draws each line's number on its square, and numbers the legend to match.

The record's fourth field is the **slot number**, `area*20 + level + 1`. It duplicates what fields 1 and 2 already state. It matters mainly because it resembles a place id and is not one, since it names no map.

The reading depends on two facts.

- **The labels are packed NUL-terminated strings**, not the fixed 25-byte fields they resemble for the first hundred. The terminator drifts one byte right every few entries after that, so a fixed-stride reading returns text that is subtly wrong and then garbage. `markers.read_labels` walks the NULs.
- **The caption is field 3, not the record's own position in the table.** Field 3 runs 1..137, and markers share captions: a place like KINGDOM OF BARIAG is a marker on several maps.
- **QUARTZ CHAMBER's records put its legend on block 3 slot 8**, which the registry names THAINE MAP 9. Quartz Chamber itself is area 5 level 16.

Every marker the records place has a caption. A large minority of the legend lines belong to slots the book does not print.

The map page's title bar reads SELECT LEGEND OR ESC, and clicking a gold square prints its caption there. [tools/capture_legend.js](../tools/capture_legend.js) drives that. It requires the DOSBox-X backend, because plain DOSBox never delivers mouse coordinates, and it requires a double click, because a single click does not select.

## The 140 slots are one grid

A cell's place in the world is a single x and y across all of them:

    x = level * 40 + cell        y = area * 24 + band

which is how the party's position is stored ([saves.md](saves.md), header offsets 152 and 154) and how the seen-grid is indexed. So the slots are not 140 separate pictures but 20 levels across by 7 areas down, 800 by 168 cells. [tools/world_map.py](../tools/world_map.py) draws the lot as one image, and what it shows is which maps abut which: the outdoor areas make continuous landmasses and the buildings and mines sit apart.

## What the party may stand on

The step at image `0x032E9` happens only when two classifiers both return zero: `0x02EEA` on the cell's terrain word and `0x02F13` on its object word.

| Terrain id | | Object id | |
|---|---|---|---|
| `<= 1` | blocked | `200..399` | blocked |
| `2..99` | blocked | anything else | clear |
| `100..199` | clear | | |
| `200..299` | blocked | | |
| `300` and over | clear | | |

**Tinting the cells this calls clear draws the floor plan.** The Athaneum then shows its rooms and corridors, the Cave of Fire as the paths with the lava left out, Delia's Island as the island with the sea left out.

**Id 2 is a wall.** 434 of the Athaneum's 960 cells carry it, so a map is not mostly floor, and on a map that is mostly water the commonest id is water.

[tools/pack_maps.py](../tools/pack_maps.py) gives each page an `arrive` cell from this rule: the walkable cell nearest the middle, preferring one with no object on it, since an object the party can stand on may be a door and arriving on a door is arriving somewhere else.

## Where a door leads

The party's place in the grid is the pair `DS:0xCF75` (x) and `DS:0xCF77` (y). A step adds to both (image `0x032E9`), and a door writes both outright.

**Section 28 is the cell event table.** It is 26,472 bytes, read whole into the buffer whose segment is `DS:0xFF7`, and looked up at image `0x10D57`. It opens with a **column index**, one uint16 per world column starting at x = 40. Each entry is the offset of that column's list of six-byte records, sorted by y and terminated by `0xFFFF`.

    +0  uint16  y
    +2  uint16  kind, one bit
    +4  uint16  argument

The offsets are from the section's own start. It holds 2,597 records in six kinds:

| Kind | Records | Argument |
|---|---|---|
| `0x8000` treasure | 380 | a 26-byte record, gated on a `CURGAME` bit, which is what "already looted" means (image `0x0252E`) |
| `0x4000` container | 71 | image `0x025CB` |
| `0x2000` door | 139 | the destination record below, 1-based |
| `0x1000` person | 139 | the NPC's own index in the table at `DS:0x0EC8`, not 1-based, and records 0 and 140 stand nowhere |
| `0x0800` item | 1,862 | something lying on the ground |
| `0x0400` script | 6 | a hand-written handler. The one at image `0x0B704` draws Saxon's ship on Yendor's shore once a flag is set |

A `STAT = N` legend square is a person: that NPC's `+0x14` is the stat's offset in the character record's maximum block ([saves.md](saves.md)) and `+0x16` is N.

**`DS:0xBA95` is the destination table** the door kind indexes: 139 eighteen-byte records, ending where the flag-gate table at `DS:0xC45B` begins.

    +0x00 uint16  destination x        +0x0A uint16  -> DS:0xCF31
    +0x02 uint16  destination y        +0x0C uint16  -> DS:0xCF33
    +0x04 uint16  facing               +0x0E uint16  gate mask
    +0x06 uint16  sound                +0x10 uint16  flags, bit 0 -> DS:0xCF3F
    +0x08 uint16  -> DS:0xCF2F

Image `0x05512` reads it. It copies x, y and facing into the party's own words, rebuilds the map window and redraws. A record whose `+0x0E` carries either of the top two bits is gated. Image `0x055A3` walks the 22-byte records at `DS:0xC45B` looking for the door's own number, and tests the flag word that one of them points at.

A door records no source, and its destination is a pair of world coordinates rather than a slot number or an `(area, level)` pair.

[tools/links.py](../tools/links.py) reads both tables.

**`DS:0xB71F`** is a second, smaller table, nineteen 20-byte records keyed by a cell's *tile* rather than its position: matched on the terrain id when `+2` bit 15 is set and on the object id otherwise (image `0x0AE45`). A record with `+2` bit 14 teleports, taking x, y and facing from `+4`, `+6` and `+8`. These are the pads inside Acoknight's Cave, the Way of the Order and Vishan's Stronghold.
