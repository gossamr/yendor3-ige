# Combat

A fight is resolved one turn list at a time, and every swing is resolved by a single attack resolver in `REGISTER.EXE`. [tools/levels.py](../tools/levels.py) mirrors the formulas, and [tools/combat_model.py](../tools/combat_model.py) builds on them. [tests/test_levels.py](../tests/test_levels.py) and [tests/test_combat_model.py](../tests/test_combat_model.py) check them.

Everything here is **code**, read off the disassembly rather than off the running game. One claim below is **measured** as well, and says so. [README.md](README.md) defines the classifiers. Coordinates are image offsets, which is the file offset minus `0x4000`, and `DS:` offsets are what the code uses directly, DGROUP being at image `0x1ddb0`.

## Where it lives

| What | Where |
|---|---|
| Round driver | `0x00a20` |
| Turn-list builder | `0x0115b` |
| End-of-turn housekeeping | `0x01285` |
| Player's turn | `0x00b10` |
| Melee swing | `0x00e62` |
| Creature's turn | `0x00f9e` |
| Creature's attack | `0x01318` |
| Attack resolver | `0x1586f` |
| Percent helper | `0x15862` |
| Random helper | `0x174ac` |
| Opposed save | `0x17882` |
| Effect applier | `0x035ab` |
| Damage to a character | `0x03737` |
| Equipment assembly | `0x0649e` |
| Attack/shoot routine | `0x0c13e` |
| Volley shot | `0x0c75e` |
| Spell on one creature | `0x1d93d` |
| Condition drain | `0x0af19` |
| Creature condition tick | `0x12863` |
| Kill rewards | `0x1270c` |
| Attack table | `DS:0x96da`, 12 bytes per entry |
| Turn list | `DS:0x5696`, 8 bytes per entry |
| Engaged creatures | `DS:0x54b8`, `0x5554`, `0x55f0`, stride `0x9c` |
| Attack readouts | `DS:0x0f4a`, 4 x `0x14` bytes |

## Entering a fight

A creature that closes to melee is copied out of the map's spawn list into one of **three** engaged buffers (`0x12b5c`–`0x12ca4`) and its spawn slot is zeroed. Each buffer is a `0x32`-byte header followed by the creature's 106-byte record, so a record offset *r* is read as `[buffer + r + 0x32]`. Setting the first one also sets `[0x5370]` bit `0x1000`, the hand-to-hand state.

`[0x54b6]` is whichever of the three engaged creatures is selected, set from the click dispatcher at `0x00dea` and refilled by `0x14bd` when the selection dies.

The eighty spawn slots at `DS:0x122c` have the same shape, and the header carries what the creature is doing now:

| Offset | Field |
|---|---|
| 0 | the object's number, and **zero means the slot or buffer is free** |
| `0x0c` | state: bit 0 is set once it has noticed the party, and `& 0x3010` leaves it out of the turn list |
| `0x10` | health now |
| `0x12` | the character it is attacking |
| `0x32` | the 106-byte record, [monsters.md](monsters.md) |

Word 0 is the occupancy test that every walk over either table makes, at `0x0c56f`, `0x10055`, `0x125e9` and `0x128cd` over the spawn slots, and at `0x01293` over the buffers. `0x12600` writes it when a new object claims a free slot. `0x0c57a` and `0x01298` are the two that then read `0x10` and pay out for anything at or below zero. The record's own health at `0x32 + 30` stays at what the creature started with, so the pair holds health now over health at full.

**The party is four slots and no geometry.** `DS:0xd0c9` is a table of four record handles and every loop over the party walks it. The creature's target picker rolls uniformly over the four handles with nothing weighting the choice, so **the game has no front or back rank**. There is also nowhere to put one, because the party occupies a single map position. Whether an attack is hand to hand or ranged is decided by that one position against the creature's position, projected along the facing word at `DS:0xcf73` (`0x1252d`).

**Group size is bits 15, 14 and 13 of record word 96.** Only three of the eight combinations appear:

| Bits 15,14,13 | Creatures | Most that can engage |
|---|---|---|
| `000` | 5 (MIMIC, both TOWERs, ALLIGATOR, CROCODILE) | 1 |
| `110` | 20 | 2 |
| `101` | 46 | 3 |

The group is assembled one creature at a time as each arrives, not drawn from an encounter table. The first creature ORs its `w96 & 0xE000` into the combat flags at `[0x5370]`. A newcomer needs bit 15 to join at all, and with two creatures already engaged, `0x12c0c` re-reads bit 14 from both occupants and makes room for a third only if neither of them carries it.

## The round

`0x0115b` rebuilds the turn list at `DS:0x5696` at the start of **every** round: space for fourteen slots, of which seven can be filled. Each entry is eight bytes, holding the combatant, its party slot, its **dexterity**, and a flag word.

1. The four party handles are walked in slot order. A character whose condition word has any of `0x1c40` is left out entirely.
2. The three engaged buffers follow, flag bit `0x8000` marking a creature and the sort key taken from record 36, the creature's dexterity.
3. A creature that is not impaired (`[buffer+0xc] & 0x3010`) draws its target **here**, not at swing time: `rand(3)` over the four party handles, rerolled while the slot is empty or incapacitated, stored at `[buffer+0x12]`.
4. A bubble sort over adjacent entries swaps only on a strictly greater dexterity, so the order is descending and stable. Party entries were inserted first, so **a dexterity tie is resolved in favor of the party**.

The sort being stable has two consequences. **Creatures of one type act as a block**, because they are copies of one record, so they share a dexterity, keep their buffer order and cannot be separated. A party that outruns them therefore takes their whole round at once, with no chance to kill between two of their swings.

**A group need not be one type.** The join test at `0x12b9c` reads the newcomer's group bits and the occupants' bit 14, and nothing else. No sprite, family or record id is compared. Two species that both carry the bits can therefore share an engagement, and the block described above then splits.

The driver at `0x00a20` then walks the list. A creature entry runs `0x00f9e`, and a party entry runs `0x00b10`, which waits for input. After each turn `0x01285` checks all three buffers, marks any creature at or below zero health dead (turn-list flag `0x4000`, so it is skipped for the rest of the round) and collects its rewards. When the list runs out the driver jumps back to the builder and the next round starts.

So an ordinary round holds at most **three creature attacks**, or twelve against three PARTY ATTACK creatures.

## The attack resolver

One routine at `0x1586f` settles every attack in the game. It takes `bx` = accuracy, `ax` = the target's absorption, `cx` = damage, and leaves the damage dealt in `[0x0f36]`.

    1586f  push dx
    15870  mov  word [0xf36], 0
    15876  cmp  cx, 0 / je done          ; zero damage resolves to nothing
    1587b  sub  bx, ax                   ; margin = accuracy - absorption
    1587d  jl   done                     ; a negative margin can never hit
    1587f  mov  ax, 0x37
    15882  lcall 0x174ac                 ; rand(55)
    15887  cmp  bx, ax / jl done         ; miss when the margin is under the roll
    1588b  mov  ax, cx / mul bx
    1588f  add  ax, 0x32 / div 100       ; pct(damage, margin)
    15897  mov  [0xf36], ax
    1589a  cmp  ax, 0 / ja done
    1589f  mov  word [0xf36], 1          ; a landed hit always does at least 1

**`margin = accuracy − absorption` does two jobs.** It decides whether the attack lands, and it is the percentage of the damage stat that is delivered. A margin over 100 delivers more than the damage stat, because there is no cap and no second roll.

The five call sites are all of them. No path resolves an attack back at the attacker, so **there is no counter attack**.

## The roll is not flat

`rand(n)` at `0x174ac` runs a 16-bit LCG, masks the result down to the bit width of `n`, and subtracts `n` once if it still overshoots. So the raw draw is `0..2**k-1` for the smallest power of two above `n`, and the values `1..2**k-1-n` are reached **twice** while 0 and everything above are reached once. It is flat only when `n` is one less than a power of two.

`rand(55)` therefore draws 0..63 and folds 56..63 onto 1..8:

    P(hit) = (margin + 1 + min(8, margin)) / 64

| Margin | 0 | 1 | 4 | 8 | 9 | 13 | 20 | 30 | 40 | 55 |
|---|---|---|---|---|---|---|---|---|---|---|
| Hit | 1.6% | 4.7% | 14% | 27% | 28% | 34% | 45% | 61% | 77% | 100% |

Two consequences. **Each of the first eight points of margin adds two outcomes, and the ninth adds one**, so the return on accuracy rises to margin 7, dips once at 8, and then rises again to 55. And a margin of 55 still ends the miss chance, as it would under a flat roll.

`rand(3)` (which party slot) and `rand(15)` (the creation roll) are flat. `rand(100)`, which every skill check and every percentage gate uses, is not: it draws 0..127 and folds 101..127 onto 1..27.

| Nominal chance | 5 | 25 | 50 | 75 | 90 | 100 |
|---|---|---|---|---|---|---|
| Actual | 8.6% | 40% | 61% | 80% | 92% | certain |

## The four attacks

All four call the same resolver, and differ only in which fields they hand it.

| Attack | Accuracy | Damage | Against | Call site |
|---|---|---|---|---|
| Melee swing | character `+0x4c` | character `+0x4e` | creature record 38 | `0x00e73` |
| Volley shot | character `+0x48` | character `+0x4a` | creature record 38 | `0x0c76b` |
| Spell | character `+0x62`, **casting** | spell record 46 | creature record 38 | `0x1d616` |
| Creature | creature record 34 | creature record 40 | character `+0x50` | `0x01353` |

Casting is a weapon skill: a damage spell rolls to hit against the creature's absorption and has its damage scaled by the same margin.

### Shoot and attack are one routine and two modes

Printable keys are dispatched through a jump table at `0x777`, indexed `(ascii − 0x20) × 2`:

| Key | Handler | | Key | Handler |
|---|---|---|---|---|
| `A` attack | `0x69e` | | `P` panels | `0x59e` |
| `S` shoot | `0x671` | | `R` rest | `0x632` |
| `C` cast | `0x68d` | | `T` hourglass | `0x60a` |
| `D` disk | `0x566` | | `K` keyring | `0x644` |
| `M` map | `0x5d2` | | `V` version | `0x769` |

`A` and `S` enter the same routine at `0x0c13e` under opposite guards:

    0671  test [0x5370], 0x1000 / jne  away   ; S: only out of hand-to-hand
          or   [0x536e], 0x100                ;    mark it a party volley
          lcall 0x0c13e
          and  [0x536e], ~0x100
    069e  test [0x5370], 0x1000 / je   away   ; A: only in hand-to-hand
          lcall 0x0c13e

`away` is the dispatcher's return to the input loop, so **a command that does not match the state has no effect**. A key that does not match is not a wasted turn, because it is not a turn at all. Two special projectiles carry the same guard in the item damage table (`0x0c8b0`, `0x0c8c6`) and do nothing in hand to hand combat.

- **Volley** (`0x0c186`): walk the four party slots, collect one shot per able character that has a projectile, count them in `[0xfd7]`, store the four results at `0x5380` and draw them at the four panel positions. The flight then steps out through six distance bands (`[0x53dc]` = `0x31, 0x2e, 0x2b, 0x28, 0x24, 0x19`), resolving each shooter in turn.
- **Hand-to-hand** (`0x0c593`): one attack, at band `0x31`, against `[0x54b6]`. No loop over the party and no reference to the `0x5380` table.

A small number of items resolve out of a fixed damage table at `0x0c809` rather than through the resolver. A matching item id deals a set amount and may inflict a condition of set strength and duration, which `rand(100)` then keeps 77% of the time.

## Where a character's numbers come from

`0x0649e` rebuilds the five combat words whenever equipment changes. Each is a seed plus what is worn:

| Word | Seed | Equipment |
|---|---|---|
| `+0x48` projectile accuracy | `+0x32` | projectile skill, if a missile weapon is held |
| `+0x4a` projectile damage | `+0x36` | the missile weapon's damage byte |
| `+0x4c` melee accuracy | `+0x34` | the skill the weapon's type flag names |
| `+0x4e` melee damage | `+0x38` | the hand weapon's damage byte |
| `+0x50` absorption | `+0x3a` | shield, two rings, five worn slots |

`+0x38` and `+0x3a` are a fifth of strength and of dexterity above 72 (`0x05c44`), so those are the two attribute bonuses that reach combat. A hand weapon carrying none of the three melee-type flags adds no accuracy at all, and a two-handed one sets `[+0x15c]` bit `0x20`, which is what bars a shield.

## What a creature does on its turn

Its first act is the condition tick at `0x12863`: a creature under a condition loses `[buffer+0x1c]` health, twice if it is also frozen or paralyzed, and `[buffer+0x1e]` counts down to the condition clearing.

Then `0x14e8` chooses the attack. **Record 58 is the creature's ordinary attack id and record 60 is its special attack id.** Both index the attack table at `DS:0x96da`. A creature that has a special attack uses it when `rand(100) < 25`, which the fold in the roll makes **38% of turns**. The rest of the time, and whenever the special attack is resisted, it uses the ordinary one.

An ordinary attack passes directly to the resolver. A special one first makes the opposed save at `0x17882`:

    chance = 5 x (character level - creature level) + resistance,  floored at 5
    the attack lands when rand(100) > chance

For a condition, the resistance is the sum of the character's protection words for the bits the attack carries. For a BREAK or a DESTROY it is **half the character's survival skill**. Level therefore adds five points to every one of these, and a save of 5 still fails 91% of the time.

### The attack table

Twelve bytes per entry at `DS:0x96da`:

| Offset | Field |
|---|---|
| `+0` | sound |
| `+2` | animation |
| `+4`, `+6` | minimum and maximum damage |
| `+8` | effect mask |
| `+0xa` | flags |

The effect mask names what lands. Nine condition bits share their layout with the character's own condition word, so the mask is OR'd straight into it:

| Bit | `0x8000` | `0x4000` | `0x2000` | `0x1000` | `0x0800` | `0x0400` | `0x0200` | `0x0100` | `0x0080` |
|---|---|---|---|---|---|---|---|---|---|
| | sick | poison | disease | paralyze | frozen | stoning | jinxing | hexing | cursing |

| Bit | `0x0020` | `0x0010` | `0x0008` | `0x0004` | `0x0002` | `0x0001` |
|---|---|---|---|---|---|---|
| | health and magic | health | magic | steal food | steal nuore | steal gold |

The flags at `+0xa` decide how the number is arrived at. `0x4000` takes `+4` flat, and `0x2000` takes `+4` multiplied by the **character's level**. With neither flag set, the entry rolls `+4..+6` and then multiplies by the character's level. `0x1000` marks the entry as needing the condition save. `0x0600` and `0x0180` route to two other handlers.

**A steal takes a fixed sum.** Record 92 is a 4-byte packed BCD amount, and only the three creatures carrying attack id 15 have one. THIEF takes 100, and ELF ASSASSIN and FROST DWARF TOWER take 1,000.

**BREAK and DESTROY name their target in record word 96.** `0x0144c` picks bit `0x0800` the missile weapon at `+0x13a`, bit `0x0400` the hand weapon at `+0x142`, and neither the shield at `+0x146`.

**PARTY ATTACK is bit `0x1000` of the same word.** It branches at `0x1008` and loops all four characters inside the creature's one turn.

Record 42 is the sound played on a hit, and record 44 is the sound played on a miss. With sound turned off the game delays instead, so the pacing is the same either way.

## Conditions

The character's condition word is `+0x1c`. It carries the nine attack bits above, plus `0x40`, which is set when health reaches zero. Four of those bits form the mask `0x1c40`, which is stoning, frozen, paralyze and dead. That one mask has three effects. It stops training, it stops the character taking a turn, and it stops the character being targeted. The other five bits leave a character acting and targetable, and drain the character instead.

| Condition | Bit | Drain | Protection word | Cure weight |
|---|---|---|---|---|
| disease | `0x2000` | 12 health | `+0x20` | 20 |
| poison | `0x4000` | 6 health | `+0x22` | 10 |
| sick | `0x8000` | 3 health | `+0x24` | 5 |
| stoning | `0x0400` | | `+0x26` | 60 |
| frozen | `0x0800` | | `+0x28` | 50 |
| paralyze | `0x1000` | | `+0x2a` | 40 |
| cursing | `0x0080` | 16 magic | `+0x2c` | 40 |
| hexing | `0x0100` | 8 magic | `+0x2e` | 30 |
| jinxing | `0x0200` | 4 magic | `+0x30` | 20 |

The protection words sit in offset order in the character record, which is also the order the F5 PROTECTIONS panel prints them in. They are what `0x03875` sums for the save. The cure weights are what an NPC charges to lift each condition, summed over the bits that are set (`0x092b1`).

**The drain fires once per battle.** `0x00a0f` presets the counter at `[0xcf3b]` to its limit immediately before the round driver, so the pass at `0x0af5c` runs on entering combat: health first over all four characters, then magic, both through the ordinary effect applier. The counter is reset when the fight ends.

## Spells

Casting charges the caster's current magic points by the spell's record 24 and the party's nuore by record 26 (`0x0d336`).

`0x1d93d` applies one spell to one creature:

1. If the spell is family-restricted (record 76 bit `0x0100`) and the creature's family at record 28 does not match, nothing happens.
2. The damage resolves through the attack resolver, with casting against absorption, unless `[0x5370]` bit `0x80` is set. When that bit is set, the record's damage lands in full with no roll.
3. **Immunity sets the damage to zero.** Record 74 is the spell's element and record 100 is the creature's immunity word. They share a bit layout, and a match sets the damage to zero (`0x1d6f0`).
4. **Resistance halves it.** Record 76 masked with `0xFE00` is the spell's damage type. It is matched against the creature's resistance word at record 102, and a match shifts the damage right once (`0x1d72f`, and `0x1d8af` is the same test written as a loop). That mask only ever holds 0, `0x200` or `0x2000`, so of a creature's three resistance bits only `0x2000` is ever answered by a spell. This one is **measured**: [tools/fight_probe.js](../tools/fight_probe.js) sets a creature's resistance word before boot and reads its health between blows, and [monsters.md](monsters.md) has the readings.
5. Each condition bit the spell carries is tested against the same immunity word and OR'd into the creature's flags if the creature is not immune (`0x1d649`). The condition then deals record 52's damage per turn for record 66 turns.

Healing does not go through any of this: a heal spell carries damage 0, which the resolver refuses at its first test, and restores a fixed amount instead.

## Damage, death and rewards

Damage to a character subtracts from current health at `0x03737`, clamps at zero, and sets the dead bit. Damage to a creature subtracts from `[buffer+0x10]` and is noticed at the end of the turn.

A creature that dies pays into four packed BCD accumulators that run for the whole battle (`0x1270c`). They are gold at record 76, nuore at 80, food at 84 and experience at 88, each four bytes. The creature's buffer is then zeroed.

When the fight ends the accumulators are handed out (`0x12de6`). The loop walks the four party handles and adds **the whole experience total to each able character**: it is not divided. A character who is dead, stoned, frozen or paralyzed at that moment is skipped and receives nothing.

## Ranged attacks on the map

A creature that has not closed can shoot in its own phase, `0x1230a` walking all 80 spawn slots. Record 98 is the frequency, read as five tiers (`0x129ed`):

| Bit | `0x1000` | `0x0800` | `0x0400` | `0x0200` | none |
|---|---|---|---|---|---|
| Nominal | 90 | 75 | 50 | 25 | 5 |
| Per round | 92% | 80% | 61% | 40% | 8.6% |

Exactly the 13 creatures with a ranged attack carry a non-zero value, three at 90 and ten at 25. The three at 90 are the three that cannot move, which are FUNGUS and the two dwarf towers.

### What the shot is made of

`0x12579` fills a 24-byte projectile record, one of four at `DS:0xA5A6`, from the creature's own. Every field it takes is one of the record's:

| Projectile | Creature | What |
|---|---|---|
| `+0x04` | record 46 | the picture, in `PICTURES.VGA` run 1 |
| `+0x14` | record 48 | the sound, played when the shot lands (`0x123b8`) |
| `+0x12` | record 62 | an id into the attack table at `DS:0x96da` |
| `+0x0c` | `&`record 70 | a six-byte recolor list, in the creature's own form |
| `+0x0e` | | 6, the length of that list |
| `+0x10` | word 96 bit 1 | whether the list applies |

Seven pictures serve the thirteen shooters: arrows (three creatures), spores, throwing stars, lightning, fire, a white bolt and a comet. Each picture holds the shot at the four angles it can travel at, and the draw at `0x123df` sets run 1 before blitting it.

Record 62 is 2 for all thirteen, which is the table's entry with no condition attached, so a shot does its damage and nothing else. Only CREEPING FUNGUS carries a recolor list, of one pair, which is what makes its spores a different color from the FUNGUS that it otherwise copies. Eleven other creatures carry the bit that would apply a list, and carry no list to apply.
