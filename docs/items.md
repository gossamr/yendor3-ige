# Item format

An item is a 58-byte record, plus one entry in whichever properties table its category names, plus an optional entry in the effects table. Settled findings only. What the numbers mean for a character build is in [leveling.md](leveling.md). [tools/items.py](../tools/items.py) is the decoder, and `python tools/items.py <name>` prints one item's page.

## Where a clue-book page comes from

Every row an F5 page prints, and what supplies it:

| Row | Source |
|---|---|
| the category it is filed under | one of six item-id lists in `REGISTER.EXE` |
| BASE VALUE, WEIGHT | the item record |
| FITS IN | the item record's containers word |
| ABSORPTION, DAMAGE, SKILL, 2-HANDED | the properties entry the record points at |
| ADDS, PROTECTIONS | the effects entry the record points at |
| DURATION, MAGIC | the misc properties entry |
| RESTORES, CURES, a potion's DAMAGE | constants in `REGISTER.EXE`, keyed on the item id |
| the ATTRIBUTE ENHANCERS rules | constants in `REGISTER.EXE` |
| USES, TIME on the TRANSPORTATIONS page | a four-entry table in `REGISTER.EXE` |

[tests/test_extract.py](../tests/test_extract.py) checks all 650 captured rows against the decode.

Two more properties are in the files but on no page, and `data/items.json` carries them as keys of their own rather than as rows: the **spell a magic scroll teaches** and the **slot an item is equipped in**.

## The item record, 631 records of 58 bytes at `0x083EE8`

19 bytes of fields, then three 13-byte name fields (12 characters and a NUL). A name runs across all three, so "BROKEN" + "BO STICK" is one item. 36,598 ÷ 58 = 631 exactly.

A name is a stored string, so it uses the game's character set. The game has no apostrophe glyph and holds one as `~`, so MAGE'S CHAIN MAIL ARMOR is stored as "MAGE~S CHAIN MAIL ARMOR". `labels.CHARSET` holds the substitution and `labels.text` applies it, and 13 item names need it.

`lcall 0x0f44c` is the loader, and it fixes the whole shape: given a **1-based** item id in `ax` it copies the record to `0xe4c`, the effects entry to `0xe3c` and the properties entry to `0xe30`. Every page renderer reads only those three buffers, and `[0x5426]` holds the id.

| Offset | Field | Evidence |
|---|---|---|
| 0 | uint16, byte offset into this item's properties table | code, `0x0F44C`; screens, below |
| 2 | uint16, a byte offset into the effects table, and 0 for no effects | code, `0x0F44C`; screens, below |
| 5 | BASE VALUE, packed BCD, three bytes | screens: F5, 148/148 |
| 8 | uint16, the item's artwork: a picture in run 8 | code, `0x0F44C`; shape, below |
| 10 | WEIGHT, uint16, tenths | screens: F5, 169/169 |
| 12 | category: the properties-table selector and the equip slot | code, `0x04237` and `0x0F4CC`; shape |
| 14 | FITS IN, a container mask | screens: F5, 170/170 |
| 16 | a group, **undecoded**, see below | |

Bytes 4 and 18 are zero on all 631. Byte 9 is the high byte of the artwork word at 8, and 234 records carry artwork above 255, so it is not spare.

**The artwork word is a picture number in run 8**, the 340 sixteen-by-sixteen icons ([pictures.md](pictures.md) has the run table). All 631 values fall inside that run, between 16 and 330 over 263 distinct pictures. Drawing the picture each record names gives the item the record is: GOLD COINS draws coins at 66, MAGIC GRAPES a bunch of grapes at 94, SLING a sling at 142 and WOODEN SHIELD a round shield at 163. `Items.art` reads it, and [tests/test_extract.py](../tests/test_extract.py) holds the range.

The Evidence column uses the classifiers [README.md](README.md) defines. Three of the fields were read off the game's own F5 pages, on every figure they print:

- **BASE VALUE** is packed BCD at offset 5, in *three* bytes, which is five digits, because the SCEPTER OF BARIAG costs 10,000. It is exact on all 148 values the pages print.
- **WEIGHT** is a uint16 at offset 10 in tenths. It has to be a word, not a byte: the ANVIL OF LIGHT weighs 50.0 and would overflow. Exact on all 169.
- **ABSORPTION** is not in the record. Bytes 0 and 1 are a byte offset into a properties table, and the first byte of that table entry is the absorption. It is exact on all 38 armor pieces. The largest pointer plus 12 is 2,652, which is exactly the size of that section.

**FITS IN is the word at 14**, or three bits of it, and `0x071d3` prints them in order: `0x8000` is BACKPACK, `0x4000` is BOX and `0x2000` is BAG. With none of the three set, the line reads CHARACTER PANEL when the record's category word carries `0x2000`, and ANY PANEL otherwise. The reading is exact on all 170 captured pages. Over the 631 records the totals are 221 BACKPACK, 193 BACKPACK BOX, 201 BACKPACK BOX BAG, 15 ANY PANEL and one CHARACTER PANEL. The 15 are the three currencies and twelve items too bulky to stow, among them the weapons of Light and the ANVIL OF LIGHT. The one is the BACKPACK, which is the one thing no container holds. Bit `0x0001` of the same word is set on 46 items, and nothing prints it.

**The word at 16 is a group, and the code that reads it has not been found.** It partitions the records cleanly. `0x8000` is on all 420 armor and weapon records, `0x4000` is on the twelve potions, and `0x2000` is on the lockpick, the hourglass, the torch and the three containers. One bit each then covers the twelve gems and bars, the five dwarf artifacts, the five elf artifacts, the four treasures of the Order, and the four ores. Zero is left on the remaining 163 records, which are the currencies, the keys, the parchments and the quest loot. That is the shape a shop's stock list would have.

**There are three properties tables.** `lcall 0x0f44c` copies the 58-byte record into a scratch buffer, reads the category word at `+0x0c`, and copies a properties entry from whichever table that category selects:

| Category bits | Table | Base | Entry | Entries | Section |
|---|---|---|---|---|---|
| `0x0e00` shield, ring, worn | armor | `0x8D71E` | 12 B | 221 | 7 |
| `0x0100` tools, keys, food | misc | `0x8E17A` | 8 B | 151 | 8 |
| `0xc000` hand, missile | weapon | `0x8E632` | 12 B | 210 | 9 |

`0x0f4cc` computes these as `0x940`, `0x139c` and `0x1854` from a base of `0x8CDDE`. All three land on a section boundary exactly, and each section's size divides by its entry size with no remainder. The entry is copied to a fixed buffer at `0xe30`. That buffer is what every later `[bx+...]` reads: the pointer the dispatch works on is a copy of the properties entry, not the record. `mov bx, ax` follows the call, at `0x042b2` and again at `0x0431d`.

**The offset is an index within its own table, so the same offset in two categories names two unrelated entries.** CLOTHES +1 and SLING both carry 24, and 2-HANDED SWORD +1 and ROYAL PLATE ARMOR both carry 2112. Reading a weapon's offset in the armor table gives the 2-HANDED SWORD an absorption of 20 that it does not have, which is ROYAL PLATE ARMOR's number. `extract` gates on whether the book prints an ABSORPTION line, which reaches the same answer from the other direction.

**Enchanted variants** are separate records, as CLOTHES, CLOTHES +1 and CLOTHES +2 each are. The clue book puts them behind a selector on the base item's page, and `extract` folds them the same way. **327 of the 631 records are +N forms**, which leaves 304 items.

Enhancement runs to **+10**, and nine items reach it, among them CROSSBOW, GOLD SHIELD, 2-HANDED SWORD, WAR HAMMER, HALBERD and ROYAL PLATE ARMOR. Each +N step adds N to the **first byte of the properties block**, and the block counts N itself in a word of its own: the armor entry's `+6`, where ROYAL PLATE ARMOR runs 22, 23, 24, 25 against 0, 1, 2, 3, and the weapon entry's `+8`, where LONG BOW runs 7 to 15 against 0 to 8.

**The rest of both entries is what the item breaks into.** Image `0x05e61` counts a use of the missile weapon, the hand weapon or the shield and rolls `rand(1000)` once the count is past the slot's threshold; [combat.md](combat.md) has the counters and the three call sites. What it rolls against, and what it puts in the slot, is here:

| Entry | Broken form | Chance in 1,000 |
|---|---|---|
| weapon, 12 B | `+4` | `+6` |
| armor, 12 B | `+8` | `+0xa` |

## What a repair does

A repair puts a broken piece back to exactly the item it was. Two things start one, a shop's own screen ([shops.md](shops.md)) and the party's repairer, and the swap below is what both come down to.

**The place is what remembers.** Breaking writes the whole form's id into the place's own second word and the broken form into its item word, in that order, at image `0x036AB`:

    036ab  mov ax, [si+0x10]     ; the item as it was
    036ae  mov [bx+2], ax        ; -> the place's second word
    036b1  mov ax, [si+0x12]     ; the broken form
    036b4  mov [bx], ax          ; -> the place's item word

`bx` is the character record plus the slot's own offset, so the pair travels with the place and a `+4` survives being broken. A repair is that pair read backwards: image `0x0470E` sets the item word to what the second word says and clears the second word. Nothing looks the whole form up, which it could not do anyway, since every step of a series shares one broken record.

**A party's own repairer rolls for it**, at image `0x1C440`. Two things pick the odds: the repairer's repair skill, which falls in one of five bands, and the piece's own enchantment, which is the row. The pair of words found there is read against a `rand(100)`:

    1c487  cmp ax, [si]          ; under the first  -> the piece is destroyed
    1c48b  cmp ax, [si+2]        ; at or under the second -> repaired
    1c490  ...                   ; over it -> the attempt fails, the piece survives

The table is 11 rows of five pairs at `DS:0x6EAC`, one row per enchantment level from +0 to +10, and the bands cut at 50, 65, 80 and 95. The first pair of each row, which is a repairer under 50:

| Piece | destroyed under | repaired at or under |
|---|---|---|
| +0 | 20 | 50 |
| +1 | 60 | 40 |
| +2 | 80 | 10 |
| +3 | 90 | 10 |
| +4 and up | 100 | 0 |

So an unskilled repairer mends a plain piece about a third of the time and ruins it a fifth, and past +3 ruins it on every roll but the one draw of exactly 100 that `rand(100)` allows ([combat.md](combat.md) has the fold). At 95 or better nothing is ever destroyed, and everything under +9 is always mended. The enchantment is read out of the properties entry the whole form carries, `+8` on a weapon and `+6` on armor.

**The broken form says so in its own entry.** Image `0x06027` tests the weapon entry's `+2` bit `0x100` and the armor entry's bit `0x40`, and answers 2 where either is set. The bit marks exactly the 26 weapons and 5 shields whose name begins BROKEN, with nothing left over either way. [combat.md](combat.md) has what the two attacks do with that answer: a broken bow does not fire, and a broken hand weapon still swings.

**176 weapon records and 40 armor records name a broken form**, and each names a real item: SLING breaks into BROKEN SLING at 50 in 1,000, LONG BOW into BROKEN LONG BOW at 70, CROSSBOW into BROKEN CROSSBOW at 60. That is what the broken forms in the item table are for, and it is why they are among the 134 items the clue book does not index.

**An enchanted piece breaks like any other, and the enchantment is not in the broken form.** Every step of a series names the same one: COPPER SHIELD and its six `+N` forms all break into BROKEN COPPER SHIELD, and 29 of the 30 series that break do the same. MACE is the exception, and it is a mistake in the data: id 161 names *itself* as its broken form, so breaking a plain MACE leaves a MACE, while MACE +1 to +4 name BROKEN MACE properly.

**What is broken is worth the broken record and nothing more**, so a COPPER SHIELD +4 absorbing 17 becomes a BROKEN COPPER SHIELD absorbing 4 while it stays that way. **The enchantment comes back with the repair**, since the place remembers the exact id, `+N` and all, in the second word above. What breaking costs is the use of the piece and whatever mending it takes.

**186 whole weapon and armor records cannot break at all.** Body armor, helmets, gloves, boots and rings name no broken form, which follows from there being three counters and no more: the missile weapon, the hand weapon and the shield. Four more carry a broken form and a chance of zero, which are the `+10` forms of CROSSBOW, 2-HANDED SWORD, WAR HAMMER and HALBERD.

**Enchantment buys durability as well as damage.** The chance falls 10 per step on WOODEN SHIELD, from 50 at +0 to 10 at +4, and 5 per step on LONG BOW, from 70 to 35 at +7. Five records reach zero that way: WOODEN SHIELD +5 and the +10 forms of CROSSBOW, 2-HANDED SWORD, WAR HAMMER and HALBERD. Zero is not quite never, since the comparison keeps a roll at or under the chance and `rand(1000)` draws a zero once in 1,024 ([combat.md](combat.md) has the fold).

**The rule is the same for both kinds of item. +N adds N to the item's primary combat number**, which is absorption for a piece of armor and damage for a weapon. That one is **measured**: it was read off the game in play rather than out of the code.

**Weapon damage is byte 0 of the weapon entry**, which is the same position that absorption occupies in the armor entry. It is exact on all 33 weapons whose page prints a DAMAGE line. `0x06558` reads `[bx]` and adds it to the character's two damage fields, which fixes the field from the code as well as from the data.

**The weapon entry's word at `+2`** carries the skill and two flags:

| Bits | Meaning |
|---|---|
| `0x8000` `0x4000` `0x2000` `0x1000` | projectile, slashing, bashing, polearm |
| `0x0800` | the item heads an enchantable series |
| `0x0001` | two-handed |

Skill decodes on 33 of 33, two-handed on 33 of 33, the series bit on 48 of 48. `0x0652a` routes on the same three melee skill bits into three different skill fields, and `0x06561` tests bit `0x0001` and sets `[si+0x15c]` bit `0x20` when the weapon is two-handed. The armor entry's word at `+2` carries the worn slot, in bits `0x8000` for head, `0x4000` for body, `0x1000` for feet and `0x0800` for hands, and it carries its own series bit at `0x0100`. That holds on 43 of 43.

The `+N` series is in the files, and it steps by one point of damage per level. The 2-HANDED SWORD runs from 30 to 40 across +0 to +10. **The ceiling on enchantment differs from item to item.** LONG SWORD stops at +6 and 21 damage, where the 2-HANDED SWORD reaches +10 and 40.

The best weapons cannot be enchanted at all. The three weapons of Light have no +N records, and the series bit is clear on them. Enchantment therefore only ever raises the second tier, to 40 damage at +10, against 250 for a SWORD OF LIGHT.

The book prints damage for the enchanted forms, but they sit behind a selector on the base item's page, so **0 of the 170 captured pages are a +N form**. `data/items.json` carries `plus`, `value` and `weight` per variant, all read out of the records.

The `+N` fold has two failure modes, both pinned by [tests/test_extract.py](../tests/test_extract.py): a pattern that matches a single digit leaks the nine `+10` records in as items of their own, and a fold loop that stops at 8 excludes them. The tests also assert no name matching the pattern survives into the list.

**Equip slots are in record word 12.** The word at offset 12 carries a slot mask, and the equip dispatch at image `0x04237` routes on it. It sends the item to the backpack when the destination slot is occupied.

| Bit | Slot word(s) in the character record | Count |
|---|---|---|
| `0x8000` | `0x13a` missile weapon | 1 |
| `0x2000` | `0x13e` ammunition | 1 |
| `0x4000` | `0x142` hand weapon | 1 |
| `0x0800` | `0x146` shield | 1 |
| `0x0400` | `0x14a`, `0x14e` rings | 2 |
| `0x0200` | `0x152`..`0x15a` worn | 5 words, 4 fillable |

The partition is clean across 249 items. Every bow and sling is `0x8000`, every sword is `0x4000`, every shield is `0x0800`, every ring is `0x0400`, and all 129 armor, helmet, glove and boot records are `0x0200`. `Items.equip_slot` reads word 12, and for the worn category it also reads the armor entry's word at `+2`. That resolves all 432 equippable records into one of eight slots and leaves nothing over. `0x0f4cc` tests the same word against `0x0e00`, which is the three wearable bits, with `si` explicitly on the record. That is a direct confirmation that word 12 is what the dispatch reads.

**The character panel carries eight items**, four bytes each, at `0x11a`, `0x11e`, `0x122`, `0x126`, `0x12a`, `0x12e`, `0x132` and `0x136`. Each holds an item id and a second word. An item that has no equip slot, or whose slot is already taken, is placed in the first of the eight whose id is zero (image `0x437E` onward). With all eight taken, the pickup is refused. The run ends where the missile weapon slot begins, at `0x13a`.

**The second word is the item's own state.** What it holds depends on the item:

- For a **container or ammunition** it is what the container holds. Image `0x44BF` returns at once unless the item's category carries `0x2000`, and image `0x05134` follows it into an eight-entry list when it is set.
- For a **light source it is how much is left to burn.** The tick at image `0x0EB7C` walks the eleven `(id, word)` pairs looking for LIT TORCH, which is id 35. It subtracts from that item's second word, and when the word reaches zero it drops the light counter at `[0xCF07]` and clears bit `0x0800` of `[0xCEF7]`, so the light is extinguished. A torch with a zero there is a torch that has already burned down.
- For everything else it is zero.

**Only five items are in the first two groups.** The DURATION gate is category bit `0x1000`, and exactly two items carry it, TORCH and LIT TORCH. The container bit `0x2000` is carried by BAG, BOX and BACKPACK and by nothing else. No item's page prints a USES row. The tick that scans the slots for a particular id searches for one id only, which is 35. A scan of the image for that shape, meaning `cmp word ptr [si], imm` inside a walk of stride 4, finds no other.

A container's word is allocated rather than carried in the file: image `0x44BF` calls out for one when the word is zero as the item is equipped, so zero is what an unallocated container holds.

**Two timers are unreachable.** Image `0x0FD9D` counts `[0xCF03]` down and clears bit `0x2000` of `[0xCEF7]`, and `0x0FDC7` does the same for `[0xCF09]` and bit `0x0400`. Nothing jumps to either: the routine they sit in tests one id, `0x23`, and branches only to the torch's.

Of the four shipped characters, DIANA and YENDOR start with MAGIC GRAPES in the first slot and the other two start empty.

**An enchanted item is its own item, and its id is the base's plus the enchantment.** That holds for all 327 of them, so LONG BOW at 307 makes LONG BOW +3 into 310. `data/items.json` carries the id on each variant.

**The worn category has four slots that can be filled, not five.** The sub-dispatch at `0x0431d` tests exactly four bits of the armor entry's word at `+2`. It sends `0x8000` to `0x152`, `0x4000` to `0x154`, `0x1000` to `0x158` and `0x0800` to `0x15a`. An item matching none of the four is placed in the backpack instead. The record does carry five one-word slots, and the absorption accumulator at `0x06591` sums all five at stride 2, but nothing tests `0x2000`. `0x156` can therefore never be filled, and no item in the game carries that bit. The data agrees. 164 worn items partition into 35 head, 60 body, 35 feet and 34 hands, with none left over.

**There is no cloak slot.** CLOTHES, ROBES, FIGHTER'S CLOTHING and MAGICIAN'S CLOAK all carry the `0x4000` body bit, the same slot as ROYAL PLATE ARMOR, so they compete with body armor rather than adding to it.

**Class does not restrict shields.** The shield branch at `0x042d6` makes two tests and no more: whether `0x146` is already occupied, and whether `[si+0x15c]` bit `0x20` is set. That bit is set in one place, `0x06568`, when a two-handed weapon is equipped. The hand-weapon branch enforces the same rule in the other direction at `0x042b4`, refusing a two-handed weapon while a shield is worn. No class field is read on either path, so **a two-handed weapon is the only thing that costs a character their shield**.

**The armor ceiling is 111, or 161 enchanted.** The set is one item per slot, which is body, helmet, gloves, boots, shield and two rings, so seven pieces. It counts purchasable items only, because a base value of zero marks quest loot that only one character can ever hold.

| Slot | Plain | Enchanted |
|---|---|---|
| body | ROYAL PLATE ARMOR 22 | +10, 32 |
| head | ROYAL PLATE HELMET 10 | +10, 20 |
| hands | ROYAL PLATE GLOVES 7 | +10, 17 |
| feet | ROYAL PLATE BOOTS 7 | +10, 17 |
| shield | GOLD SHIELD 20 | +10, 30 |
| ring | RING OF INVISIBILITY 25 | no +N form |
| ring | GOLD RING OF ARMOR 20 | no +N form |
| | **111** | **161** |

**No ring has a `+N` form**, so the two ring slots contribute 45 either way. And the second ring is not a second Ring of Invisibility: the walkthrough has Yardley make **four** of them from one copper bar, which is one per party member. A character wears one.

Dropping the shield for a two-handed weapon costs 20 plain, 30 enchanted, and takes the ceiling to 91 or 131.

[tools/combat_model.py](../tools/combat_model.py) carries the figures. [tests/test_combat_model.py](../tests/test_combat_model.py) reads the best purchasable item for each slot back out of `WORLD.DAT`, sums them, and asserts the sum against the constants.

## The effects table, 148 entries of 16 bytes at `0x08CDDE`

Record word 2 is a byte offset into this table, which is section 6, and that is the same base the three properties tables are measured from. An entry is **four pairs of words, each `(character record offset, amount)`**, and a zero offset ends the list. The loader copies the table to `0xe3c`. 147 items point at a filled entry, and the other 484 carry offset 0.

The offset is what names the row, because it is a field of the character record. Two renderers walk the same entry and split it on the offset:

| Renderer | Offsets it prints | Caption | Names from |
|---|---|---|---|
| `0x08499` | `0x20`–`0x30` | `PROTECTIONS:` | ds:`0x7e63`, 9 strings |
| `0x08398` | `0x3c`–`0xae` | `ADDS:` | ds:`0x80f4`, 27 strings |

Both name tables are indexed by `(offset − first) / 2`. ds:`0x80f4` therefore runs STRENGTH, DEXTERITY, STAMINA, INTELLIGENCE, WISDOM, CHARISMA, five blanks, HEALTH, MAGIC POINTS, a blank, and then the twelve skills. That is exactly the character record's own layout, and [tools/skills.py](../tools/skills.py) places the attributes at `0x3c` and the skills at `0x58`. ds:`0x7e63` runs DISEASE, POISON, SICKNESS, STONING, FROZEN, PARALYZE, CURSING, HEXING, JINXING, which matches the nine condition words at `0x20` to `0x30` in [combat.md](combat.md).

That also answers what writes a character's protection words: equipping an item whose effects entry names one. The four protection rings, DWARVEN FUR and the three weapons of Light are the whole set.

The renderers print one row per pair, and a continuation row carries no caption. The screen reader keyed rows by their caption, so **the captures only ever kept the first row of each list**. PARALYSIS PROTECTION RING reads "50 PARALYZE" on the page, and decodes to 50 paralyze, 60 frozen and 40 stoning. Nine items carry an ADDS list and four carry a PROTECTIONS list, and 13 of those carry more than one row.

The misc page has no ADDS row, which is why an enhancer's `+3` is not on its own page: the book states it once, on the ATTRIBUTE ENHANCERS rules page.

## The book's own filing, which is six lists in `REGISTER.EXE`

The category an item is filed under is not in its record. It is membership of a list: `0x06944` reads a pointer out of the table at ds:`0xf6a8`, indexed by list id − 1, and each list is a count word followed by that many 4-byte entries of `(1-based item id, flags)`.

Ids 12 to 17 are the six item categories. Which caption belongs to which id is set by the F5 menu, one branch per category (`mov ax, <caption> / mov [0xe96], ax / mov [0xe92], <list id>`), so the name and the list it opens can be read out of the file together:

| List | Category | Items |
|---|---|---|
| 12 | ARMOR / RINGS | 38 |
| 13 | JEWELS/ORES/UNIQUE ITEMS | 51 |
| 14 | MAGIC SCROLLS | 26 |
| 15 | POTIONS / MAGIC FOOD | 14 |
| 16 | SUPPLIES | 8 |
| 17 | WEAPONS | 33 |

That is 170 pages in total, which is every page the capture reached, and the two sources agree on all of them. The same registry holds the panel's other lists: 1 is maps, 2 is monsters, 3 is spells, 4 is magic users, and 11 is the F5 category menu itself.

## The misc properties entry

Eight bytes, and the word at `+2` determines what the word at `+4` means:

| `+0` | `+2` | `+4` | Items |
|---|---|---|---|
| `0x0090` / `0x0050` plus a lock bit in the high byte | | | the seven chest and seven door keys |
| `0x0010` | `0x2600` | a spell id | the 26 magic scrolls |
| `0x0000` | `0x8000` | magic points | MAGIC GRAPES 15, MAGIC CARROTS 30 |
| `0x0008` | `0x0001` | tenths of a duration | TORCH, 24 → 240 MINUTES |
| `0x0000` | `0x1000`/`0x2000`/`0x4000` | a text id | the parchments, scrolls and books |

The DURATION row is gated on the *record's* category bit `0x1000` rather than on the entry (`0x06c14`), and it prints ten times the word. TORCH holds 24, which becomes the 240 MINUTES on its page.

## The potion lines are in the code

`0x07429` switches on the item id and prints immediate values, so the eight potions whose pages print RESTORES, CURES or DAMAGE have their figures nowhere in `WORLD.DAT`. BLACK, GRAY and WHITE POTION share one properties entry byte for byte, and they restore 25, 50 and 100 percent of health. The difference between them is which `cmp word ptr [0x5426], <id>` arm each one reaches. [tools/items.py](../tools/items.py) transcribes the nine arms, with an assertion on the bytes they were read from.

The FLAMING OIL FLASK is the same page reached through a variable: `[0x5464]` is set to its id at `0x0f130`, and its line is 40 over a 3 X 3.

## Two pages that are not item lists

**ATTRIBUTE ENHANCERS** is one page of rules, six rows of constants at `0x06f2f`: scrolls +3 and wands +5 and gems +7 to an attribute, parchments +3 and rods +5 and stones +7 to a skill. Each row holds its amount as a single ASCII digit and calls one of two tail routines, and which tail it calls determines whether the page prints ATTRIBUTE or SKILL.

**TRANSPORTATIONS** lists three entries that appear nowhere in the 631 item records. They are a four-entry table at ds:`0x7af4`, 26 bytes each: a name, a four-byte BCD value at `+0x0e`, a use count at `+0x16`, and a flag word at `+0x18` whose bit `0x0002` is TIME: ANYTIME against BETWEEN 7P.M. AND 7A.M.

| | Value | Uses | Time |
|---|---|---|---|
| PEGASUS | 10,000 | 1 | anytime |
| GIANT EAGLE | 30,000 | 2 | anytime |
| MAGIC DRAGON | 70,000 | 4 | 7p.m. to 7a.m. |

`0x07937` walks entries 0, 1 and 3: the fourth, the **FLYING RUG** at 50,000 for 4 uses, is in the game's table but not in the book.

**What the book does and does not list.** 170 of the 304 items have an F5 page. The other 134 are not a gap in the capture. They are items the book never indexes: the three currencies (gold coins, food, nuore), the broken form of every weapon and shield, the fourteen chest and door keys, the quest parchments, and the attribute enhancers, which the book covers as one page of rules rather than as item pages. The decode reaches all 304 either way. An unindexed item has its value, weight and FITS IN like any other, and `data/items.json` marks it `listed: false`.

**The F5 screens have their own colors**, which were sampled from the frames and carried into the panel. Value and weight are `#ffeb24`, damage and absorption are `#a62424`, FITS IN is `#5959c7`, SKILL is `#007900`, and captions are `#aaaaaa`. The two dark colors are lifted for legibility, because `#a62424` measures 2.5:1 on the panel ground and `#5959c7` measures 3.2:1, both below the 4.5:1 floor. The panel keeps the hue and raises the value.
