# Quest flags

The game's progress is 224 bits in the roster. Six mechanisms write those bits and six read them. A conversation topic is one. So are a gated door, a greeting, a monster's death, an item the party uses, and six hand-written world scripts. This document says what each of the 224 bits is, what writes it, and what reads it.

**Evidence is code** throughout, at the image addresses given. **Shape** stands behind the counts. Every flag number in every table falls in 1 to 224. The kill table's records tile to a zero key, and the gate table's records tile to a word of `0xFFFF`. [README.md](README.md) defines the classifiers.

[tools/quests.py](../tools/quests.py) reads all of it: the gate table, the kill table, the six world scripts and the three item handlers. It assembles the table below from those and from the conversation tables in [npcs.py](../tools/npcs.py), rather than by hand. The scripts and the item handlers are immediates rather than a table, so `check_scripts` and `check_uses` hold every constant to the bytes at the image address it was read from. [tests/test_quests.py](../tests/test_quests.py) holds the counts this document states.

## The array

The flags are fourteen words at `DS:0xCFAF` to `DS:0xCFC9`, 224 bits in all. They sit at roster header offsets 210 to 236 ([saves.md](saves.md)), so a save carries them and a load restores them. The `WORLD.DAT` template holds zero in all fourteen. That is what starts a new game with nothing done.

**Image `0x17AFE` resolves a 1-based flag number.** It divides the number by 16. The quotient indexes the words from `DS:0xCFAF`. The remainder picks the bit, counting down from the high bit. Where the remainder is zero the routine steps back a word and takes bit `0x0001`, so flag 16 is the last bit of the first word rather than the first bit of the second. In one line, flag `n` is word `(n - 1) / 16`, bit `0x8000 >> ((n - 1) mod 16)`.

Three far-callable wrappers call it, each taking the flag number in `ax`:

| Wrapper | Does |
|---|---|
| `0x17A90` | clears it |
| `0x17AAC` | sets it |
| `0x17AC4` | tests the bit; ZF set means clear |

The routine checks no range. A flag number above 224 would run off the end of the array into the rest of the roster header. No table in the game holds a number above 224.

**Two more resolvers sit next to it in the image, and neither one reaches this array.** Image `0x17AD4` adds `0x10C` to a base the caller passes in `si`, and image `0x17B27` adds `0xCA`. Each of those resolves a bit array inside a character record ([saves.md](saves.md)). The two have six wrappers of their own, at `0x17A86`, `0x17AA4`, `0x17ABC`, `0x17A9A`, `0x17AB4` and `0x17ACC`. All nine wrappers are consecutive, and three of the nine reach `DS:0xCFAF`. Picking the wrong wrapper out of the run puts a quest flag inside a character.

**The gate table is the one reader that skips the resolver.** A scan of the whole image for the fourteen word addresses turns them up in the gate table and nowhere else. A gate record holds a pointer to a word and the bit to test in it, rather than a flag number. Every other reader and writer calls one of the three wrappers.

## What writes a flag

| Mechanism | Where | Flags |
|---|---|---|
| a conversation topic's six write slots | `0x09452` | 167 |
| an NPC's one-shot service marker | `0x08DD0`, `0x08EFB` | 24 |
| killing a monster in the `DS:0xCE51` table | `0x1273E` | 23 |
| answering a gate's password | `0x05653` | 13 |
| using a gate's key | `0x197CF` | 1 |
| the code, below | | 5 |

## What reads a flag

| Mechanism | Where | Flags |
|---|---|---|
| a topic's six condition slots | `0x090CA` | 141 |
| which greeting a conversation opens on | `0x0A31A` | 59 |
| an NPC refusing to talk | `0x0A20B` | 55 |
| a one-shot service already spent | `0x08D42`, `0x08E81` | 24 |
| a gated door | `0x055BE`, `0x197C0`, `0x1DB19` | 35 |
| the code, below | | 8 |

## A topic's six conditions and six writes

Each of the 1,073 conversation topics carries six signed words at `+0x24` and six more at `+0x30` ([shops.md](shops.md)). **A zero slot is skipped rather than ending the run.** The sign carries the state. A positive number means the flag is set, and a negative number means it is clear.

Image `0x090CA` walks the condition slots. It refuses the topic where any non-zero slot is in the wrong state, so every condition on a topic has to hold at once. 263 topics carry at least one condition, and the tables set out 337 conditions in all, 143 of them positive. No topic uses more than three of the six slots.

Image `0x09452` walks the write slots and writes every non-zero one. A positive number sets its flag and a negative number clears it. 172 topics carry at least one write, and the tables set out 182 writes in all, 13 of them clears. No topic uses more than four of the six slots.

**A topic that moves gold writes its flags only after the payment goes through.** Image `0x09442` tests the topic's own `pays` bit. Where that bit is clear, the writes run. Where it is set, the writes run only if `DS:0x536C` bit `0x40` is set as well, and bit `0x40` is the payment's own answer. Image `0x0A09D` clears it on entry to the PAY service and dispatches on the topic's selector. Image `0x0A0DA`, `0x0A161`, `0x0A188` or `0x0A1AF` sets it once the party has handed something over. Image `0x09475` clears it again after the writes. A party that cannot afford PAY 3,000 therefore gets the refusal, and the flag stays clear.

The same dispatch names the four PAY selectors. 1 is gold, 2 is food, 3 is nuore and 9999 is an item. The topic's own `+0x10` holds the amount.

## What the flags do to a conversation

**Which greeting a conversation opens on.** Image `0x0A31A` tries the NPC record's `+0x10`, `+0x0E` and `+0x0C` in that order. The first of the three that names a set flag wins, and the conversation opens on topic 4, 3 or 2 to match. A zero field is skipped, and a record where none of the three answers opens on topic 1. 59 records carry `+0x0C`, 8 carry `+0x0E`, and 6 records carry both. NPCs 20 and 25 carry `+0x0E` alone. `+0x10` is zero on all 141.

**Whether the NPC talks at all.** `+0x22` names a flag. Where that flag is set, image `0x0A20B` ends the conversation before the menu is built. 63 records carry one, and it is what stops an NPC talking once their part is over. NPC 127, NPC 128, NPC 129 and NPC 131 all fall silent on flag 206, which killing King Slator sets.

**Whether a one-shot service is still available.** `+0x12` names a flag as well. The attribute service at image `0x08D42` and the experience service at image `0x08E81` both refuse where that flag is already set, and both set it when they run, at `0x08DD0` and `0x08EFB`. 24 records carry one.

A topic of the same NPC also sets four of those 24. NPCs 90, 91, 92 and 93 are built alike: a cheaper GIVE that sets the flag, a dearer GIVE that leaves it alone, and a BLESSING carrying the attribute service. Paying the cheaper amount therefore spends the flag without the blessing running. Flag 224 is the fifth overlap, and NPC 140's TELEPORT clears it rather than setting it.

## A gated door

The 35 records of 22 bytes at `DS:0xC45B` ([map.md](map.md)) are the flag side of the door table. Each record names a destination, a pointer to one of the fourteen words, and the bit to test in that word. The 35 pointer-and-bit pairs resolve to flag numbers 19 to 218. They reach thirteen of the fourteen words, and no gate names the first.

Image `0x055A3` answers the door handler with 1 where the flag is already set, 2 where the party has just opened the gate, and 0 where it refuses. Three kinds of gate refuse in three different ways.

- **A password**, on 13 records. `+0x06` holds 26 on all thirteen, and 26 is a prompt number. Image `0x058F0` indexes the prompt registry at `DS:0xE265` 1-based, and prompt 26 reads "WHAT IS THE PASSWORD". Image `0x05644` compares the typed answer against the twelve characters at `+0x0A` and stops at the first space. **A match sets the flag** at `0x05653`, so a password is answered once and the door stays open after that. The thirteen are NOBLEMAN, GAUNTLET, COMPASSION, PATRIARCH, PARCHMENT, RUSE, GEMSTONE, CALANTHA, ALLIANCE, TIMBER, SOLITAIRE, DELIA and DRAGONSKIN.
- **An item**, on 1 record. Destination 58 names item 374, the JEWELED PORTAL KEY. The party uses the key rather than carrying it. Image `0x19763` handles that use: it asks which cell, reads that cell's destination, and compares the gate record's `+0x08` against the item in hand at `0x197CA`. A match sets flag 121 at `0x197CF` and answers "UNLOCKED". A miss answers from the lock message table at `DS:0x7F00`.
- **The flag alone**, on the remaining 21. Nothing at the door opens one of these. Bit `0x4000` of the destination record's own `+0x0E` sends the refusal to image `0x05672`, which prints "YOU CANNOT ENTER HERE RIGHT NOW". Bit `0x8000` picks the password branch instead.

Image `0x1DB02` walks the same table for an item that carries the party home ([items.md](items.md)). It makes the same test and writes nothing.

## Killing a monster

**The table at `DS:0xCE51` is 23 records of six bytes.** Each record holds a spawn id and two signed flag numbers. The records ascend by spawn id and end at a zero key. Image `0x126C8` walks the table when a monster goes into one of the eighty slots, right after image `0x127B4` sets the section 5 bit, and it copies the two flag numbers into that slot's own head at `+0x14` and `+0x16`. Image `0x1273E` reads the pair back out and writes it the way a topic's write slots go, a positive number setting and a negative number clearing.

`0x1273E` is the last thing the death routine at `0x1270C` does. All nine death sites call that routine with the slot in `si`, once the monster's health at `+0x10` has reached zero, and each one calls `0x12CA6` straight after to free the slot ([encounters.md](encounters.md)). The flag is therefore written on the kill. It stays written, because nothing clears a dead spawn's section 5 bit ([saves.md](saves.md)).

The second flag number is zero on all 23 records. The first one carries the main quest, and the flags rise with the spawn ids:

| Flag | Spawn | Monster | Where |
|---|---|---|---|
| 1 | 1 | CENTIPEDE | Thaine Map 10 |
| 6 | 10 | WASP QUEEN | Thaine Map 10 |
| 9 | 39 | RABID WOLF | Kingdom of Bariag |
| 20 | 145 | PURPLE SLIME | Sewers of Bariag |
| 34 | 203 | MILLIPEDE | Keep |
| 41 | 241 | GNOLL | Copper Mine |
| 52 | 310 | SCORPION | Nuore Mine |
| 56 | 314 | BEHOLDER | Castle of Bariag Level 1 |
| 59 | 362 | KING BARIAG | Castle of Bariag Level 2 |
| 68 | 444 | PIXIE LEADER | Kingdom of Obversia |
| 80 | 487 | ACOKNIGHT | Acoknight's Cave Level 1 |
| 99 | 806 | QUEEN OBVERSIA | Tower of Obversia |
| 103 | 849 | ALLIGATOR | Thaine Map 6 |
| 108 | 900 | FUNGUS | Kingdom of Yendor |
| 114 | 992 | KNIGHT | Castle of Yendor |
| 162 | 1,154 | ELF WATCHMAN | Elfin Sewer |
| 163 | 1,181 | PURPLE DRAGON | Silver Mine |
| 183 | 1,243 | VISHAN | Vishan's Stronghold Level 2 |
| 201 | 1,422 | SPECTRE | Dungeon of Slator Level 1 |
| 206 | 1,566 | KING SLATOR | Castle of Slator Level 2 |
| 211 | 1,750 | TITAN LORD | Castle of Euron |
| 223 | 1,861 | BLAZIOS | Thaine Map 1 |
| 224 | 1,862 | PALTIVAR | Quartz Chamber |

Two of the 23 rewrite a whole region's conversation. Killing King Bariag withdraws thirteen topics and offers six, across NPCs 1, 13, 14, 15, 16 and 24. Killing Queen Obversia withdraws fifteen and offers five, across NPCs 39, 40, 46, 47 and 48, and it silences NPC 67.

## The world scripts

The `0x0400` cell event kind has six records, and each one has a hand-written handler ([map.md](map.md)). The event's argument is the script number, which both dispatches read from `[si+4]`. Image `0x0B751` says which object the cell draws. Image `0x0B7A8` runs when the party uses the cell.

**Using the cell is the space bar, not the step.** Image `0x0040A` picks the cell the party stands on or the one in front of it through image `0x10CD5`, then tests the event's kind: `0x8000` opens a container, `0x2000` takes a door, `0x1000` starts a conversation, and `0x0400` reaches image `0x0B7A8` at image `0x00425`. That is the only call to it anywhere in the load image. Three of the six cells carry an object the walk rule refuses anyway, so a step could never reach them.

| Script | Cell | Object | What using it does |
|---|---|---|---|
| 1 | Yendor (40, 62) | 210 while flag 5 is clear | sets flag 5 and lands the party on Thaine Map 10 at (397, 94) facing west |
| 2 | Yendor (69, 50) | 223 while flag 27 is set | refuses while flag 27 is clear, otherwise lands the party in the Keep at (540, 121) facing south |
| 3 | Kingdom of Bariag (487, 32) | 224 | refuses while flag 46 is clear, otherwise lands the party in the Prison at (638, 36) facing west |
| 4 | Prison (603, 44) | 231 | moves the party to (619, 37) and turns every RING OF INVISIBILITY into a COPPER RING OF ARMOR, answering "THE RINGS HAVE BEEN DRAINED" |
| 5 | Thaine Map 5 (352, 68) | 212 | refuses while flag 145 is clear, otherwise sets flag 157 and lands the party in the Plane of Souls at (604, 123) facing east |
| 6 | Plane of Souls (635, 136) | 250 | clears flag 157, sets flag 158 if the party carries a WEAK SOUL, destroys every SWORD, HAMMER and TRIDENT OF LIGHT it finds, and lands the party back on Thaine Map 5 at (332, 70) facing south |

Script 1 is Saxon's ship. Image `0x0B7D7` writes the landing coordinates as immediates, and they match the pair `WALKED_LINKS` in [tools/pack_maps.py](../tools/pack_maps.py) recorded from a walk.

**A handler lands the party by hand.** A door assigns `DS:0xCEF9` whole out of its destination record ([map.md](map.md)). Each of these writes the party's three words itself and then ORs into and ANDs out of that one word: scripts 2, 3 and 4 set the indoor bit, script 2 clears the cold bit with it, and scripts 5 and 6 set and clear bit `0x4000`. Each writes the area word at `DS:0xCF33` as well, which picks the ambient list ([audio.md](audio.md)): 2, 4, 5, 5, 8 and 2 in script order. Script 5 is the only writer of area 8 anywhere in the game.

**The view draws the first two of those cells a second way.** Image `0x0B704` runs inside the view and tests the coordinates of the cell it is about to draw. Cell (40, 62) takes object 210 while flag 5 is clear, and cell (69, 50) takes object 223 once flag 27 is set. Script 1 and script 2 stand on those two cells, so each gets its object from two routines rather than one.

**An item the party uses is the last writer.** Image `0x0B490` dispatches USE on whichever item the search found, and three items have a handler there: the JEWELED PORTAL KEY, the ENHANCED LENS and the ORB OF ZAMORA. The ENHANCED LENS is item 382, and it reaches image `0x0B4DB`. That routine sets flag 145 only where the party stands at (352, 67) on Thaine Map 5 facing south. The cell it faces holds script 5, so the lens is what opens the Plane of Souls.

**A swap is one routine.** Image `0x0161C` takes an item to find at `DS:0x53EE` and an item to write over it at `DS:0x53F0`, walks the party's own six inventory places at `DS:0xCFF7` and then the characters, and answers with what it found at `DS:0x5426`. Script 4 calls it with 198 and 205 and goes round again while it keeps answering, which is what drains every ring the party holds. Image `0x0B1FC` is the same search without the write, and it is what every other handler here looks for an item with.

## The other flags the code reads

| Flag | Read at | Set means |
|---|---|---|
| 5 | `0x0B715`, `0x0B75A`, `0x0B7B4` | the party has boarded the ship |
| 27 | `0x0B73B`, `0x0B771`, `0x0B850` | the keep is built |
| 32 | `0x02EAA` | the map wants reloading |
| 46 | `0x0B8C5` | script 3 opens into the Prison |
| 145 | `0x0BA1E` | script 5 opens into the Plane of Souls |
| 157 | `0x0CFE3`, `0x1DA9E`, `0x1DAC0` | the party is inside the Plane of Souls |
| 223 | `0x0B56E` | Blazios is dead |
| 224 | `0x00070` | Paltivar is dead |

Flag 32 is the only one of the eight that marks no progress. NPC 18's BUILD NOW sets it beside flag 27. Image `0x02EAA` clears it as the conversation ends and calls image `0x0FE74`, the map reload every teleport makes, so the keep appears the moment the party stops talking.

Image `0x1DA90` clears flag 157 where the party carries none of items 383 to 385, so the flag falls whichever way the party leaves the Plane of Souls. While flag 223 is clear the ORB OF ZAMORA answers "BLAZIOS IS STILL ALIVE". Image `0x00070` tests flag 224 at the top of every pass of the main loop and sends a set flag to image `0x05290`, which nothing else calls.

## The ending, end to end

The last chain reads straight out of the tables.

1. Killing the TITAN LORD sets flag 211, which offers NPC 132's CROWN and NPC 133's TOUCH CROWN.
2. NPC 139, standing on Yendor at (59, 66), hands over bundle 395 as a reward: the GEMSTONE OF YENDOR and the ORB OF ZAMORA. His DONE sets flag 222 so the reward is taken once.
3. Killing BLAZIOS sets flag 223.
4. The party uses the ORB OF ZAMORA at (246, 30) on Thaine Map 1 facing west. Image `0x0B507` handles it and applies three guards in order, each with its own message. The position answers "YOU MUST BE CLOSER TO THE THRONE". Flag 223 answers "BLAZIOS IS STILL ALIVE". The five items answer "YOU DO NOT HAVE ALL THE KING'S ITEMS", and those five are the SCEPTER OF BARIAG, the AMULET OF OBVERSIA, the SWORD OF SLATOR, the CROWN OF EURON and the GEMSTONE OF YENDOR, one per kingdom.
5. The handler destroys all five items. Image `0x0B69C` then opens a conversation with NPC 140 directly rather than through a cell. NPC 140 is King Thaine, one of the two records no cell event places.
6. His REWARD is an attribute service, and it raises every character's HEALTH by 200. The topic wants flag 224 clear, and the service sets it, so the party takes the reward once. His TELEPORT then clears flag 224 again.
7. The party lands in the Quartz Chamber at (660, 132) facing north. PALTIVAR is spawn 1,862, standing at (660, 131).
8. Killing him sets flag 224, and the main loop runs `0x05290`.

Flag 224 therefore does two jobs. The same bit marks the king's gift as spent and marks the last monster as dead. Clearing it on TELEPORT is what keeps the two apart.

## The ending sequence

**Image `0x05290` is what flag 224 sends the main loop to**, and nothing else calls it. Three routines in order.

| Image | Does |
|---|---|
| `0x05472` | stops the music and clears a 320 x 200 buffer |
| `0x0531F` | plays song 24, draws the first page, wipes it on, speaks over it |
| `0x053C0` | draws the second page, wipes it on, speaks over it |

**The two pages are run 0 pictures 13 and 14**, the same run the menu and the assembly are painted into. The epilogue is paint rather than text, so there is no string to read: the picture is the words. Image `0x054C3` is the wipe, 80 columns of 200 scanlines copied a dword at a time with a stride of `0x13C`.

**The speech is the last twelve sounds of the bank**, 130 to 135 over the first page and 136 to 141 over the second, 37 seconds between them ([audio.md](audio.md)). Image `0x05501` is what paces them: image `0x184B4` spins on `DS:0xF2E` while a sound is playing and answers ZF set, which skips the wait beside it, so a line's own length is the pacing. The 13 ticks in `cx` are what stands in for that length where sound is switched off. The pauses of 7 and 4 ticks between some of the lines run either way.

The screen then holds for 30 ticks and 20 more each time round while a sound is still playing, and image `0x052B6` frees the buffer and exits to DOS.

## Every flag, its writers and its readers

**223 of the 224 bits are used.** No table and no instruction names flag 58. Two more are written and never read. Killing the WASP QUEEN sets flag 6, and NPC 133's TOUCH CROWN sets flag 212. Every other flag has both a writer and a reader.

The numbering follows the game's own order. The kill table's flags rise with its spawn ids, and the conversation flags run through the regions in the same sequence: the Athaneum, the Kingdom of Bariag, the Keep, Obversia, the Dwarven Homeland, Yendor, the Way of the Order and the Holy Order, the Elfin City, Vishan's Stronghold, Slator, Euron, Delia's Island, and flags 222 to 224 at the end. A flag's number is therefore a rough measure of how far into the game it belongs.

The whole array follows. A topic is written `NPC n KEYWORD`. **Offers** counts the topics a set flag makes available, and **withdraws** counts the topics a set flag takes away.

| Flag | Written by | Read by |
|---|---|---|
| 1 | NPC 1 HELLO; killing CENTIPEDE (spawn 1) | offers 1: 1.HELLO 2; NPC 1 greeting 2 |
| 2 | NPC 1 YES | offers 1: 1.THAINE; withdraws 1: 1.TASKS |
| 3 | NPC 7 GIVE 100 GOLD | offers 2: 7.HELLO-2, 7.ENHANCEMENT; withdraws 1: 7.HELLO; NPC 7 greeting 2 |
| 4 | NPC 7 service | NPC 7 service spent |
| 5 | boarding the ship | offers 3: 1.AREA SECURED, 1.EXPERIENCE, 1.PORTALS; withdraws 1: 1.THAINE; the ship on Yendor |
| 6 | killing WASP QUEEN (spawn 10) | nothing |
| 7 | NPC 1 service | withdraws 1: 1.EXPERIENCE; NPC 1 service spent |
| 8 | NPC 1 DONE | withdraws 2: 1.AREA SECURED, 1.USEFUL THINGS |
| 9 | killing RABID WOLF (spawn 39) | NPC 10 greeting 2; NPC 12 greeting 2; NPC 20 greeting 3 |
| 10 | NPC 13 RETURN CAT | offers 2: 12.PLAN, 13.REWARD; withdraws 2: 12.BUSINESS, 13.CAT |
| 11 | NPC 13 HELLO | NPC 13 greeting 2 |
| 12 | NPC 13 CLOSE CHEST | withdraws 1: 13.REWARD |
| 13 | NPC 12 WILL YOU HELP | offers 2: 13.CAT, 13.CORNELIUS; withdraws 1: 12.FROM YENDOR |
| 14 | NPC 13 CORNELIUS | offers 1: 12.PENNY |
| 15 | NPC 12 PLAN | offers 1: 16.RINGS |
| 16 | NPC 12 HELLO-2 | NPC 12 greeting 3 |
| 17 | NPC 14 MONSTERS | offers 1: 15.GALEN |
| 18 | NPC 15 HELLO | NPC 15 greeting 2 |
| 19 | password NOBLEMAN | door to destination 7 |
| 20 | killing PURPLE SLIME (spawn 145) | offers 1: 15.PAYMENT; withdraws 1: 15.GALEN |
| 21 | NPC 15 THANK YOU | offers 1: 14.COMBAT LESSON; withdraws 2: 14.MONSTERS, 15.PAYMENT |
| 22 | NPC 16 HELLO | NPC 16 greeting 2 |
| 23 | NPC 16 COPPER BAR | offers 1: 24.COPPER BAR |
| 24 | NPC 14 service | withdraws 2: 14.COMBAT LESSON, 14.RIGHT NOW; NPC 14 service spent |
| 25 | NPC 17 HELLO | NPC 17 greeting 2 |
| 26 | NPC 18 HELLO | NPC 18 greeting 2 |
| 27 | NPC 18 BUILD NOW | offers 1: 18.ADDITIONS; withdraws 1: 18.KEEP; the keep portal on Yendor |
| 28 | NPC 19 HELLO | NPC 19 greeting 2 |
| 29 | NPC 19 PAY 500 | offers 1: 19.RAISE SKILL; withdraws 2: 19.ENHANCEMENT, 19.PAY 500 |
| 30 | NPC 19 service | withdraws 3: 19.ENHANCEMENT, 19.PAY 500, 19.RAISE SKILL; NPC 19 service spent |
| 31 | NPC 19 GIVE SCROLL | offers 1: 19.OPEN CHEST; withdraws 1: 19.INVENTORY |
| 32 | NPC 18 BUILD NOW; cleared on leaving a conversation | the map rebuild |
| 33 | password GAUNTLET | NPC 18 silent; door to destination 10 |
| 34 | killing MILLIPEDE (spawn 203) | offers 1: 18.ADD FARM; withdraws 1: 18.ADDITIONS |
| 35 | NPC 18 YES, NOW | offers 1: 18.PASSWORD; withdraws 1: 18.ADD FARM |
| 36 | NPC 20 HIRE NOW | offers 2: 20.BUY FOOD, 20.GAME MENU; withdraws 1: 20.SHOPS; NPC 21 greeting 2; NPC 22 greeting 2 |
| 37 | NPC 21 PAY NOW | offers 4: 21.SELL, 21.BUY SUPPLIES, 21.INVENTORY, 23.MINE SHOP; withdraws 1: 21.SERVICES |
| 38 | NPC 19 CLOSE | withdraws 1: 19.OPEN CHEST |
| 39 | NPC 22 HIRE JEWELER | offers 1: 22.SELL JEWELS; withdraws 1: 22.JEWELER; NPC 23 greeting 2 |
| 40 | NPC 23 PAY 2,000 | offers 1: 23.SELL ORE; withdraws 1: 23.MINE SHOP; NPC 25 greeting 3; NPC 26 greeting 2 |
| 41 | killing GNOLL (spawn 241) | offers 1: 24.KILLED GNOLLS; withdraws 1: 24.COPPER BAR |
| 42 | NPC 24 HELLO | NPC 24 greeting 2 |
| 43 | NPC 24 CLOSE BAG | offers 1: 16.GIVE BAR; withdraws 3: 16.RINGS, 16.COPPER BAR, 24.KILLED GNOLLS |
| 44 | NPC 16 GIVE BAR | offers 1: 16.WORK; withdraws 1: 16.GIVE BAR |
| 45 | NPC 16 FINISHED | offers 1: 12.GOT RINGS; withdraws 1: 16.WORK |
| 46 | NPC 12 SHOW RING | offers 1: 12.GIVE IT BACK; NPC 12 silent; the way into the Prison |
| 47 | NPC 25 HIRE NOW | offers 5: 20.UPGRADE, 25.SELL ITEMS, 25.BUY NUORE, 25.BUY POTIONS ...; withdraws 1: 25.SERVICES; NPC 35 greeting 2 |
| 48 | NPC 27 HELLO | NPC 27 greeting 2 |
| 49 | NPC 27 GIVE ROBES | offers 2: 1.YENDOR FREED, 27.EXPERIENCE; withdraws 4: 1.NAME, 1.PORTALS, 27.RESCUE, 27.GIVE ROBES |
| 50 | NPC 27 service | withdraws 1: 27.EXPERIENCE; NPC 27 service spent; NPC 27 silent |
| 51 | NPC 26 PAY 2,500 | offers 3: 26.REPAIR, 26.BUY EAGLE, 26.SELL; withdraws 1: 26.START WORK; NPC 31 greeting 2; NPC 32 greeting 2 |
| 52 | killing SCORPION (spawn 310) | offers 1: 1.SCEPTER; withdraws 1: 1.YENDOR FREED |
| 53 | NPC 36 service | NPC 36 service spent; NPC 36 silent |
| 54 | NPC 37 service | NPC 37 service spent; NPC 37 silent |
| 55 | NPC 38 service | NPC 38 service spent; NPC 38 silent |
| 56 | killing BEHOLDER (spawn 314) | offers 1: 19.PASSWORD |
| 57 | NPC 19 PAY $2,000; password COMPASSION | withdraws 1: 19.PASSWORD; door to destination 25 |
| 58 | nothing | nothing |
| 59 | killing KING BARIAG (spawn 362) | offers 6: 1.BARIAG'S DEAD, 13.KING BARIAG, 14.KING BARIAG, 15.KING BARIAG ...; withdraws 13: 1.SCEPTER, 13.JOB, 13.BARIAG, 13.CORNELIUS ... |
| 60 | NPC 1 OKAY | withdraws 1: 1.KEY; NPC 1 silent |
| 61 | NPC 39 HELLO | NPC 39 greeting 2 |
| 62 | NPC 20 PAY 1,000 | offers 2: 20.SPECIAL FOOD, 21.EXPAND; withdraws 1: 20.UPGRADE |
| 63 | NPC 31 PAY 3,000 | offers 3: 31.SELL ITEMS, 31.BUY ARMOR, 31.FINISHED; withdraws 1: 31.PAY 3,000; NPC 31 greeting 3 |
| 64 | NPC 32 OPEN WEAPONRY | offers 2: 32.SELL ITEMS, 32.PURCHASE; withdraws 1: 32.OPEN WEAPONRY; NPC 32 greeting 3 |
| 65 | NPC 35 HIRE NOW | offers 1: 25.UPGRADE; withdraws 1: 35.HIRE NOW; NPC 35 greeting 3 |
| 66 | NPC 40 HELLO | NPC 40 greeting 2 |
| 67 | password PATRIARCH | withdraws 1: 40.PASSWORD; door to destination 28 |
| 68 | killing PIXIE LEADER (spawn 444) | offers 1: 46.REWARD |
| 69 | NPC 45 service | NPC 45 service spent; NPC 45 silent |
| 70 | NPC 46 HELLO | NPC 46 greeting 2 |
| 71 | NPC 46 CLOSE CHEST | withdraws 2: 46.APPROVAL, 46.REWARD |
| 72 | NPC 47 HELLO | NPC 47 greeting 2 |
| 73 | NPC 48 HELLO | NPC 48 greeting 2 |
| 74 | NPC 48 PAY 2,000 | withdraws 1: 48.MEMBERSHIP; NPC 50 greeting 2 |
| 75 | NPC 49 READ BOOK | NPC 49 greeting 2 |
| 76 | NPC 50 PAY 1,500 | offers 1: 50.RAISE SKILL; withdraws 1: 50.ENHANCEMENT |
| 77 | NPC 50 service | withdraws 1: 50.RAISE SKILL; NPC 50 service spent |
| 78 | NPC 50 GIVE WAND | offers 1: 50.REWARD; withdraws 1: 50.QUEST |
| 79 | NPC 50 FINISHED | withdraws 1: 50.REWARD |
| 80 | killing ACOKNIGHT (spawn 487) | offers 3: 21.EXPAND, 25.UPGRADE, 40.ACOKNIGHT; withdraws 2: 40.NAME, 40.ADRIAN |
| 81 | NPC 49 GIVE BOOK | offers 1: 49.DRAGONS |
| 82 | NPC 51 FINISHED | offers 1: 49.DRAGONS; withdraws 1: 51.TAKE EMERALD; NPC 51 silent |
| 83 | NPC 25 PAY NOW | offers 1: 25.BUY SCROLLS; withdraws 1: 25.SCROLLS |
| 84 | NPC 21 EXPAND | offers 1: 21.NEW ITEMS; withdraws 1: 21.INVENTORY |
| 85 | NPC 55 GIVE STAFF | offers 2: 49.SCROLL, 55.BUY SCROLL; withdraws 3: 49.DWARVES, 54.ORIGIN, 55.BUSINESS; NPC 56 greeting 2 |
| 86 | NPC 54 HELLO | NPC 54 greeting 2 |
| 87 | NPC 57 PAY; password PARCHMENT | withdraws 1: 57.PRICE; NPC 57 silent; door to destination 36 |
| 88 | NPC 60 PAY | withdraws 1: 60.PRICE; NPC 60 silent; door to destination 42 |
| 89 | NPC 58 service | NPC 58 service spent; NPC 58 silent |
| 90 | NPC 59 service | NPC 59 service spent; NPC 59 silent |
| 91 | NPC 49 LYDIA | offers 1: 40.CASTLE; withdraws 1: 40.ACOKNIGHT; NPC 49 silent |
| 92 | password RUSE | door to destination 46 |
| 93 | NPC 61 PAY 4,000 | NPC 61 silent; NPC 62 greeting 2 |
| 94 | NPC 62 PAY 4,000 | NPC 62 silent; NPC 63 greeting 2 |
| 95 | NPC 63 PAY 4,000 | NPC 63 silent; NPC 64 greeting 2 |
| 96 | NPC 64 PAY 4,000 | NPC 64 silent; NPC 65 greeting 2 |
| 97 | NPC 65 PAY 4,000 | NPC 65 silent; NPC 66 greeting 2 |
| 98 | NPC 66 PAY 4,000 | NPC 66 silent; door to destination 48 |
| 99 | killing QUEEN OBVERSIA (spawn 806) | offers 5: 39.QUEEN'S DEAD, 40.THANK YOU, 46.OBVERSIA, 47.OBVERSIA ...; withdraws 15: 39.NAME, 39.WHAT NOW?, 40.NAME, 40.ADRIAN ...; NPC 67 silent |
| 100 | NPC 68 GIVE GOLD | NPC 68 silent; door to destination 50 |
| 101 | NPC 39 CLOSE POUCH | offers 1: 69.MISSION; withdraws 2: 39.QUEEN'S DEAD, 39.KEY |
| 102 | NPC 69 HELLO | NPC 69 greeting 2 |
| 103 | killing ALLIGATOR (spawn 849) | offers 1: 70.PASSWORD; withdraws 1: 70.KINGDOM; NPC 72 greeting 2 |
| 104 | NPC 70 HELLO | NPC 70 greeting 2 |
| 105 | NPC 71 HELLO | NPC 71 greeting 2 |
| 106 | NPC 71 PARCHMENT | offers 1: 71.BUY SCROLLS; withdraws 2: 71.ASSIST, 71.PARCHMENT |
| 107 | password GEMSTONE | withdraws 1: 70.PASSWORD; door to destination 56 |
| 108 | killing FUNGUS (spawn 900) | offers 1: 70.ORCHARD; withdraws 3: 70.NAME & JOB, 70.FUNGUS, 71.NAME |
| 109 | NPC 70 CASTLE | offers 1: 74.PASSWORD |
| 110 | NPC 74 HELLO | NPC 74 greeting 2 |
| 111 | NPC 75 HELLO | NPC 75 greeting 2 |
| 112 | password CALANTHA | withdraws 1: 74.PASSWORD; door to destination 60 |
| 113 | password ALLIANCE | door to destination 62 |
| 114 | killing KNIGHT (spawn 992) | offers 1: 69.CASTLE SECURE; withdraws 2: 69.MISSION, 70.ORCHARD |
| 115 | NPC 69 KING YENDOR | offers 1: 70.HIDING |
| 116 | NPC 70 HOLY ORDER | offers 1: 71.HOLY ORDER |
| 117 | NPC 71 ITEM | offers 1: 74.PORTAL ITEM |
| 118 | NPC 74 PORTAL ITEM | offers 1: 75.KEY |
| 119 | NPC 75 KEY | offers 1: 22.MAKE KEY |
| 120 | NPC 22 MAKE KEY | offers 1: 22.BUY KEY/GEMS; withdraws 5: 22.MAKE KEY, 70.HIDING, 71.HOLY ORDER, 74.PORTAL ITEM ... |
| 121 | the JEWELED PORTAL KEY | door to destination 58 |
| 122 | NPC 81 service | NPC 81 service spent; NPC 81 silent |
| 123 | NPC 82 service | NPC 82 service spent; NPC 82 silent |
| 124 | NPC 83 PHYSICAL | withdraws 1: 83.PHYSICAL; door to destination 65 |
| 125 | NPC 83 MENTAL | withdraws 1: 83.MENTAL; door to destination 66 |
| 126 | NPC 84 HELLO | offers 1: 83.COMPLETED; NPC 85 silent; door to destination 67 |
| 127 | NPC 85 HELLO | offers 2: 83.COMPLETED, 96.REWARD; NPC 84 silent; door to destination 68 |
| 128 | NPC 86 QUESTION | withdraws 1: 86.QUESTION; NPC 86 silent; door to destination 69 |
| 129 | NPC 87 QUESTION | withdraws 1: 87.QUESTION; NPC 87 silent; door to destination 70 |
| 130 | NPC 88 QUESTION | withdraws 1: 88.QUESTION; door to destination 71 |
| 131 | NPC 89 FIRST | offers 3: 83.COMPLETED, 83.COMPLETED, 89.SECOND; withdraws 1: 89.FIRST; door to destination 72 |
| 132 | NPC 89 SECOND | offers 1: 96.REWARD; withdraws 1: 89.SECOND; NPC 89 silent |
| 133 | NPC 83 COMPLETED; NPC 83 COMPLETED | withdraws 2: 83.COMPLETED, 83.COMPLETED; NPC 83 silent; door to destination 73 |
| 134 | NPC 90 GIVE $10,000; NPC 90 service | NPC 90 service spent; NPC 90 silent |
| 135 | NPC 91 GIVE $5,000; NPC 91 service | NPC 91 service spent; NPC 91 silent |
| 136 | NPC 92 GIVE $5,000; NPC 92 service | NPC 92 service spent; NPC 92 silent |
| 137 | NPC 93 GIVE $5,000; NPC 93 service | NPC 93 service spent; NPC 93 silent |
| 138 | NPC 95 BANISH | offers 3: 48.PLANE, 69.KING'S SOUL, 96.BANISHED; withdraws 1: 69.CASTLE SECURE |
| 139 | NPC 16 CLOSE | withdraws 1: 16.LENS |
| 140 | NPC 48 GIVE LENS | withdraws 1: 48.GIVE LENS |
| 141 | NPC 48 THANK YOU | withdraws 2: 48.PLANE, 48.ENHANCED LENS; NPC 95 silent |
| 142 | NPC 94 HELLO | NPC 46 silent; NPC 94 greeting 2 |
| 143 | NPC 96 HELLO | NPC 96 greeting 2 |
| 144 | NPC 26 ANVIL | offers 1: 32.NEW WEAPONS; withdraws 2: 26.ANVIL, 97.ANVIL |
| 145 | the ENHANCED LENS at (352,67) | the way into the Plane of Souls |
| 146 | NPC 96 SOUL | offers 3: 69.RECOVERY, 96.HELLO-2, 96.REVIVE; withdraws 4: 69.KING'S SOUL, 96.KING YENDOR, 96.BANISHED, 96.SOUL |
| 147 | NPC 96 CLOSE | withdraws 1: 96.REWARD |
| 148 | NPC 96 service | withdraws 1: 96.EXPERIENCE; NPC 96 service spent |
| 149 | NPC 1 HELLO; NPC 69 SOUND (clears); NPC 98 MESSAGE | NPC 98 silent |
| 150 | NPC 98 MESSAGE | offers 1: 69.THAINE; withdraws 1: 69.RECOVERY |
| 151 | NPC 69 DONE | withdraws 1: 69.PREZLIN; NPC 69 silent |
| 152 | NPC 99 HELLO | NPC 99 greeting 2 |
| 153 | NPC 99 MISSION | offers 1: 70.GEMSTONE |
| 154 | NPC 70 ELFIN CITY | offers 1: 71.ELFIN CITY |
| 155 | NPC 71 ELFIN CITY | offers 1: 97.ELFIN CITY |
| 156 | password TIMBER | door to destination 75 |
| 157 | entering the Plane of Souls | the weapons of Light |
| 158 | leaving it carrying a WEAK SOUL | withdraws 1: 32.NEW WEAPONS |
| 159 | NPC 100 HELLO | NPC 100 greeting 2 |
| 160 | NPC 100 PROVE | NPC 102 greeting 2 |
| 161 | NPC 101 HELLO | NPC 101 greeting 2 |
| 162 | killing ELF WATCHMAN (spawn 1,154) | offers 2: 100.SEWER, 102.WATCHMEN; withdraws 2: 100.MISSION, 102.SEWER |
| 163 | killing PURPLE DRAGON (spawn 1,181) | offers 2: 100.SILVER MINE, 102.STRONGHOLD; withdraws 3: 100.SEWER, 101.BROTHER, 102.WATCHMEN |
| 164 | NPC 96 HELLO; NPC 102 BUTTONS (clears) | NPC 105 silent; NPC 106 silent; NPC 107 silent; NPC 108 silent; NPC 109 silent; NPC 110 silent |
| 165 | NPC 105 PUSH BUTTON; NPC 107 PRESS BUTTON (clears); NPC 108 PRESS BUTTON (clears); NPC 109 PRESS BUTTON (clears); NPC 110 PRESS BUTTON (clears) | offers 1: 106.PUSH BUTTON; withdraws 1: 106.PRESS BUTTON |
| 166 | NPC 106 PUSH BUTTON; NPC 108 PRESS BUTTON (clears); NPC 109 PRESS BUTTON (clears); NPC 110 PRESS BUTTON (clears) | offers 1: 107.PUSH BUTTON; withdraws 1: 107.PRESS BUTTON |
| 167 | NPC 107 PUSH BUTTON; NPC 109 PRESS BUTTON (clears); NPC 110 PRESS BUTTON (clears) | offers 1: 108.PUSH BUTTON; withdraws 1: 108.PRESS BUTTON |
| 168 | NPC 108 PUSH BUTTON; NPC 110 PRESS BUTTON (clears) | offers 1: 109.PUSH BUTTON; withdraws 1: 109.PRESS BUTTON |
| 169 | NPC 109 PUSH BUTTON | offers 1: 110.PUSH BUTTON; withdraws 1: 110.PRESS BUTTON |
| 170 | NPC 110 PUSH BUTTON | withdraws 2: 100.SILVER MINE, 102.STRONGHOLD; door to destination 89 |
| 171 | NPC 111 SCALE | offers 1: 111.PORTAL; withdraws 1: 111.SCALE |
| 172 | NPC 111 PAY GOLD | NPC 111 silent; door to destination 92 |
| 173 | NPC 112 SCALE | offers 1: 112.PORTAL; withdraws 1: 112.SCALE |
| 174 | NPC 112 PAY GOLD | NPC 112 silent; door to destination 93 |
| 175 | NPC 113 SCALE | offers 1: 113.PORTAL; withdraws 1: 113.SCALE |
| 176 | NPC 113 PAY GOLD | NPC 113 silent; door to destination 94 |
| 177 | NPC 114 SCALE | offers 1: 114.PORTAL; withdraws 1: 114.SCALE |
| 178 | NPC 114 PAY GOLD | NPC 114 silent; door to destination 95 |
| 179 | NPC 115 SCALE | offers 1: 115.PORTAL; withdraws 1: 115.SCALE |
| 180 | NPC 115 PAY GOLD | offers 1: 115.ENHANCEMENT; withdraws 2: 115.PORTAL, 115.PAY GOLD; door to destination 96 |
| 181 | NPC 115 service | NPC 115 service spent; NPC 115 silent |
| 182 | NPC 103 SILVER | offers 1: 103.NEW ARMOR; withdraws 2: 103.ARMOR, 103.SILVER |
| 183 | killing VISHAN (spawn 1,243) | offers 3: 99.ELVES, 100.VISHAN'S DEAD, 102.VISHAN'S DEAD; withdraws 6: 22.BUY KEY/GEMS, 99.BYSETTE, 100.STRONGHOLD, 100.VISHAN ... |
| 184 | NPC 99 SHARD | offers 2: 99.HELLO-2, 99.WINZE; withdraws 1: 99.ELVES |
| 185 | NPC 99 DONE | withdraws 2: 99.HELLO-2, 99.WINZE; NPC 99 silent |
| 186 | NPC 116 HELLO; NPC 116 HELLO-2 | NPC 116 greeting 2; NPC 117 greeting 2 |
| 187 | NPC 116 GEMSTONE | withdraws 1: 116.GEMSTONE |
| 188 | NPC 117 PAY GOLD | withdraws 1: 117.PAY GOLD; NPC 117 silent; NPC 123 greeting 2; door to destination 40 |
| 189 | NPC 121 HELLO | NPC 121 greeting 2 |
| 190 | NPC 123 PAY GOLD | withdraws 1: 123.PAY GOLD; NPC 123 silent; door to destination 38 |
| 191 | NPC 124 GIVE GOLD | offers 1: 124.ENHANCEMENT |
| 192 | NPC 124 service | NPC 124 service spent; NPC 124 silent |
| 193 | NPC 125 GIVE GOLD | offers 1: 125.ENHANCEMENT |
| 194 | NPC 125 service | NPC 125 service spent; NPC 125 silent |
| 195 | NPC 126 PAY GOLD | NPC 126 silent; door to destination 98 |
| 196 | NPC 121 GIVE STAFF | offers 1: 121.END WAR; withdraws 4: 116.DWARVES, 121.INTERFERING, 121.UNDEAD SPELLS, 121.GIVE STAFF; NPC 33 greeting 2; NPC 120 greeting 2; NPC 122 greeting 2 |
| 197 | NPC 127 HELLO | NPC 127 greeting 2 |
| 198 | NPC 129 HELLO | NPC 129 greeting 2 |
| 199 | NPC 33 HIRE | offers 1: 22.JEWELED ITEMS; NPC 33 greeting 3 |
| 200 | NPC 22 PAY 4,500 | offers 1: 32.JEWELED ITEMS; withdraws 1: 22.JEWELED ITEMS |
| 201 | killing SPECTRE (spawn 1,422) | offers 1: 127.DUNGEON; withdraws 2: 127.JOIN, 131.ZOE |
| 202 | NPC 131 HELLO | NPC 131 greeting 2 |
| 203 | NPC 127 BROOKS | NPC 128 greeting 2 |
| 204 | NPC 128 service | withdraws 1: 128.REWARD; NPC 128 service spent |
| 205 | password SOLITAIRE | door to destination 108 |
| 206 | killing KING SLATOR (spawn 1,566) | offers 1: 116.GOT SWORD; withdraws 1: 116.WINZE; NPC 34 greeting 2; NPC 127 silent; NPC 128 silent; NPC 129 silent; NPC 131 silent |
| 207 | NPC 34 HIRE | NPC 34 greeting 3 |
| 208 | NPC 116 DONE | NPC 116 silent |
| 209 | NPC 132 HELLO | NPC 132 greeting 2 |
| 210 | NPC 132 GEMSTONE | withdraws 1: 132.GEMSTONE |
| 211 | killing TITAN LORD (spawn 1,750) | offers 2: 132.CROWN, 133.TOUCH CROWN; withdraws 3: 132.FINAL ITEM, 132.TITANS, 132.EURON |
| 212 | NPC 133 TOUCH CROWN | nothing |
| 213 | NPC 133 REPAY | offers 1: 134.NEW ITEMS; withdraws 1: 133.TOUCH CROWN; NPC 133 silent |
| 214 | NPC 132 DONE | withdraws 1: 132.GET KEY; NPC 132 silent |
| 215 | password DELIA | door to destination 133 |
| 216 | NPC 137 ITEMS | NPC 138 greeting 2 |
| 217 | NPC 137 GEMSTONE | withdraws 1: 137.GEMSTONE |
| 218 | password DRAGONSKIN | offers 1: 138.NO BOOTS; withdraws 1: 138.BOOTS; door to destination 134 |
| 219 | NPC 138 QUESTION | offers 1: 138.GET BOOTS; withdraws 1: 138.QUESTION |
| 220 | NPC 138 FINISHED | offers 1: 137.GOT BOOTS; withdraws 2: 137.MANY THINGS, 138.GET BOOTS |
| 221 | NPC 137 OKAY | withdraws 1: 137.ZAMORA; NPC 137 silent |
| 222 | NPC 139 DONE | withdraws 1: 139.ORB |
| 223 | killing BLAZIOS (spawn 1,861) | the ORB OF ZAMORA |
| 224 | NPC 140 TELEPORT (clears); NPC 140 service; killing PALTIVAR (spawn 1,862) | withdraws 1: 140.REWARD; NPC 140 service spent; the ending |

## What is open

- **Flag 58.** No table and no instruction names it. Flags 57 and 59 are both in use, so 58 is a gap inside a run rather than the end of one.
- **Flag 6 and flag 212.** Both are written and never read. Killing the WASP QUEEN sets flag 6, and that monster stands on Thaine Map 10 beside the CENTIPEDE whose death sets flag 1. NPC 133's TOUCH CROWN sets flag 212, and that NPC's own REPAY sets flag 213 one topic later.
- **The kill table's second flag number**, at `+0x04` of each record. The lookup copies it into the monster's slot at `+0x16`, and the death routine writes it the same way as the first. It is zero on all 23 records, so nothing in the game has ever exercised it.
- **How the ending gets its speech across with sound off.** Image `0x05501` waits 13 ticks per line there, which is 0.7 seconds against the 1.8 to 3.8 the lines actually run. Nothing puts the caption of an ending line on screen the way the intro's talking-head blocks do, so a player with no sound card gets the pages and not the words.
