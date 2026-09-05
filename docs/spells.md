# The spell record

The spell record is 80 bytes, and there are one hundred and seven of them at `WORLD.DAT 0x41B5BF`, which is section 31 of the directory. Eight of the records are placeholders named `ERROR`, and their bytes are leftovers. This document records settled findings only. What a spell's blow does to a monster is in [combat.md](combat.md), and what a training level costs is in [leveling.md](leveling.md). [tools/extract.py](../tools/extract.py) is the decoder.

## The record

A 21-byte name, then little-endian uint16 fields from offset 22.

The Evidence column uses the classifiers [README.md](README.md) defines. All 98 F3 pages were captured.

| Offset | Field | Evidence |
|---|---|---|
| `0` | name, 21 bytes, space padded | screens: every page's title |
| `22` | level, the lowest of the spell's class levels | screens: F3, 95/98, below |
| `24` | magic points | screens: F3, 98/98 |
| `26` | nuore | screens: F3, 98/98 |
| `30` | what the spell singles out: 9 insects, 13 undead, read with 76 bit 8 | screens: F3 AFFECTS, 98/98 |
| `32` | attack table id, which says what the effect does | code, `0x1c5e1`, and seven further branches pass it the same way |
| `34` | amount, whose meaning follows the effect | code, `0x1d9f1`, on the restorative branch; shape elsewhere, below |
| `46` | damage | screens: the prose quotes it on 64 of 65 |
| `68` | scroll mask, six bits | screens: F3 class rows, 224/224 |
| `70` | bit 10 is the out-of-melee restriction | screens: F3 WHEN, 98/98 |
| `72` | scope, what the spell acts on, and how far it reaches | screens: F3 AFFECTS and WHEN, 98/98 |
| `74` | element | screens: the prose, bit by bit; four bits **undecoded**, below |
| `76` | blow word | screens: F3 AFFECTS, bits 1, 2 and 8, 98/98; code, `0x1D72F` for the upper bits and `0x1c5a4` for bit 0, which no page shows, below |

**MP and nuore** are exact on all 98 spells the clue book lists, against the game's own F3 SPELL INFORMATION screen.

**Damage** at 46 matches the number quoted in the description on 64 of the 65 spells that quote one.

**Offset 32** holds 18 for every healing and every cure spell and for nothing that does damage. **Offset 34** is an amount rather than a healing field. For a heal it is the health restored, as HEAL 10 and GREAT HEAL 500. Damage spells carry unrelated values in the same offset. What a restorative spell does with 32, 34 and three more offsets is below. `extract` exposes `amount` and `restorative` raw.

**Offset 22** is the lowest level at which any class can cast the spell, and that holds on 95 of the 98 listed spells. FIREBALL 14 is the Mage level, and ACID RAIN 17 is the Monk level. Offset 22 is also the level printed beside SCROLL for a class that learns the spell that way.

## The description text

Descriptions are a stream of 39-column lines, held in the last entry of the Restoration table. Entry 3 of that table indexes them as `(start line, line count)` uint16 pairs. Entry 0 is a sentinel, so spell *i* uses pair *i+1*.

## Which records the clue book lists

The list registry at `DS:0xF6A8` holds the clue book's lists. List 1 is the maps, list 2 is the monsters and list 3 is the spells. List 3 names 98 of the 107 records. The nine it leaves out are the eight `ERROR` placeholders and `SHARD OF ICE`.

## AFFECTS and WHEN

The F3 printer builds the AFFECTS row at image `0x0776E` and the WHEN row at `0x07889`. Between them they read four words (72, 76, 30 and 70), and the order of the tests is what decides the row.

The printer works from a copy of the record in a scratch buffer at `DS:0x5DA6`, so the DS addresses in that code are record offsets: `[0x5DBC]` is offset 22, `[0x5DEA]` is the scroll mask at 68, `[0x5DEE]` is 72 and `[0x5DF2]` is 76. `[0x5DF6]`, the word after the buffer, is the current spell's 1-based number.

**WHEN**, in test order:

| Test | Row |
|---|---|
| `70 & 0x0400` | out of hand to hand |
| `72 & 0x3000` | in hand to hand |
| otherwise | anytime |

**AFFECTS** is blank when any of the low eight bits of 72 is set. That covers the nine spells that act on the world, below. Otherwise the row holds a scope, a noun, and for most spells a reach phrase.

Scope reads ALL when `76 & 0x0006` or `72 & 0x5E00`, and ONE otherwise.

The noun, in test order:

| Test | Noun |
|---|---|
| `72 & 0xC000` | character |
| `76 & 0x0006` or `72 & 0x0200` | visible monsters, or visible undeads when `76 & 0x0100` and 30 is 13 |
| `76 & 0x0100` and 30 is 9 | insect |
| `76 & 0x0100` and 30 is 13 | undead |
| otherwise | monster |

**The visible branch ends the row**: it prints its noun and jumps to WHEN, so a visible spell takes neither a plural nor a reach phrase. Every other noun takes an `S` when `72 & 0x5C00`, and then a reach phrase, in this test order:

| Test | Reach |
|---|---|
| `72 & 0x3000` | in hand to hand |
| `72 & 0x0800` | in a straight line |
| `72 & 0x0400` | in a 3x3 area |
| `72 & 0x0100` | at a distance |
| otherwise | none |

Reach and WHEN are **nested rather than independent**, and they share the same enumeration of phrases. All 36 spells that reach "in hand to hand" are cast "in hand to hand", and all 19 that reach "at a distance", "in a 3x3 area" or "in a straight line" are cast "out of hand to hand". WHEN is the coarser condition, and reach is the pattern within it. "Out of hand to hand" is a *restriction on casting*, meaning that the caster must not be engaged in melee. It is not a targeting mode, because the ranged sense belongs to the reach value instead.

Friend-or-foe is not separate information. Across the 98 listed spells, all 70 that do damage act on monsters, undead or insects and none on a character, and all 19 restorative ones act on characters.

### Offset 76 bit 0

**code**. No page shows this bit.

TURBULENT ATMOSPHERE holds 0 at 72 and `0x0001` at 76. No other spell record carries 76 bit 0. With 72 empty, every branch above falls through, so the F3 page prints ONE MONSTER. The description prints ALL VISIBLE MONSTERS.

Image `0x1c5a4` tests 76 bit 0 and routes the cast to `0x1d5be`, which reaches the applier at `0x1d374`. EARTHQUAKE and the ACID RAIN spells reach that applier too. [combat.md](combat.md) has it.

`0x1c5a4` is the only read of the bit. Twenty-five instructions reference the word: twenty-three test a mask that excludes bit 0, `0x1d8bc` loads the word and masks it with `0xFE00`, and `0x1c5a4` is the twenty-fifth.

`data/spells.json` holds scope `all` and target `visible monsters` for this record, against its page. An F3 page carries the class rows, MP, nuore, AFFECTS and WHEN. Compared field by field against the 98 captured pages, this AFFECTS row is the only value the file departs on.

## The element word

Offset 74 uses the **same bit layout as the enemy immunity word** at enemy offset 100. The game tests one against the other, so `COLD` on a spell and `IMMUNE TO COLD` on a monster are the same flag.

| Bit | Meaning | Bit | Meaning |
|---|---|---|---|
| 0 | power | 11 | hexing |
| 1 | electric | 12 | freezing |
| 2 | cold | 13 | paralysis |
| 3 | fire | 14 | disease |
| 4 | magic damage | 15 | poison |
| 10 | cursing | | |

This was confirmed bit by bit against the game's prose. The field is never set on a spell that does no damage, and the four condition spells (HEX MONSTER, PARALYZE, FREEZE and CURSE MONSTER) all do damage as well. Zero means untyped damage, which no immunity stops, and **63 of the 98 listed spells hold zero**.

**Bits 5 to 8 are undecoded.** Four spells set one of them and nothing else: DWINDLING DAMAGE `0x0020`, THIN SKIN `0x0040`, FEET OF LEAD `0x0080` and BLIND `0x0100`. No monster's immunity word carries any of the four, so nothing in the game stops these four spells either, and they behave as untyped. Counting them that way makes 67 of the 98 untyped in play, which is the figure the panel uses. What the bits are *for* is not established.

Offset 76 is also the spell's blow word, and a spell-resistant monster halves the damage on its bit 13. That holds on 55 of the 59 records that set the bit. The other four are the LIFE FORCE line below. Their casts never reach the test. See [combat.md](combat.md). The AFFECTS row reads the low bits of that word, and the resolver reads the upper bits.

## What a restorative spell does

Record 72 picks the branch. `0x8000` sends the spell to one character, at `0x1c5b5`. `0x4000` sends it to the party, at `0x1c617`. All 19 restoratives carry one or the other.

The party branch walks the four handles at `DS:0xd0c9`. It passes over an empty slot. It passes over a character carrying condition bit `0x40`. Past that the two branches do the same work. Each fills a readout slot. Each hands the slot to the effect applier. The applier routes attack table entry 18 to the handler at `0x037d9`.

That handler is the whole effect, in two lines:

    field = min(field + amount, character[maximum])   ; 0x037f6
    condition word &= mask                            ; 0x03830

The clamp is skipped where no maximum is named.

| Offset | Field | Evidence |
|---|---|---|
| `32` | attack table id. 18 on all 19, the entry that adds. | code. `0x1c5e1` and `0x1c617` pass it to `0x0357e` |
| `34` | the amount added | measured, 2 of 19, below; code at `0x1d9f1` and `0x037f0` |
| `36` | the character field it is added to | measured, 2 of 19, below; code at `0x1d9f7` and `0x037f6` |
| `38` | the field holding the maximum for 36. 0 means no maximum. | code. Written to readout `+0x12` at `0x1c5fd`, compared against at `0x037fd` |
| `40` | a mask ANDed into the character's condition word. Its bit 6 also gates a dead target. | measured, 4 of 19, below; code at `0x03830` and `0x1d9ce` |

The field numbers are offsets into the character record. 82 is health in the live block. 146 is health in the maximum block. 62 is dexterity and 60 is strength. [saves.md](saves.md) has the layout.

The dead-target test reads `[0x537c]`. The single-character branch points that at the target, at `0x1c5c4`. The party branch leaves it pointing at the caster. It makes its own test instead, at `0x1c63b`. No party restorative clears bit 6, so the two rules never disagree.

**Casting does not enter it.** Three checks, all negative.

The record arrives by straight copy. `0x0bd72` computes `(spell number - 1) * 0x50`. It moves 80 bytes into the scratch buffer. No field is touched on the way.

Nothing writes 34, 36 or 38 after that. A scan of every store form against all three addresses finds no writer.

Four instructions read `+0x62` off a base register. Two are the spell attack rolls, at `0x1d60f` and `0x1d623`. One is the F1 sheet printer, at `0x149d8`. The fourth is at `0x1257f`, where the base is a monster and the same displacement is record 48. None of the four sits on this branch.

Level stays out for a structural reason. `0x03622` tests the entry's flags. Anything carrying `0x180` goes straight to `0x037d9`. The level multiply is at `0x038f1`, on the branch that test skips. Entry 18 carries `0x0100`, so it never reaches that arithmetic.

So the amount a character receives is record 34 and nothing else.

A blank below is a zero.

| Spell | 34 | 36 | 38 | 40 | What 40 clears |
|---|---|---|---|---|---|
| HEAL | 10 | 82, health | 146 | `0xffff` | nothing |
| CURE POISON |  |  |  | `0x3fff` | sick, poison |
| FEET OF FEATHERS | 5 | 62, dexterity |  | `0x0000` | everything |
| IMPROVE HEALTH | 50 | 82, health | 146 | `0xffff` | nothing |
| REMOVE JINX |  |  |  | `0xfdff` | jinxing |
| PARTY HEAL | 100 | 82, health | 146 | `0xffff` | nothing |
| DISEASE ANTIDOTE |  |  |  | `0xdfff` | disease |
| THAW |  |  |  | `0xf7ff` | frozen |
| RESTORE HEALTH | 200 | 82, health | 146 | `0xffff` | nothing |
| ARMS OF GIANTS | 5 | 60, strength |  | `0x0000` | everything |
| PARTY REJUVINATION | 200 | 82, health | 146 | `0xffff` | nothing |
| REMOVE HEX |  |  |  | `0xfeff` | hexing |
| GREAT HEAL | 500 | 82, health | 146 | `0xffff` | nothing |
| CURE PARALYSIS |  |  |  | `0xefff` | paralyze |
| UNSTONE |  |  |  | `0xfbff` | stoning |
| PERFECT HEALTH | 9999 | 82, health | 146 | `0x007f` | sick, poison, disease, paralyze, frozen, stoning, jinxing, hexing, cursing |
| REMOVE CURSE |  |  |  | `0xff7f` | cursing |
| RESURRECT | 2 | 82, health |  | `0xffbf` | dead |
| HARDY PARTY | 600 | 82, health | 146 | `0xffff` | nothing |

**The mask and the bit agree.** Bit 6 of the condition word is set when health reaches zero ([combat.md](combat.md)). A mask that clears bit 6 marks a spell meant for a corpse. `0x1d9ce` reads the same bit to decide whether to pass a dead target over. RESURRECT is the one restorative that clears it. PERFECT HEALTH clears the nine conditions and keeps bit 6. It cures everything and leaves the dead dead.

**Two records carry a mask of zero.** They are FEET OF FEATHERS and ARMS OF GIANTS. Both grant an attribute bonus rather than a cure. The AND at `0x03830` runs for every spell that reaches the handler. It makes no test for the spell being a cure. So each of the two clears the whole condition word, bit 6 included, and the target stops being dead.

That one is **measured**. [tools/revive_probe.js](../tools/revive_probe.js) kills a party member in the running game, casts one restorative at the body, and reads the roster back out of the emulator. A level-6 Mage does the casting, standing in the Athaneum. No spell record is touched.

| Spell | MP spent | Mask | Condition word | Health after the cast | After one rest |
|---|---|---|---|---|---|
| HEAL | 3 | `0xffff` | `0x0040`, unchanged | 0 | 0 |
| FEET OF FEATHERS | 19 | `0x0000` | `0x0040` to `0x0000` | 0 | 13 of 13 |
| ARMS OF GIANTS | 55 | `0x0000` | `0x0040` to `0x0000` | 0 | 13 of 13 |
| RESURRECT | 400 | `0xffbf` | `0x0040` to `0x0000` | 2 | 13 of 13 |

Every MP figure is the spell's own record 24, so each row is a cast that happened. RESURRECT moved health by 2, which is its record 34 into the field its record 36 names. FEET OF FEATHERS moved the target's dexterity from 59 to 64, which is its own 34 and 36. HEAL changed nothing, because its bit 6 is set and `0x1d9ce` zeroes the amount for a dead target.

The probe exercised bit 6. The mask is zero, so every other bit goes on the same instruction.

**A rest finishes the revival.** `0x0d6a6` passes over a character carrying `0x1c40`, so a corpse gets nothing from resting. Clear the bit and the character rests like any other. One rest took the body from 0 health to full. The dexterity went back to 59 at the same time, which is the revert at `0x0d7a1` writing the base column over the current one ([leveling.md](leveling.md)).

So a level-6 Mage spell costing 19 magic points raises the dead, where the spell written to do it is a level-34 Monk spell costing 400.

## What each reach does

The AFFECTS row above says how far a cast reaches. What the cast then touches is the dispatcher's, at image `0x1C4E4`, which tests the same words in an order of its own. **Evidence is code.**

| Reach | Word 72 | Branch | What it touches |
|---|---|---|---|
| in hand to hand | `0x2000` | `0x1CCCD` | one of the three engaged places |
| in hand to hand | `0x1000` | `0x1CD1F` | all three of them, and nothing else |
| at a distance | `0x0100` | `0x1CD82` | the first monster along the middle column |
| in a straight line | `0x0800` | `0x1CD82` | that one, and on through each it kills |
| in a 3x3 area | `0x0400` | `0x1CD82` | nine cells about where it stopped |
| none | `0x0200`, or word 76 bits 0 to 2 | `0x1D2E9`, `0x1D4D4`, `0x1D5BE` | every monster the view holds ([combat.md](combat.md)) |

**The two melee bits are two branches**, which the printer does not distinguish: it prints "in hand to hand" for either and reads `0x1000` as part of its ALL mask. So 24 records land on one engaged place and 13 on all three. **The dispatcher's order is not the printer's** either, and where they disagree the dispatcher is what happens: SWORD OF ICE carries `0x2000` and word 76 bit 2 both, so the row prints ALL VISIBLE MONSTERS and the cast lands on one engaged place.

**A cast that reaches out steps along the same six bands a volley's flight does**, `DS:0x53DC` running `0x31, 0x2E, 0x2B, 0x28, 0x24` and `0x19` ([combat.md](combat.md)). The party's own band is drawn and never tested, so the first band that can answer is the one in front. Image `0x02F93` answers each step and the walk stops where it says something is there.

**The two shape bits are read once it has stopped.** Bit `0x800` carries the cast on: image `0x1CF18` tests whether the monster it just struck is still standing, and where it is not the walk resumes at the next band out and strikes again, down to band `0x19`. Bit `0x400` opens it instead: image `0x1CEEE` sends it to `0x1D035`, which names the left cell of three bands and calls `0x1D8F7` on each, and that routine takes three cells from the one it is given. So a 3x3 is nine cells, the band it stopped on and the bands either side, each left, middle and right.

| Stopped at | Bands struck |
|---|---|
| `0x24` | `0x18`, `0x23`, `0x27` |
| `0x28` | `0x23`, `0x27`, `0x2A` |
| `0x2B` | `0x27`, `0x2A`, `0x2D` |
| `0x2E` or `0x19` | `0x2A`, `0x2D`, `0x30` |

The table names three bands and answers the other two the same way, so a cast that reaches the farthest band still opens about the nearest one. **Word 76 bit 3** takes the same six bands with another drawing (image `0x1D146`), and the seven records that carry it print no reach at all.

**Nothing tests line of sight.** The lookup at image `0x12F60` reads the monster off the view table entry and tests bit `0x400` alone, so the skip bit that hides the cells a wall stands in front of ([view.md](view.md)) has no say in it. A monster standing on a cell of the frustum is reached whether the frame drew it, drew part of it, or drew none of it.

## What a spell does to the world

Nine spells act on the world rather than on a body, and **evidence is code** throughout: each takes its own branch out of the cast dispatcher at image `0x1C4E4`, which tests the low byte of word 72 one bit at a time.

| Bit | Spell | Branch | What it does |
|---|---|---|---|
| `0x01` | UNLOCK MAGIC | `0x1CB6B` | opens a magically locked container or door |
| `0x02` | SAFE HAVEN | `0x1CB51` | rests eight hours with no monster closing in ([encounters.md](encounters.md)) |
| `0x04` | JUMP OVER, JUMP THROUGH | `0x1C733` | carries the party whole cells |
| `0x08` | DISPEL ILLUSION | `0x1CAC2` | clears the lock that is standing in for a wall |
| `0x10` | — | `0x1C6E8` | one ERROR record carries this bit and no listed spell does |
| `0x20` | MARK OR RETURN | `0x1CA3F` | writes the party down, or goes back |
| `0x40` | SAFE UNLOCK | `0x1CC0B` | opens a pickable or trapped container or door |
| `0x80` | MINER'S LIGHT I and II | `0x1C676` | lights the party for a while |

Each branch reads fields of its own out of the record, and the same offsets mean something else on a spell that lands on a body.

**A light picks one of six strengths and burns for its own time.** Offset 42 is a strength of 1 to 6. The branch turns on that strength's bit in `DS:0xCEF7`, `0x100` for 1 down to `0x8` for 6, which is the dimmest of the six up to the brightest ([view.md](view.md)), and writes offset 44 onto that strength's own timer at `DS:0xCF11 + 2 x (42 - 1)`. The tick at image `0x0EBC0` takes the elapsed minutes off each of the six and clears the bit of any that reaches zero, so two lights burn side by side and the brighter one draws. Offset 44 is tens of minutes: MINER'S LIGHT I carries 15 against the 2 1/2 hours its description quotes and II carries 21 against 3 1/2, 2 of 2.

**A jump reads five words and takes the first that is not zero**: 54 forward, 56 back, 58 left, 60 right, 62 through what stands between. JUMP OVER carries 2 forward and JUMP THROUGH 2 through. The branch turns the way into a step by the party's facing and tests the cell it lands on.

**A mark belongs to the caster.** Image `0x1CA3F` adds offset 64 to the acting character's own record pointer, and MARK OR RETURN carries 240, which is inside a 500-byte roster slot ([saves.md](saves.md)). It writes the party's x, y and facing and the arrival word of the place, or reads them back where that slot holds one. Prompt 34 is what picks between the two, DO YOU WANT TO... MARK or RETURN TO ([party.md](party.md)). The description says the same: "you can only have one spot marked at a time for each character that has the spell".

**The three that open something ask what stands on a cell first.** Image `0x10CD5` takes the party's own cell where something stands on it and the cell in front otherwise, and image `0x10BC8` reads what stands there into eleven states ([map.md](map.md)). Each spell takes the states that are its own: SAFE UNLOCK the pickable and the trapped, UNLOCK MAGIC the magically locked, DISPEL ILLUSION the lock whose armed trap stands in for a wall. All three end at image `0x1CBD0`, which sets the same bank bit an opening sets, so the thing stays dealt with.

[tools/extract.py](../tools/extract.py) reads all of it.

## The LIFE FORCE line

Two bits in the low byte of 76 divert a cast at `0x1ccd5`. `0x40` sits on LIFE FORCE I, II and III. `0x80` sits on LIFE FORCE IV. No other record carries either.

The diversion happens before the applier that reads element and blow. So three offsets carry a meaning on these four records alone. [combat.md](combat.md) has the branch.

| Offset | Read as | Value on all four |
|---|---|---|
| `40` | the character field the transfer moves | 82, health |
| `42` | attack table id used when the roll lands | 18, the entry that adds |
| `44` | attack table id used when the roll misses | 20, the entry that subtracts |

Every other spell reaching that handler reads 40 as the condition mask above. `0x03825` tests bits 6 and 7 of 76 to tell the two readings apart. Ten further records carry a non-zero 42 or 44. What reads them there is not established.

## Which classes can cast a spell

Not in the record. The printer at image `0x7660` makes three tests per class, in this order, and the order matters: a class that both trains a spell and carries its scroll bit shows as TRAINING.

1. **`DS:0xB89D`**, two 1-based spell numbers per class, which is the pair the class already holds at level 1. A hit here is level 1, with no route printed.
2. **`DS:0xB8B5 + 0x50 * class`**, the class's training row. It holds twenty four-byte slots, one per even level from 2 to 40, each holding up to two spell numbers. A hit here is TRAINING at that level.
3. **Record offset 68**, a six-bit scroll mask running from monk `0x20` down to marksman `0x01`. A hit here is SCROLL, at the spell's own level from offset 22.

The six classes are monk, alchemist, paladin, mage, druid, marksman, in that order, in both tables and in the mask.

A spell is castable by between one and five of the six classes. The three tables produce 246 class rows. The F3 page has room for three rows and prints the first three in class order, so the 224 rows that the screens show are a subset of the 246. Every one of those 224 is reproduced exactly, and 22 further rows exist that no F3 page can display. The F4 Magic Users pages print the same relation from the other direction, giving a class's whole list with no limit on rows.

## TRAINING versus SCROLL

The two words are an enumeration in the label run at `0x2ADA4`, immediately after the spell field names, so the route is a property of the *(class, spell)* pair rather than of the spell:

- **TRAINING**, granted on leveling. `0x2A074` holds `TRAIN TO LEVEL ` and `0x2A1EE` holds `YOU HAVE LEARNED SOME SPELLS`.
- **SCROLL**, learned from a *magic scroll* item. `MAGIC SCROLLS` (`0x2AB0D`) is one of the eight item categories, and `LEARN SPELL?` (`0x3085F`) sits beside `USE ITEM?` in the right click prompts. Learning teaches the spell permanently, and the listed level is what the class must reach first.

Eight spells are training for one class and scroll for another. ACID RAIN, for example, is a scroll for the Monk and the Alchemist and training for the Paladin. A further 15 spells are scroll only for every class that can cast them. Scroll levels run lower than training levels, with a median of 13 against 18.

**A magic scroll names its spell by id**, in its misc properties entry, which [items.md](items.md) describes. The link is therefore a field rather than a naming convention. `SCROLL OF BLINDING` teaches BLIND, and it is the one scroll named for its effect rather than for its spell.

The 26 scrolls teach 26 distinct spells. All 23 spells with a SCROLL row have one. The other three (ARMS OF GIANTS, FIREBALL, JUMP OVER) have a scroll and no SCROLL row: every class that can cast them also trains them, so the book prints the training route.

**The item table and the scroll mask at 68 name different sets**, and they differ on four spells. ARMS OF GIANTS and FIREBALL have a scroll item and a mask of zero. CURE PARALYSIS and MINER'S LIGHT II carry a mask that no item answers. On both, every class the mask names also trains the spell, so the mask never reaches a page. The mask decides what the book prints, and the item decides what can be learned. Read the 26 items' spell ids against all 107 masks to see the four.

## Where the game's own data contradicts itself

Each is asserted in [tests/test_extract.py](../tests/test_extract.py).

- **`SWORD OF ICE`** promises in prose that "monsters immune to cold will not be hit", but its record carries no element bit, so in game they are hit. Every other cold spell sets bit 2.
- **`ERADICATE`** quotes 400 damage in its description, and the record holds 480.
- **`HARDY PARTY`** quotes 650 health, and the record holds 600.
- **`FIERY SPEAR`** appears on the F4 Druid page, but no table grants it to the Druid. It is not in the level-1 pair, not in the training row, and its scroll mask is zero. F3's own page for the spell lists only the Marksman, so the two pages disagree with each other.
- **Offset 22** is the lowest class level on 95 of the 98. The three that differ are DISEASE CLOUD (16 against 14), FIERY SPEAR (21 against 24) and MINER'S LIGHT I (3 against 4).
