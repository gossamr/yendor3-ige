# PICTURES.VGA

Every drawing in the game is in this one file. It holds the map's tiles, the monsters, the spell effects, the scenery behind a fight, and the interface. This document records settled findings only.

The run table and the ten runs are **shape**. Every run divides exactly and the last ends at the end of the file. Which fields draw a monster is **code**, at the image addresses given. The whole is **rendered**. Each monster is drawn from its record and diffed against a capture of the game's own F2 page. [README.md](README.md) defines the classifiers.

## Ten runs of fixed-size pictures

The file has no header and no per-picture record. It is ten runs laid end to end, each a flat array of pictures of one size, and a table in the executable states where each run starts and what shape its pictures are.

The table is at `DS:0x7B5C`, and it holds ten entries of sixteen bytes.

| Offset | Field |
|---|---|
| `+0x04` | bytes in one picture, always width x height |
| `+0x08` | width in pixels |
| `+0x0A` | height in pixels |
| `+0x0C` | where the run starts in the file, 32-bit |

The other fields are filled in at run time. `+0x00` holds the segment that the game allocates for the run's cache, and `+0x02` holds a value copied out of a ten-word table at `DS:0x4406` (image `0x121B9`).

A run ends where the next run begins, and the last run ends at the end of the file. The number of pictures in each run therefore follows from the table and the size of the file. Every run divides exactly.

| Run | Pixels | Pictures | Starts at | Holds |
|---|---|---|---|---|
| 0 | 318 x 198 | 23 | 0 | full-screen backdrops |
| 1 | 210 x 105 | 156 | 1,448,172 | |
| 2 | 140 x 155 | 270 | 4,887,972 | monsters drawn tall, and scenery |
| 3 | 190 x 110 | 238 | 10,746,972 | monsters drawn wide, and spell effects |
| 4 | 224 x 74 | 28 | 15,721,172 | |
| 5 | 224 x 62 | 14 | 16,185,300 | |
| 6 | 56 x 136 | 70 | 16,379,732 | |
| 7 | 32 x 32 | 180 | 16,912,852 | |
| 8 | 16 x 16 | 340 | 17,097,172 | |
| 9 | 8 x 8 | 576 | 17,184,212 | the map's tiles, see [map.md](map.md) |

The game reads one picture by seeking to `base + n * size` and reading `size` bytes. Image `0x39ED` computes the seek as `count * index + base`, from a seven-word parameter block (handle, destination segment and offset, byte count, index, and a 32-bit base). The read follows at `0x3997`. The filename `PICTURES.VGA` is at `DS:0x969E`, which is the tail of that same block.

[tools/pictures.py](../tools/pictures.py) reads the table.

## A pixel is a group and a shade

One byte a pixel, row major, no compression. `0xFF` is transparent.

The other 255 values are palette indices split by nibble. **The high nibble picks one of sixteen groups of sixteen entries, and the low nibble picks the entry within that group.** Groups 0 to 12 each run from dark to light in one hue (group 0 gray, group 10 green, group 12 blue), so the low nibble is a shade. That layout is what makes a monster recolorable. Substituting one high nibble for another moves every pixel of a group into another group at the same shade, which costs sixteen bytes rather than a second copy of the artwork.

The palettes are in `WORLD.DAT` section 12. There are seven of them, each 768 bytes of 6-bit VGA DAC values, displayed as `(v << 2) | (v >> 4)`. The first palette draws the map, the monsters and the clue book's own monster pages.

## A monster's pictures

A monster is ten consecutive pictures, in either run 2 or run 3. The 106-byte enemy record states which.

| Where | What |
|---|---|
| offset 26 | the first of the ten |
| word 96, bit 0 | set means run 3, clear means run 2 (image `0x10352`) |
| word 96, bit 2 | the recolor list at 64..69 applies (image `0x10337`) |
| word 98, bit 15 | draw every pixel in group 0, which is the gray group (image `0x10378`) |
| offsets 64..69 | up to six recolor pairs, `from << 4 \| to`, stopping at the first zero byte |

The record does not state that the six bytes are pairs. Their shape is the evidence. All 32 monsters that carry a list stop at the first zero byte, and in all 32 the groups being replaced are distinct. Neither of those would hold if the bytes were counts or coordinates. The reading also accounts for the picture groups exactly. FROST GIANT carries no list, while SNOW GIANT and FIRE GIANT recolor the same drawing. SLIME carries no list, while PURPLE SLIME swaps a single group, 9 for 1.

Within the ten pictures, the draw loop cycles 0 to 5 while the monster stands and walks. It shows 6 when the monster attacks (image `0x80B0`), and 9 when the monster dies (image `0x10397`). The current picture is held at offset 8 of the monster's struct in memory, which is the record copied to an origin 50 bytes later.

**How the cycle runs** is two more bits of word 96, read at image `0x15398`:

| Bit | What |
|---|---|
| 4 | run 0 to 5 and back down again, bit 3 remembering which way |
| 5 | run 0 to 5 and snap back to 0 |
| 6 | do not animate |

Every monster the game lists carries exactly one of bits 4 and 5, with 23 that bounce and 48 that loop, and no monster carries bit 6.

**Records 54 and 56 place an effect on the monster.** When the monster is struck, the draw loop picks a base position from the type of effect, adds these two values, and draws a picture from run 6 at that place (image `0x10443`). The two values mostly belong to the artwork rather than to the monster. 37 of the 39 pictures a monster uses carry one pair across every monster that draws them, and 29 of the 45 monsters drawn tall share 35, 45. The two exceptions are run 3's picture 140, where BLACK DRAGON reads 70, 30 against 75, 40 for EMERALD and PURPLE DRAGON, and run 2's picture 80, where SORCERER reads 35, 45 against WIZARD's 40, 45.

Twenty five of the twenty seven ten-picture blocks in run 2 are monsters. The first block is scenery (trees, trunks, stalactites), and so is the block at 250. The placeholder record named `NOT USED` carries sprite 0, so it points at the trees.

Three monsters carry the gray bit: `GHOST`, `SPECTRE` and `PHASE TITAN`. The last shares `TITAN`'s picture and recolor list, so the two are one drawing shown in two color groups. Their records are not otherwise the same: PHASE TITAN is a level higher and carries more of every combat statistic.

**The check.** The clue book's own F2 page draws the monster at a fixed place, `(8, 7)` for run 2 and `(6, 33)` for run 3. Rendering a record's picture and comparing it against a capture of that page therefore tests the run, the picture number, the palette, the recolor list and the gray bit at the same time. Of the 71 monsters the game lists, **64 match pixel for pixel**. The other seven match no single picture, because the page animates and the capture caught it partway through a refresh. On `ACOKNIGHT`, rows 15 to 105 match one step of the walk cycle and rows 106 to 148 match the next step. [tools/verify_monsters.py](../tools/verify_monsters.py) measures this.
