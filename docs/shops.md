# NPCs, conversation and shops

Every person the maps place, what they say, what they sell and what it costs. [tools/npcs.py](../tools/npcs.py) reads it and [tests/test_npcs.py](../tests/test_npcs.py) holds the arithmetic.

The clue book has no NPC page, so nothing here is **screens**. Three things check a reading instead. The table shapes, which a wrong record size breaks. The prose the reading makes an NPC speak, which is the game's own description of what the field does. And the quest flags, where a topic's effect and the gate it opens have to name the same number. The Evidence column says which; [README.md](README.md) defines the classifiers.

## Three tables, two of them split across section boundaries

The section directory lists five sections. They are three tables:

| Table | Section | Base | Record | Count |
|---|---|---|---|---|
| NPCs | 21 | `0x3D8EB9` | 40 B | **141** |
| Conversation topics | 22, 23 | `0x3DA4C1` | 60 B | **1,073** |
| Prose lines | 24, 25, 26 | `0x3EA03D` | 34 B | **4,090** |

The counts are exact: 47,400 + 16,980 = 64,380 = 1,073 x 60, and 51,034 + 51,000 + 37,026 = 139,060 = 4,090 x 34.

Image `0x0A1BA` loads one NPC at a time. It frees the last NPC's two buffers, reads the record into `DS:0x0EC8` by the index at `DS:0x0EC6`, then allocates and reads that record's own run of topics and its own run of prose lines. So `DS:0x0FE7` is the topic buffer's segment and `DS:0x0FEB` is the topic number **inside the NPC**, 1-based. Image `0x08F7E` turns that number into `ES:SI` as `(n - 1) x 60`.

**A cell event of kind `0x1000` stands an NPC on a cell**, and its argument is the record's own index. 139 of the 141 are placed, one cell each; records 0 and 140 stand nowhere ([map.md](map.md)).

## The NPC record, 141 records of 40 bytes

| Offset | Field | Evidence |
|---|---|---|
| `+0x00` | portrait, a picture in run `0x70` | code, `0x09153` |
| `+0x02` | 2 or 4 on 27 records, 0 on the rest, **undecoded** | |
| `+0x04` | how many conversation topics | code, `0x0A23A`; shape: a running total |
| `+0x06` | how many prose lines | code, `0x0A28A`; shape: a running total |
| `+0x08` | its first topic, 0-based | code, `0x0A231`; shape: 140 of 140 blocks open on a greeting |
| `+0x0A` | its first prose line, 0-based | code, `0x0A281`; shape: 953 of 955 responses quote cleanly |
| `+0x0C`, `+0x0E` | quest flags picking which topic the conversation opens on | code, `0x0A338` |
| `+0x10` | would pick topic 4, zero on all 141 | code, `0x0A332` |
| `+0x12` | the quest flag a one-shot service is spent against | code, `0x08D42` and `0x08DD0` |
| `+0x14`, `+0x16` | read differently per service, below | code |
| `+0x18` | price factor, as a percentage | code, `0x0A740` and `0x0920F` |
| `+0x1A` | a per-character bit index, for a service given once to each | code, `0x08FB2` |
| `+0x1C`, `+0x1E` | a flat price, four packed BCD bytes | code, `0x09679` |
| `+0x20` | an item the party must carry for one topic to appear | code, `0x0A386` |
| `+0x22` | a quest flag that, set, makes the NPC refuse to talk | code, `0x0A20B` |
| `+0x24`, `+0x26` | zero on all 141 | |

`+0x04`/`+0x08` and `+0x06`/`+0x0A` are running totals: `+0x08[i+1] = +0x08[i] + +0x04[i]` holds on 139 of the 140 consecutive pairs, and so does the prose pair. That is what fixes where each block ends.

**Both indices are 0-based**, so a block runs from one past the field. Two counts fix that. Read that way every one of the 140 topic blocks opens on a topic no menu lists, which is the NPC's greeting, and closes on one carrying a close or a leave bit, which is its farewell; read a record earlier only 3 and 35 of them do. And a response read at the offset a topic names has its quotation marks paired on 953 of the 955 responses that carry any, against 760 read a record earlier.

**Which topic a conversation opens on is a quest flag.** Image `0x0A31A` tries `+0x10`, then `+0x0E`, then `+0x0C` as flag numbers and takes the fourth, third or second of the NPC's topics from the first that is set, falling back to the first. `+0x10` is zero on all 141, so at most two of the three can answer. The armorer at NPC 31 carries 51 and 63 and has three greetings for it: HELLO before the blacksmith can be hired, HELLO-2 with the offer, HELLO-3 once the shop is open.

**`+0x20` is an item, and carrying it turns on a conversation bit.** Image `0x0A386` passes it to the party-wide item search at `0x0B1FC` and, on a hit, sets bit `0x0001` of the high conversation word. The 18 NPCs that carry one name the same 18 item ids that the PAY topics ask for, so the pair is one mechanism: the NPC looks for the item and the topic takes it.

### What `+0x14` and `+0x16` hold, per service

| Service | `+0x14` | `+0x16` | Read at |
|---|---|---|---|
| attribute | a live-block record offset, 60 to 110 | how much to add | `0x08DDE` |
| stat, once per character | a maximum-block record offset, 124 to 174 | the ceiling it raises to | `0x09698` |
| train | unused | the highest level it will train to | `0x09D80` |
| enhance | the lowest enchantment it will take | the highest | `0x062D1` |
| experience | four packed BCD bytes at `+0x14`, the award | | `0x08EDF` |

**The live block's 26 words are named in the image.** The table of 13-byte strings at `DS:0x80F4` holds one name per word, and image `0x08D85` indexes it by `(offset - 60) / 2`: STRENGTH, DEXTERITY, STAMINA, INTELLIGENCE, WISDOM, CHARISMA, three blanks, HEALTH, MAGIC POINTS, a blank, then SURVIVAL through LINGUISTICS ([saves.md](saves.md) has the block). **The maximum block's words are named by a second table** at `DS:0x5708`, which is (record offset, string pointer) pairs ending at a zero key: 25 entries from 124 to 174, read by image `0x0969E`.

## The topic record, 1,073 records of 60 bytes

| Offset | Field | Evidence |
|---|---|---|
| `+0x00` | 13 bytes of keyword, NUL padded | shape |
| `+0x0E` | action word, the service and the flow | code, the dispatch at `0x02B26` |
| `+0x10` | a gold amount the topic asks for | shape: PAY 3,000 holds 3000 |
| `+0x12` | selector, read by whichever service the action names | code |
| `+0x14` | byte offset into this NPC's prose block | shape: the blocks tile |
| `+0x16` | how many prose lines the response runs to | shape: the blocks tile |
| `+0x18`, `+0x1A` | the one bit this topic is listed under | code, `0x090AE` |
| `+0x1C`, `+0x1E` | bits picking this topic turns on | code, `0x09436` |
| `+0x20`, `+0x22` | bits picking this topic turns off | code, `0x09424` |
| `+0x24` to `+0x2E` | six signed quest flag numbers the topic is conditional on | code, `0x090CA` |
| `+0x30` to `+0x3A` | six signed quest flag numbers picking it writes | code, `0x09452` |

### Which topics are offered

`DS:0x0EA6` and `DS:0x0EA8` are a 32-bit word pair holding which of this NPC's topics are live. Entering a conversation zeroes both (image `0x0A374`), and image `0x0916A` then rebuilds the menu: it walks the NPC's topics in order, asks image `0x09094` about each, and lists the ones that answer yes, to a limit of ten entries in the table at `DS:0x0EB2`.

Image `0x09094` refuses a topic when any of these holds:

1. `+0x18` and `+0x1A` are both zero. Such a topic is never listed, which is how a greeting stays off the menu.
2. `+0x18` is set and shares no bit with `DS:0x0EA6`.
3. `+0x1A` is set and shares no bit with `DS:0x0EA8`.
4. One of the six words from `+0x24` names a quest flag in the wrong state: a positive number is a flag that has to be set, a negative one a flag that has to be clear.

Each word carries at most one bit on all 1,073 records, so a topic occupies one slot of the 32.

### What picking one changes

Image `0x093D9` runs on every pick, before the service does:

- Action bit `0x0020` **opens a list**: it saves `DS:0x0EA6`/`0x0EA8` into `DS:0x539E`/`0x53A0`, with the topic's own `+0x18`/`+0x1A` cleared out of the copy, so returning does not re-offer the topic just taken.
- Action bit `0x0010` **closes one**: it restores that copy. The pair is a one-level stack, which is what makes BUY ARMOR and FINISHED a screen you enter and leave.
- `+0x20`/`+0x22` are then cleared out of the live pair and `+0x1C`/`+0x1E` ORed in. So a topic hides what it replaces and reveals what follows. NPC 11's HELLO turns on `0xA400`/`0x0004`, which is REPAIR, BUY PEGASUS, SELL and GOODBYE: the whole opening menu, in one word.
- Each of the six words from `+0x30` that is not zero is written as a quest flag: positive sets it, negative clears it. 383 topics carry a flag in one field or the other.

**This is what sets the quest flags a gated door tests.** Image `0x17AFE` resolves a 1-based bit number against the 14 words from `DS:0xCFAF`, high bit first, 224 bits in all, and the roster carries all fourteen at header 210 ([saves.md](saves.md)). The same resolver answers the gate table, an NPC's `+0x12` and `+0x22`, and a topic's conditions. Every flag number in the tables falls inside 1 to 224.

The armorer at NPC 31 is the whole mechanism in one NPC. PAY 3,000 is offered while flag 63 is clear, asks 3,000 gold, and sets flag 63. BUY ARMOR, SELL ITEMS and FINISHED each want flag 63 set. His own prose says the same: "I CANNOT OPEN UP MY ARMORY UNTIL THE BLACKSMITH HAS BEEN HIRED", then "AT THE COST OF ONLY 3,000 GOLD COINS, I CAN OPEN MY SHOP RIGHT AWAY".

### Where a conversation stands, and where a panel puts it back

**`DS:0x0FEB` is the conversation's own cursor**, a topic number inside the block rather than a global one: image `0x08F7E` reads it as `(n - 1) x 60` into the topic table. The opener at image `0x0A332` writes 4, 3, 2 or 1 into it, one per opens-on flag that holds, which is how a record greets a party differently as the game goes on.

**`DS:0x0EB2` is the row as drawn**, ten words of topic numbers, filled by image `0x09179` from the live pair. Ten is the row's whole length, which is why a menu never shows an eleventh keyword.

A service panel writes the cursor again as it closes, so the conversation carries on from somewhere other than where it left. Three of them stand it on `[DS:0x0EB2]`, the first keyword on the row. **The commodity panel stands it on the block's second topic**, image `0x06252`, and the alchemist is what that is for: NPC 3's second topic is an unlisted AFTER QTY that turns the three keywords back on and says "I HOPE THE QUALITY OF OUR NUORE MEETS WITH YOUR APPROVAL". Without it the row the order emptied would stay empty.

### Resolving a response

    line = NPC's first prose line + (topic +0x14) / 34 + 1

The extra line is `+0x0A` being 0-based. A prose line is 33 characters and a NUL; the game writes a quotation mark as `%` and an apostrophe as `~`, the same substitutions every other string in the game uses ([tools/labels.py](../tools/labels.py)). Read this way the responses tile and the quotation marks pair on 953 of the 955 responses that carry any. The two left over are one farewell reusing a greeting's offset with a different count, and one speech that opens a quotation mark the line above it closed.

For the armorer the offsets in lines are 0, 2, 7, 9, 12, 15 and 17 against counts of 2, 5, 2, 3, 3, 2 and 3, so each response ends where the next begins.

Read this way NPC 31 speaks as an armorer, NPC 5 as a food seller, NPC 7 as the wishing well and NPC 1 as the wizard Flagell.

## Every service a topic can open

The action word at `+0x0E` selects a handler. The dispatch runs from `0x02B26` to `0x02C8F`, and the counts are over all 1,073 topics:

| Action | Handler | Topics | Selector at `+0x12` | What they are called |
|---|---|---|---|---|
| `0x8000` | `0x06082` | 27 | a bundle, 1-based | PURCHASE, BUY ARMOR, NEW WEAPONS, BUY SCROLLS |
| `0x4000` | `0x063CF` | 17 | a merchant class mask | SELL ITEMS, SELL ORE, SELL JEWELS, SELL ARTIFACT |
| `0x2000` | `0x0931E` | 72 | 1, 2, 3 or 9999 | PAY GOLD, PAY 4,000, GIVE $10,000, HIRE NOW |
| `0x1000` | `0x0A548` | 21 | a bundle, 1-based | REWARD, KEY, TAKE RINGS, OPEN CHEST |
| `0x0800` | `0x0A3B9` | 35 | which body service, below | HEAL, CURE, RESURRECT, BUY PEGASUS |
| `0x0400` | `0x08E79` | 6 | unused | EXPERIENCE, SENSATION |
| `0x0200` | `0x08D3E` | 18 | unused | ENHANCEMENT, BLESSING, RAISE SKILL |
| `0x0100` | `0x06259` | 5 | unused | ENHANCE, all five of them |
| `0x0080` | `0x060D3` or `0x05738` | 15 | an item id, or a question | BUY FOOD, BUY NUORE, QUESTION, SCALE |
| `0x0040` | `0x0631E` | 3 | unused | REPAIR, all three of them |
| `0x0008` | `0x09F4E` | 12 | unused | SELL PEGASUS, SELL EAGLE, SELL RUG, SELL DRAGON |

The remaining bits are flow rather than service. `0x0020`, on 84 topics, opens a list. `0x0010` and `0x0004` close a screen and go back to the menu (DONE, FINISHED, CLOSE).

**`0x0002` holds the topic's quest flags back until the thing asked for is done.** Image `0x09442` tests it and then `DS:0x536C`'s `0x40`, and writes the six flag words only where that bit stands. A payment taken, an item handed over and a right answer each set it (images `0x0A188`, `0x0A0DA` and `0x058A9`), and image `0x09332` runs the flag routine a second time once a payment is in, so the flags land on the same pick. 104 topics carry it, which is every PAY, GIVE and HIRE in the game: **a refused payment opens nothing**. The armorer is the shape of it again, since a party that cannot afford his 3,000 leaves flag 63 clear and his armory shut.

**`0x0001` ends the conversation.** Image `0x02BD8` sends a topic carrying it to `0x02E89`, which frees the NPC's two buffers and returns, so the pick is the last one. 183 topics carry it, most of them greetings that no menu lists: the opening topic is reached by number rather than by a pick, and image `0x0A3A8` tests the bit there only to clear a redraw flag.

**The farewell is the block's last topic.** All 140 close on one carrying the bit, and 136 list it under the same high-word bit `0x0004`. The 16 other listed topics that carry it are not goodbyes but things that end a conversation as a side effect of doing something: PUSH BUTTON, PRESS BUTTON, LYDIA, GIVE IT BACK. Several write a quest flag, and the six button topics at NPCs 105 to 110 are a sequence that walks flags 165 to 170.

**None of the 140 farewells carries a service**, so leaving hands nothing over and takes nothing. Four write a quest flag: NPC 84's and NPC 85's are a single unlisted topic that fires as the party walks up, NPC 98's MESSAGE writes 149 and 150, and NPC 140's TELEPORT clears 224, which is the king sending the party to the last battle and is also the flag the reward beside it wants clear.

**A keyword is either something to say or something to do.** The table holds both and the game draws both the same way. A topic carrying a service bit or the `pays` bit is a control: it opens a screen or moves gold. A topic carrying neither, and having prose, is a conversation move: the keyword is what the party asks about and the answer is a paragraph. That splits the topics a menu can list 410 to 295, and the 64 with neither bits nor prose are all the yes and no a quote is answered with. The split is the topic's own until a screen is open or a quote is waiting, and then the whole menu is that service's: the same DONE closes a stock list in one place and a list of things to ask about in another.

**Four services open the item panel** and set a mode bit in `DS:0x536C`, which the panel reads to caption the price. Image `0x11172` shows VALUE: under `0x30`, which is buy and sell together, and COST: only under `0x08`.

| Action | `DS:0x536C` | Caption | Price word |
|---|---|---|---|
| `0x8000` buy | `0x20` | VALUE: | `DS:0x0E2C` |
| `0x4000` sell | `0x10` | VALUE: | `DS:0x53D0` |
| `0x0100` enhance | `0x08` | COST: | `DS:0x0FAC` |
| `0x0040` repair | `0x04` | none | `DS:0x538A` |

## The question a portal guard asks

**A commodity topic whose keyword does not begin "BUY " is not an order.** Image `0x02B3E` compares the topic's first four characters against `BU`, `Y ` and sends the rest to image `0x05738`, which is a question rather than a panel. Eleven topics take that road, against four that are orders.

The topic's own prose is the question. The handler prints it, takes 34 characters (image `0x0BDAC`, into `DS:0x9926`), and compares them against the answer its selector names: a word table at `DS:0xA8C6`, eleven pointers followed by the strings themselves, read length first and then byte for byte. A match prints "THAT SOUNDS GOOD TO ME." and sets `DS:0x536C`'s `0x40`; a miss prints "THAT IS INCORRECT." and sets nothing. Since the riddle runs before the flag routine on this branch, a right answer writes the topic's own quest flag and a wrong one does not, which is what keeps the portal shut.

| Selector | Answer | Asked by |
|---|---|---|
| 1 | PEACEFUL | NPC 86, QUESTION |
| 2 | 120 | NPC 87, QUESTION |
| 3 | ARCHIBALD | NPC 88, QUESTION |
| 4 | OVIAS | NPC 89, FIRST |
| 5 | WIN | NPC 89, SECOND |
| 6 | 30 | NPC 111, SCALE |
| 7 | 500 | NPC 112, SCALE |
| 8 | 3925 | NPC 113, SCALE |
| 9 | 46080 | NPC 114, SCALE |
| 10 | 400000 | NPC 115, SCALE |
| 11 | 70 | NPC 138, QUESTION |

The selectors run 1 to 11 in the order the table holds them, and each of the eleven topics writes a quest flag of its own: 128, 129 and 130 for the three portals of the Order, 131 and 132 for the two halves of NPC 89's, 171 to 180 for the five scales, and 219 for the last. Each guard is gated on the flag his own question writes, at his record's `+0x22`, so answering him retires him: NPC 86 asks about flag 128, writes 128, and goes quiet once it stands.

## What a BUY screen stocks

**A shop's stock is a bundle in `WORLD.DAT` section 10**, the same 26-byte record a chest on a cell names. Image `0x06082` takes the topic's `+0x12` straight to `0x0252E`, which is the bundle loader, and then runs the same panel a container opens. **Evidence is code** at those two addresses, with the names as corroboration: all 27 buy topics name a bundle in range, and each reads as the shop it belongs to. BUY POTIONS at NPC 3 holds four potions, BUY ARMOR at NPC 31 holds LEATHER ARMOR, a COPPER RING OF ARMOR, a WOODEN SHIELD +5 and a COPPER SHIELD, and NEW WEAPONS at NPC 32 holds the three weapons of Light.

A bundle is eight item places and three counts ([map.md](map.md) has the record). A shop uses the eight places; its three counts are zero on every buy topic.

**A reward is the same thing handed over for nothing.** Image `0x0A548` is `0x06082` without the mode bit: the same `+0x12`, the same loader, the same panel. Its 21 bundles carry the counts as well, so a reward pays gold, food and nuore alongside items. Seven of them hand over a DOOR KEY, one per metal, which are the keys the Athaneum's six gates and Yendor's seventh want ([map.md](map.md)). That correspondence is what ties the reward table to the gate table.

## What a shop will buy

Image `0x047D3` reads the SELL topic's `+0x12` and tests it against the item record's word 16, refusing with "I HAVE NO NEED FOR THAT TYPE OF ITEM" where the two share no bit. That word partitions all 631 items ([items.md](items.md)), and the 17 sell topics name exactly the eight bits it takes:

| Mask | Items | What they are | Topic |
|---|---|---|---|
| `0x8000` | 420 | weapons and armor | SELL ITEMS, eight of them |
| `0x4000` | 12 | potions | two |
| `0x2000` | 6 | the lockpick, the hourglass, the torch, three containers | one |
| `0x0800` | 12 | gems, bars and nuggets | SELL JEWELS, two |
| `0x0200` | 5 | dwarf goods | one |
| `0x0100` | 5 | elf goods | one |
| `0x0080` | 4 | the Order's chalice, cup, urn and candlestick | SELL ARTIFACT, one |
| `0x0020` | 4 | copper, iron, silver and gold ore | SELL ORE, one |

The 163 records holding zero are the currencies, the keys, the parchments and the quest loot. Nothing buys those.

## Prices

Every price in a shop is an item's own packed BCD value, at record `+4`, scaled by a percentage. Image `0x0AA1D` does the scaling: it multiplies each BCD digit by the percentage, adds 50 to the units digit's product, and shifts the total right two digits through `0x0AB4B` twice. That is `round(value x percent / 100)`, half up.

**Buying and selling are haggled.** Image `0x0A692` writes the item's value into both price words and then picks a margin from the barterer's own bartering skill, at character record offset 104:

| Bartering | Margin |
|---|---|
| to 54 | 55% |
| to 64 | 45% |
| to 79 | 35% |
| to 100 | 25% |
| to 124 | 15% |
| to 149 | 8% |
| to 999 | 2% |
| over 999 | 55% |

The buy price is `value x (100 + margin)%` and the sell price is `value x (100 - margin)%`. The last band is the first one's figure again, so a skill over 999 haggles as badly as a beginner. Who haggles is the party's own barterer at `DS:0xCF81` ([party.md](party.md)); image `0x06447` puts up WHO WILL BARTER, prompt 10, where that word is zero, and rejects a character whose condition word has any of `0x1C40` set.

**Repairing and enhancing are not haggled.** Both take the NPC's own `+0x18` as the percentage, and the 29 NPCs that carry one hold 2, 3, 4, 5, 10, 40 or 50.

**A repair is priced on the whole form, not the broken one.** Image `0x0A763` reads the item id the broken place's second word names, which is what breaking wrote there ([items.md](items.md)), and scales that record's value. So mending a COPPER SHIELD +4 is priced on the +4's own worth.

**An enhancement is priced on the next form.** Image `0x0A725` reads the record one past the one in hand. That is also the whole of what an enhancement does: image `0x045A8` writes `id + 1` into the place, because a series runs as consecutive item ids.

**Food and nuore cost 10 gold per unit**, in the prompt at `DS:0x84B3`, and the screen refuses an order under 10 units (`DS:0x8372`). Image `0x060D3` takes the quantity, adds it to the count at `DS:0xCF95` for food or `DS:0xCF99` for nuore, fills the matching party inventory slot if it is empty, and subtracts the cost from the purse.

**What each of the four writes** is image `0x098E2`, one branch per bit of the selector it was quoted under:

| Service | What it writes |
|---|---|
| HEAL | health to its maximum, and no condition touched |
| CURE | `conditions &= 0x7F`, which is the nine |
| RESURRECT | clears the held bit and writes **2** health, not the maximum |
| RESTORATION | health to its maximum and `conditions &= 0x3F`, so the held bit goes too |

A heal on a corpse therefore fills the pool and leaves a corpse, since nothing on that branch reads the condition word. The game offers it anyway: image `0x08FC6` sets the health bit on health below its maximum and looks no further.

**The four services on a body are priced per level.** Image `0x091EB` multiplies a base by the NPC's `+0x18` and then by the character's level at record offset 22:

    price = base x factor x level

| Service | Base | At |
|---|---|---|
| HEAL | 20 | `0x099A9` |
| CURE | the sum over the conditions, below | `0x0999D` |
| RESURRECT | 100 | `0x09992` |
| RESTORATION | the conditions, plus 20 for health short of its maximum, plus 100 where condition `0x0040` is held | `0x09968` |
| a training | 100 | `0x09E15` |

**What clearing one condition costs** is the cure weight [combat.md](combat.md) tables against each of the nine, summed over the bits set in the character record's word 28. Image `0x092B1` is that sum. All nine together are 275.

## A quote, then a yes

A service that costs money runs in two picks. The first quotes: image `0x091EB` works out the total, writes it to `DS:0x543C`, prints "IT WILL COST n GOLD" and "IS THAT PRICE AGREEABLE?", and leaves the service pending in `DS:0x0EAA`. The player then picks a follow-up topic, and its own `+0x12` says which answer it is: bit `0x02` pays and bit `0x04` declines. The payment is a four-byte BCD compare against the purse at `DS:0xCF91` (image `0x0A7D2`), "YOU DON'T HAVE ENOUGH GOLD" where it is short, and a BCD subtract (image `0x0A9F7`) where it is not.

`DS:0x0EAA` survives the pick, which is what lets one pair of YES and NO topics answer every quote an NPC makes. Image `0x02AC9` dispatches on it at the top of the conversation loop, before the action word is read at all:

| `DS:0x0EAA` | Routine | Pending |
|---|---|---|
| `0x8000` | `0x09825` | a body, with health and conditions read |
| `0x4000` | `0x099B4` | a body, with levels owed read |
| `0x3000` | `0x09E1D` | a transport, bought or sold |
| `0x0800` | `0x0947E` | one stat, once per character |
| `0x0400` | `0x09732` | |

## Which character a service acts on

`DS:0x53D4` points at one of the four handle slots from `DS:0xD0C9`, and it is what every service on a body reads. Image `0x0A3D7` writes the first slot on entry, so the service starts on place 1.

**The four portraits are the picker.** Image `0x16C78` draws them across the conversation screen at x 8, `0x42`, `0x7C` and `0xB6`, each the 32 x 32 run 7 picture the character record names at offset 18, skipping a slot that holds nobody. Image `0x03AA8` then lights the ones that do, setting one of `DS:0x536C`'s bits `0x4000`, `0x2000`, `0x1000` and `0x0800` per place and drawing a frame around it. The click handler at `0x0486F` hit-tests the four boxes at `DS:0x6646`, refuses a place whose bit is clear, and writes that character's handle slot into `DS:0x53D4`.

Moving between them rebuilds the menu, because the menu is built out of what the picked character needs. A party with one hurt and one dead offers the heal on the first and the resurrection on the second.

**A flight is the picked character's too.** Image `0x192E0` reads word 180 off whoever `DS:0x53D4` names, so which SELL topics a stable lists follows the pick rather than the party.

## What a character needs, as topic bits

Before the menu is drawn, the pending service computes the top of `DS:0x0EA6` from the chosen character, and the follow-up topics are listed under those bits. So the same four bits mean both "the character needs this" and "this topic is live".

Image `0x08FC6`, for a body:

- `0x8000` where live health at record offset 82 is below the maximum at 146
- `0x4000` where any of the nine conditions in word 28 is set
- `0x2000` where condition `0x0040` is held
- `0x1000` where two or more of those hold, `0x0200` where none does

Image `0x09059`, for a training: `0x8000` where the character has a level owed, which is the "ready for level" field at record offset 30 that image `0x065BA` recomputes on every shop visit ([leveling.md](leveling.md)).

Image `0x08F93`, for a stat: `0x8000` where the NPC's `+0x1A` bit is still **clear** in that character's own bit array, which image `0x17ABC` resolves at record offset 202. Fourteen NPCs carry a `+0x1A`, holding 1 to 14 with no repeat, so each is spent once per character. Each names a maximum-block stat at `+0x14`, a ceiling at `+0x16` and a flat price at `+0x1C`: NPC 28 is the Challenge of Strength, which raises maximum strength to 80 for 1,000 gold.

## Raising an attribute

Image `0x08D3E` is the `0x0200` service, and it acts on the whole party rather than on one character. It refuses outright where the NPC's `+0x12` flag is already set, and sets that flag when it runs, so each is given once per game. For every character whose condition word does not carry `0x0040`, and whose live word at `+0x14` is above zero, it adds `+0x16` to the live word and the same again to the maximum 64 bytes further on. Image `0x08E56` clamps: health and magic to 9,999, everything else to 999.

The wishing well at NPC 7 is the check on this reading. 100 gold sets flag 3, which offers ENHANCEMENT, which names offset 100 and 3. Offset 100 is MAPPING, and the well's own prose answers "EVERYONE IS NOW BETTER ABLE TO FIND THEIR WAY AROUND".

## Experience

Image `0x08E79` is the `0x0400` service, gated and spent on `+0x12` the same way. The award is the four packed BCD bytes at `+0x14`, and every character whose condition word does not carry `0x0040` gains all of it, added to the BCD experience at record offset 24. Experience is not divided among the party.

## Enhancing a piece of gear

The screen behind ENHANCE gates on `0x062D1`, which admits an item when three conditions hold:

1. its category word is `0x0A00` (shield or worn) or `0xC000` (hand or missile),
2. its properties word at `+2` carries the series bit, which is `0x0800` for a weapon and `0x0100` for a piece of armor,
3. its current enchantment falls between the NPC's `+0x14` and `+0x16`.

The level is the properties word at `+8` for a weapon and `+6` for armor, and it runs 0 to 10 across a series. **Rings cannot be enhanced**: the category test admits shields and worn pieces but not `0x0400` rings, and no ring carries a series bit or has a `+N` form.

**How far a piece can be taken is a property of the NPC.** The five enhancers hold `+0x14`/`+0x16` of 0/1, 0/9, 2/3, 4/5 and 6/7, against a factor of 50 on all five. NPC 34 is the one that takes a piece already at +9, so it is the only one that makes a +10, and the 161 absorption ceiling in [items.md](items.md) assumes reaching it.

## Repairing, as a shop does it

A REPAIR topic opens the item panel in repair mode at `0x0631E`. The screen admits one kind of item: the filter at `0x06396` answers only for the broken form of a weapon or a shield ([items.md](items.md) has the bit and what a repair does to the piece).

**Paying is three steps, in this order** (image `0x046A1`): the picked item is tested, and a whole one answers with a message; the purse is compared against `DS:0x538A`, and a short purse answers with another; and then the price is subtracted and the piece is put right, which is the swap [items.md](items.md) sets out.

**A shop always succeeds.** No skill is read on this path and no roll is made. What the party's own repairer does instead, and how badly it can go, is [items.md](items.md)'s.

**Bartering is the only party skill a shop reads.** Everything else a WHO WILL prompt names is the party acting on its own ([party.md](party.md)).

## Transports

The four flights are a table of 26-byte records at `DS:0x7AF4`: a 12-character name, a four-byte BCD value at `+0x0E`, how many uses at `+0x16`, and a word at `+0x18` whose bit `0x0002` means the flight can be taken at any hour. The clue book's TRANSPORTATIONS page prints three of the four; FLYING RUG is the one it leaves out. [tools/items.py](../tools/items.py) reads it.

| Name | Value | Uses | When |
|---|---|---|---|
| PEGASUS | 10,000 | 1 | any time |
| GIANT EAGLE | 30,000 | 2 | any time |
| FLYING RUG | 50,000 | 4 | any time |
| MAGIC DRAGON | 70,000 | 4 | 7 p.m. to 7 a.m. |

Buying one is the `0x0800` service with a selector of `0x1000` and selling one is `0x2000`, both reaching `0x09E1D`; the `0x0008` service at `0x09F4E` is the four SELL PEGASUS, SELL EAGLE, SELL RUG and SELL DRAGON topics that name which. Three NPCs deal in them, all three with a factor of 40 and a REPAIR topic beside the flights, so the smith and the stable are one person.

## What is still open

- **How a flight is taken.** Buying and selling are read; using one is not. A character's word 180 holds which flights it owns and the four words from 182 count how many times each has been used, which buying zeroes (image `0x09EFA`). Image `0x15CE6` draws that character's flights with the row lit only while the count is under the table's own limit at `+0x16` and the hour suits `+0x18`, and all three of its callers are inside a stable's conversation. **Nothing found increments those counts**, so the code that spends a use has not been located.
- **`+0x02` of the NPC record**, 2 or 4 on 27 records.
- **The `0x2000` PAY service's selector**, which image `0x09338` compares against 1, 2, 3 and 9999 and which image `0x02AC9` also reads as a bit mask. It is not one field.
- **What the two buy and sell prices do to the stock.** Image `0x0252E` computes a bundle's bank-0 bit the way a container's opening does, and nothing found sets it on a buy, so a shop's eight places do not visibly run out.
