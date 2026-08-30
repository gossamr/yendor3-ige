# Encounters

Where every monster in the game stands, which monster it is, and what happens
to it once it is killed. [monsters.md](monsters.md) has the enemy record and
[combat.md](combat.md) what a monster does with it; this file is about the
1,862 of them the maps place.

The chain is **code**, and the addresses are below. The counts are **shape**.
Three of them have to agree, and they do. The save-file reading is
**measured**, against six saves from the user's own playthrough.

## A monster is a cell event

The section 28 cell-event table ([map.md](map.md)) has six kinds. The `0x0800`
kind is a monster, and its argument is a **spawn id**:

    0x10CB4  the cell carries kind 0x0800 -> test the spawn id's flag
    0x127FB  save section 5, bit `id`: set means the monster is not there
    0x1003A  clear -> mark the world cell, `[cell+6] |= 0x400`, `[cell+4] = id`
    0x107B8  the cell comes into view at range >= 0x11 -> find or make a slot
    0x125E6  claim a free slot of the eighty at DS:0x122C, `[slot] = id`
    0x12602  read section 30 record `id`  -> the enemy record's number
    0x1261D  read section 29 record that  -> the monster itself

**Section 30 is the spawn table.** One `uint16` per spawn id, holding the
number of the enemy record that id stands for. Its loader stub is image
`0x1807E`, which sets a record length of 2 and takes the record number from
`bx`, the id the cell carried. The section is 10,000 bytes and the table is
only the head of it. Ids run 1 to 1,862, and what follows the last one is other
data, a run of section sizes among it.

A spawn id is therefore a monster's identity for the whole game. It names the
enemy record through section 30, it carries the monster's own bit in the save,
and image `0x126EE` matches a live slot on it.

**Three counts agree.** That is what fixes the reading.

- The 1,862 `0x0800` events carry the arguments 1 to 1,862 with no gap and no
  repeat.
- Every one of those resolves through section 30 to an enemy record between 1
  and 72, never to record 0 (the sentinel) and never to record 62 (`NOT USED`).
- Every one of the 71 monsters the clue book lists is placed somewhere.

[tools/spawns.py](../tools/spawns.py) decodes it and prints the census;
[tests/test_spawns.py](../tests/test_spawns.py) asserts all three.

## A monster is killed once

Save section 5's flag says whether a monster is still on its cell. Three
instructions touch it:

| Image | What | When |
|---|---|---|
| `0x127B4` | set the bit | a slot is claimed for the monster, `0x126C5` |
| `0x1276B` | clear the bit | the monster drifts out of the window, `0x100B8` |
| `0x127FB` | test the bit | the cell is looked up, `0x10CC3` |

Set means the monster is not standing on its cell. Until it is killed, that is
because it is in one of the eighty live slots instead. The pair of states is
what makes a monster persist. Walk away and image `0x100B8` clears the bit and
zeroes the slot, so the monster is back on its own cell, at the position the
cell event gives it rather than wherever it had wandered to.

**Death leaves the bit set.** Image `0x0C57A` finds a slot whose health has
reached zero, pays the party at `0x1270C` and frees the slot at `0x12CA6`. That
routine clears the world cell's `0x400` bit and its `+4` word and zeroes the
156-byte slot, and it does not touch the flag. Nothing else clears it. Image
`0x1276B` has one caller, and it is the drift-out-of-window path, so a killed
monster does not come back.

The game therefore holds a fixed population. Each of the 1,862 monsters
pays out once, and the whole game is worth 13,322,378 experience, 10,989,385
gold and 66,180 nuore. Nothing regenerates and nothing is farmable.

**Measured.** Six saves from a playthrough have between 52 and 131 of these
flags set. Every set flag in all six names a monster standing on a map that
party had reached, which is Yendor, Thaine 6, 9 and 10, Kingdom of Bariag, the
Keep and the Sewers of Bariag. None falls outside the range the maps use. The
two the Athaneum's south gate sets, 37 and then 36, are the pair of centipedes
on adjacent cells of Yendor, where that gate leads. They are monsters coming
off the map as the party sees them, not gate state.
[tools/saves.py](../tools/saves.py) prints the flags and `spawns.gone` names the
monsters behind them.

## Which monsters stand where

47 of the 54 map slots hold monsters. The seven that hold none are ATHANEUM,
THE HOLY ORDER, ELFIN CITY, VISHAN'S STRONGHOLD LEVEL 1, DELIA'S ISLAND, GOLD
MINE and THE WAY OF THE ORDER. A map holds one to four kinds, and on 26 of
the 47 it holds two. Eleven monsters are placed once each: ACOKNIGHT, BLAZIOS,
CHAOTIC MINOTAUR, KING BARIAG, KING SLATOR, PALTIVAR, PIXIE LEADER, QUEEN
OBVERSIA, TITAN LORD, VISHAN and WASP QUEEN.

Slot is `(area, level)`, the block of the world grid [map.md](map.md)
describes.

| Map | Slot | Monsters | What stands there |
|---|---|---|---|
| DWARVEN HOMELAND MAP 1 | 1, 3 | 47 | FROST GIANT ×43, SNOW GIANT ×4 |
| DWARVEN HOMELAND MAP 2 | 1, 4 | 42 | FROST DWARF ×33, FROST DWARF TOWER ×6, DWARF TRANSMUTER ×3 |
| THAINE MAP 1 | 1, 6 | 26 | BLACK DRAGON ×25, BLAZIOS ×1 |
| THAINE MAP 2 | 1, 7 | 35 | BANDIT ×35 |
| KINGDOM OF BARIAG | 1, 12 | 35 | RABID WOLF ×21, WASP ×14 |
| SEWERS OF BARIAG | 1, 13 | 47 | SLIME ×19, SEWER RAT ×19, PURPLE SLIME ×6, FIRE MANTIS ×3 |
| COPPER MINE | 1, 14 | 38 | GNOLL ×30, PURPLE SLIME ×8 |
| PRISON | 1, 15 | 34 | PRISON GUARD ×30, GNOLL ×4 |
| NUORE MINE | 1, 16 | 25 | SCORPION ×17, MIMIC ×8 |
| CASTLE OF BARIAG LEVEL 1 | 1, 17 | 48 | BEHOLDER ×26, CASTLE GUARD ×12, MIMIC ×10 |
| CASTLE OF BARIAG LEVEL 2 | 1, 18 | 48 | BEHOLDER ×20, CASTLE GUARD ×17, EYE OF BARIAG ×10, KING BARIAG ×1 |
| YENDOR | 2, 1 | 13 | SCORPION ×11, CENTIPEDE ×2 |
| DWARVEN HOMELAND MAP 3 | 2, 3 | 59 | DWARF SCOUT ×37, FIRE DWARF TOWER ×16, DWARF ALCHEMIST ×6 |
| THAINE MAP 3 | 2, 6 | 44 | SATYR ×44 |
| THAINE MAP 4 | 2, 7 | 18 | CROCODILE ×11, CREEPING FUNGUS ×7 |
| THAINE MAP 5 | 2, 8 | 37 | CROCODILE ×22, CREEPING FUNGUS ×15 |
| THAINE MAP 6 | 2, 9 | 42 | ALLIGATOR ×25, WIZARD ×17 |
| KINGDOM OF OBVERSIA | 2, 11 | 42 | PIXIE ×41, PIXIE LEADER ×1 |
| ACOKNIGHT'S CAVE LEVEL 1 | 2, 12 | 53 | FIGHTER ×27, THIEF ×25, ACOKNIGHT ×1 |
| ACOKNIGHT'S CAVE LEVEL 2 | 2, 13 | 34 | EMERALD DRAGON ×25, FIGHTER ×9 |
| CAVE OF FIRE | 2, 14 | 48 | DWARF ALCHEMIST ×19, FIRE DWARF ×16, DWARF SCOUT ×13 |
| CASTLE OF OBVERSIA | 2, 15 | 78 | WARRIOR ×57, EMERALD DRAGON ×21 |
| TOWER OF OBVERSIA | 2, 16 | 43 | WIZARD ×34, WARRIOR ×8, QUEEN OBVERSIA ×1 |
| KINGDOM OF YENDOR | 2, 17 | 36 | FUNGUS ×16, ALLIGATOR ×10, SOLDIER ×10 |
| IRON MINE | 2, 18 | 36 | SOLDIER ×27, SORCERER ×9 |
| DWARVEN HOMELAND MAP 4 | 3, 3 | 36 | FIRE GIANT ×36 |
| THAINE MAP 7 | 3, 6 | 45 | LIZARD MAN ×38, CHAMELEON MAN ×7 |
| THAINE MAP 8 | 3, 7 | 42 | GHOUL ×28, SKELETON ×14 |
| THAINE MAP 9 | 3, 8 | 62 | PRAYING MANTIS ×34, FIRE MANTIS ×14, RABID WOLF ×14 |
| THAINE MAP 10 | 3, 9 | 35 | CENTIPEDE ×20, WASP ×14, WASP QUEEN ×1 |
| CASTLE OF YENDOR | 3, 11 | 33 | SORCERER ×15, KNIGHT ×12, SOLDIER ×6 |
| SILVER MINE | 3, 14 | 43 | DARK ELF ×30, PURPLE DRAGON ×13 |
| ELFIN SEWER | 3, 15 | 46 | ELF WATCHMAN ×43, SATYR ×3 |
| VISHAN'S STRONGHOLD LEVEL 2 | 3, 17 | 38 | ELF ASSASSIN ×26, DARK ELF ×6, PURPLE DRAGON ×5, VISHAN ×1 |
| CAVE OF ICE | 3, 18 | 39 | DWARF TRANSMUTER ×22, ICE DWARF ×17 |
| KINGDOM OF SLATOR | 4, 11 | 1 | SKELETON ×1 |
| DUNGEON OF SLATOR LEVEL 1 | 4, 12 | 35 | SPECTRE ×18, SKELETON ×17 |
| DUNGEON OF SLATOR LEVEL 2 | 4, 13 | 46 | WIGHT ×32, SPECTRE ×14 |
| CASTLE OF SLATOR LEVEL 1 | 4, 14 | 48 | SKELETAL WARRIOR ×29, WIGHT ×19 |
| CASTLE OF SLATOR LEVEL 2 | 4, 15 | 51 | GHOST ×34, SKELETAL WARRIOR ×16, KING SLATOR ×1 |
| UNDERGROUND TUNNEL | 4, 16 | 57 | CHAMELEON MAN ×49, GENIE ×8 |
| KINGDOM OF EURON | 4, 17 | 47 | GENIE ×28, TITAN ×19 |
| CASTLE OF EURON | 4, 18 | 50 | TITAN ×31, PHASE TITAN ×18, TITAN LORD ×1 |
| LABYRINTH | 5, 12 | 35 | MINOTAUR ×34, CHAOTIC MINOTAUR ×1 |
| KEEP | 5, 13 | 23 | MILLIPEDE ×18, WASP ×5 |
| THE PLANE OF SOULS | 5, 15 | 41 | WISP ×41 |
| QUARTZ CHAMBER | 5, 16 | 1 | PALTIVAR ×1 |

## How many of each

| Monster | Level | Placed | Experience each | Experience in all |
|---|---|---|---|---|
| WASP | 1 | 33 | 15 | 495 |
| CENTIPEDE | 1 | 22 | 10 | 220 |
| RABID WOLF | 2 | 35 | 25 | 875 |
| MILLIPEDE | 2 | 18 | 18 | 324 |
| WASP QUEEN | 2 | 1 | 50 | 50 |
| PRAYING MANTIS | 3 | 34 | 35 | 1,190 |
| SLIME | 4 | 19 | 60 | 1,140 |
| SEWER RAT | 4 | 19 | 55 | 1,045 |
| FIRE MANTIS | 4 | 17 | 47 | 799 |
| PURPLE SLIME | 5 | 14 | 80 | 1,120 |
| GNOLL | 6 | 34 | 100 | 3,400 |
| PRISON GUARD | 7 | 30 | 115 | 3,450 |
| SCORPION | 8 | 28 | 130 | 3,640 |
| MIMIC | 8 | 18 | 145 | 2,610 |
| BEHOLDER | 9 | 46 | 175 | 8,050 |
| CASTLE GUARD | 10 | 29 | 210 | 6,090 |
| EYE OF BARIAG | 10 | 10 | 245 | 2,450 |
| BANDIT | 11 | 35 | 280 | 9,800 |
| KING BARIAG | 11 | 1 | 1,000 | 1,000 |
| PIXIE | 13 | 41 | 325 | 13,325 |
| THIEF | 13 | 25 | 355 | 8,875 |
| EMERALD DRAGON | 14 | 46 | 430 | 19,780 |
| FIGHTER | 14 | 36 | 365 | 13,140 |
| PIXIE LEADER | 15 | 1 | 600 | 600 |
| DWARF SCOUT | 16 | 50 | 590 | 29,500 |
| FROST GIANT | 16 | 43 | 520 | 22,360 |
| FIRE DWARF TOWER | 16 | 16 | 100 | 1,600 |
| ACOKNIGHT | 16 | 1 | 1,000 | 1,000 |
| DWARF ALCHEMIST | 17 | 25 | 640 | 16,000 |
| WARRIOR | 18 | 65 | 770 | 50,050 |
| FIRE DWARF | 18 | 16 | 700 | 11,200 |
| SNOW GIANT | 18 | 4 | 600 | 2,400 |
| WIZARD | 19 | 51 | 900 | 45,900 |
| ALLIGATOR | 20 | 35 | 1,100 | 38,500 |
| SOLDIER | 21 | 43 | 1,500 | 64,500 |
| SORCERER | 21 | 24 | 1,800 | 43,200 |
| FUNGUS | 21 | 16 | 1,300 | 20,800 |
| CROCODILE | 22 | 33 | 2,300 | 75,900 |
| CREEPING FUNGUS | 22 | 22 | 2,100 | 46,200 |
| KNIGHT | 22 | 12 | 2,100 | 25,200 |
| QUEEN OBVERSIA | 22 | 1 | 10,000 | 10,000 |
| SATYR | 25 | 47 | 3,000 | 141,000 |
| ELF WATCHMAN | 26 | 43 | 3,300 | 141,900 |
| PURPLE DRAGON | 26 | 18 | 4,000 | 72,000 |
| DARK ELF | 27 | 36 | 3,600 | 129,600 |
| ELF ASSASSIN | 27 | 26 | 4,000 | 104,000 |
| FIRE GIANT | 28 | 36 | 4,300 | 154,800 |
| VISHAN | 28 | 1 | 15,000 | 15,000 |
| FROST DWARF | 29 | 33 | 4,600 | 151,800 |
| FROST DWARF TOWER | 29 | 6 | 500 | 3,000 |
| WISP | 30 | 41 | 2,500 | 102,500 |
| GHOUL | 30 | 28 | 8,000 | 224,000 |
| DWARF TRANSMUTER | 30 | 25 | 4,800 | 120,000 |
| ICE DWARF | 30 | 17 | 5,000 | 85,000 |
| SKELETON | 31 | 32 | 10,000 | 320,000 |
| SPECTRE | 32 | 32 | 11,000 | 352,000 |
| WIGHT | 33 | 51 | 13,000 | 663,000 |
| SKELETAL WARRIOR | 34 | 45 | 15,000 | 675,000 |
| GHOST | 35 | 34 | 18,000 | 612,000 |
| LIZARD MAN | 36 | 38 | 20,000 | 760,000 |
| KING SLATOR | 36 | 1 | 100,000 | 100,000 |
| CHAMELEON MAN | 37 | 56 | 22,000 | 1,232,000 |
| TITAN | 38 | 50 | 26,000 | 1,300,000 |
| GENIE | 38 | 36 | 25,000 | 900,000 |
| PHASE TITAN | 39 | 18 | 27,000 | 486,000 |
| MINOTAUR | 40 | 34 | 30,000 | 1,020,000 |
| BLACK DRAGON | 40 | 25 | 40,000 | 1,000,000 |
| TITAN LORD | 40 | 1 | 150,000 | 150,000 |
| CHAOTIC MINOTAUR | 41 | 1 | 200,000 | 200,000 |
| BLAZIOS | 42 | 1 | 500,000 | 500,000 |
| PALTIVAR | 45 | 1 | 1,000,000 | 1,000,000 |

The next smallest counts after the eleven singletons are SNOW GIANT at four and
FROST DWARF TOWER at six.
