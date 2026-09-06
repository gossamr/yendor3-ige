# WORLD.DAT and the section directory

`WORLD.DAT` is 4,350,901 bytes and carries an explicit table of contents, which is stored in `REGISTER.EXE`. This document records settled findings only. Each format has a document of its own, named in the tables below. [tools/sections.py](../tools/sections.py) reads the directory, and [tools/labels.py](../tools/labels.py) reads the label run.

## The two tables

- **Master table, `REGISTER.EXE:0x2CF37`**, 36 consecutive little-endian dwords, each a byte offset into `WORLD.DAT`. Consecutive entries bound the 35 sections. The last entry equals the length of the file, so it also serves as an end marker. Entries 5 and 6 hold the same offset, which makes section 5 empty.
- **Restoration table, `REGISTER.EXE:0x2D4AF`**, five offsets covering the clue book's own corpora. Its last entry has no successor, so the upper bound of the spell descriptions comes from the next master table offset instead.

Four more tables follow the master table, running from `0x2CFC7` to `0x2D3A3` with no gap: the offsets and lengths of the 24 songs in section 14 and of the 141 sounds in section 15 ([audio.md](audio.md)). Eight more run from `0x2D3A3` to `0x2D4AF`, which is where the Restoration table begins: the positions and lengths of the books, parchments and scrolls in sections 16 to 18, and of the fourth kind that holds nothing ([items.md](items.md) names all eight by their `DS:` addresses).

The map grid sits **before** section 0. Seven areas of 76,800 bytes fill `0x000000` to `0x083400`, and the first section begins exactly where they end.

## How the game opens a section

One stub per section points a file handle at the right master-table entry and sets the record length. The handle is the one [saves.md](saves.md) describes for `CURGAME`, and the seek is the same multiply. **The record length is the game's own reading of a section**, so the table below takes it from the stub rather than from a division that happens to come out whole. Six stubs take the length from a variable instead of an immediate, and one initializer at image `0x0F166` to `0x0F1D2` sets all six.

Sections 16 to 20 are reached without one. The books, parchments and scrolls are addressed through the eight tables at `0x2D3A3` ([items.md](items.md)) and the clue book's corpora through the Restoration table. Section 20 is the container those corpora sit in, and its own first 16,800 bytes are the per-cell bit array at `0x3C4F02` ([map.md](map.md)).

The **Stub** column below is what a scan of the image for each master-table entry's own address returns: 26 sections have one, and it is `none` for the nine that do not. A scan finds a literal, so a section addressed through a computed index would read `none` here too.

| # | Offset | Size | Stub | Record | Records | Content |
|---|---|---|---|---|---|---|
| 0 | `0x0083400` | 840 | `0x18029` | 6 | 140 | the map registry ([map.md](map.md)) |
| 1 | `0x0083748` | 760 | `0x180BD` | 20 | 38 | map names, one 20-character line each ([map.md](map.md)) |
| 2 | `0x0083A40` | 912 | `0x17B53` | 24 | 38 | the same 38 names as two 12-character lines |
| 3 | `0x0083DD0` | 280 | `0x180D7` | 2 | 140 | the song each map slot plays ([audio.md](audio.md)) |
| 4 | `0x0083EE8` | 36,598 | `0x17FED` | 58 | 631 | item records ([items.md](items.md)) |
| 5 | `0x008CDDE` | 0 | `0x1800B` | 58 | 0 | a second table of the item record's own 58 bytes, zero length here |
| 6 | `0x008CDDE` | 2,368 | `0x17F39` | 16 | 148 | the effects table ([items.md](items.md)) |
| 7 | `0x008D71E` | 2,652 | `0x17F57` | 12 | 221 | armor properties ([items.md](items.md)) |
| 8 | `0x008E17A` | 1,208 | `0x17F75` | 8 | 151 | misc properties ([items.md](items.md)) |
| 9 | `0x008E632` | 2,520 | `0x17F93` | 12 | 210 | weapon properties ([items.md](items.md)) |
| 10 | `0x008F00A` | 26,000 | `0x17FB1` | 26 | 1,000 | loot bundles ([map.md](map.md)) |
| 11 | `0x009559A` | 1,600 | `0x17FCF` | 4 | 400 | cell locks in the first 71 records ([map.md](map.md)); records 71 to 399 are **undecoded**, below |
| 12 | `0x0095BDA` | 5,376 | `0x17D6D` | 768 | 7 | VGA palettes ([map.md](map.md)) |
| 13 | `0x00970DA` | 2,493 | none | | | Creative's CT-VOICE driver ([audio.md](audio.md)) |
| 14 | `0x0097A97` | 144,419 | none | | 24 | CMF songs ([audio.md](audio.md)) |
| 15 | `0x00BAEBA` | 3,174,774 | none | | 141 | VOC sounds ([audio.md](audio.md)) |
| 16 | `0x03C2030` | 6,864 | none | | 8 | books ([items.md](items.md)) |
| 17 | `0x03C3B00` | 2,944 | none | 368 | 8 | parchments ([items.md](items.md)) |
| 18 | `0x03C4680` | 2,178 | none | | 6 | scrolls ([items.md](items.md)) |
| 19 | `0x03C4F02` | 0 | none | | 0 | the fourth text kind, whose table holds one entry of zero length ([items.md](items.md)) |
| 20 | `0x03C4F02` | 81,847 | none | | | the per-cell bit array, then the Restoration corpora below |
| 21 | `0x03D8EB9` | 5,640 | `0x17C78` | 40 | 141 | NPC records ([shops.md](shops.md)) |
| 22 | `0x03DA4C1` | 47,400 | `0x17BE4` | 60 | 790 | conversation topics ([shops.md](shops.md)) |
| 23 | `0x03E5DE9` | 16,980 | `0x17C05` | 60 | 283 | the rest of the same table |
| 24 | `0x03EA03D` | 51,034 | `0x17C99` | 34 | 1,501 | prose lines ([shops.md](shops.md)) |
| 25 | `0x03F6797` | 51,000 | `0x17CBA` | 34 | 1,500 | the same |
| 26 | `0x0402ECF` | 37,026 | `0x17CDB` | 34 | 1,089 | the same |
| 27 | `0x040BF71` | 18,844 | `0x17DBE` | 18,844 | 1 | where each cell of the first-person view lands on screen ([view.md](view.md)) |
| 28 | `0x041090D` | 26,472 | `0x17D35` | 26,472 | 1 | cell events ([map.md](map.md)) |
| 29 | `0x0417075` | 7,738 | `0x18061` | 106 | 73 | enemies ([monsters.md](monsters.md)) |
| 30 | `0x0418EAF` | 10,000 | `0x1807F` | 2 | 5,000 | the spawn table in the first 1,862 ([encounters.md](encounters.md)); ids 1,863 to 5,000 are **undecoded**, below |
| 31 | `0x041B5BF` | 8,560 | `0x18043` | 80 | 107 | spells ([spells.md](spells.md)) |
| 32 | `0x041D72F` | 5,000 | `0x17D17` | 5,000 | 1 | the roster template ([saves.md](saves.md)) |
| 33 | `0x041EAB7` | 29,214 | `0x17D54` | 29,214 | 1 | the publisher's logo, below |
| 34 | `0x0425CD5` | 1,760 | `0x17B72` | 1,760 | 1 | the screen DOS is left on, below |

**Three of those tables are split across section boundaries**, and each is one table. [shops.md](shops.md) shows the arithmetic.

**Evidence for the directory itself is shape.** The last of the 36 dwords equals the length of `WORLD.DAT`, entries 5 and 6 hold the same offset, and the run never decreases. **Evidence for a record length is code**, the stub named on that row, and every section whose stub carries one divides by it with no remainder. What each section *holds* is confirmed in the document the row names.

## The two sections that are a picture and a screen

**Section 33 is the publisher's logo**, a 640 by 480 PCX in 256 colors. Its header reads manufacturer 10, version 5, RLE encoding, 8 bits in one plane, 640 bytes to a line, and bounds 0,0 to 639,479. The RLE decodes to exactly 307,200 bytes and stops exactly where the 769-byte palette trailer begins.

Three images show it. `0x158AE` asks for VESA mode `0x101`, which is 640 by 480 in 256 colors. `0x15A4E` allocates `0x722` paragraphs and reads the section whole into them. `0x15A3C` writes the 768-byte palette to ports `0x3C8` and `0x3C9`. The same bytes ship beside the game as `LOGO.PCX`, and the two are **identical over all 29,214**.

**Section 34 is the screen DOS is left on**, 880 character and attribute pairs, which is 80 columns by 11 rows. Image `0x00737` opens it and image `0x00745` reads it into `DS:0x9926`, after `INT 10h AX=0003` has put the adapter back in text mode. Image `0x0074F` copies `0x370` words to `B800:0000` and the exit follows through `INT 21h AH=4Ch`. The glyphs are CP437 and the screen blanks with `0x00` as well as `0x20`, which a text-mode adapter draws alike. Boxed in block characters, it reads:

    █▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀█
    █                 Thank you for playing The Tyrants of Thaine                  █
    █                from SW Games and Spectrum Pacific Publishing                 █
    █                                                                              █
    █  Be sure to check out other releases from Spectrum Pacific Publishing at     █
    █                       www.SpectrumPacific.com.au                             █
    █                                                                              █
    █                THIS IS NOT SHAREWARE. PLEASE DO NOT DUPLICATE!               █
    █                                                                              █
    █              The Tyrants of Thaine, Copyright (C) 1997 SW Games              █
    █▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄█

[tools/startup.py](../tools/startup.py) reads all three of these, and [tests/test_startup.py](../tests/test_startup.py) holds them to the bytes.

## Three runs past the end of a table, all **undecoded**

Sections 11 and 30 both hold more bytes than the records they are read for, and the legend labels stop short of their own run. The three runs are 1,316 bytes, 6,276 and 2,912, and they are **undecoded**. What is established about them:

- **All three open on the same 44 bytes.** Read as a 32-byte signature, that opening occurs **exactly three times in the whole of `WORLD.DAT`**: section 10 at `+19,321`, section 11 at `+284` and section 30 at `+3,726`.
- **The string `..\GAME\DAD\WORLD.DAT` occurs six times in the file.**
- **Section 30's run holds `0x2710` and `0x0418EAF`**, which are that section's own record count and its own offset in the file.
- **Section 11's run is 1,096 zero bytes of 1,316 over 56 distinct values; section 30's is 2,216 of 6,276 over all 256; the label run's is 263 of 2,912 over 127.**

**Which of the three the game reads is observed.** [tools/trace_reads.js](../tools/trace_reads.js) drives a boot under the hook [tools/trace_fs.js](../tools/trace_fs.js) puts on every `FS.read`, and a run to the menu logs 1,022 reads of `WORLD.DAT`. Seven sections come in whole, one request each, inside the first 260 ms:

| Section | Requested | Section is |
|---|---|---|
| 4, items | 36,597 | 36,598 |
| 28, cell events | 26,471 | 26,472 |
| 10, loot bundles | 25,999 | 26,000 |
| 27, view slots | 18,843 | 18,844 |
| 31, spells | 8,559 | 8,560 |
| 32, roster template | 4,999 | 5,000 |
| 11, cell locks | 1,599 | 1,600 |

Every one of the seven asks for a byte less than the section holds. **Section 11 is among them, so its whole run past record 71 is read off the disk at startup.** Section 30 is not: it is read two bytes at a time through its own stub as the game wants a spawn id, and over that run the furthest byte reached was 811 of 10,000. The label section is read in 1,024-byte blocks as the clue book wants captions, reaching record 39 in the same run.

**What is established is how far each table's own index reaches.** All three are indexed out of the game's data rather than by a loop with a bound in the code, so the reach is a property of the data and can be counted:

| Table | Indexed by | Range the data names | Records the table holds |
|---|---|---|---|
| section 11, locks | the `0x4000` cell event's argument | 1 to 71, each exactly once over 71 events | 400 |
| section 30, spawn ids | the `0x0800` cell event's argument | 1 to 1,862, each exactly once over 1,862 events | 5,000 |
| legend labels | a marker record's own caption field | 1 to 137, all 137 present over 207 markers | 138 including the ruler at 0 |

Each index is onto exactly the part of its table that holds data, with nothing skipped and nothing repeated, so **no cell and no marker in the maps names a record inside any of the three runs**. An index the code computes rather than reads off a record does not appear in the count.

**One instruction addresses section 11.** Sections 10 and 11 are read into one buffer by two stubs that differ in where they start and how much they take: image `0x0F1EB` opens at offset 0 for a record of 26,000 bytes, image `0x0F21C` at offset 26,000 for a record of 1,600, both onto the handle block at `DS:0x96C2` and the buffer segment at `DS:0x0FAA`. So a read of section 11 is a read of that buffer at 26,000 or past it, and 26,000 reaches the code as `26 * [DS:0x545E]`. Reading every offset of the image as if an instruction began there, the superset disassembly [xref.py](../tools/xref.py) uses, `DS:0x545E` is named twice: image `0x0F070` writes 1,000 into it, and image `0x02623` multiplies it by 26 and adds `(argument - 1) * 4`, which is the lock reader. **Evidence is code.** A site that reached the same base by a literal or by a register the scan cannot follow would not appear, and the scan was also run for the literal 26,000, which occurs at the two stubs and nowhere else.

## The Restoration corpora

| # | Offset | Size | Content |
|---|---|---|---|
| 0 | `0x03c90a2` | 42,075 | the walkthrough, 33 × 1,275 |
| 1 | `0x03d34fd` | 2,000 | the legend marker table, 207 × 8 ([map.md](map.md)) |
| 2 | `0x03d3ccd` | 6,500 | legend labels, 138 of them ([map.md](map.md)) |
| 3 | `0x03d5631` | 432 | the spell description index ([spells.md](spells.md)) |
| 4 | `0x03d57e1` | 14,040 | spell descriptions, 360 × 39 ([spells.md](spells.md)) |

**Restoration is the clue book that shipped with the game.** `REGISTER.EXE:0x2A7CD` holds the string `RESTORATION:THE ON-LINE CLUE BOOK`. It opens with F8 or TAB, either from the main menu or during play, and it has six sections: F1 maps, F2 monster statistics, F3 spells, F4 magic users, F5 inventory items, and F6 complete walk through. F2, F4 and F5 are rendered from the binary tables. Only the walkthrough and the spell descriptions are stored as text.

## Text formats

- **The walkthrough** is 33 pages of 1,275 bytes, which is 25 rows of 51 columns. The last row of each page is its footer, `"n OF 33"`. The section headings are the rows matching `NN. LOCATION`, and there are 50 of them.
- **Legend labels** are NUL-terminated strings of 25 visible characters and a NUL, on a fixed 26-byte stride. Slot 0 is a column ruler, `1234567890123456789012345`. The run holds **138 non-empty labels**, records 0 to 137, and record 138 is the first the stride returns something unprintable for. What the section's remaining 2,912 bytes are is **undecoded**, and they open the same way sections 11 and 30 do past their own data, above. The marker records index captions 1 to 137, so every caption a marker names sits inside the run. [map.md](map.md) describes how the run is read.

**The character set.** The font has no apostrophe, so `~` stands for one. `\` is the fraction slash, so `1\2` is one half. A run of four or more `e` is a horizontal rule glyph rather than text. Every string is upper case. `labels.text()` applies these substitutions, and a raw read is not a name. The file stores `MAGE~S CHAIN MAIL ARMOR`, and `MAGE'S CHAIN MAIL ARMOR` is what it means.

## The label run, which names the fields

`REGISTER.EXE:0x2A780` to `0x2B300` is a contiguous run of NUL-separated strings. It holds every caption the Restoration screens print: the monster statistic names, the twelve effect names *in bit order*, the seventeen special attack names, the eight item categories, the spell field names, the AFFECTS and WHEN vocabularies, and the six magic user class triads (`MONK/CLERIC/PRIEST`, `ALCHEMIST/TRANSMUTER/HEALER`, `PALADIN/CAVALIER/HERO`, `MAGE/WIZARD/SORCERER`, `DRUID/ENCHANTER/SAGE`, `MARKSMAN/RANGER/KNIGHT`).

[tools/labels.py](../tools/labels.py) reads these strings from the file, and asserts that all 86 strings it declares are present.

## The executable

`REGISTER.EXE` is a real mode 16-bit MZ image in a large or huge memory model. It is not packed, it has no overlays, it has almost no BSS, and its length matches its header exactly. It **requires EMS** (`EMM Ver 4.0`, with at least 1 MB expanded memory), which `README.DOC` states and which the game enforces at startup.

`e_csum` is zero, and DOS ignores that field. The loader rewrites 4,000 words from the **relocation table** at load time, so those words in memory do not match the words in the file. [tools/mz.py](../tools/mz.py) builds the map of them, and [patching.md](patching.md) describes what that constrains.

Addresses in these documents are **image offsets**, meaning the file offset minus the 16 KB header, except where a `DS:` prefix indicates otherwise. `DS:0` sits at image `0x1DDB0`, and a far call to `seg:off` lands at image `seg * 16 + off`.

### How it gives up, and what it names

Image `0x18C1A` is the abort handler, and 168 far calls reach it. `DS:0x53E0` holds the code to give up with: zero returns at once, so a caller sets the code before the operation it is guarding and the operation clears it on success. A nonzero code indexes a table of twenty near offsets at `cs:0x39E`, each a three-byte stub loading that code's message address into `ax` and falling into the teardown at `0x18C39`, which stops the sound, restores the video, puts the mouse away, prints the message with `INT 21h AH=09` and exits through `INT 21h AH=4Ch` with `DS:0x53E0` as the exit status.

**The twenty messages are what the game distinguishes between when it cannot go on**, and the list names four of its data files and both of its memory requirements.

| Code | Message |
|---|---|
| 0 | Calling program error. |
| 1 | Memory allocation error. |
| 2 | Problem with PICTURE.VGA. |
| 3 | Problem with pallette data. |
| 4 | Required Expanded Memory Manager (EMM Ver 4.0 or later) was not found or is not functioning properly. |
| 5 | Minimum of 1MB Expanded RAM must be available. |
| 6 | An EMM mapping error has occurred. |
| 7 | Problem with music or sound data. |
| 8 | Problem with a driver. |
| 9 | Problem with WORLD.DAT. |
| 10 | Problem with CURGAME. You need to run the install process first. |
| 11 | Problem with a SAVED GAME file. |
| 12 | Expanded memory allocation error. |
| 13 | Problem retrieving text data. |
| 14 | Problem retrieving NPC data. |
| 15 | Problem retrieving conversation data. |
| 16 | Invalid background type found. |
| 17 | Invalid foreground type found. |
| 18 | Please run Tyrants of Thaine from SW.BAT |
| 19 | . |

Code 2 names `PICTURE.VGA` where the file shipped is `PICTURES.VGA`, which is the message's own error and not a second file. Code 19 is a bare full stop, so nineteen codes carry text.

