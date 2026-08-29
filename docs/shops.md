# NPCs, conversation and shops

Decoded NPC records, conversation topics and prose. Settled findings only.

## Three tables, two of them split across section boundaries

The section directory lists these as five sections. They are three tables:

| Table | Base | Record | Count | Directory sections |
|---|---|---|---|---|
| NPCs | `0x3D8EB9` | 40 B | **141** | 21 |
| Conversation topics | `0x3DA4C1` | 60 B | **1,073** | 22 + 23 |
| Prose lines | `0x3EA03D` | 34 B | **4,090** | 24 + 25 + 26 |

The counts are exact: 47,400 + 16,980 = 64,380 = 1,073 × 60, and 51,034 + 51,000 + 37,026 = 139,060 = 4,090 × 34.

Indices are 1-based, the same convention the item loader uses. `0x08f7e` addresses a topic as `(index − 1) × 60`.

## The NPC record, 141 records of 40 bytes

| Offset | Field |
|---|---|
| `+4` | how many conversation topics this NPC has |
| `+6` | how many prose lines |
| `+8` | index of its first topic |
| `+10` | index of its first prose line |
| `+0x12` | service bit index |
| `+0x14`, `+0x16` | service parameters, read differently per service |
| `+0x18` | price factor |

`+8` and `+10` are running totals of `+4` and `+6`: `+8[i+1] = +8[i] + +4[i]` and `+10[i+1] = +10[i] + +6[i]` hold on 139 of the 140 consecutive pairs.

The record in play sits at `DS:0x0ec8`.

**`+0x12` is a bit *index*, not a mask.** `0x08d45` passes the word to the tester at `0x17ac4`, which resolves it to a word and a mask before testing, so an NPC's services are gated on game state rather than on a fixed flag.

**`+0x14` and `+0x16` hold different values for different services.** For an NPC that raises an attribute they hold the attribute's offset in the character record and a threshold. `0x08dd0` loads them into `[0x53ee]` and `[0x53f0]`, walks the four party handles at `DS:0xd0c9`, adds the offset to each character and compares. For a trainer, `+0x16` is the level cap that the trainer quotes. The five NPCs with a TRAIN topic carry 10, 20, 25, 30 and 40 there, against `+0x18` of 5 or 10.

`[0x53ee]`/`[0x53f0]` is a general scratch pair used elsewhere for an item-index range and for a price accumulator. It is not one thing.

## The topic record, 1,073 records of 60 bytes

13 bytes of keyword, then:

| Offset | Field |
|---|---|
| `+14` | action word |
| `+16` | a gold amount |
| `+18` | depends on the mode, see below |
| `+20` | byte offset into this NPC's prose block |
| `+22` | how many prose lines the response runs to |

The action word at `+14` names the service. `0x8000` is buy, `0x4000` is sell, `0x0100` is enhance, `0x0040` is repair, `0x0080` is buy a commodity, `0x2000` is take gold, and `0x0200` is raise an attribute. A topic carries the bit for its service together with flags. BUY ARMOR reads `0x8020`, of which `0x8000` is the buy. The five services that open a screen are set out under *The five services* below.

`+16` carries the sum a topic requests: the topic "PAY 3,000" holds 3000.

`+18` is read differently in each mode. The bit dispatch at `0x02ac9` treats it as a handler selector, sending `0x8000`, `0x4000`, `0x3000`, `0x0800` and `0x0400` each to its own routine. The gold branch at `0x09338` instead compares it against 1, 2, 3 and
9999. It cannot be read as a single field.

The selected topic is copied to `DS:0x0e98`, so `[0x0ea6]` is its action word and `[0x0eac]` its prose offset.

## Resolving a response

    line = NPC's first prose line + (topic +20) / 34

The blocks tile exactly. For the armorer at NPC 31, `+20` runs 68, 238, 306, 408, 510 and 578 against line counts of 5, 2, 3, 3, 2 and 3, so each response ends where the next one begins.

Read this way NPC 31 speaks as an armorer ("I CANNOT OPEN UP MY ARMORY UNTIL", "THE ARMORER CROSSES THE ROOM AND"), NPC 5 as a food seller, NPC 7 as the wishing well (HELLO, GIVE 100 GOLD, ENHANCEMENT, GOODBYE) and NPC 1 as the wizard Flagell.

## A shop is a topic

Shops are conversation topics, not a kind of NPC: BUY ARMOR, BUY SCROLLS, BUY NUORE, BUY POTIONS, BUY FOOD, NEW WEAPONS, BUY SUPPLIES, SELL ITEMS, ENHANCE, REPAIR. `0x02b3e` compares a topic's first four bytes against `"BU"` and `"Y "` literally.

Of the 34 NPCs carrying a shop topic, all but two hold zero in `+0x12`, `+0x14`, `+0x16` and `+0x18`, so what a shop deals in is not in the NPC record.

**Commodities are named by item index.** A topic with action `0x0080` holds a 1-based item index at `+18`: BUY FOOD holds 2 for item 1, FOOD, and BUY NUORE holds 3 for item 2, NUORE. An item shop carries the buy bit instead, and lists from stock rather than naming one item.

## Every service a merchant offers

The action word at `+14` selects a handler. The dispatch runs from `0x02b26` to `0x02c8f`, and the topic counts are over all 1,073 topics:

| Action | Handler | Topics | What they are called |
|---|---|---|---|
| `0x8000` | `0x06082` | 27 | PURCHASE, BUY ARMOR, NEW WEAPONS, BUY SCROLLS, BUY ITEMS |
| `0x4000` | `0x063cf` | 17 | SELL ITEMS, SELL, SELL ORE, SELL JEWELS, SELL ARTIFACT |
| `0x2000` | `0x0931e` | 72 | PAY GOLD, PAY 4,000, GIVE $10,000, HIRE NOW, GEMSTONE |
| `0x1000` | `0x0a548` | 21 | REWARD, KEY, TAKE RINGS, OPEN CHEST, TAKE EMERALD |
| `0x0800` | `0x0a3b9` | 35 | HEAL, CURE, RESURRECT, RESTORATION, BUY PEGASUS/EAGLE/DRAGON |
| `0x0400` | `0x08e79` | 6 | EXPERIENCE, SENSATION |
| `0x0200` | `0x08d3e` | 18 | ENHANCEMENT, BLESSING, RAISE SKILL |
| `0x0100` | `0x06259` | 5 | ENHANCE, all five of them |
| `0x0080` | `0x060d3` | 15 | BUY FOOD, BUY NUORE, SCALE, QUESTION |
| `0x0040` | `0x0631e` | 3 | REPAIR, all three of them |
| `0x0008` | `0x09f4e` | 12 | SELL PEGASUS, SELL EAGLE, SELL RUG, SELL DRAGON |

The remaining bits are flags for the panel and the flow rather than services. `0x0020`, on 84 topics, opens a list beside a buy, sell or reward. `0x0010` and `0x0004` close a screen (DONE, FINISHED, CLOSE). `0x0002` accompanies a payment. `0x0001`, on 183 topics, greets or leaves (GOODBYE, BYE, HELLO, LEAVE).

**Four of them open a screen** that sets a mode bit in `[0x536c]`, which the item panel reads:

| Action | `[0x536c]` | Caption |
|---|---|---|
| `0x8000` buy | `0x20` | VALUE: |
| `0x4000` sell | `0x10` | VALUE: |
| `0x0100` enhance | `0x08` | COST: |
| `0x0040` repair | `0x04` | none |

`0x11172` shows VALUE: under mode `0x30`, which is buy and sell together, and shows COST: only under mode `0x08`.

**`0x0800` is a service that acts on one character.** `0x0a3b9` copies the topic's `+18` into `[0x0eaa]`, points `[0x53d4]` at the party table `DS:0xd0c9`, and dispatches on that word at `0x02ac9`. `0x8000` dispatches to `0x09825`, `0x4000` to `0x099b4`, `0x3000` to `0x09e1d`, `0x0800` to `0x0947e`, `0x0400` to `0x09732`, and anything else to `0x093d9`. Its topics are the temple's (HEAL, CURE, RESURRECT, RESTORATION) and the transport sellers'.

**`0x0200` raises a named attribute.** `0x08d3e` reads the NPC's `+0x14`, subtracts `0x3c`, halves it and multiplies by 13 to index a table at `DS:0x80f4` holding **STRENGTH, DEXTERITY, STAMINA, INTELLIGENCE, WISDOM, CHARISMA**. So `+0x14` is the attribute's offset in the character record and the NPC names it on screen.

## What an NPC will enhance

The screen behind ENHANCE gates on `0x062d1`, which admits an item when three conditions hold:

1. its category word is `0x0a00` (shield or worn) or `0xc000` (hand or missile),
2. its properties word at `+2` carries the series bit, which is `0x0800` for a weapon and `0x0100` for a piece of armor,
3. its current enchantment level falls between `[0x0ec8+0x14]` and `[0x0ec8+0x16]`, the NPC's own bounds.

The level is the properties word at `+8` for a weapon and `+6` for armor, and it runs 0 to 10 across a series: 2-HANDED SWORD +0 through +10 read 0 to 10 at `+8`, ROYAL PLATE ARMOR and GOLD SHIELD the same at `+6`.

**Rings cannot be enhanced.** The category test admits shields and worn pieces but not `0x0400` rings, and no ring carries a series bit or has a `+N` form.

**How far a piece of gear can be taken is a property of the NPC**, not of your gold. The 161 absorption ceiling in [items.md](items.md) assumes reaching one whose range extends to +10.

## Prices

`0x0a719` reads the item record's packed BCD base value as two words, at record `+4` and `+6`, into `[0xfac]` and `[0xfae]`, and passes the NPC's `+0x18` to the scaler at `0x0aa1d`. The value itself is three BCD bytes at record offset 5. KNIFE reads `00 00 45` for 45, and RING OF INVISIBILITY reads `00 30 00` for 3,000.

## Choosing who trades

`0x06447` picks the party member. It rejects a character whose condition word at `+0x1c` has any of `0x1c40` set, meaning dead, stoned, frozen or paralyzed, and it stores the choice in `[0x5442]`.
