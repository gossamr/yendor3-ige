# The first-person view

How the game draws the world in front of the party: which cells it shows, where each one lands on screen, and what it draws them from. Settled findings only.

The frustum is **code**, at image `0x107E9`, and **measured**: [tools/view_probe.js](../tools/view_probe.js) reads the game's own 51-entry table with the party poked anywhere and turned, and standing in the Athaneum facing north all 51 entries name the cells the frustum names. All four facings are **measured** too, by the compass the game prints beside the view: `0x8000` reads NORTH, `0x4000` SOUTH, `0x2000` WEST and `0x1000` EAST. Facing reaches the drawing in two places and no others: the axis bit below, and an object's four faces. Everything else is indexed by the cell number in `DS:0x53DC`, so it is the same whichever way the party looks. The slot geometry and the artwork are **shape**, tables that divide their section exactly, and **rendered**: [tools/view_check.py](../tools/view_check.py) redraws the floor, the ceiling and the strips from the files and diffs a frame the game drew. The wall pass and the object passes are **code**. [README.md](README.md) defines the classifiers.

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

All of them call one blitter, image `0x19DC9`, which switches on the mode in `DS:0x53C8` to pick which slot table to read. `DS:0x0FC5` names the run, as that run's own offset into the picture table at `DS:0x7B5C` ([pictures.md](pictures.md)).

**The axis bit is bit 0 of every ceiling and floor picture number.** Image `0x1021D` takes it from the party's own cell where that cell names a ceiling, and from the facing otherwise: 0 for north and south, 1 for east and west. So a corridor is drawn from one picture along one axis and another along the other.

## Where a cell lands

**`WORLD.DAT` section 27 is the view's geometry**: 18,844 bytes at `0x40BF71`, loaded whole into one segment at startup. Image `0x0F3EB` asks for `0x49A` paragraphs, which is 18,848 bytes and the first count that covers it. Image `0x13088` writes eleven offsets into it at `DS:0x546A` upward, one per blitter mode. Three of them are the view's:

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

Mode 3 reads its shape a column at a time instead, walking down the source by the picture's width per pixel (image `0x1AA1A`), which is how it maps a flat wall face into a slot. That format is not read yet.

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

[tools/view_art.py](../tools/view_art.py) writes all of it to `data/view_art.json`, cropping the wall and object faces to their own pixels and keeping the corner each was cut from. `make view-art` runs it. Monsters and their shots are the fifth thing the viewport draws and are already exported, by `monster_art` and `projectile_art` in [extract.py](../tools/extract.py).

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

## The sky

**The sky's 32 colors are a window on a gradient, and the window slides with the time of day.** `DS:0x4D62` holds 143 colors, built at run time, running from black through deep blue, purple, red and orange to daylight blue and white. Image `0x0EDA0` copies 32 of them from `DS:0x4D62 + [0xD00F]`, uploads them to the DAC at index 224 (`0x0EE14`), and calls `0x178B0` to recompute the lighting.

Each call moves the cursor one color, `[0xD011]` being `+3` or `-3`, and `[0xD073]` counts 113 of them. Which way it goes is the clock: `0x0EDBB` compares `DS:0xCF7F` against 1080, six in the evening, and takes the window back from `0x14D` toward zero when it matches and forward from zero otherwise. `[0x540C]` bit `0x2000` marks a slide in progress, so a second call advances the window rather than starting again.

**It is driven from the clock, not from the draw.** The two callers are at images `0x0E93B` and `0x0EC5C`, on the path that advances time. Poking `DS:0xCF7F` and redrawing therefore moves the shading, which is read per draw, and leaves the sky alone.

Measured, standing in the Athaneum at nine in the morning: `[0xD00F]` reads `0x14D`, its maximum, so the window rests at the daylight end of the gradient. The 32 entries the game has uploaded, read back from `DS:0x49D0`, equal section 12's stored 224 to 255 shifted down one place, on all 31 that can be compared. **Section 12's stored ramp is the window one step further along than the game ever rests**, which is the whole of the one-step difference every frame in this document shows.

## What is not read yet

- **The wall pass's slot format**, modes 0, 3 and 4, and the object passes, modes 7, 8 and 13. The seven band numbers above place the same faces, so what these formats add is a frame reproduced pixel for pixel.
- **The visibility pass at `0x108DF`.** It sets the skip bit that hides cells behind walls. Until it is read, a redrawn frame needs a probe's reading of the bits.
- **The one step of the sky ramp** above.

## Reproducing

    bun tools/view_probe.js --json=tmp/view-north.json     # about 15 minutes
    PYTHONPATH=tools python tools/view_check.py
    make view-art
