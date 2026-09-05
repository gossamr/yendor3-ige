# Making a character, and making a party

Three screens stand between the game starting and the party walking: character creation, the party assembly, and the disk. This reads all three, in the order a player meets them, and the introduction the menu's fifth item plays.

Everything here is **code**, read off the disassembly, with two readings **rendered** and one **screens**, each marked where it is made. [README.md](README.md) defines the classifiers. Coordinates are image offsets, which is the file offset minus `0x4000`, and `DS:` offsets are what the code uses directly, DGROUP being at image `0x1ddb0`. The formulas creation runs are [leveling.md](leveling.md)'s, and the record it fills is [saves.md](saves.md)'s.

## Where it lives

| What | Where |
|---|---|
| Creation screen, and its option list | `0x14c60` |
| Class list | `0x13f36`, picked at `0x140de` |
| Portrait gallery | `0x145c2`, picked at `0x14703` |
| Attribute roll | `0x14e20` |
| Skills derived from it | `0x13af3` |
| Item list | `0x1410d`, picked at `0x14235` |
| Name entry | `0x144ea` |
| Keep character | `0x14de1` |
| Discard the character being made | `0x13f26` |
| Party assembly | `0x1b7b4`, read at `0x1b83e`, toggled at `0x1b905` |
| Assembly done | `0x1b9c9` |
| New game | `0x1514e` |
| The roster | `DS:0xCEDD`, 10 x 500 bytes |
| The party's four handles | `DS:0xD0C9` |
| The character being made | `DS:0x537C` |
| The eight items on offer | `DS:0x0F18`, and which are taken in `DS:0x536A` |
| What the screens say | `DS:0x7C94` onward, and `DS:0x8863` onward |

## The labels

Every labels these screens display is a NUL-terminated string in the data segment, drawn by the text routine as each screen is put up. [tools/labels.py](../tools/labels.py) reads the run at `DS:0x7C94` to `DS:0x7DD7` and the three at `DS:0x8863`, `DS:0x8899` and `DS:0x88A9`:

CHARACTER CREATION, PICK A CLASS, `QUIT "CREATE"`, MALE, FEMALE, PICK A PORTRAIT, SELECT AN OPTION, CLASS, PORTRAIT, ROLL ATTRIBUTES, PICK ITEMS, TAKE UP TO FOUR ITEMS, NAME CHARACTER, ENTER THE NAME, KEEP CHARACTER, CHARACTER PREVIEW, DELETE, RETURN, ARE YOU SURE?, YES, DELETE, NO, KEEP.

**Two of the screens say their words in paint.** The first menu is run 0 picture 2, a stone wall under a gold THE TYRANTS OF THAINE with Character Creation, Assemble a Party, Enter the Game, Credits and Introduction under it, and the assembly is run 0 picture 4, nine boxes over ASSIGN UP TO 4 CHARACTERS and DONE. Neither set of words is stored as text anywhere, so they are read off the pictures rather than out of the file, and the picture each is painted in is given beside it wherever they are used.

## The Introduction

**The menu's fifth item is image `0x1BB7C`**, and [tools/intro.py](../tools/intro.py) reads it. The same routine is what the menu falls into on its own after about four seconds of no input, which [patching.md](patching.md)'s `no-attract` takes out and leaves the menu item alone.

Five scenes, each a routine of its own, with an Escape poll between them and after every frame inside them. Image `0x1BBD3` is the teardown: it fades out, redraws the menu and puts song 1 back.

| Scene | Image | Draws | Says |
|---|---|---|---|
| 1 | `0x1BC75` | run 0 picture 8, faded in | nothing; holds 35 ticks |
| 2 | `0x1BCD1` | run 0 picture 9, wiped on | sounds 51 to 53, a 3-tick pause, then 54 to 58 |
| 3 | `0x1BD4A` | run 0 picture 10, wiped on | sounds 59 to 66 |
| 4 | `0x1BDB0` | run 0 picture 11, then picture 12 scaled onto it over 25 frames | song 10, sound 83, and COPYRIGHT 1997 SW GAMES |
| 5 | `0x1BF44` | run 3 pictures at (70, 40) | song 11, sound 71, and the three talking heads |

**Scene 4's zoom is a rectangle walked frame by frame.** Each of the 25 frames redraws picture 11 whole and blits picture 12 through the scaling blitter at image `0x19DC9`, mode 20, into a box that starts at (6, 4) to (157, 98) and steps by (12, 8) and (-6, -4) a frame. That is the same blitter the viewport places an object face with ([view.md](view.md)).

**Two routines here are the ending's own** ([quests.md](quests.md)). Image `0x1C376` is the scanline wipe, 80 columns of 200 rows a dword at a time with a stride of `0x13C`. Image `0x1C3B4` waits for a sound to finish, or `cx` ticks where sound is switched off, which is what paces a run of spoken lines.

**Image `0x1C11E` cycles pictures.** It draws `DS:0xFC3`, shows it, steps the number and waits two ticks, `cx` times, polling Escape between frames. Scene 5 is nine of those beats in a row.

### The three talking heads

**Image `0x1C13C` plays a 14-byte block** ([audio.md](audio.md) has the layout). The intro holds the only three, at `DS:0x597C`, `DS:0x598A` and `DS:0x5998`, and they are the only path to sounds 67 to 75 except 71.

| Block | Sounds | First picture | Pictures per sound | Quiet ticks |
|---|---|---|---|---|
| `0x597C` | 67 to 70 | 40 | 5 | 120 |
| `0x598A` | 72 | 73 | 7 | 180 |
| `0x5998` | 73 to 75 | 73 | 7 | 280 |

**The caption is the substitute, not a subtitle.** The routine tests the SOUND FX switch, `DS:0xCF63` bit 3, before anything else. With sound on it plays the block's run of lines, cycling the head's pictures while each one sounds, and prints nothing. With sound off it prints the caption and cycles the head for the block's own tick count instead. So the words reach the screen only where they cannot be heard, which is why these three lines are the only spoken content the game writes down anywhere.

The three read, in order: "ALTHOUGH THE APPEARANCE OF PALTIVAR IS IMMINENT, THERE ARE MORE URGENT MATTERS AT HAND IN THAINE.", "THEIR SUPPLY OF MAGIC ORE HAS RUN OUT, AND THE KINGDOMS HAVE BECOME MORE AGGRESSIVE IN THEIR ATTACKS AGAINST EACH OTHER.", and "IF THE KINGDOMS IN THAINE ARE NOT AT PEACE, YENDOR WILL SURELY BECOME THEIR NEXT VICTIM. WE MUST ACT QUICKLY. GO NOW TO THE ATHANEUM AND SPEAK WITH FLAGELL. HE WILL TELL YOU WHAT IS TO BE DONE."

Scene 5 opens with a panel of its own above them, two lines at `DS:0x9325`: YOU SPEAK WITH ZAMORA AT HIS HOME NEAR THE ATHANEUM...

## The roster is ten slots, and nine of them are characters

`DS:0xCEDD` is 500 bytes a slot, and slot 0 is the party header rather than a character: the position, the clock, the purse, the four handles and the container allocator's two words ([saves.md](saves.md)). So slots 1 to 9 hold characters, and a handle is that slot's number. `WORLD.DAT` section 32 is the template of all ten, and the game ships four characters in slots 6 to 9.

**A slot with level 0 in it is empty.** That is the test the assembly makes at image `0x1b911`, on record offset 22, and it is what leaves five slots for characters a player makes.

## Character creation

The screen shows one character being made, at `DS:0x537C`, and an option list beside it. Image `0x14c60` draws the list and image `0x14cfc` reads it, so both the mouse and a letter reach the same branch:

| Key | Option | What it does |
|---|---|---|
| `C` | CLASS | the class list, and the sex |
| `P` | PORTRAIT | the portrait gallery |
| `R` | ROLL ATTRIBUTES | roll the six, and derive everything from them |
| `I` | PICK ITEMS | take up to four of eight |
| `N` | NAME CHARACTER | up to 13 characters |
| `K` | KEEP CHARACTER | write the character into a free roster slot |
| `Q` | QUIT "CREATE" | discard it and leave |

Leaving discards: image `0x14e17` calls `0x13f26`, which zeroes all 500 bytes of the slot the character was being built in.

### The class, and the sex

Image `0x13f36` draws the nine classes in three columns under NON-MAGIC USERS, CLERIC TYPES and WIZARD TYPES, which is fighter, merchant and rogue, then monk, alchemist and paladin, then mage, druid and marksman. The record stores 1 to 9 in that order ([leveling.md](leveling.md)). A class answers to its initial where the initial is free, and MERCHANT and ALCHEMIST take `M` and `A` first, so MONK answers to `O`, MAGE to `G` and MARKSMAN to `K`.

**Picking a class rebuilds the character.** Image `0x140de` stores the class, sets level 1, and then rolls and derives, so the attributes a player was happy with are gone. [patching.md](patching.md) has the three bytes that stop that.

The sex is record offset 16, 1 for male and 2 for female. It is switched in the portrait gallery rather than here, by `M` and `F` at image `0x146a3`.

### The portrait

Nine portraits, a 3 by 3 gallery, drawn by image `0x145f0` as pictures of run 7 of `PICTURES.VGA`. The picture number is `28 + 2 x cell + sex - 1`, so the eighteen portraits at 28 to 45 are the two galleries interleaved, even for male and odd for female. `M` and `F` switch, which redraws the gallery, and the keys `1` to `9` pick.

Picking writes both halves at image `0x14713`: record 18 takes the picture number and **record 20 takes the cell, 0 to 17**, which is the field the gallery reads back to show which one is chosen. **Rendered**, for the four the game ships: each holds a number in 28 to 45 whose parity matches its sex, and [view.md](view.md) has the drawing diffed against a capture.

### The roll

Image `0x14e20`, `45 + rand(15)` per attribute, written into the live column and the maximum column both, so the two are identical at level 1. The order rolled is strength, dexterity, intelligence, wisdom, charisma, stamina, and stamina is last because health is derived from it immediately after.

Then, in this order: carry capacity is ten times strength, health is 25% of stamina, magic points come from that class's blend of wisdom and intelligence, and image `0x13af3` derives the twelve skills. [leveling.md](leveling.md) reads all four, and [tools/skills.py](../tools/skills.py) rebuilds 56 of 56 fields of the four shipped characters from their attributes alone.

### The items

**Eight items, and a character takes up to four.** Image `0x0f040` writes the eight at startup and they stand for the run, so every class is offered the same:

| Item | id |
|---|---|
| SLING | 8 |
| KNIFE | 14 |
| CLUB | 18 |
| BO STICK | 22 |
| CLOTHES | 4 |
| ROBES | 25 |
| BAG | 28 |
| MAGIC GRAPES | 31 |

The low eight bits of `DS:0x536A` are which have been taken, bit `0x80` for the first, and the list draws only what is left, so each is taken once. Each goes through the ordinary equip dispatch at image `0x04237`, which is what puts the weapon in hand, the clothes on the body and the grapes in the pack ([items.md](items.md)). Leaving creation clears the eight bits at image `0x14312`.

**Screens**, against the party the game ships: SQUIRE holds SLING, BO STICK, CLOTHES and a BAG, and DIANA holds SLING, CLUB, ROBES and MAGIC GRAPES. Four each, all eight ids from this table.

### The name, and keeping the character

The name entry at image `0x14536` passes a 13-character limit to the text input and a scratch buffer at `DS:0x9926`. An empty answer is refused, and the accepted name is copied to record offset 0.

KEEP CHARACTER copies the character into a free roster slot and then writes the whole 5,000-byte roster to disk, at image `0x14de4`: one write, offset 0, length `0x1388`. It goes to `CURGAME`, which the game writes and never reads back, so the character stands for the rest of the session and a relaunch rebuilds the roster from the `WORLD.DAT` template without it ([saves.md](saves.md)).

## Assembling the party

The assembly lists the roster slots holding a character, level above 0, with a mark per slot saying whether it is in, and toggles membership at image `0x1b905`:

- **Membership is bit `0x0800` of record offset `0x15C`.** Image `0x1b974` sets it and `0x1b922` clears it.
- The four words at `DS:0xD0C9` hold the handles, in the order they were picked. Adding takes the first of the four that is zero, and removing zeroes whichever word holds that handle. **The party is four because the list is**: with no zero word left, image `0x1b967` plays a sound and refuses.
- DONE needs at least one member. Image `0x1b9cf` adds the four handles and returns without leaving where the sum is zero.

Nothing sorts the four. The order in the list is the order a player picked them, and it is the order every loop over the party walks, so it is the order the character plates appear in and the order a turn list is built from ([combat.md](combat.md)).

## New game

The disk panel's NEW GAME, at image `0x1514e`, is what puts the three screens back in front of a player mid-game. It clears the four handles, clears bit `0x0800` on all nine roster slots, and resets the party state: the position to x 460, y 46 facing north, the clock, the mapping bits, the container allocator's free list, and the travel flags. Then it writes a fresh save. The characters themselves are left standing in the roster, so a new party is assembled out of the same nine.
