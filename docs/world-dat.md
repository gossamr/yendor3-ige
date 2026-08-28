# WORLD.DAT and the section directory

`WORLD.DAT` is 4,350,901 bytes and carries an explicit table of contents, which is stored in `REGISTER.EXE`. This document records settled findings only. Each format has a document of its own, named in the tables below. [tools/sections.py](../tools/sections.py) reads the directory, and [tools/labels.py](../tools/labels.py) reads the label run.

## The two tables

- **Master table, `REGISTER.EXE:0x2CF37`**, 36 consecutive little-endian dwords, each a byte offset into `WORLD.DAT`. Consecutive entries bound the 35 sections. The last entry equals the length of the file, so it also serves as an end marker. Entries 5 and 6 hold the same offset, which makes section 5 empty.
- **Restoration table, `REGISTER.EXE:0x2D4AF`**, five offsets covering the clue book's own corpora. Its last entry has no successor, so the upper bound of the spell descriptions comes from the next master table offset instead.

The map grid sits **before** section 0. Seven areas of 76,800 bytes fill `0x000000` to `0x083400`, and the first section begins exactly where they end.

## The sections that are decoded

| # | Offset | Size | Content |
|---|---|---|---|
| 0 | `0x0083400` | 840 | the map registry, 140 × 6 ([map.md](map.md)) |
| 1 | `0x0083748` | 760 | map names, 38 × 20 ([map.md](map.md)) |
| 2 | `0x0083a40` | 912 | area names, 12 + 12 |
| 4 | `0x0083ee8` | 36,598 | item names and records ([items.md](items.md)) |
| 12 | `0x0095bda` | 5,376 | seven 768-byte VGA palettes ([map.md](map.md)) |
| 13–15 | `0x00970da` | | CT-VOICE driver, CMF music, VOC audio |
| 16 | `0x03c2030` | 6,864 | in-game books and lore |
| 21 | `0x03d8eb9` | 5,640 | NPC records, 141 × 40 ([shops.md](shops.md)) |
| 22–23 | `0x03da4c1` | 64,380 | conversation topics, 1,073 × 60 ([shops.md](shops.md)) |
| 24–26 | `0x03ea03d` | 139,060 | prose lines, 4,090 × 34 ([shops.md](shops.md)) |
| 28 | `0x041090d` | 26,472 | cell events ([map.md](map.md)) |
| 29 | `0x0417075` | 7,738 | enemies, 73 × 106 ([monsters.md](monsters.md)) |
| 31 | `0x041b5bf` | 8,560 | spells, 107 × 80 ([spells.md](spells.md)) |
| 32 | `0x041d72f` | 5,000 | the roster template, 10 × 500 ([saves.md](saves.md)) |

Three of these tables are split across section boundaries, and each is one table. [shops.md](shops.md) shows the arithmetic.

## The Restoration corpora

| # | Offset | Size | Content |
|---|---|---|---|
| 0 | `0x03c90a2` | 42,075 | the walkthrough, 33 × 1,275 |
| 1 | `0x03d34fd` | 2,000 | the legend marker table, 207 × 8 ([map.md](map.md)) |
| 2 | `0x03d3ccd` | 6,500 | legend labels, 250 × 26 ([map.md](map.md)) |
| 3 | `0x03d5631` | 432 | the spell description index ([spells.md](spells.md)) |
| 4 | `0x03d57e1` | 14,040 | spell descriptions, 360 × 39 ([spells.md](spells.md)) |

**Restoration is the clue book that shipped with the game.** `REGISTER.EXE:0x2A7CD` holds the string `RESTORATION:THE ON-LINE CLUE BOOK`. It opens with F8 or TAB, either from the main menu or during play, and it has six sections: F1 maps, F2 monster statistics, F3 spells, F4 magic users, F5 inventory items, and F6 complete walk through. F2, F4 and F5 are rendered from the binary tables. Only the walkthrough and the spell descriptions are stored as text.

## Text formats

- **The walkthrough** is 33 pages of 1,275 bytes, which is 25 rows of 51 columns. The last row of each page is its footer, `"n OF 33"`. The section headings are the rows matching `NN. LOCATION`, and there are 50 of them.
- **Legend labels** are 26-byte records, holding 25 visible characters and a NUL. Slot 0 is a column ruler, `1234567890123456789012345`. Past about record 130 the run is packed rather than fixed width. [map.md](map.md) describes how it is read.

**The character set.** The font has no apostrophe, so `~` stands for one. `\` is the fraction slash, so `1\2` is one half. A run of four or more `e` is a horizontal rule glyph rather than text. Every string is upper case. `labels.text()` applies these substitutions, and a raw read is not a name. The file stores `MAGE~S CHAIN MAIL ARMOR`, and `MAGE'S CHAIN MAIL ARMOR` is what it means.

## The label run, which names the fields

`REGISTER.EXE:0x2A780` to `0x2B300` is a contiguous run of NUL-separated strings. It holds every caption the Restoration screens print: the monster statistic names, the twelve effect names *in bit order*, the seventeen special attack names, the eight item categories, the spell field names, the AFFECTS and WHEN vocabularies, and the six magic user class triads (`MONK/CLERIC/PRIEST`, `ALCHEMIST/TRANSMUTER/HEALER`, `PALADIN/CAVALIER/HERO`, `MAGE/WIZARD/SORCERER`, `DRUID/ENCHANTER/SAGE`, `MARKSMAN/RANGER/KNIGHT`).

[tools/labels.py](../tools/labels.py) reads these strings from the file, and asserts that all 84 strings it declares are present.

## The executable

`REGISTER.EXE` is a real mode 16-bit MZ image in a large or huge memory model. It is not packed, it has no overlays, it has almost no BSS, and its length matches its header exactly. It **requires EMS** (`EMM Ver 4.0`, with at least 1 MB expanded memory), which `README.DOC` states and which the game enforces at startup.

`e_csum` is zero, and DOS ignores that field. The loader rewrites 4,000 words from the **relocation table** at load time, so those words in memory do not match the words in the file. [tools/mz.py](../tools/mz.py) builds the map of them, and [patching.md](patching.md) describes what that constrains.

Addresses in these documents are **image offsets**, meaning the file offset minus the 16 KB header, except where a `DS:` prefix indicates otherwise. `DS:0` sits at image `0x1DDB0`, and a far call to `seg:off` lands at image `seg * 16 + off`.
