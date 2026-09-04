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
| 1 | 210 x 105 | 156 | 1,448,172 | the view's wall faces and its object faces from id 100 up, projectiles, interface panels ([view.md](view.md)) |
| 2 | 140 x 155 | 270 | 4,887,972 | monsters drawn tall, scenery, and the view's object faces below id 100 |
| 3 | 190 x 110 | 238 | 10,746,972 | monsters drawn wide, and spell effects |
| 4 | 224 x 74 | 28 | 15,721,172 | the view's floors, each a whole floor in perspective ([view.md](view.md)) |
| 5 | 224 x 62 | 14 | 16,185,300 | the view's ceilings and skies ([view.md](view.md)) |
| 6 | 56 x 136 | 70 | 16,379,732 | the effect drawn on a struck monster |
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
| word 98, bit 15 | the pixel takes the ground's own group, see *The blend* below (image `0x10378`) |
| offsets 64..69 | up to six recolor pairs, `from << 4 \| to`, stopping at the first zero byte |

The record does not state that the six bytes are pairs. Their shape is the evidence. All 32 monsters that carry a list stop at the first zero byte, and in all 32 the groups being replaced are distinct. Neither of those would hold if the bytes were counts or coordinates. The reading also accounts for the picture groups exactly. FROST GIANT carries no list, while SNOW GIANT and FIRE GIANT recolor the same drawing. SLIME carries no list, while PURPLE SLIME swaps a single group, 9 for 1.

Within the ten pictures, the draw loop cycles 0 to 5 while the monster stands and walks. The picture it is on sits at offset 8 of the monster's struct in memory, which is the record copied to an origin 50 bytes later.

**How the cycle runs** is two more bits of word 96, read at image `0x15398`:

| Bit | What |
|---|---|
| 4 | run 0 to 5 and back down again, bit 3 remembering which way |
| 5 | run 0 to 5 and snap back to 0 |
| 6 | do not animate |

Every monster the game lists carries exactly one of bits 4 and 5, with 23 that bounce and 48 that loop, and no monster carries bit 6. Bit 3 is the stepper's own, set and cleared as a bouncing cycle turns around, and no record ships with it set.

**A picture is stepped once per draw of that monster.** The stepper is the last thing image `0x10337` does (image `0x104A1`), so how fast the cycle runs is how fast the view redraws and no interval is stored anywhere.

## What takes the cycle off 0 to 5

The state word at `+0x0C` of the monster's struct decides which of the ten the draw shows. Four of its bits reach the picture:

| Bit | What the draw does with it | Image |
|---|---|---|
| 1 | show picture 9 this draw, then clear the bit | `0x10393` |
| 2 | the attack is running: snap the cycle up to 6, and let the stepper walk it to 8 | `0x103A9`, `0x153BC` |
| 3 | draw the run 6 effect over the monster this draw, then clear the bit | `0x103E2` |
| 4, 12, 13 | park the cycle on 9 and set bit 1 again, without stepping | `0x10487` |

Bits 10 to 15 of that word are the six conditions in the layout the immunity word uses ([monsters.md](monsters.md)): a blow ORs `~immunity & its own condition mask` straight into it at image `0x0C68D`. So two of the three the draw tests are freezing and paralysis, and bit 4 is **undecoded**.

**An attack is pictures 6, 7 and 8, and it takes three draws.** The monster's turn sets bit 2, draws the view three times over, resolves the blow, then clears the bit and assigns the picture back to the first of the ten rather than stepping it there (images `0x00FEF` to `0x01150`). The stepper holds at 8 rather than running past, so a fourth draw would show 8 again. Three is what the turn spends.

**Picture 9 is the monster being struck, not the monster dying.** A blow that lands sets bits 1 and 3 together (image `0x1892D`, reached by `0x0C6B6` for a swing and `0x0AEE6` for a spell), and the same call picks which run 6 effect to draw from how much damage it did. The draw shows 9 once and clears the bit, and the stepper still runs underneath, so the walk keeps its place in time and the picture it would have shown is skipped rather than held over. Picture 9 stays only while bit 4, 12 or 13 is set, which is the frozen or paralyzed monster.

**Nothing draws a death.** Image `0x0C57A` finds a slot whose health has reached zero, pays the party and zeroes the 156-byte slot in the same pass, so the monster stops being drawn rather than falling over ([encounters.md](encounters.md)).

**The clue book paces the cycle, and the world does not.** Image `0x8040` redraws the monster on the F2 page with a counter at `DS:0x53E8` that runs 1 to `0x4F` and wraps: below `0x49` it steps the cycle, at `0x49` it snaps to picture 6 and sets bit 2, at `0x4A` it plays the monster's hit sound, `0x4B` to `0x4F` step through 7 and 8, and past `0x4F` it resets the counter, clears bit 2 and assigns the picture back. That page is also where it puts the monster, at `(8, 7)` for run 2 and `(6, 33)` for run 3, and its animating is why seven of the 71 captures under *The check* caught it partway through a refresh.

## Recoloring, and the blend

Three things happen to a monster's pixel between the picture and the screen, in the order image `0x1A9BE` runs them. The blitter's other passes take the shade alone.

**The blend, where word 98 bit 15 is set.** The bit puts 6 in `DS:0x0E28` (image `0x10378`), and the copy loops test that word before anything else (images `0x1A9C5` and `0x1AA55`): a pixel of `0xFF` is still passed over, and every other pixel is rebuilt as **the destination pixel's own color group with the source pixel's low nibble**. So the three monsters that carry the bit, GHOST, SPECTRE and PHASE TITAN, are drawn see-through: what is behind them keeps its hue and takes their shading.

That is **code**. The clue book's F2 page cannot tell it from the older reading, every pixel forced into group 0, because the page's ground behind the monster is group 0 throughout: under the transparent pixels of the picture each of the three matched to, [tools/verify_monsters.py](../tools/verify_monsters.py)'s own index reads group 0 on all 15,614 for GHOST and SPECTRE and all 13,209 for PHASE TITAN. The two readings therefore give that page the same 1.000, and only a monster drawn over the world separates them.

**The shade offset**, added next (image `0x1AA93`) and clamped inside the pixel's own ramp, exactly as it is for a wall or a floor. It applies to the blended pixel, so the group it clamps within is the ground's.

**The recolor list last** (image `0x1A8B5`). The blitter builds a table of up to 16 words from the six bytes at 64, `from` in the high byte and `to` in the low, and scans it: it stops at the first entry that is zero or whose `from` is above the pixel's own group, and a match moves the group and keeps the shade. Two things follow that the list's shape alone would not give. **A `to` of 15 makes the pixel transparent** rather than moving it, and **the scan needs the list in ascending order of `from`**, since a pair sitting after a higher one is never reached. All 38 lists in the game are in that order and none names 15, so neither reaches a player. Both are **code**, at `0x1A8D6` and `0x1A8CF`, and **shape** for the counts.

**Records 54 and 56 place an effect on the monster.** When the monster is struck, the draw loop picks a base position from the type of effect, adds these two values, and draws a picture from run 6 at that place (image `0x10443`). The two values mostly belong to the artwork rather than to the monster. 37 of the 39 pictures a monster uses carry one pair across every monster that draws them, and 29 of the 45 monsters drawn tall share 35, 45. The two exceptions are run 3's picture 140, where BLACK DRAGON reads 70, 30 against 75, 40 for EMERALD and PURPLE DRAGON, and run 2's picture 80, where SORCERER reads 35, 45 against WIZARD's 40, 45.

Twenty five of the twenty seven ten-picture blocks in run 2 are monsters. The first block is scenery (trees, trunks, stalactites), and so is the block at 250. The placeholder record named `NOT USED` carries sprite 0, so it points at the trees.

Three monsters carry the blend bit: `GHOST`, `SPECTRE` and `PHASE TITAN`. The last shares `TITAN`'s block and, like it, carries no recolor list, so the bit is the whole of the difference in how the two are drawn: TITAN in the picture's own colors and PHASE TITAN in whatever it stands in front of. Their records are not otherwise the same: PHASE TITAN is a level higher and carries more of every combat statistic.

**The check.** The clue book's own F2 page draws the monster at a fixed place, `(8, 7)` for run 2 and `(6, 33)` for run 3. Rendering a record's picture and comparing it against a capture of that page therefore tests the run, the picture number, the palette and the recolor list at the same time. Of the 71 monsters the game lists, **64 match pixel for pixel**. The other seven match no single picture, because the page animates and the capture caught it partway through a refresh. On `ACOKNIGHT`, rows 15 to 105 match one step of the walk cycle and rows 106 to 148 match the next step. [tools/verify_monsters.py](../tools/verify_monsters.py) measures this.
