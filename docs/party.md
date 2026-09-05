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

So the sheet says who holds what by drawing those rows in a second color on the one character who holds each. Repair, thievery and linguistics follow at `0x04DFE`, `0x04E2B` and `0x04E58`, against `0xCF83`, `0xCF85` and `0xCF87`.

**A press on one of those four rows moves the skill.** The hit test at `0x04B90` answers 2 to 5 for the four rows and puts the matching word in `si`, and `0x04C85` does the rest: a character carrying any of `0x1C40` is refused, and where the word already holds this character `si` is zeroed, which is how a skill is taken off somebody and left with nobody.

**A character holds one of the four at most.** The store at `0x16D2E` walks all four words and clears any that already names the character before writing the new one:

    16d47  mov cx, 4
    16d4a  mov di, 0xcf81
    16d4d  cmp bx, [di]
    16d4f  jne ...
    16d51  mov word [di], 0         ; already holds one -> give it up

## WHO WILL, where nobody holds it

Eight two-line prompts sit together from `DS:0xA75B`: **WHO WILL OPEN**, **SEARCH**, **EVALUATE**, **USE**, **REPAIR**, **BARTER** and **TRANSLATE**, with **WHO WILL LEARN** apart from them at `DS:0xA9FE`. They are put up by `0x058F0`, which takes a prompt number in `ax` and answers with a character handle or zero.

Every use of a party skill runs the same three steps. Repair, at `0x1C3F3`, is the pattern:

1. Read the word. Non-zero, and that character acts.
2. Zero, and the prompt goes up: `mov ax, 9 / lcall 0x058F0`. An answer of zero leaves without doing anything.
3. The answer is stored through `0x16D2E`, so the party has named someone and the prompt does not come again.

A character who cannot act is dropped from the word and the prompt comes back: `0x10FF3` writes zero over `DS:0xCF83` and loops to the read.

Bartering takes the same path at `0x06447`, with prompt 10, which is the one place a shop asks the question ([shops.md](shops.md)). What the party's repairer then does to a broken piece is [items.md](items.md)'s.

**What is not established** is which prompt number is which: the eight strings are in the file in that order, and two of the calls pass 9 and 10, but nothing has been read that maps the numbers onto the strings. Nor has the code that raises OPEN, SEARCH, EVALUATE, USE, TRANSLATE or LEARN been found: no word anywhere in the executable holds any of the eight string addresses.
