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

Ten 500-byte slots. Slot 0 is a header, slots 1–5 are the created characters and 6–9 the four the game ships. `WORLD.DAT 0x41D72F`, the `PRE-CREATED PARTY` section, holds the same 5,000 bytes as a template. [creation.md](creation.md) reads the screens that fill a slot and pick the four that walk.

**`CURGAME`'s roster is written but never read.** KEEP CHARACTER writes the 5,000 bytes immediately, and SAVE writes them again. The only reads of `CURGAME` belong to the save routine, and they start at offset 5,000. Every launch truncates `CURGAME` and rewrites all 81,037 bytes, and NEW GAME does the same, both from the `WORLD.DAT` template. A character kept at the menu therefore survives a relaunch only if it is written into that template, which is what [tools/keep_characters.py](../tools/keep_characters.py) and the cabinet's **Keep characters** button do, for slots 1 to 5.

**Only two routines fill the roster.** Image `0x15130` reads it from `WORLD.DAT` section 32, the template: NEW GAME, and the launch rebuild. Image `0x0DC0C` reads it from a `SAVGAMEn` and writes the same bytes on to `CURGAME`: LOAD. Everything in the header slot travels with the characters, the container allocator's two words included.

### The header slot

The first bytes ship holding `PRE-CREATED PARTY`, and the name typed at a save slot is written over them.

The slot is the party's own state as the running game holds it, so an offset is a `DS:` address less `0xCEDD`, and every word another document names by its address is one of these: the light at `DS:0xCEF7` ([view.md](view.md)), the environment at `DS:0xCEF9` ([encounters.md](encounters.md)), the area at `DS:0xCF33` ([audio.md](audio.md)), the four skill handles at `DS:0xCF81` ([party.md](party.md)).

| Offset | Field | Evidence |
|---|---|---|
| 26 | light flags, a pair of bits per strength: cast sets the low one, carried the high | code, `0x17971`, see [view.md](view.md) |
| 28 | environment, `DS:0xCEF9`: bit 13 indoor, bit 0 cold | code, `0x05555` and `0x0AC45`, see [encounters.md](encounters.md) |
| 32 | mapping rungs, a bit per rung the party's average passes, and three bits saying which overlay panel is up | code, `0x05CB0`, see [party.md](party.md), and below |
| 34 | the key ring: one bit per metal for the chest key in the high byte and for the door key in the low, brass first | code, `0x1B4A8` writes it and `0x111D0` draws it, see [items.md](items.md) |
| 36–46 | six carried-light counters, one per strength, the sixth first; only 5, 3 and 2 are ever stepped | code, `0x0FE29`, `0x0FE35`, `0x0FE41`, and `0x0EB3A`, see [view.md](view.md) |
| 52–62 | six cast-light timers, tens of minutes, in the same order as the counters above | code, `0x1C676` and `0x0EBC0`, see [spells.md](spells.md) |
| 70, 72, 74 | party average mapping, navigation and survival | code, `0x05CB0`, see [party.md](party.md) |
| 80 | carried by MARK and put back by RETURN, and nothing else in the image reads or writes it | code, `0x1CA3F`, below |
| 82, 84 | the arrival song pair, day then default; both zero in `WORLD.DAT` | code, `0x1858F`, see [audio.md](audio.md) |
| 86 | which of the eight ambient lists the place runs | code, `0x009C8`, see [audio.md](audio.md) |
| 88 | the four dawn windows that have already fired today, bits 15 to 12 | code, `0x008DC`, see [audio.md](audio.md) |
| 94 | steps since the last condition drain: `0x0AF37` counts to 40, `0x0AF5C` drains and resets it to 1 | code, see [combat.md](combat.md) |
| 98 | the same in a cold place: `0x0AF4D` counts to 40 where the environment word's bit 0 is set, and `0x0B085` applies attack-table entries `0x2E`, `0x2F` and `0x30` | code, see [encounters.md](encounters.md) |
| 110 | roster slot of whoever cast last, written as the cast takes their magic | code, `0x0D337` |
| 130, 132 | two settings NEW GAME preserves along with 134; `0x188E3` writes 1 into 130 | code, `0x15128` and `0x15178`, below; both **undecoded** |
| 134 | whether music and sound play: bit 1 gates music, bit 3 sound | code, `0x18631`, see [audio.md](audio.md) |
| 136 | ticks between one self-redraw of the view and the next, cycled 5, 1, 9 | code, `0x0E913` and `0x0EAE2`, below |
| 150 | facing: `0x8000` north, `0x4000` south, `0x2000` west, `0x1000` east | code, `0x112D6`; measured, one turn a step |
| 152 | the party's x, in cells across the whole world grid | measured; the trainer writes it and the party arrives there |
| 154 | the party's y | measured, the same way |
| 156 | the day of the month, 1 to 30, advanced by clock wrapping | code, `0x0EC34`; measured, across a wrap |
| 158 | the month, 1 to 12 | code, `0x0EC45`; measured, against six saves |
| 160 | the year | code, `0x0EC50`; measured, against six saves |
| 162 | the clock, in minutes, 0 to 1,439 | measured, one step at a time |
| 180 | gold, packed BCD, four bytes | screens: the F5 purse |
| 184 | food, the same | screens: the F5 purse |
| 188 | nuore, the same | screens: the F5 purse |
| 164, 166, 168, 170 | who holds bartering, repair, thievery and linguistics, 0 for nobody | code, `0x04DD1` and `0x16D2E`, see [party.md](party.md) |
| 210–236 | fourteen quest flag words, 224 bits, below | code, `0x17AFE` and `0x1DB19`; measured, across a played save |
| 270, 274, 278 | the purse as three panel slots: the currency's own item id where the party holds any, 0 where it holds none | code, `0x1709C` |
| 282–305 | the party's own six inventory slots, four bytes each, below | code, `0x0B242`; measured, against a played save |
| 306, 308 | where the sky's window sits on its gradient, and the step it moves by | code, `0x0EDD1` |
| 310 | the sky ramp: 32 colors of three six-bit components | measured; shape: 96 bytes, every component 63 or below |
| 406 | how far the sky slide has left to run, counted down from 113 | code, `0x0EDD1`, see [view.md](view.md) |
| 430 | the next container record to hand out | code, `0x16044`; measured, 3 in every save |
| 432 | the head of the free list of container records, 0 for none | code, `0x1600F` and `0x051E1`; measured, 0 in every save |
| 492 | the roster slots that are playing, four words, 0 for an empty place | measured, against the party assembled |

The facing values are the ones the look-ahead dispatch at image `0x112D6` tests, where `0x8000` steps `y` back and `0x4000` steps it on, `0x1000` steps `x` on and anything else steps it back.

**The key ring is one word, and the two bytes are the two kinds of key.** Header 34 holds a bit per metal: the high byte for the chest keys and the low byte for the door keys, brass at the top bit down to gold at bit 1. Image `0x1B4A8` sets one. It loads the key's own misc properties entry, whose `+0` word carries the metal in its high byte and `0x0090` or `0x0050` in its low ([items.md](items.md)), and `test ax, 0x80` splits them: a chest key keeps the high byte and a door key is shifted down into the low one.

Image `0x111D0` draws the ring, which is what the keyboard's `K` puts up. It walks eight 13-byte rows at `DS:0x7FE4`, `BRASS   (  )` through `GOLD    (  )` and a blank eighth, testing bit 15 against bit 7 and shifting left for the next metal. A row with neither bit is skipped; where the chest bit is set it stamps `C` into the first space inside the brackets and where the door bit is set it stamps `D` into the second. So a party holding both copper keys reads `COPPER  (CD)`. No key's properties entry carries `0x01` in its high byte, so the eighth row cannot draw.

The same word is what a lock is tested against. Image `0x19A56` reads it for a container and image `0x19A88` reads it for a bare lock, and the second differs by an `xchg al, ah`: that swap is the whole of the rule [items.md](items.md) states, that a container takes the chest key and a bare lock the door key.

**Three words survive NEW GAME, and that is what marks them as settings.** Image `0x15128` pushes headers 130, 132 and 134 before it loads the roster template over the whole 500 bytes, and image `0x15178` pops all three back in order. 134 is the music and sound pair ([audio.md](audio.md)), so 130 and 132 are two more of the player's own choices rather than the party's state. What each holds is **undecoded**. The only other instruction a scan of the image finds for either is `0x188E3`, which writes 1 into 130.

**Word 136 is how often the view repaints itself.** It is the reload value of a countdown, not the countdown: image `0x0E913` steps `DS:0x53FC` down once per tick while `DS:0x540C` bit `0x8000` is set, and on zero image `0x0EAE2` raises `DS:0x536A` bit `0x400` and reloads `DS:0x53FC` from word 136. That bit is the view's own redraw flag, which image `0x178B8` sets when the lighting is reassembled and image `0x0F6AC` tests and clears when it draws ([view.md](view.md)).

Image `0x0DF22` is the control that changes it, reached from the in-play dispatch at `0x0D9AB` behind `DS:0x536A` bit 8. It cycles three values and no others: 5 goes to 1, 1 goes to 9, and anything else goes to 5. NEW GAME writes 5 at image `0x15184`. Which key or button reaches that branch is not established.

**Six counters sit beside the six cast-light timers.** Header 36 to 46 is a counter per light strength in the same order as the timers at 52 to 62, the sixth strength first and the first last, and image `0x0EB3A` adds all twelve words to ask whether the party has any light at all. Only three are ever stepped, at images `0x0FE29`, `0x0FE35` and `0x0FE41` for strengths 5, 3 and 2 ([view.md](view.md)). **Both routines that clear them write five of the six.** Images `0x0FD7D` and `0x0FE0A` each zero header 36, 38, 40, 44 and 46 and skip 42, which is the strength-3 counter and one of the three that is stepped.

**Word 32 does two jobs.** Image `0x05CB0` rewrites the mapping rungs through `and [0xcefd], 0x70ff`, which keeps bits `0x1000`, `0x2000` and `0x4000` along with the low byte, so those three are not its own. They say which overlay panel is up, and image `0x10A6A` dispatches a redraw on them: `0x2000` to image `0x11A20` and `0x1000` to image `0x17060`, which is the party panel above and which clears the other two as it opens. Bit `0x0400`, the mapping rung at 45, is separately what image `0x10A12` tests before it draws the compass. Which panel `0x4000` and `0x2000` name is not established.

**The sky ramp is a window rather than a reading.** Image `0x0EDD1` writes 333 into the offset at 306 and -3 into the step at 308, and `0x0EDE0` copies 96 bytes from `DS:0x4D62` plus that offset into the ramp and adds the step to it. So the ramp, its window and the mapping rungs and party averages above are all rebuilt from what they are derived from rather than read back.

The world is one grid, seven areas of 24 bands down by twenty levels of 40 cells across, so `x = level * 40 + cell` and `y = area * 24 + band`, and a map is one `(area, level)` block of that grid. The cabinet's trainer writes those two words to put a party on a named map. It takes the cell from `arrive` in `data/map_pages.json`, which is the drawn cell nearest the middle of that map, because a cell whose bit at `0x3C4F02` is clear is not part of the map at all.

The template's own fields state where a new game starts: x 460, y 46, facing north, clock 540. That is area 1 level 11, which the map registry names `ATHANEUM` ([map.md](map.md)), and 09:00.

**The clock carries a date, and the date is three more words.** Image `0x0EC34` runs when the clock passes 1,440 minutes. It steps the day at 156, and on 31 it writes the day back to 1 and steps the month at 158; on 13 it writes the month back to 1 and steps the year at 160. So a month is 30 days and a year is twelve of them, 360 days.

NEW GAME sets all four at image `0x151AE`: month 3, day 20, year 547, clock 540. The party therefore starts at 09:00 on 03/20/547, and the first of the in-game books opens on `03/15/547`, five days before. The `WORLD.DAT` template carries the same four, and across one playthrough's six saves the date reads 03/21 to 03/23 of 547 with the clock anywhere in the day, which is what a party walking for three days should show.

**Gold, food and nuore are party-wide**, and are what the game's F5 panel prints. All three are **packed BCD, most significant byte first**: 3,557 gold reads `00 00 35 57`. It is the encoding [items.md](items.md) records on the item table's BASE VALUE. A new game starts with none of the three.

A step costs the clock 2 or 3 minutes and a rest about 483. The clock wraps at 1,440 and the day at 156 advances with the wrap. The sky ramp is rewritten as the clock moves: blue to white by day, near black at night, with every component 63 or below, as a VGA palette entry requires.

**The party's own panel is nine slots, at header offsets 270 to 305**, four bytes each in the same (item, state) shape every other slot takes. The last six are its inventory, and they are the first six of the eight the character record keeps its panel slots in, which is what the header slot's own 500 bytes leave sitting there. The first three are the purse drawn as items: image `0x1709C` walks the three purse words at 180, 184 and 188 against the three slots at 270, 274 and 278, writing the currency's own item id, 1, 2 and 3, into each and zeroing it again where that purse word is zero. Image `0x17102` then hands all nine to the drawer against the boxes at `DS:0x66A4`, so a party holding no food has an empty second box rather than a zero beside a caption.

The item search at image `0x0B242` walks those six **before** it walks any character's pack: given a low and a high item id in `DS:0x53EE` and `DS:0x53F0`, it answers with the id it found in `DS:0x5426` and where in `DS:0x542C` for a party slot or `DS:0x542E` for a character's. `K`, `M` and `T` are that search, for the KEY RING, the PARTY MAP and the HOURGLASS ([items.md](items.md)).

**Nothing binds a slot to a particular item.** The six are a store like every other, and what sits in one is what that player put there, so a save's contents are a habit rather than a rule. What a played save shows is the shape: all six filled with ordinary item ids, and a second word carrying the item's own state the way it does everywhere else. One save has 24 beside a TORCH and 240 beside a LIT TORCH: the minutes each has left to burn ([items.md](items.md)), one mostly spent and one at the full 240 its page prints.

**190 of the header slot's 500 bytes are named by no row above, and every one is undecoded**: 20 to 25, 30 to 31, 48 to 51, 64 to 69, 76 to 79, 90 to 93, 100 to 109, 112 to 129, 138 to 149, 172 to 179, 192 to 209, 238 to 239, 254 to 269, 408 to 429 and 434 to 491. Across the six slots of one played save most of them are byte for byte the `WORLD.DAT` template, `0xFFFF` fill or a small constant. [tools/save_coverage.py](../tools/save_coverage.py) is what keeps that list honest: it reads every offset of the image as if an instruction began there and buckets each `[DS:0xCEDD + n]` it finds by the *n* it names, so the count is derived rather than maintained. **Every header offset any instruction names that way now has a row.**

A diff over a played session is a positive test for any of them: [tools/save_probe.js](../tools/save_probe.js) takes `CURGAME` after every step, [tools/save_map.py](../tools/save_map.py) compares consecutive copies against this document's rows, and a word that changes is written by something. The roster reaches `CURGAME` only on a save, not as the party walks, so a run watching it has to interleave saves.
**What has been played through it is three short sessions.** Two walked, six steps and ten, one of them opening the character sheet and the cast menu; the third walked out of the Athaneum and swung at the centipedes beyond the gate. Between them they moved the save name at 2 and 4, word 32, the environment at 28, the ambient area at 86, the drain counter at 94, facing, y, the clock, the four party places at 492, each character's equipment flags at 348, the seen grid, section 5's bits and section 6's first two monster structs. **None of the three bought anything, took a service, opened a container or finished a quest**, and none of them ran long enough to be evidence about a byte it did not touch.
**That measures three short sessions of one party and nothing else.** A field only a later quest, a spell nobody cast or a shop nobody visited writes looks exactly like a field nothing has been seen to write.

**Two scans stand behind that.** The absolute scan on `DS:0xCEDD + n` named 80, 88, 94, 98 and 406 above and finds nothing for the other 114 words. Twelve sites in the image load `0xCEDD` into a register: every one hands the address to the section 0 stub or to a block clear, and none walks the slot field by field.

**Fourteen words at 210 to 236 are the quest flags**, 224 bits, `DS:0xCFAF` to `DS:0xCFC9` in the running game. Image `0x17AFE` resolves a 1-based flag number against them, high bit first. The roster's own base is `DS:0xCEDD`, which puts the array's first word at header offset 210 and its last at 236. The gate table a door is gated on points at one of the last thirteen and carries the bit to test ([map.md](map.md)), and 383 conversation topics carry a flag number in one field or the other ([shops.md](shops.md)). All fourteen are zero in the `WORLD.DAT` template, and across one played game's six save slots the bits set run 11, 7, 15, 21, 24 and 8 as the party gets further, so the words fill as the game is played. [quests.md](quests.md) says what each of the 224 bits is, what writes it and what reads it.

### The character record

500 bytes, at the same displacements the code uses. The roster sits at `DS:0xCEDD` in the running game, so slot 1 begins at `DS:0xD0D1`, which is where [monsters.md](monsters.md) puts a character struct: record offset N is `[si+N]`.

| Offset | Field | Evidence |
|---|---|---|
| 0 | name, NUL terminated | screens: F1 |
| 14 | class | screens: F1; code, `0x04CC3` |
| 16 | sex, 1 or 2 | screens: F1 |
| 18 | portrait, a picture in run 7 of `PICTURES.VGA` | rendered, the four shipped ([view.md](view.md)) |
| 22 | level | screens: F1 |
| 24 | experience, packed BCD, four bytes | screens: F1 |
| 28 | conditions, the word the cure prices are read from | code, `0x092B1`; screens: F1 |
| 20 | gallery cell the portrait was picked from, picture less run 7's own first | code, `0x14716` |
| 30 | how many levels are owed, rewritten on every shop visit | code, `0x065BA`, see [leveling.md](leveling.md) |
| 32–48 | the nine protection words, in the order the condition bits are listed | code, `0x03875`, see [combat.md](combat.md); screens: F5 |
| 50–58 | the five seeds the equip dispatch derives the combat words from | code, `0x0649E`, see [combat.md](combat.md) |
| 60–110 | the live block, 26 words, below | screens: F1, every field |
| 124–174 | the same 26 words again, holding the maximum | screens: F1, and the pair below |
| 114–122 | five combat seeds again, the ones the maximum column is rebuilt from | code, `0x064A6`, below |
| 180 | which flights this character owns, one bit each | code, `0x09E6E`, see [shops.md](shops.md) |
| 182–188 | four flight use counts, one per flight, zeroed as a flight is bought | code, `0x09EFA`, see [shops.md](shops.md) |
| 190, 192, 194 | uses of missile weapon, hand weapon, shield, counted toward a break | code, `0x05E61`, see [combat.md](combat.md) |
| 200 | spell the cast menu was left on, so it opens where this character left it | code, `0x0CC61` and `0x0CF8A` |
| 202–214 | which spells this character knows, one bit per spell number | code, `0x0CF28`, `0x09CAF`, `0x1DC3E` and `0x14FD9` |
| 240–252 | where MARK OR RETURN wrote the party down, six words, below | code, `0x1CA3F` |
| 268 | one bit per once-per-character service taken | code, `0x17ABC` and `0x08FB2` |
| 280 | weight carried, in tenths: the sum over everything held | shape, below |
| 282–313 | the eight panel slots, four bytes each | code, `0x0437E`, see [items.md](items.md) |
| 314, 318, 322, 326, 330, 334 | missile, container, hand, shield, two rings | code, `0x04237`, see [items.md](items.md) |
| 338–346 | the worn slots, a word each: head, body, nothing, feet, hands | code, `0x0431D`, see [items.md](items.md) |
| 348 | four unrelated fields in one word, below | code, `0x16943`, `0x06568`, `0x1B974` |
| 350 | bit `0x8000` marks a character the open chooser refuses | code, `0x1DCD5` sets it, `0x1DD42` clears it, `0x1DC27` obeys it |
| 380, 418, 456 | the open-container stack, three slots of 38 bytes, below | code, `0x16539`, `0x1655D`, `0x1657A` |

**Two of those are a conversation's bookkeeping.** Word 180 holds the four transport bits the table at `DS:0x7AF4` carries in its own records, so a flight belongs to a character rather than to the party. The word at 268 is what the fourteen NPCs that raise one stat spend. Each of them holds a bit index of 1 to 14 at its own `+0x1A`, and image `0x08FB2` tests that index against the word before it offers the service ([shops.md](shops.md)).

**The seven words at 202 are the character's spell book.** Each bit stands for one 1-based spell number, spell 1 taking the high bit of the first word, so all 107 spells fit in 202 to 214. Three routines set a bit, and they are the three routes [spells.md](spells.md) already names from the other side.

- Image `0x14FD9` runs at creation. It reads the pair of spell numbers the class starts with, at `DS:0xB89D + 4 x class`.
- Image `0x09CAF` runs on a training. It reads the four-byte slot that the class's row at `DS:0xB8B5 + 0x50 x class` holds for the level reached.
- Image `0x1DC3E` runs on learning a scroll.

Image `0x0CF28` builds the cast menu. It walks the spell numbers and lists the ones whose bit is set. Image `0x1DCB7` refuses a scroll the character already knows.

**Three resolvers reach three bit arrays, and their nine wrappers are consecutive in the image.** Image `0x17AFE` takes no base and reaches the party's quest flags at `DS:0xCFAF` ([quests.md](quests.md)). Image `0x17B27` adds `0xCA` to a base in `si` and reaches the spell book. Image `0x17AD4` adds `0x10C` and reaches the word at 268. Each resolver has a clear, a set and a test wrapper, at `0x17A90`/`0x17AAC`/`0x17AC4`, `0x17A9A`/`0x17AB4`/`0x17ACC` and `0x17A86`/`0x17AA4`/`0x17ABC`. Picking the wrong wrapper out of the run puts a field in the wrong record.

**The mark is the caster's own.** The spell record carries the offset rather than the code, at its word 64, and MARK OR RETURN carries 240 ([spells.md](spells.md)). A character who has never cast it holds zeros there, and the description says one spot per character.

**It writes six words and reads the same six back.** Image `0x1CA3F` branches on `DS:0x536A` bit 7, which prompt 34 sets for MARK and clears for RETURN, and either copies the six out of the party's own globals or puts them back:

| Offset | Global | What |
|---|---|---|
| `+0` | `DS:0xCF75` | x |
| `+2` | `DS:0xCF77` | y |
| `+4` | `DS:0xCF73` | facing |
| `+6` | `DS:0xCF2D` | a word nothing else in the image reads or writes |
| `+8` | `DS:0xCF33` | the area the ambient list is picked by ([audio.md](audio.md)) |
| `+12` | `DS:0xCEF9` | the environment word, whose bit 0 is cold and bit 13 indoor ([encounters.md](encounters.md)) |

So the return puts the party back on the cell it marked, in the place that cell was in: the same map's ambient area and the same environment, rather than whatever the party walked into since. `DS:0xCF2D` sits one word under the arrival pair at `DS:0xCF2F` and `DS:0xCF31`, which no record in `WORLD.DAT` fills ([audio.md](audio.md)); the mark carries it and nothing fills it.

**Word 280 is the sum of the weights of everything the character holds**, worn, wielded and packed alike. Summing the item weights over each shipped character's equipment words and panel slots gives 80, 65, 65 and 75 tenths against the 80, 65, 65 and 75 the records hold, so the identity is exact on all four. The capacity it is measured against is `10 x` strength, at `LIVE+26`. [items.md](items.md) has the item weights.

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

The five seeds at 50 sit in the same order as the five combat words the block holds at `+12`: shot accuracy, melee accuracy, shot damage, melee damage, absorption. `0x0649E` rebuilds each word as its seed plus what is worn or held, so nothing but the seed survives taking the equipment off. Two of them are the only attribute bonuses that reach combat, a fifth of strength above 72 into melee damage and a fifth of dexterity above 72 into absorption. All five read zero on the four the game ships, whose attributes are all below 72 and who carry nothing that adds to a combat word.

The four combat words are the ones [tools/fight_probe.js](../tools/fight_probe.js) writes, at `0x48`, `0x4A`, `0x4C` and `0x4E`. The ACC and DAM rows of the sheet are the hand pair, and the shot pair is not printed there. The block at 124 is the maximum column. Health and magic differ from the live copy whenever the party is hurt or has cast, and the attributes and skills do not. Every field in both blocks, and the purse, agree with what the game prints on F1 to F5 for a save loaded back into it.

**Offsets 380, 418 and 456 are a stack of open containers, three deep.** They are three slots of 38 bytes. The first two words of a slot are an ordinary `(item, state)` pair, written straight out of `[di]` and `[di+2]` the way every other slot is filled, and the third word is the weight of what the container holds. That leaves 32 bytes, which is the eight four-byte entries a section 2 container record carries, so a slot is an item slot with its contents' weight and room for the contents beside it.

**Three slots is a nesting depth, not three things worn.** A character wears one container, in the equipment slot at 318. An entry inside that container's record can itself be a container with a record of its own, the nesting `tools/containers.py` walks as `nested_references`, and opening one of those is what fills the next slot down.

**Three is the length of the type chain**, not an arbitrary cap. FITS IN, the item record's word 14, says which containers an item goes into, and the three containers answer it about each other: BACKPACK fits inside nothing, BOX fits inside BACKPACK alone, and BAG fits inside either ([items.md](items.md)). So the deepest a party can nest is BACKPACK, then BOX, then BAG, and the stack has a slot for each. Image `0x16C3B` is where the rule is kept: it takes the open container's own category bit, `0x4` for a BAG, `0x8` for a BOX and `0x10` for a BACKPACK, and turns it into the FITS IN bit an item has to carry to go in, answering `0xFFFF` where the thing open is none of the three.

**Word 348 is four fields sharing a word.** Nothing reads it whole: each of the four is tested on its own bits.

| Bits | What |
|---|---|
| `0xF000` | how deep the open-container stack is, below |
| `0x07C0` | which store a slot number last resolved into, below |
| `0x0800` | this character is in the playing party (images `0x1B974`, `0x1B922`) |
| `0x0020` | a two-handed weapon is in hand (images `0x06568`, `0x0650E`, [items.md](items.md)) |

**The five bits at `0x07C0` are one-hot, and they say which store a slot number resolved into.** Image `0x16943` takes a slot number in `ax` and the record in `di`, clears the five, and walks the three container slots in order: where 380 holds a container it adds 384 and sets `0x400`, else where 418 does it adds 422 and sets `0x200`, else where 456 does it adds 460 and sets `0x100`, and where none does it adds 280 and sets `0x80`. A slot number of 1 to 9 then adds `4n - 2`, so the address lands on that entry of the container's eight or on one of the character's own eight panel slots at 282. A slot number over 9 takes the branch at `0x169DA` instead, which resolves an equipment slot -- 330 and 334 are the two rings -- and at `0x16A22` clears `0x80` and sets `0x40`. So the five stand for the innermost open container, the next out, the outermost, the panel slots and the equipment slots, in that order. Image `0x165BA` reads `0x80` to mean the address is inside the record and writes `di` less `DS:0x537C` into `DS:0x542E`, which is where the item search reports a character's slot.

**How deep the stack is stands in the other field, at `0xF000`, and its two paths are a push and a pop.** Pushing runs from the bottom: image `0x16518` refuses with a sound where 380 is taken, `0x16539` fills 380 and sets `0x8000` where 418 is taken, `0x1655D` fills 418 and sets `0x4000` where 456 is taken, and `0x1657A` fills 456 and sets `0x2000`. Popping runs the other way: image `0x16498` takes the deepest filled slot, 380 before 418 before 456, hands it to `0x168D9` and clears that slot's bit alone. Image `0x164DE` empties all three at once and then writes 456 with `0x1000`, which is how opening a container closes whatever was open.

**One bit is meaningful at a time**, which is what makes the four a depth rather than four slots: image `0x16C0A` reads 380 and tests `0x8000`, then 418 and `0x4000`, then 456 and `0x2000`, then `0x1000`, stopping at the first that is set. The resolver above walks the same order, so a click lands in the innermost container the stack holds.

The five bits above are written into a save and survive it: a save from a played game carries `0x0880` on each of the four playing characters, and the game writes `0x0880` again when it saves that party back.

**The weight is kept as the contents change.** Image `0x1673B` adds to a slot's third word and image `0x16BC7` subtracts from it, and each skips a slot whose first word is 17, which is BROKEN CLUB. Both also add to or subtract from word 280, the weight the character carries, so a container's contents weigh against its holder and the slot's own word is the part of that total the container accounts for.

**The maximum column has seeds of its own.** Image `0x064A6` rebuilds it from offsets 114 to 122 exactly as it rebuilds the live column from the seeds at 50 to 58, and in the same order: 114 and 116 and 118 and 120 and 122 land on `+12`, `+16`, `+14`, `+18` and `+20` of the block at 124, which is shot accuracy, accuracy, shot damage, damage and absorption.

**92 of a character record's 500 bytes are named by no row above, and every one is undecoded**: 112 to 113, 176 to 179, 196 to 199, 216 to 239, 254 to 267, 270 to 279, 352 to 379, 494 to 499. A sweep for `[si+N]`, `[bx+N]`, `[di+N]` and `[bp+N]` over the whole image is what cut that list down, one pass for all 500 displacements ([tools/save_coverage.py](../tools/save_coverage.py)), and it and it cannot tell a character's struct from a monster's, which share the register and the form: the one hit on 112 reads `[si+0x70]` inside a monster pass and is that record's offset 62, not this one's 112. Rerun over every displacement, decimal forms included, it turns up one more decode, `[bx+0x108]` at image `0x0F1E6`, and that one writes the attack table at `DS:0x96DA` rather than a character. **So no instruction in the image names any of the 94.** Every one reads zero in all nine character slots of a played save, which bounds what that party reached and says nothing about what the record holds. The same offsets are in use in the header slot, which is the same 500 bytes put to a different purpose.

An item with no equipment slot, or whose slot is already taken, is placed in the first panel slot whose id is zero. [items.md](items.md) holds the slot masks and the equipment offsets. The second word of a slot is the item's own state, which for a container is its record number in section 2.

## Section 1, the seen grid

One bit per cell of the world, in the same geometry as the clue book's tables at `WORLD.DAT 0x3C4F02`: 7 areas of 24 bands, and a band is 20 levels of 40 cells, so 5 bytes to a level and 100 to a band.

    seen(x, y) = save[5000 + y*100 + x//8] >> (7 - x%8) & 1

with `x` and `y` counting across the whole world, so `area = y // 24` and `level = x // 40`. This is the marker at image `0x11268`, which divides `x` by 8, adds the row buffer's address, and ORs in `0x80 >> (x % 8)`. Its caller at `0x11361` first sets `0x8000` in the map cell's own word 6, so the bit is written once per cell rather than on every look.

What a party lights is two rows of three: its own cell and the two beside it, and the same three one step ahead. The dispatch at `0x112D6` marks the cell in front and then the party's own, and each of those marks itself and its two neighbors across. A row is written back to the file as it is marked, so walking a corridor writes one record a step.

## Section 2, containers

1,296 records of 34 bytes: a word, then eight four-byte entries. The reader at image `0xB323` walks the entries from record offset 2 and passes the first word of each to the item loader (`lcall 0x0F44C`), so an entry begins with an item id.

A character reaches its own by number: the id of the container item is at character offset 318 and this record number at 320. Every panel slot works the same way, since a slot's second word is the item's state and a container's state is its record here. All 1,296 are empty in a fresh game.

**Records are numbered from 1, and 0 means the container has none.** The two words at header offsets 430 and 432 are the allocator, and they travel with the roster like everything else in that slot.

Image `0x1600E` hands one out. With the free list at 432 empty it takes the counter at 430 and increments it; otherwise it takes the record the list names and replaces the head with that record's own first word. Either way the record is zeroed before it is returned. Image `0x051C8` gives one back: it zeroes the record, writes the current head into the record's first word, and points the head at the record.

**The first word does two jobs.** While the record is free it is the free-list link the two routines above pass along. While it is in use it is the weight of what the record holds, in tenths, which is the same figure the holder's own container slot keeps at its `+4` (character offset 380 and its two pairs). One played save has two records in use, and the sum of the item weights matches the word in both: record 3 holds two slings, a third sling, two sets of clothes and the party map, 10.0 against its 100, and record 4 holds two gold nuggets, robes and a club, 7.5 against its 75.

The two are set by the `WORLD.DAT` template rather than by any code that resets them: every save carries 430 = 3 and 432 = 0, because the pre-created party holds two containers, SQUIRE's bag in record 1 and JOSEPHINE's in record 2. Nothing writes 430 but that increment, and nothing writes 432 but the two above and image `0x15196`, which clears it for a new game.

The cabinet's save editor does the same arithmetic when it puts a container in a slot, and refuses past record 1,295, where the next record would be written over section 3.

## Sections 3 and 4, bundles and what has been taken from them

`WORLD.DAT` section 10 is **1,000 records of 26 bytes**, and the low four hundred of them are bundles of loot: a lock at word 0, a pick-and-trap number at word 1, eight item ids at words 2 to 9, and three counts at words 10, 11 and 12 for the three items that stack. [map.md](map.md) has the whole record and both lock tables. Past about record 400 the section holds something else, text among it.

**Words 10, 11 and 12 are not one gold amount.** Image `0x02881` walks the eight places, and a place holding item 1, 2 or 3 takes its own second word out of word 10, 11 or 12 in turn, which are GOLD COINS, FOOD and NUORE.

A record is a **bundle** rather than a chest, because a chest is only one of the ways the game hands one over.

* **Section 4 gives each bundle one byte, and each of its eight item slots one bit of that byte.** The bit is set when the item is handed over, by whichever route it leaves the bundle. A bit is never set where the record holds no item. Its index is the bundle number less one, which entry 0 forms and entry 1 never touches, so the highest byte any argument in `WORLD.DAT` names is 402. The 605 bytes above it are **undecoded**, and the paragraph on the same question for section 3 below says what bounds the number.
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

The second entry has no per-item bits at all, and it reads no bundle either: it takes a four-byte record out of the head of section 11, which is a lock and nothing behind it ([map.md](map.md)). So bank 1 records that a lock has been opened, one bit each over 71 locks, and bank 0 records that a container has been opened, one bit each over 380.

**Image `0x19AB2` is what sets a bank 1 bit.** It runs on the lock path, after the sound a lock makes as it gives: it ORs the bit the entry worked out into `DS:0x588F`, points section 3's own stub at that byte and writes it back through image `0x039C2`. The arithmetic at the entry is `(record - 1 + 1,008)`, divided by 8 for the byte and left as the remainder for the bit, so bank 1 begins at byte 126.

**Both banks are the same shape and only one of them fills in the saves read.** Over one playthrough's six saves bank 0 climbs 7, 8, 24, 29, 32 and 7 bits as chests are opened and bank 1 holds none. 71 lock events and 380 treasure events stand on the maps, so the party those saves belong to opened chests and no bare lock.

**How far into the section an index can reach is countable, because nothing computes one.** Ten calls land on the two entries: eight far, and two near at `0x02791` and `0x02797` that a far-call scan alone misses. Every one takes the index straight out of a record. Six far sites load a cell event's own argument at `[si+4]` and two load a conversation topic's selector at `es:[si+0x12]`; the two near sites take `ax` from their caller, image `0x00444`, which loads `[si+4]` as well. Nothing touches the value between the load and the call, so the entry's own `record - 1` and `record - 1 + 1,008` are the whole of the arithmetic.

The treasure events run 1 to 403, the lock events 1 to 71, and the 48 buy and reward topics 6 to 395. **The highest byte any of them names is 176**, entry 1 at the largest argument either kind of event carries. The 882 bytes above it are **undecoded**. Both halves of that are settled: `WORLD.DAT` holds no larger argument, and no call site turns a smaller one into a larger index. The enumeration follows direct calls, a far `0x9A` or a near `0xE8` naming the address, and the image holds 21 corroborated indirect call decodes it cannot follow.

## Section 5, which monsters are still on the map

626 bytes, so 5,008 flags, with a set / clear / test triple at image `0x127B4`, `0x1276B` and `0x127FB`, each taking the flag number in `ax`. The flag number is a **spawn id**: the 1,862 monsters the maps place are numbered 1 to 1,862, and each one's bit says whether it is still standing on its cell. [encounters.md](encounters.md) has the whole chain.

Set means the monster is not standing on its cell. Until it is killed it is in one of the eighty slots section 6 holds instead. Opening the Athaneum's south gate sets flags 37 and then 36, which are the two centipedes on adjacent cells of Yendor, where that gate leads: they come off the map as the party sees them. Death frees the slot at image `0x12CA6` and leaves the flag set, and nothing else clears it, so a killed monster does not return.

The 1,862 spawn ids fill flags 1 to 1,862, which is byte 232 of the 626. The remaining 3,146 flags are **undecoded**. The triple takes its flag number in `ax`, and its three call sites load that out of a record rather than working it out: the clear at `0x100B8` and the test at `0x10CC3` from a cell event, and the set, which is reached by a near call at `0x126C5` and by no far call at all, from `[si+0]` of a live monster slot, where `0x125E6` wrote the spawn id.

## Section 6, the monsters on the map

12,480 bytes written from `DS:0x122C`, which is the spawn table: 80 monster structs of 156 bytes each, the same ones [monsters.md](monsters.md) describes. A monster's name sits at struct offset `0x32`.

This is the one section that the game does not keep up to date as it plays. It is written to `CURGAME` only by the save itself, so `CURGAME` carries the copy made at launch until the first save.

## Reading one

    .venv/bin/python tools/saves.py SAVGAME1        # parse against this model
    .venv/bin/python tools/saves.py --layout        # the sections

`saves.character()` reads one 500-byte slot and takes the ten slots as bytes, so it reads a save's section 0 and `WORLD.DAT`'s template alike. `saves.shipped_party()` is the template's last four through it.

The cabinet's save editor writes one too: it opens a `SAVGAMEn` the cabinet is holding, edits the roster at the displacements above, and puts the bytes back. [panel.md](panel.md) has what it edits and where the bytes go.

[tools/save_probe.js](../tools/save_probe.js) plays a scripted session and copies `CURGAME` after every step. [tools/save_map.py](../tools/save_map.py) compares consecutive copies and names the offsets that moved. `--load=DIR` with `--start=load` puts save files on the emulated disk and opens one of them, so a save made elsewhere can be read on the game's own screens. F1 to F4 are the character sheets, and F5 is gold, food and nuore.

    bun tools/save_probe.js --out=tmp/save-probe/walk --steps='south:<<;open: ;out:^'
    bun tools/save_probe.js --out=tmp/sheets --load=tmp/saves --start=load \
        --slot=5 --steps='c1:!f1;w:..;c2:!f2;w:..'
