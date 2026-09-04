# The first-person view

How the game draws the world in front of the party: which cells it shows, where each one lands on screen, and what it draws them from. Settled findings only.

The frustum is **code**, at image `0x107E9`, and **measured**: [tools/view_probe.js](../tools/view_probe.js) reads the game's own 51-entry table with the party poked anywhere and turned, and standing in the Athaneum facing north all 51 entries name the cells the frustum names. All four facings are **measured** too, by the compass the game prints beside the view: `0x8000` reads NORTH, `0x4000` SOUTH, `0x2000` WEST and `0x1000` EAST. Facing reaches the drawing in two places and no others: the axis bit below, and an object's four faces. Everything else is indexed by the cell number in `DS:0x53DC`, so it is the same whichever way the party looks. The slot geometry and the artwork are **shape**, tables that divide their section exactly, and **rendered**: [tools/view_check.py](../tools/view_check.py) redraws the floor, the ceiling and the strips from the files and diffs a frame the game drew. The wall pass and the object passes are **rendered** as well, against thirteen captures, under *What a redrawn frame accounts for*. So is the character panel under the viewport, and so are the three places a monster in hand to hand stands. The monster pass out in the world is **code** alone; *A monster in the view* says what is missing. [README.md](README.md) defines the classifiers.

## The geometry is a table

Every slot's shape on screen is stored, and the artwork is drawn at its final size. A floor picture is a whole 224 x 74 floor already in perspective, and a cell copies its own trapezoid out of it. A wall face is a flat 210 x 105 wall, and a cell maps it into its slot a column at a time from a stored list of steps.

The same geometry is also four numbers and a multiply, which *The rule behind the table* below gives.

## Which cells the view shows

The view is 51 cells: seven rows in front of the party, far row first.

| Row | Cells ahead | Cells across | Lateral offsets |
|---|---|---|---|
| 0 | 6 | 17 | -8 to +8 |
| 1 | 5 | 17 | -8 to +8 |
| 2 | 4 | 5 | -2 to +2 |
| 3 | 3 | 3 | -1 to +1 |
| 4 | 2 | 3 | -1 to +1 |
| 5 | 1 | 3 | -1 to +1 |
| 6 | 0 | 3 | -1 to +1 |

Row 6 is the party's own row, so its middle cell is the cell the party stands on. Because the rows run far to near, drawing them in table order is the painter's algorithm.

Image `0x107E9` builds this. It picks two byte strides off the facing word at `DS:0xCF73`, one step right and one step forward, and walks the map window with them from the first cell of row 0:

| Facing | | Forward | Right | Row 0 starts at |
|---|---|---|---|---|
| `0x8000` | north | `0, -1` | `1, 0` | x - 8, y - 6 |
| `0x4000` | south | `0, +1` | `-1, 0` | x + 8, y + 6 |
| `0x2000` | west | `-1, 0` | `0, -1` | x - 6, y + 8 |
| `0x1000` | east | `+1, 0` | `0, +1` | x + 6, y - 8 |

Right is forward turned clockwise in all four, which is what y counting south makes it. The four values are the ones [saves.md](saves.md) gives; `0x4000` is south, not east.

The strides are eight bytes a cell and `0x270` a row, so the map window is 78 cells wide with eight bytes to a cell. `DS:0x0FF9` and `DS:0x1001` are its origin in world coordinates.

## The table at `DS:0x708E`

Image `0x10873` copies each cell of the frustum into a 51-entry table of eight bytes, in row order. The table is 408 zero bytes in the executable's image: the game fills it in on every redraw, so it is read rather than derived.

| Offset | Field |
|---|---|
| `+0` | the cell's terrain id |
| `+2` | its object id |
| `+4` | the spawn slot standing on it |
| `+6` | flags: bit 0 skips the cell, `0x400` marks the object at `+4`, `0x8000` marks a cell the party has seen |

Bit 0 is set after the copy, by image `0x108DF` and the helper at `0x109FF` that sets it over a run of entries. That is what hides the cells a wall stands in front of.

`DS:0x53DC` counts the entries as a pass walks them, and the combat code indexes the same table with it ([combat.md](combat.md)): hand to hand reaches cell `0x31`, and a spell walks `0x32`, `0x30` and then `0x2F` down to `0x00`.

## The passes, in order

The viewport is 224 x 136 pixels at screen (8, 8), and the two halves meet inside it: the ceiling picture is drawn at (8, 8) and the floor at (8, 70).

Image `0x100CE` draws the view. It builds the table, sets the skip bits, then:

| What | Image | Mode | Run | Picture from |
|---|---|---|---|---|
| the sky, whole, at screen (8, 8) | `0x1026D` | | 5 | the axis bit alone |
| the floor, whole, at screen (8, 70) | `0x1028F` | | 4 | bit 0 of the party's own floor number |
| every cell's floor | `0x10299` | 1 | 4 | terrain record `+0` |
| every cell's ceiling | `0x10153` | 2 | 5 | terrain record `+2` |
| every cell's walls | `0x104A8` | 0, 3, 4 | 1 | terrain record `+4` |
| the strips either side of the view | `0x10732`, `0x10776` | 6 | 6 | terrain record `+6` |
| every cell's objects | `0x104A8` | 7, 8, 13 | 1, 2 | the object record |
| every cell's monster | `0x1079B` | 10, 13 | 2, 3 | the enemy record |

All of them call one blitter, image `0x19DC9`, which switches on the mode in `DS:0x53C8` to pick which slot table to read. `DS:0x0FC5` names the run, as that run's own offset into the picture table at `DS:0x7B5C` ([pictures.md](pictures.md)).

**The axis bit is bit 0 of every ceiling and floor picture number.** The ceiling pass ORs `DS:0xF32` into it (`0x101DE`) and the floor pass `DS:0xF3A` (`0x1030D`). Image `0x1021D` fills both from the party's own cell, whose offset in the map window `DS:0x537A` holds: the ceiling word's bit 0 where the word is nonzero, else 0 facing north or south and 1 otherwise, and the floor word's bit 0. **Measured**, on a walk: [tools/view_probe.js](../tools/view_probe.js) stepping the party north from the Athaneum's courtyard reads `DS:0xF3A` as 1, 0, 1 on 307, 306, 307 and both words as 1 on a 305, and the frame at each step matches the redraw on every pixel. The room ids come in pairs whose words differ in that bit, so a step flips every floor in view between two pictures, which is the game's cue that a step landed. A position the probe pokes leaves `DS:0x537A` on the cell last stepped to, so a poked frame draws with that cell's bits, floor 0 and the ceiling's by facing in every poked capture here, and the checks below draw poked stops that way.

## Where a cell lands

**`WORLD.DAT` section 27 is the view's geometry**: 18,844 bytes at `0x40BF71`, loaded whole into one segment at startup. Image `0x0F3EB` asks for `0x49A` paragraphs, which is 18,848 bytes and the first count that covers it. Image `0x0F07C` writes eleven offsets into it at `DS:0x546A` upward, and the dispatch at `0x19DC9` pairs each blitter mode with one of them. Three of them are the view's:

| Mode | At | What it draws |
|---|---|---|
| 1 | `0x0386` | the floor half, from screen row 70 |
| 2 | `0x0BF2` | the ceiling half, from screen row 8 |
| 3 | `0x13B6` | the wall faces |

Each opens with **51 six-byte records**, one per cell:

    +0  uint16  x, in the half's own picture and on screen alike
    +2  uint16  y, the same
    +4  uint16  where this cell's shape is, or 0 for a cell the pass skips

Modes 1 and 2 read the shape as **one six-byte record per scanline**, ending at a length of zero:

    +0  int16  pixels to copy on this row, 0 ends the list
    +2  int16  added to the source and the destination alike once the row is copied
    +4  int16  not read by this pass

So a slot is a trapezoid: a length per row, and a step that walks its left edge. The source and the destination share the same x and y, which is what makes the picture a whole floor rather than a tile: mode 1 draws at screen (x + 8, y + 70) and mode 2 at (x + 8, y + 8), and both read the picture at (x, y). Image `0x1A015` is the loop.

Each half draws 43 of the 51 slots. Row 1's outer four cells on each side fall outside the viewport and carry a shape offset of zero.

**Modes 0, 7, 8 and 13 read a two-level list** (image `0x19F39`, and `0x1A1A3` and `0x1A235` for the object modes, which pick their table and fall into the same walker). The list opens with a pointer to a row list and continues with a column list, both runs of six-byte records ending at a word of zero:

    +0  int16  repeat
    +2  int16  draw: pixels copied from consecutive source pixels
    +4  int16  skip: source pixels passed over after them

A row record draws `draw` destination rows from consecutive source rows and then skips `skip` source rows, `repeat` times; a column record does the same along a row, and one column list serves every row (image `0x1A98E`). The terminator is one word, so the walker's six-byte read at it takes in the next list's head, which is harmless. A face two cells ahead is `(16, 4, 1)`, `(1, 1, 0)`, `(12, 3, 1)`, `(1, 1, 0)`, `(16, 4, 1)` across and `(8, 4, 1)`, `(1, 1, 0)`, `(6, 3, 1)`, `(8, 4, 1)` down: 166 by 83 from 210 by 105. The source starts at the picture's top left, and a transparent pixel advances the destination without writing.

**Modes 3 and 4 read column records** (images `0x1A09F` and `0x1A121`):

    +0  int16  count: destination columns drawn from this record
    +2  int16  step: source columns passed over after each of them
    +4  ...    a row list as above, ended by one zero word, or a zero word alone

Each column draws the record's row list down from the picture's top (image `0x1AA1A`), then the source moves on by one column plus `step`. After a record the destination drops one row in mode 3 and rises one in mode 4, which is the slant of the top edge, and the next record begins two bytes past the zero. A record whose list is empty only moves the source by its step. The side face one cell ahead is eleven records of two columns, steps alternating 9 and 8, whose lists run 105, 103, 101 and so on down to 85 rows.

[tools/view.py](../tools/view.py) reads all four tables as `faces`, and `tests/test_view.py` holds the front lists to the widths and heights the rule below gives. Mode 4 raising the destination is what makes a right-hand face's top edge climb toward the party.

**The wall pass walks a row in a fixed order** (image `0x104A8`): the left half from the outside in, then the right half from the outside in, then the middle cell last, so the middle's front face covers whatever the side faces beside it drew. For each cell it draws the front face in mode 0, then a side face in mode 3 or 4 only where the cell toward the center names neither a wall face nor a strip (`0x10520`), then the object: mode 8 with the front table for ids 200 and up, mode 7 for 100 to 199, mode 13 with run 2 for the rest (`0x10699`); then the monster standing on the cell, if there is one. Two things there are not read: a cell flag `0x2000` makes the pass draw a second front face from the record's first word (`0x10633`), and an object whose face is `DS:0xEA2` under flag `0x1000` draws picture 5 over itself (`0x106DC`).

**Mode 6 needs no shape at all.** It takes its place from mode 3's own table, the `x` and `y` of the same cell, and copies a fixed rectangle: 7 pixels a row for `0x71` rows, from the column `DS:0x53E2` names (image `0x1A055`). The pair of cells either side of the view take the two halves of one 14-column strip, the first from the record's own column and the second from that column plus 7 (`0x10723` and `0x10764`).

## The rule behind the table

The two halves meet at viewport row 62, which is the horizon, and **one cell is four pixels wider for every row away from it**.

The floor's rows count out from 61.5 and the ceiling's from 62.5, the half pixel two integer tables cannot both hold, so the floor's width at its own row *y* is `4y + 2` and the ceiling's is `250 - 4y`. At the near edge, 53 and a half rows below the horizon, one cell is 214 pixels across, and the viewport's own 224 clips anything wider.

Where each row of cells ends, counted in rows from the horizon:

| | 0 ahead | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|---|
| floor | 53 | 42 | 32 | 22 | 13 | 4 | 0 |
| ceiling | 52 | 41 | 31 | 21 | 12 | 3 | 0 |

Those seven numbers place every wall face: the face between the party's cell and the one ahead stands 53 rows above and below the horizon and 214 pixels wide, and the sixth face is three rows from the horizon. A projection of a floor plane keeps `row x distance` constant. Taking the faces as half a cell, one and a half, and so on, that product runs 26.5, 63, 80, 77, 58.5 and 22, so the row spacing is drawn and the width rule alone is perspective.

`tests/test_view.py` holds the stored table to this rule on the middle cell of every row.

## The artwork

The runs are [pictures.md](pictures.md)'s. What the view draws from them:

| Run | Pixels | What the view takes | How many |
|---|---|---|---|
| 4 | 224 x 74 | floors, each a whole floor in perspective | all 28 |
| 5 | 224 x 62 | ceilings and skies, the same the other way up | 12 of 14 |
| 1 | 210 x 105 | wall faces, drawn flat | 15 |
| 6 | 56 x 136 | strips, a wall seen almost edge on at the far left and right | 2 |
| 1 and 2 | 210 x 105, 140 x 155 | object faces, run 1 from object id 100 up and run 2 below it | 122 |

A terrain record is 12 bytes and every one of them is now read. Four are pictures, one is a column into the fourth, and the last is the map tile [map.md](map.md) reads:

| Offset | Holds |
|---|---|
| `+0x00` | the floor, run 4, bit 0 the axis bit |
| `+0x02` | the ceiling, run 5, bit 0 the axis bit; zero means the sky |
| `+0x04` | the wall face, run 1; zero means the cell draws no wall |
| `+0x06` | the strip, run 6; zero means the cell draws none |
| `+0x08` | the strip's first column, one of 0, 14, 28 and 42 |
| `+0x0A` | the map tile, run 9 |

An object record is ten bytes and the first eight are **four view pictures, one per facing**, in the order image `0x10668` tests them: north, south, east, west. Its `+0x08` is the map tile. So an object draws a different picture from each side.

That is **measured**. Standing the party on all four sides of one object and looking in, the frames pair the way the record does. Object 104, a well, holds `52, 52, 53, 53`, and its north and south frames agree on 98.7% of the viewport against 32.4% between north and east. Object 101, a bed, holds `17, 16, 19, 18`, and every pair of its four frames agrees on 21 to 23%: a headboard from one end, the mattress from the other, and a different drawing from each side. What the pairs disagree on is the cells behind the object, which are not the same cells.

[tools/view_art.py](../tools/view_art.py) writes all of it to `data/view_art.json`, cropping the wall and object faces to their own pixels and keeping the corner each was cut from. `make view-art` runs it. Monsters and their shots are the fifth thing the viewport draws, and `monster_art` and `projectile_art` in [extract.py](../tools/extract.py) write a still of each to `data/monster_art.json` and `data/projectile_art.json`.

## A monster in the view

**A monster is drawn after the cell's object, by its own pass.** Image `0x1079B` runs at the tail of the row helper the wall pass calls, once per cell, and draws where three tests pass: the cell's index in `DS:0x53DC` is `0x11` or more, the cell's flags at `+6` carry `0x400`, and the spawn slot at `+4` resolves to a live monster (`0x126EE`, or a slot claimed at `0x125E6`). So **the far row draws no monster**: the first 17 entries are row 0, six cells ahead. Cell `0x31`, the party's own, is skipped too, and the three monsters in hand to hand are drawn there instead by the pass at `0x107CE`, which walks the structs at `DS:0x54B8`, `0x5554` and `0x55F0`.

**The monster's blitter mode is 10 or 13.** Image `0x126A8` sets it when the slot is claimed: 10 where the record's word 96 carries bit 0, which is the monster drawn wide from run 3, and 13 otherwise, drawn tall from run 2 ([pictures.md](pictures.md)). It is held at `+0x0A` of the 156-byte monster struct, and image `0x10337` copies it into `DS:0x53C8` before the blit. Mode 13 is the same table the small objects use, and both draw a 140 x 155 picture.

**The eleven tables, and which mode reads which.** Image `0x0F07C` writes them at `DS:0x546A` upward and the dispatch at `0x19DC9` picks one per mode, so the mode is not the index:

| Mode | At | Walker | What it draws |
|---|---|---|---|
| 0 | `0x0000` | `0x19F39` | wall front faces, and object faces for ids 200 and up |
| 1 | `0x0386` | `0x19FC0` | the floor half |
| 2 | `0x0BF2` | `0x19FDF` | the ceiling half |
| 3, 4 | `0x13B6` | `0x1A09F`, `0x1A121` | wall side faces, left and right of center |
| 6 | `0x13B6` | `0x1A055` | the strips, from mode 3's own corners |
| 7 | `0x3B76` | `0x1A1A3` | object faces, ids 100 to 199 |
| 8 | `0x0000` | `0x1A1A3` | object faces, ids 200 and up |
| 9, 10, 11 | `0x3CA8`, `0x3DF2`, `0x41D2` | `0x1A235` | a monster drawn wide |
| 12, 13, 14 | `0x4316`, `0x4460`, `0x4858` | `0x1A235` | a monster drawn tall, and object faces below id 100 |

Each is the same 51 six-byte corner records and two-level lists the object faces use, so a monster is placed and scaled the way an object face is. **Mode 10 fills 24 of the 51 cells and mode 13 fills 22**, both starting at cell 21. The pass's own floor is cell 17, and the four cells between are row 1's outermost, which fall outside the viewport the same way they do for the floor and ceiling halves. Mode 13 also skips the two cells beside the one ahead and the two beside the party, so a monster drawn tall standing diagonally adjacent is drawn nowhere. The middle cell of each row:

| | 5 ahead | 4 | 3 | 2 | 1 | 0 |
|---|---|---|---|---|---|---|
| mode 10, from 190 x 110 | 13 x 7 | 45 x 26 | 78 x 45 | 114 x 66 | 150 x 87 | 190 x 110 |
| mode 13, from 140 x 155 | 13 x 15 | 33 x 35 | 55 x 57 | 80 x 82 | 102 x 105 | 140 x 136 |

**Each run's three tables are the three places a monster in hand to hand stands.** Only cell `0x31` carries an entry in modes 9, 11, 12 and 14, and the six entries put the picture at viewport x 0, 17 and 74 for the wide ones and 0, 42 and 99 for the tall, which is left, middle and right.

**A monster's place is the engaged buffer it sits in, and its mode is 9 or 12 plus that index.** Image `0x126A8` sets the mode to 10 or 13, the middle, when a spawn slot is claimed, and the three buffers at `DS:0x54B8`, `0x5554` and `0x55F0` are the left, the middle and the right. A first arrival is copied straight to the middle one (`0x12B77`). Every later arrival takes the left buffer and pushes the group right, `0x12BE1` and `0x12C86` stepping the mode up as they go and `0x12C02` stepping the newcomer's down; the shuffle at `0x12ED6` steps them back the same way after a death. So the occupancy stays centered: **one monster stands in the middle, two in the outer two with the middle empty, and three fill all three**. [combat.md](combat.md) has what decides whether a newcomer may join.

The placement is **rendered**. `tools/view_check.py --melee=CENTIPEDE` draws the monster at each of the three places, in each of its ten pictures, and diffs the pixels its own picture writes against a capture of the game in hand to hand. Against the three frames [tools/fight_probe.js](../tools/fight_probe.js) took of a lone centipede, the best match is the middle place every time, on **2,705, 2,733 and 2,705 pixels**, which is every pixel the picture writes in each. A lone monster is what those runs set up, and the middle is where this reading puts one.

## Lighting

One mechanism lights everything the view draws. It is a shade offset per row, applied to every pixel the blitter copies, so walls, floor, ceiling, objects and monsters all take it together.

**The offset is added to a pixel's low nibble** and clamped inside that pixel's own sixteen-color ramp, so a pixel moves darker or lighter within its hue and never changes hue (image `0x1AA93`). A negative offset darkens. **Pixels of `0xD0` and above are left alone**, which is the whole of the sky ramp: the sky does not darken by this.

The seven offsets, one per row, are assembled at image `0x178B0` in two steps.

**The distance fog comes first.** Where `DS:0xCEF9` bit `0x2000` is set the seven words are a fixed `-7, -6, -5, -4, -3, -2, -1`, from `DS:0x7A68`. Otherwise they come from the time of day: 37 records of 32 bytes at `DS:0x7556`, each a range of the clock at `DS:0xCF7F`, and the seven words at the matching record's `+0x12`. Those are zero from 08:02 to 18:21 and fall to `-10, -9, -8, -7, -6, -5, -4` at night.

That table is **measured**. Poking the clock and redrawing, the floor changes where the table says it changes: dark at 00:01, 05:00, 06:01 and 07:00, flat from 08:00 to 18:00, dark again at 20:00 and 21:01. 19:01 stays flat because that record's offsets are zero for the near rows, which are the rows those pixels belong to.

**A light then brightens it, row by row.** `DS:0x7A06` is 7 rows of 6 words, stride 12, and the light's level picks the column:

| | rung 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|
| 6 cells ahead | 10 | 8 | 5 | 4 | 3 | 2 |
| 5 | 10 | 8 | 5 | 4 | 3 | 2 |
| 4 | 9 | 8 | 5 | 4 | 3 | 2 |
| 3 | 9 | 7 | 5 | 4 | 3 | 2 |
| 2 | 8 | 7 | 5 | 4 | 3 | 2 |
| 1 | 7 | 6 | 5 | 4 | 3 | 2 |
| 0 | 6 | 6 | 5 | 4 | 3 | 2 |

The loop at `0x179FA` adds the row's number to the row's offset and clamps at zero, so a light lifts the dark toward none and never past it. Rung 1 cancels night outright, since its column is the night fog negated. A row whose offset is already zero is skipped, so a light does nothing in daylight.

**Which rung applies** is decided at `0x17971` by `DS:0xCEF7`, a word of light flags. Each rung answers to either of two bits, `0x200` or `0x8` for the first down to `0x4000` or `0x100` for the sixth. Eight instructions in the whole executable change that word, and they set three of the six: `0x2000` at image `0xFE29`, `0x800` at `0xFE35` and `0x400` at `0xFE41`, which are rungs 5, 3 and 2. Each also steps a counter at `DS:0xCF03`, `DS:0xCF07` or `DS:0xCF09`, all cleared together at `0xFE0A`, so a light is a timed effect rather than a state.

**A light standing in the world** would take the last three rungs. Image `0x17918` walks nine eight-byte entries at `DS:0x71C6`, which the game fills with the 3x3 block of cells about the party in the same shape as the view table, far row first. It looks for one whose object word is `DS:0x5486`, or that id plus one, two or three, and takes the match only if the party faces the matching way: `+0` north, `+1` south, `+2` east, `+3` west. The index of the match divided by three, plus one, is a level of 1, 2 or 3, which satisfies rungs 6, 5 and 4, so a nearer light is a brighter one.

`DS:0x5486` is written once in the executable, at image `0xF160`, and holds 47. **No cell in the world carries object 47, 48, 49 or 50**, and none carries those as terrain either, so this path cannot fire in the game as it shipped. It is a facility for a wall-mounted light that the maps do not use.

## What a redrawn frame accounts for

[tools/view_check.py](../tools/view_check.py) redraws the floor and ceiling passes from the files and compares them against a frame captured in the Athaneum, standing at x 460, y 46, facing north.

- All 51 entries of the game's own table name the cell the frustum names.
- Of the 17,422 pixels the floor and ceiling passes write outside the columns a wall stands in, 9,796 hold the index the capture holds, and on another 7,442 the capture holds one less. The 184 left over are all on cells that touch a wall.
- Both strips of the nearest pair match exactly, 767 opaque pixels each: cell 48 from picture 22 column 0 and cell 50 from column 7. Those two are drawn last, so nothing covers them. The strips of the farther pairs are drawn over by nearer cells and are not counted.

The 7,442 are the sky, and they are counted apart because the sky is not drawn with the stored palette. *The sky* below says what it is drawn with, and why every frame reads one step below section 12.

`tools/view_check.py --ledger` draws the whole view, every pass, from the lists above and diffs it against a probe ledger's captures index for index across the 30,464 pixels of the viewport, splitting the count by the pass that drew each pixel. On the thirteen poked stops beside objects, eleven match on every pixel, one on all but three of the sky step, and the other two differ on 25 pixels at the bases of bottles on a shelf and on 23 in a portal's sparkle, which the game may animate. On the walk under *Reproducing*, one poked stop and five walked to, four steps north from the courtyard and a turn east, all six match on every pixel but the sky step.

## The character panel

Under the viewport the game draws four places, one per character, 58 pixels apart across the 320 x 200 screen. Everything in a place is one of two drawings.

| What | Where | Size |
|---|---|---|
| the portrait | `(8 + 58 x place, 148)` | 32 x 32, run 7 |
| the health bar | `(9 + 58 x place, 181)` | 38 x 5 |
| the magic bar | the same x, 186 | 38 x 5 |
| the burden bar | the same x, 191 | 38 x 5 |

**The portrait is a picture number the character record holds at offset 18**, in run 7 of `PICTURES.VGA`, which is 180 pictures of 32 x 32. The four the game ships name 42, 35, 34 and 29. [saves.md](saves.md) has the rest of that record.

**A bar is one flat color filled from the left over a recess of index 6.** Health fills with index 89, magic with 202 and burden with 134. **The filled width is `38 x now / most`, dividing down.** A bar therefore shows nothing until `now` reaches a thirty-eighth of `most`. A character with no magic pool draws an empty bar rather than a full one, since `most` is zero and the width is taken as none.

Each bar measures a pair of the character record's own fields. Health and magic are read against their maximum column, and weight carried at offset 280 against capacity at offset 86, both of those in tenths.

That is **rendered**. `tools/view_check.py --panel` draws the four places from the roster `WORLD.DAT` ships and diffs them against a captured screen. Each of the fourteen frames the object walk took agrees on **6,376 of 6,376 pixels**, which is four portraits and twelve bars. All fourteen hold a party at full health. What they pin is the geometry, the four colors and the empty case. Of the fill rule they reach the two ends and the four burdens, 8.0 of 56.0, 6.5 of 59.0 twice and 7.5 of 56.0, which come out at 5, 4, 4 and 5 pixels.

Six sunken boxes sit between the portrait and the bars, two columns of three. They are empty in every capture there is, and what they hold is **undecoded**.

## The sky

**The sky's 32 colors are a window on a gradient, and the window slides with the time of day.** `DS:0x4D62` holds 143 colors, built at run time, running from black through deep blue, purple, red and orange to daylight blue and white. Image `0x0EDA0` copies 32 of them from `DS:0x4D62 + [0xD00F]`, uploads them to the DAC at index 224 (`0x0EE14`), and calls `0x178B0` to recompute the lighting.

Each call moves the cursor one color, `[0xD011]` being `+3` or `-3`, and `[0xD073]` counts 113 of them. Which way it goes is the clock: `0x0EDBB` compares `DS:0xCF7F` against 1080, six in the evening, and takes the window back from `0x14D` toward zero when it matches and forward from zero otherwise. `[0x540C]` bit `0x2000` marks a slide in progress, so a second call advances the window rather than starting again.

**It is driven from the clock, not from the draw.** The two callers are at images `0x0E93B` and `0x0EC5C`, on the path that advances time. Poking `DS:0xCF7F` and redrawing therefore moves the shading, which is read per draw, and leaves the sky alone.

Measured, standing in the Athaneum at nine in the morning: `[0xD00F]` reads `0x14D`, its maximum, so the window rests at the daylight end of the gradient. The 32 entries the game has uploaded, read back from `DS:0x49D0`, equal section 12's stored 224 to 255 shifted down one place, on all 31 that can be compared. **Section 12's stored ramp is the window one step further along than the game ever rests**, which is the whole of the one-step difference every frame in this document shows.

## What is not read yet

- **The visibility pass at `0x108DF`.** It sets the skip bit that hides cells behind walls. A frame drawn far row first covers them anyway; what the pass decides beyond the picture, which cells count as seen for the map, is not read.
- **The `0x2000` cell flag and the picture 5 overlay** in the wall pass, above.
- **The one step of the sky ramp** above.
- **The six boxes beside each portrait** in the character panel, above.

## Reproducing

    bun tools/view_probe.js --json=tmp/view-north.json     # about 15 minutes
    PYTHONPATH=tools python tools/view_check.py
    bun tools/view_probe.js --json=tmp/view-objects.json \
        --at=456,26,0x8000 --at=461,28,0x4000 --at=478,28,0x8000 --at=441,28,0x8000 \
        --at=444,37,0x4000 --at=454,28,0x8000 --at=465,28,0x8000 --at=444,27,0x1000 \
        --at=472,43,0x4000 --at=442,25,0x2000 --at=447,43,0x4000 --at=470,36,0x8000 \
        --at=478,25,0x1000                                    # one stop beside each of 13 objects
    PYTHONPATH=tools python tools/view_check.py --ledger=tmp/view-objects.json
    bun tools/view_probe.js --walk=up,up,up,up,right --json=tmp/walk/readings.json
    PYTHONPATH=tools python tools/view_check.py --ledger=tmp/walk/readings.json
    make view-art
    make view-panel                                        # the panel, and a monster in hand to hand
