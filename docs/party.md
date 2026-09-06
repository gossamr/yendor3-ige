# The party's own skills

Four of a character's twelve skills are not that character's to use. They are the party's, and the party names one character to hold each: **bartering**, **repair**, **thievery** and **linguistics**. Whoever holds a skill is who acts whenever the game needs it, wherever it needs it, and the choice stands until it is moved.

Everything here is **code**, read off the disassembly, except the counts, which are **shape**. [README.md](README.md) defines the classifiers.

## Four words hold the party's choice

`DS:0xCF81` and the three words after it, one per skill, in this order:

| Word | Skill | Column offset |
|---|---|---|
| `DS:0xCF81` | bartering | live `+0x68`, base `+0xA8` |
| `DS:0xCF83` | repair | `+0x6A`, `+0xAA` |
| `DS:0xCF85` | thievery | `+0x6C`, `+0xAC` |
| `DS:0xCF87` | linguistics | `+0x6E`, `+0xAE` |

Each holds a **character handle**, the same kind the four party slots at `DS:0xD0C9` hold, and zero means nobody. They sit with the party's own state, beside the position at `DS:0xCF75`, the clock at `DS:0xCF7F` and the purse at `DS:0xCF91` ([saves.md](saves.md)), so they travel with the party rather than with a character.

## The three the whole party shares

**Evidence is code.** Image `0x05CB0` walks the four handles at `DS:0xD0C9`, skips anyone carrying `0x1C40`, and sums three skills out of each record it keeps: mapping at `+0x64`, navigation at `+0x66` and survival at `+0x58`. It then divides each sum by the number of characters it summed, leaving a sum of zero alone rather than dividing it, and writes the three averages to `DS:0xCF23`, `DS:0xCF25` and `DS:0xCF27`. **So which character holds the points makes no difference**, and a character who is dead, stoned, frozen or paralyzed is out of the average altogether.

Each average is then read against rungs of its own. Each ladder is one run of comparisons against that average, so the numbers are read off the code rather than copied out of it ([extract.py](../tools/extract.py)). The averaging routine's own test of each average against zero is its divide guard and not a rung.

**Mapping** sets a bit of `DS:0xCEFD` per rung, in the same routine: `0x400` at 45, `0x8000` at 50, `0x200` at 60, `0x800` at 70 and `0x100` at 80. Bit `0x200` is the one the map screen tests before it will draw at all ([map.md](map.md)).

**Survival** decides how much of a monster is shown, at image `0x130CA`:

| Average | What the monster shows |
|---|---|
| 60 | a bar of what is left of its health, drawn from the struct's `+0x10` against its full at `+0x50` |
| 75 | a mark per condition it is under, the pictures picked off its state word at `+0x0C` |
| 80 | those conditions in words: DISEASED, POISONED, SICK, STONED, FROZEN, PARALYZED, CURSED, HEXED, JINXED |

Under 60 the party is told nothing about it at all.

**Navigation** sets the travel window at image `0x19022`, at 65, 80 and 95, each rung a smaller box of four words.

The other eight skills are personal. Four are the weapon skills a swing reads, casting is what a cast rolls against, survival is what a character saves a BREAK or a DESTROY with ([combat.md](combat.md)), and mapping and navigation are read where the party is drawn rather than asked of anyone.

## The character sheet names them, and moves them

Image `0x04DD1` draws the four rows in a run, and each one compares the character being drawn against its own word:

    04dd1  mov ax, [si+0x68]        ; bartering
    04dd4  mov bx, [si+0xa8]
    04dd8  mov [0xeac], 0x0f        ; the ordinary ink
    04dde  mov [0xeae], 0x8a
    04de4  cmp di, [0xcf81]         ; is this the character who holds it?
    04de8  jne  ...
    04dea  mov [0xeac], 0xcb        ; the second ink
    04df0  mov [0xeae], 0x9b

So the sheet says who holds what by drawing those rows in a second color on the one character who holds each. Repair, thievery and linguistics follow at `0x04DFE`, `0x04E2B` and `0x04E58`, against `0xCF83`, `0xCF85` and `0xCF87`. Image `0x14A87` draws the same four rows the same way on the other sheet, reading each character's live column and its base beside it.

**A press on one of those four rows moves the skill.** The hit test at `0x04B90` answers 2 to 5 for the four rows and puts the matching word in `si`, and `0x04C85` does the rest: a character carrying any of `0x1C40` is refused, and where the word already holds this character `si` is zeroed, which is how a skill is taken off somebody and left with nobody.

**A character holds one of the four at most.** The store at `0x16D2E` walks all four words and clears any that already names the character before writing the new one:

    16d47  mov cx, 4
    16d4a  mov di, 0xcf81
    16d4d  cmp bx, [di]
    16d4f  jne ...
    16d51  mov word [di], 0         ; already holds one -> give it up

## WHO WILL, where nobody holds it

Eight two-line prompts sit together from `DS:0xE75B`: **WHO WILL OPEN**, **SEARCH**, **EVALUATE**, **USE**, **REPAIR**, **BARTER** and **TRANSLATE**, with **WHO WILL LEARN** apart from them at `DS:0xE9FE`. They are put up by `0x058F0`, which takes a prompt number in `ax` and answers with a character handle or zero.

Every use of a party skill runs the same three steps. Repair, at `0x1C3F3`, is the pattern:

1. Read the word. Non-zero, and that character acts.
2. Zero, and the prompt goes up: `mov ax, 9 / lcall 0x058F0`. An answer of zero leaves without doing anything.
3. The answer is stored through `0x16D2E`, so the party has named someone and the prompt does not come again.

A character who cannot act is dropped from the word and the prompt comes back: `0x10FF3` writes zero over `DS:0xCF83` and loops to the read.

Bartering takes the same path at `0x06447`, with prompt 10, which is the one place a shop asks the question ([shops.md](shops.md)). What the party's repairer then does to a broken piece is [items.md](items.md)'s.

**The number indexes a table of panels at `DS:0xE265`**, one word each. Image `0x058F0` takes the word at `(n - 1) * 2` past it, which points at an eight-byte head and then a ten-byte line apiece: a line's fourth word is where its text starts and its fifth is how many strings to take from there. Reading the table gives the numbering.

| 1 to 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 to 17 |
|---|---|---|---|---|---|---|---|---|
| DO YOU WANT | OPEN | SEARCH | EVALUATE | USE | REPAIR | BARTER | TRANSLATE | PASSWORD |

Repair passing 9 and bartering passing 10 each land on their own string. A container raises 5 or 6 by its kind, a lid to open against a surface to search ([map.md](map.md)). WHO WILL LEARN is panel 33, raised where a magic scroll is learned rather than cast ([items.md](items.md)), and panel 32 is the USE ITEM? / LEARN SPELL? that asks which.

Twenty-three sites pass a panel number to `0x058F0`, and eight of them pass one of the seven WHO WILL numbers. Each of the eight names one of the four words:

| Prompt | Raised at | Names | Where |
|---|---|---|---|
| OPEN, SEARCH | `0x027B5`, `0x027AA` | `DS:0xCF85` thievery | a container, by its kind ([map.md](map.md)) |
| EVALUATE | `0x10FCA` | `DS:0xCF83` repair | the item panel ([items.md](items.md)) |
| USE | `0x1ABD8` | `DS:0xCF85` thievery | the item panel, mode 11 |
| REPAIR | `0x1C403` | `DS:0xCF83` repair | the party's own mend |
| BARTER | `0x06458` | `DS:0xCF81` bartering | a shop ([shops.md](shops.md)) |
| TRANSLATE | `0x0A2E8`, `0x1B087` | `DS:0xCF87` linguistics | both gated on a record's `+2` |

**EVALUATE is the item panel's own prompt**, answered into the repair word, so the party's repairer is also its appraiser. What the panel then draws off that character's repair skill is [items.md](items.md)'s.

**USE is the LOCKPICK's own prompt.** The dispatcher at `0x1987D` branches on `DS:0x5426`, which is the item being used, and item 11 is the LOCKPICK. It calls `0x1ABC8`, which reads `DS:0xCF85` and raises prompt 8 where it is zero, so the party's thief is who picks a lock, the same character OPEN and SEARCH name.

**Using one picks the lock the party faces.** Past the naming, `0x10CD5` picks the cell out of the two the party can reach, and an empty one answers "nothing to use it on". The cell event's own `+2` then says which lock it is: `0x8000` at `0x1AC42` goes to `0x0252E` and `0x4000` at `0x1AC4B` to `0x025CB`, which are the container and the passage. So the item is the second road to a lock, beside acting on the thing itself ([map.md](map.md)).

**TRANSLATE names the linguist at both of its sites**, and each is gated before it asks: `0x0A2D3` skips where the object's own `+2` is zero, and `0x1B070` where an item's `+2` carries none of bits `0x0E`. So a party is asked for a translator only against something written in a script it does not read. Both sites then turn the handle into a record through `0x15AFA`, which is `(handle - 1) * 500 + 0xD0D1`, and leave it at `DS:0x4424` and `DS:0x537C` for the ladder below to read.

### What the holder's own points then buy

Two of the four are read against a ladder of bare thresholds, the way the three averages are. Both ladders are one run of comparisons against the holder's live column, so the numbers come off the code ([extract.py](../tools/extract.py)) into `rungs` beside the three averaged ones.

| Skill | Column | Rungs | What each buys |
|---|---|---|---|
| Repair | `+0x6A` | 65, 80, 95 | weight, then damage and absorption, then worth ([items.md](items.md)) |
| Thievery | `+0x6C` | 55, 65, 80 | the trap, then locked and trapped together, then the key's metal ([map.md](map.md)) |

The mend roll reads the repair column again at `0x1C456`, against four bands of its own rather than these three.

**Bartering's ladder carries a margin per band** instead of a bare threshold, so it is read whole as seven bands rather than three rungs ([shops.md](shops.md)).

### Linguistics reads against one ladder per script

Linguistics is the one held skill whose rungs move. A thing written in a foreign hand names the **script** it is written in, and the script picks which four rungs the linguist's `+0x6E` is read against. Image `0x0A48C` holds the three, hardest last:

| Script | Rungs | Carried by |
|---|---|---|
| 2 | 80, 85, 90, 95 | 17 dwarves |
| 6 | 90, 95, 100, 115 | nothing |
| 4 | 100, 115, 120, 125 | 10 elves, 9 items |

Matching none of the three sets bit `0x20` of `DS:0x536A` and writes 0 to `DS:0xFED`, which is the party's own letters: nothing was foreign, so nothing needs translating.

**Two kinds of thing carry a script**, and each names it differently.

`DS:0x4422` is a copy of `[0xEC8 + 2]`, which is the person the party is talking to: `0xEC8` is the NPC record buffer, the same one `[0xec8+0x16]` holds a trainer's level cap in ([leveling.md](leveling.md)), and its `+2` is the record's `kind`. The word is the script id itself. **27 of the 141 people speak one**: 17 dwarves at kind 2 and 10 elves at kind 4. The game's own prose names both, "THE FROST DWARF LOOKS YOU UP AND DOWN" on npc 54 and "THE ELF SITTING AT THE TABLE" on npc 100. 25 of the 27 run a shop or sell a service, so the ladder gates trade rather than only flavor.

Image `0x1B3F2` is the same routine for an item, reached from the use dispatch at `0x19989` where the properties entry's `+2` carries any of bits `0x7800` ([items.md](items.md)). It selects on bits `0x08`, `0x04` and `0x02` of that same word, hardest last, so a record carrying two would read as the easier. **Nine items carry a script and each carries exactly one**, all of them bit `0x02`, which is the elves' script 4: GOLD PARCHMENT, the two SCROLLS OF WEIGHTS, RECIPE BOOK, SCROLL and the four PASSWORD PARCHMENTs.

**Script 6 is in the code and on nothing.** Its ladder is read and its `DS:0xFED` value is written, and no person's kind and no item's properties word selects it.

**The four rungs carry no numbers of their own.** `0x0A48C` loads them into `ax`, `dx`, `di` and `si` and falls into a run of four comparisons against the registers, so the ladder is in the loads rather than in the tests. [extract.py](../tools/extract.py) reads the loads.

**What a rung buys is how many words come through.** The band sets one bit of `DS:0x536A`, and the drawer at `0x18D12` branches on it. Each branch calls the word-drawer at `0x18E30` five times, and zeroes `DS:0xFED` around the first few of the five:

| Band | Bit | Words legible per 5 |
|---|---|---|
| under the first rung | none | 0 |
| first rung | `0x10` | 1 |
| second | `0x08` | 2 |
| third | `0x04` | 4 |
| fourth | `0x02` | 5, and `DS:0xFED` cleared for the whole text |

`0x18E30` draws one word: it emits characters until a space, and only on reaching the string's end does it wrap the line and count the string off `cx`. So the five are five words, and a linguist one rung short of fluent still reads four words in every five.

**`DS:0xFED` is which alphabet to draw in.** Image `0x19D63` takes a character's code, subtracts a space and multiplies by 6 to reach a glyph of six rows, each row six bits with the high bit leftmost. It reads that glyph out of whichever of the four alphabets `DS:0xFED` picks, the word being a byte offset into the four pointers at `DS:0x516`: 0 is the party's own letters and 2, 4 and 6 are the three scripts, each 96 glyphs from a space up. So a word nobody in the party can read is drawn in the speaker's own hand rather than blanked, and [extract.py](../tools/extract.py) carries all four out.
