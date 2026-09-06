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
| 0 | 318 x 198 | 23 | 0 | full-screen backdrops: the two title screens, the clue book's cover, the book pages and the panel grounds |
| 1 | 210 x 105 | 156 | 1,448,172 | the view's wall faces and its object faces from id 100 up, projectiles, interface panels ([view.md](view.md)) |
| 2 | 140 x 155 | 270 | 4,887,972 | monsters drawn tall, scenery, and the view's object faces below id 100 |
| 3 | 190 x 110 | 238 | 10,746,972 | monsters drawn wide, and the animation a cast draws, below |
| 4 | 224 x 74 | 28 | 15,721,172 | the view's floors, each a whole floor in perspective ([view.md](view.md)) |
| 5 | 224 x 62 | 14 | 16,185,300 | the view's ceilings and skies ([view.md](view.md)) |
| 6 | 56 x 136 | 70 | 16,379,732 | wall strips, struck-monster effects, and body armor on the paper doll, below |
| 7 | 32 x 32 | 180 | 16,912,852 | icons: portraits, effects and worn equipment, below |
| 8 | 16 x 16 | 340 | 17,097,172 | interface icons, then the item icons, below |
| 9 | 8 x 8 | 576 | 17,184,212 | the map's tiles, see [map.md](map.md) |

The game reads one picture by seeking to `base + n * size` and reading `size` bytes. Image `0x39ED` computes the seek as `count * index + base`, from a seven-word parameter block (handle, destination segment and offset, byte count, index, and a 32-bit base). The read follows at `0x3997`. The filename `PICTURES.VGA` is at `DS:0x969E`, which is the tail of that same block.

## Every run keeps a cache in expanded memory

**No picture is read twice in a row, and none of them lives in conventional memory.** Each run table entry carries a cache of its own, and the blitter goes through it rather than through the file. Six more fields of the sixteen are this:

| Offset | Field |
|---|---|
| `+0x00` | segment of the cache's own array of records |
| `+0x02` | how many records the array holds |
| `+0x06` | the round-robin cursor, a byte offset into that array |

A record is six bytes: the picture number at `+0`, the first EMS **logical page** it sits on at `+2`, and its offset inside the page frame at `+4`.

**The lookup is image `0x1AACD`.** It walks the array comparing `DS:0x0FC3` against each record's own number. On a hit it writes that record's first page and the three after it into `DS:0x58D8` and maps all four with `INT 67h AX=5000h`, stopping early where the page number passes the run's last at `DS:0x0FA8`, and hands back the record's offset. That is what makes a redraw cost nothing: the picture is already in expanded memory and only the mapping changes.

**A miss replaces the record the cursor names.** Image `0x1AB18` takes the record at `+0x06`, steps the cursor six bytes and wraps it at the end of the array, writes the wanted number into the record, fills the `PICTURES.VGA` request block at `DS:0x9692` from the run's own fields, and reads. So a run's cache is round robin, not least-recently-used, and a walk longer than the array evicts what it is about to want again.

**This is what the game needs EMS for.** `README.DOC` asks for `EMM Ver 4.0` and 1 MB, the startup enforces it, and codes 4, 5, 6 and 12 of the abort table are the four ways that can fail ([world-dat.md](world-dat.md)). The pictures are 17 MB and the caches are where the working set sits.

[tools/pictures.py](../tools/pictures.py) reads the table.

## Run 3 is monsters and cast animations

The monsters take 140 of the 238 in fourteen blocks of ten frames: 0 to 39, 90 to 169, 190 to 199 and 228 to 237. The cast animations take 38 more, out of two branches of the dispatcher ([spells.md](spells.md)):

| Numbers | Frames | Spells |
|---|---|---|
| 80 to 89 | 10 | POISON CLOUD, DISEASE CLOUD, BALL OF FIRE, FROZEN EXPLOSION, BALL OF POWER |
| 200 to 204 | 5 | SHRAPNEL |
| 205 to 210 | 6 | HOLY ROLLER, RANGER'S ROCK, METEOR |
| 211 to 215 | 5 | BALL OF ELECTRICITY |
| 216 to 221 | 6 | SWARM OF INSECTS, SWARM OF KILLER BEES |
| 222 to 227 | 6 | TORNADO, FIRE WIND |

**Run 3 is finished.** The monsters take 140, the cast animations 38, and the intro's fifth scene takes 40 to 79, which is Zamora at his forge over four beats of 7, 5, 23 and 7 frames ([creation.md](creation.md)). 170 to 189 are twenty pictures of one palette entry, blank fill.

## What the three sparse runs hold

**Run 0 is 23 full-screen backdrops and 16 of them are named.** The intro takes 8 to 12 and the ending 13 and 14 ([creation.md](creation.md), [quests.md](quests.md)); the rest are named at a call site, and picture 7 through `DS:0x0E98`, which is the clue book's own backdrop word: image `0x06995` writes 7 and seven other sites write 6, and image `0x08C03` draws whichever is there. What is left is seven, and a contact sheet reads them:

| Number | What it shows |
|---|---|
| 15 | an order form: `1-800-4WEBTEC`, `Yendor 3 Only $24.95`, `Available on CD-ROM and on-line at BUYDIRECT.COM` |
| 16 | the WebTec Technologies splash |
| 17, 18, 19 | three scenes: two figures in a stone room, figures in snow, a blue face beside a red-robed figure |
| 22 | a help screen, the F1 statistics panel labeled, over `PRESS F5 AT ANYTIME TO ACCESS STATISTICAL INFORMATION` |

No record this project reads names any of the seven, and neither does a literal at a draw site.

**Run 1's 24 are wall faces and a logo.** 35 to 45 are eleven frames of the SW Games logo assembling, which is the still run 0 picture 0 animated; 4, 13, 15, 24, 73, 92, 110, 112, 129 and 131 are wall and doorway faces no terrain id names; 135, 147 and 155 are projectile shapes no weapon or spell names.

**Run 5's 2 and 3** are two of the fourteen ceilings and skies that no terrain record names.

## What is blank

**60 pictures are a single palette entry over the whole frame**, which is fill at the end of a run rather than artwork: run 1's 134, run 2's 253, run 3's 170 to 189, run 6's 69, run 7's 152 to 179 and run 8's 331 to 339. Run 9 has 431 more, which is the tile bank's own unused tail. Counting them apart is what takes runs 2, 3, 4 and 9 to nothing left over.

Run 6's 47 is the exception that is not fill: it is one entry over the frame and it is drawn, as the ground four rain spells lay down before their cycle ([spells.md](spells.md)).

## Which pictures the code names outright

Most of the artwork is named by a record: an item points at its icon, an enemy at its sprite, a terrain id at its wall face. The rest is named at the call site, by a literal, and [tools/picture_sites.py](../tools/picture_sites.py) reads those off the image. A draw takes two words, `DS:0x0FC5` for the run as an offset into the run table and `DS:0x0FC3` for the picture inside it, so a site that writes both as immediates names one picture and a site that loads `DS:0x0FC3` from a register draws whatever its caller worked out.

| Run | Sites | Pictures the code names |
|---|---|---|
| 0 | 16 | 0 to 6, 8 to 14, 20, 21 |
| 1 | 16 | 0, 1, 2, 3, 5, 6, 7, 8, 10, 11, 12, 34 |
| 3 | 6 | 40, 45, 50, 73, 80 |
| 6 | 8 | 0, 15, 20 |
| 7 | 11 | 0, 3, 11 |
| 8 | 20 | 0 to 6, 8, 10, 12, 13, 15, 17, 18, 20, 22, 24, 26, 28, 44, 108 to 113 |
| 9 | 14 | 0 to 20 |

Runs 2, 4 and 5 are drawn only from a record or a variable, so no site in them names a number.

**A literal belongs to the nearest selection before it, not to one inside a window.** A routine may set its run well before it names a picture, and `sites` reads 64 bytes forward from a selection, which walks past a second one: image `0x11C1B` selects run 6, image `0x11C3F` selects run 9 twenty bytes later, and the literal 7 at `0x11C45` is run 9's. `picture_sites.paired` pairs backward instead and drops any pair whose run does not hold that number, which is what catches a pairing made across a routine boundary. [tests/test_picture_sites.py](../tests/test_picture_sites.py) holds every literal to the run it was selected under.

## Run 8 is the interface, then the items

The 631 item records name 263 of its 340 pictures, and the other 77 partition without a remainder.

| Numbers | What they are |
|---|---|
| 0 to 65 | interface: the mouse pointer at 0, direction arrows, framed panels, wall swatches and banners. PARTY MAP at 16 is the one item that reaches into this block |
| 66 to 330 | the item icons. All 631 records point inside this range, and 89, 91 and 93 are the three containers opened |
| 331 to 339 | nine pictures of 256 bytes of palette index 0, blank fill at the end of the run |

**Three numbers inside the item range belong to no record, and all three are a container opened.** 89 follows BACKPACK at 88, 91 follows BOX at 90 and 93 follows BAG at 92, and they are the only three of 66 to 330 no record names. Image `0x16800` draws a held container by adding one to the record's own artwork word, and its three callers are the character screen's three container slots ([items.md](items.md)).

## Run 7 is three kinds of icon, not one

**84 of its 180 pictures are accounted for and they are all portraits**: 65 the NPC records name, the eighteen of the creation gallery at 28 to 45, and the four the shipped roster carries. Drawn as a contact sheet the run falls into three blocks, and the portraits are only the middle one.

| Numbers | What they are | Named by |
|---|---|---|
| 0 to 16 | what a blow or a cure draws over the character it reached: sparkles, blobs, a gold crown, crossed marks, colored rings, a `$` | the attack table entry's `+2` ([combat.md](combat.md)), eleven of the seventeen, 2 of them the restoratives' ([spells.md](spells.md)); 12 and 13 are also the two-handed weapon on the paper doll |
| 17 to 27 | single objects: a shield, a cauldron, a sword, a bar | **undecoded** |
| 28 to 134 | faces | the creation gallery, the NPC records, the roster |
| 90 to 151 | helmets, boots and gauntlets, interleaved with the faces above | the armor properties entry's `+4`, for the head, feet and hands slots ([items.md](items.md)) |
| 152 to 179 | 28 pictures of one palette entry, blank fill at the end of the run | shape |

**A character's portrait is drawn at image `0x11AAD`**, which takes record offset 18 straight into the picture number ([saves.md](saves.md)). Image `0x145EA` draws the creation gallery, image `0x16C88` the four portraits across the conversation screen and image `0x1BA49` the intro's talking heads.

**The first block is the attack table's, drawn over a character's own portrait.** Images `0x03643` and `0x03676` select run 7 and take the picture from the entry a blow was queued with, `[di+2]` where `di` is the entry pointer the animation slot holds; `0x0368C` is the `0x0600` handler beside them and draws from run 8 instead. The slot names the corner, and the four corners are the four portraits ([combat.md](combat.md)). **Picture 2 is what every restorative draws**, since all 19 name entry 18: [tools/cast_probe.js](../tools/cast_probe.js) cast HEAL in the running game and 39 of the picture's 45 opaque pixels landed on the healed character's portrait exactly, the six left being the mouse cursor.

**The equipment is the paper doll on the character screen.** Image `0x161A8` draws one picture per worn slot, and the head, feet and hands slots all take theirs from this run: the armor properties entry's `+4`, plus one for a female character ([items.md](items.md)). 26 distinct values cover 90 to 149, and with their female forms they account for every number in that span. What 152 to 179 hold is **undecoded**, and so is the effect block at 0 to 11 and 14 to 16.

**179 of the 180 are accounted for.** Picture 1 is the only one nothing is known to ask for.

## Run 6 is three things at 56 by 136

| Numbers | What they are | Named by |
|---|---|---|
| 0 to 17 | the character's own body, one per gallery cell and sex | character record offset 20 ([saves.md](saves.md)), at image `0x1609E` |
| 18, 19, 24 | the effect drawn on a struck monster, light, medium and heavy | three constants at `DS:0x5480`, `DS:0x5482` and `DS:0x5484`, written once at image `0x0F14E` |
| 20 | the party panel's nine sunken boxes, three columns of three | a literal at image `0x170D9` |
| 21 | a sign reading THE TYRANTS OF THAINE | **undecoded** |
| 47 | the ground the rain falls on, one palette entry over all 7,616 pixels | spell offset 48 ([spells.md](spells.md)) |
| 48 to 52 | five frames of falling rain, the four places cycling out of step | spell offsets 50, 52 and 40 ([spells.md](spells.md)) |
| 69 | a rectangle of one palette entry | **undecoded** |
| 22, 23 | a wall seen almost edge on at the far left and right of the view | a terrain record ([view.md](view.md)) |
| 25 to 68 | body armor on the paper doll | the armor properties entry's `+4` for the body slot ([items.md](items.md)) |

**Which of the three is drawn is the damage as a share of the monster's health.** Image `0x188EA` takes ten percent of the monster's health field, rounded, and compares the damage at `DS:0x0F36` against it: at or under, it sets struct word `+0x0E` bit `0x8000`; over ten and at or under thirty percent, bit `0x4000`; over thirty, bit `0x2000`. Image `0x10451` reads those three bits back and picks `DS:0x5480`, `DS:0x5482` or `DS:0x5484`, which hold 18, 19 and 24 and are never written again. So the ladder has three rungs and reaches three pictures, not seventy.

**Where the splat lands is the drawing mode plus the monster's own pair.** Image `0x103F0` writes a corner per mode, and `0x10443` then adds records 54 and 56 to it:

| Mode | Corner | The position it draws |
|---|---|---|
| 9 | `-22, 34` | wide left |
| 10 | `25, 34` | wide middle |
| 11 | `82, 34` | wide right |
| 12 | `-7, 8` | tall left |
| 13 | `50, 8` | tall middle |
| 14 | `107, 8` | tall right |

Screen coordinates, so the viewport's own 8 comes off both. The six are the three hand-to-hand places of each run ([view.md](view.md)), and a monster out in the world draws through 10 or 13, so it takes the middle place's corner whatever cell it stands on and the splat is laid at one size. Image `0x10471` takes the near row's shade for it and `0x10477` the plain copy.

**Rendered, all six.** [tools/cast_probe.js](../tools/cast_probe.js) seats the fight rather than waiting for one: `--melee=3` copies a live monster out of its spawn slot into the three engaged buffers, writes each one's own drawing mode at `+0x0A`, which image `0x126A8` fills with 10 or 13 and the two either side are one below and one above, sets the hand-to-hand bit and marks one place struck per frame. A renderer driven from the table above then redraws the splat at every mode and diffs it. A pixie, which ships drawn wide carrying the pair `70, 30`, matches on **341 of 341 opaque pixels** through modes 9, 10 and 11; a fighter, which ships drawn tall carrying `35, 45`, matches on 341 again through 12, 13 and 14.

**One place at a time, because the draw order covers them.** A splat is laid inside its own monster's draw and the three are drawn in order, so a place marked alongside a later one has its splat painted over by that monster's body, and only the last of the three survives whole.

A swing landing is captured the same way and needs no seating: `--soften` leaves a monster 30,000 health and nothing to turn a blow aside with, and the frame the blow lands on carries picture 18 at screen `95, 97`, mode 10's `25, 34` plus the centipede's own `70, 63`, 341 of 341.

**69 of the 70 are accounted for.** 69 is one palette entry over the whole frame, and picture 21, a sign reading THE TYRANTS OF THAINE, is the only one nothing is known to ask for. All eight are identified by eye in the table above; what is missing is what asks for them.

**Picture 20 is the party panel's nine sunken boxes**, a 3 by 3 grid image `0x170D9` draws before it fills each box with an item icon out of run 8 ([view.md](view.md)).

**A base body is a whole panel, and the worn pieces are sprites.** Every pixel of the eighteen is opaque: the figure stands in the stone alcove the game's own character screen shows, and the alcove is part of the picture. The stone is one ramp per body, 2 on the nine that use it and 3 on the other nine, and that ramp fills 99 percent of the frame's border. The 164 worn pieces carry no ground at all, which is why only the bodies need cutting.

**Cutting the ground is a flood from the border, not a ramp test.** A figure may wear the ground's own ramp: body 6's clothing is ramp 2 on a ramp 2 ground, and a plain test takes 312 pixels of it away. Flooding the ramp inward from the frame's edge leaves every figure whole and strands 15 to 36 pixels of ground in the pockets between a forearm and a hip. `pictures.without_ground` does it.

**The paper doll is a base body with four pieces over it.** Image `0x1609A` draws the body first, taking the picture straight from character record offset 20, which is the cell of the creation gallery the portrait was picked from and therefore carries the sex. The four shipped characters resolve to cells 14, 7, 6 and 1 and each draws a figure of the right sex. Image `0x161A8` then draws the body armor over it out of this run and the head, feet and hands out of run 7 ([items.md](items.md)). All 164 items that fill a worn slot carry a picture and its female form, none of the 164 pairs is byte-identical and none is blank.

## A pixel is a group and a shade

One byte a pixel, row major, no compression. `0xFF` is transparent.

The other 255 values are palette indices split by nibble. **The high nibble picks one of sixteen groups of sixteen entries, and the low nibble picks the entry within that group.** Groups 0 to 12 each run from dark to light in one hue (group 0 gray, group 10 green, group 12 blue), so the low nibble is a shade. That layout is what makes a monster recolorable. Substituting one high nibble for another moves every pixel of a group into another group at the same shade, which costs sixteen bytes rather than a second copy of the artwork.

The palettes are in `WORLD.DAT` section 12. There are seven of them, each 768 bytes of 6-bit VGA DAC values, displayed as `(v << 2) | (v >> 4)`. The first palette draws the map, the monsters and the clue book's own monster pages.

### Group 13 twinkles

**Sixteen entries at index 208 turn on a timer of their own.** Image `0x0EC8B` holds them as four four-color ramps, blue, green, magenta and orange, each running dark to light, and one step moves every entry one place down its own ramp and wraps the darkest back to the lightest. The cursor at `DS:0x5376` runs 0 to 3, image `0x0ED91` reloads a countdown of five ticks each time it turns, and image `0x0E946` is the tick: the game hooks `INT 1Ch` at image `0x0E9E1` and never reprograms the timer, so a step is five ticks of 18.2 a second, about 275 ms. Image `0x0ED8C` hands the turned ramp to the DAC writer at `0x15837`, which waits for vertical retrace where `DS:0x536E` bit `0x800` is set. Image `0x1567F` turns the whole thing on as the world comes up, and nothing turns it off.

Run 7's sparkles, blobs and rings are drawn in this ramp, which is what makes a cast's animation a different color from one frame to the next. So is the sparkle an enchanted piece of armor wears on the paper doll ([items.md](items.md)), which is why it glitters. Measured: of the twenty frames [tools/cast_probe.js](../tools/cast_probe.js) kept of a heal, two hold the picture at the file's own indices and two hold it one place down every ramp.

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

**The word takes the immunity word's own layout.** A blow ORs `~immunity & its own effect mask` straight into it at image `0x0C68D`, so every bit the immunity word names can land there: the six conditions at 10 to 15 and the five damage types at 0 to 4 ([monsters.md](monsters.md)). The three the draw parks the cycle for are therefore bit 13 paralysis, bit 12 freezing and **bit 4 magic**, which is why a monster held by a magic effect stands on picture 9 the way a frozen one does.

The same three appear twice more in the monster's turn. Image `0x12869` takes the per-turn drain where any of `0xFC10` is set, which is the six conditions and magic, and image `0x12879` takes a second drain for `0x3010`, which is that trio again.

**An attack is pictures 6, 7 and 8, and it takes three draws.** The monster's turn sets bit 2, draws the view three times over, resolves the blow, then clears the bit and assigns the picture back to the first of the ten rather than stepping it there (images `0x00FEF` to `0x01150`). The stepper holds at 8 rather than running past, so a fourth draw would show 8 again. Three is what the turn spends.

**Picture 9 is the monster being struck, not the monster dying.** State bit 1 is what shows it, and three paths set it: the melee swing through the ladder at image `0x188EA`, the volley's own `0x0C6B6`, which ORs bits 0 and 1, and a cast at `0x0AEE6`, `0x1CD01`, `0x1CD6A` and `0x1D420`, each ORing bit 1 alone.

**Only the melee swing leaves a splat.** Bit 3 is what the draw at image `0x103E2` tests before it lays one down, and one instruction in the game sets it: `0x1892D`, `or [di+0xc], 0x0A`, the tail of the ladder that picks which of the three pictures to draw. Image `0x00E90` is the ladder's only caller and it is the swing, so a shot and a cast show the struck picture and leave nothing behind them. The three rung bits at `+0x0E` are the ladder's too, so they belong to the swing as well.

The draw shows 9 once and clears the bit, and the stepper still runs underneath, so the walk keeps its place in time and the picture it would have shown is skipped rather than held over. Picture 9 stays only while bit 4, 12 or 13 is set, which is the frozen or paralyzed monster.

**Nothing draws a death.** Image `0x0C57A` finds a slot whose health has reached zero, pays the party and zeroes the 156-byte slot in the same pass, so the monster stops being drawn rather than falling over ([encounters.md](encounters.md)).

**The clue book paces the cycle, and the world does not.** Image `0x8040` redraws the monster on the F2 page with a counter at `DS:0x53E8` that runs 1 to `0x4F` and wraps: below `0x49` it steps the cycle, at `0x49` it snaps to picture 6 and sets bit 2, at `0x4A` it plays the monster's hit sound, `0x4B` to `0x4F` step through 7 and 8, and past `0x4F` it resets the counter, clears bit 2 and assigns the picture back. That page is also where it puts the monster, at `(8, 7)` for run 2 and `(6, 33)` for run 3, and its animating is why seven of the 71 captures under *The check* caught it partway through a refresh.

## Recoloring, and the blend

Three things happen to a monster's pixel between the picture and the screen, in the order image `0x1A9BE` runs them. The blitter's other passes take the shade alone.

**The blend, where word 98 bit 15 is set.** The bit puts 6 in `DS:0x0E28` (image `0x10378`), and the copy loops test that word before anything else (images `0x1A9C5` and `0x1AA55`): a pixel of `0xFF` is still passed over, and every other pixel is rebuilt as **the destination pixel's own color group with the source pixel's low nibble**. So the three monsters that carry the bit, GHOST, SPECTRE and PHASE TITAN, are drawn see-through: what is behind them keeps its hue and takes their shading.

That is **code**. The clue book's F2 page cannot tell it from the older reading, every pixel forced into group 0, because the page's ground behind the monster is group 0 throughout: under the transparent pixels of the picture each of the three matched to, [tools/verify_monsters.py](../tools/verify_monsters.py)'s own index reads group 0 on all 15,614 for GHOST and SPECTRE and all 13,209 for PHASE TITAN. The two readings therefore give that page the same 1.000, and only a monster drawn over the world separates them.

**The shade offset**, added next (image `0x1AA93`) and clamped inside the pixel's own ramp, exactly as it is for a wall or a floor. It applies to the blended pixel, so the group it clamps within is the ground's.

**The recolor list last** (image `0x1A8B5`). The blitter builds a table of up to 16 words from the six bytes at 64, `from` in the high byte and `to` in the low, and scans it: it stops at the first entry that is zero or whose `from` is above the pixel's own group, and a match moves the group and keeps the shade. Two things follow that the list's shape alone would not give. **A `to` of 15 makes the pixel transparent** rather than moving it, and **the scan needs the list in ascending order of `from`**, since a pair sitting after a higher one is never reached. All 38 lists in the game are in that order and none names 15, so neither reaches a player. Both are **code**, at `0x1A8D6` and `0x1A8CF`, and **shape** for the counts.

**Records 54 and 56 place the splat on the monster.** When the monster is struck, image `0x103F0` picks a corner off the drawing mode the monster itself took, image `0x10443` adds these two values to it, and the run 6 picture the damage ladder named is drawn there. The table of six corners is above, under run 6. The two values mostly belong to the artwork rather than to the monster. 37 of the 39 pictures a monster uses carry one pair across every monster that draws them, and 29 of the 45 monsters drawn tall share 35, 45. The two exceptions are run 3's picture 140, where BLACK DRAGON reads 70, 30 against 75, 40 for EMERALD and PURPLE DRAGON, and run 2's picture 80, where SORCERER reads 35, 45 against WIZARD's 40, 45.

Twenty five of the twenty seven ten-picture blocks in run 2 are monsters. The first block is scenery (trees, trunks, stalactites), and so is the block at 250. The placeholder record named `NOT USED` carries sprite 0, so it points at the trees.

Three monsters carry the blend bit: `GHOST`, `SPECTRE` and `PHASE TITAN`. The last shares `TITAN`'s block and, like it, carries no recolor list, so the bit is the whole of the difference in how the two are drawn: TITAN in the picture's own colors and PHASE TITAN in whatever it stands in front of. Their records are not otherwise the same: PHASE TITAN is a level higher and carries more of every combat statistic.

**The check.** The clue book's own F2 page draws the monster at a fixed place, `(8, 7)` for run 2 and `(6, 33)` for run 3. Rendering a record's picture and comparing it against a capture of that page therefore tests the run, the picture number, the palette and the recolor list at the same time. Of the 71 monsters the game lists, **64 match pixel for pixel**. The other seven match no single picture, because the page animates and the capture caught it partway through a refresh. On `ACOKNIGHT`, rows 15 to 105 match one step of the walk cycle and rows 106 to 148 match the next step. [tools/verify_monsters.py](../tools/verify_monsters.py) measures this.
