# Leveling, training and bonus points

A character gains a level by paying a trainer, and the level-up then grows the base column of the character record by fixed formulas. Those formulas and the experience ladder behind them are in the code and data of `REGISTER.EXE`. [tools/levels.py](../tools/levels.py) reads the tables from the file and mirrors the formulas, and [tests/test_levels.py](../tests/test_levels.py) checks them.

Everything here is **code**, read off the disassembly rather than off the running game, except the bonus-point payout and its place in the order, which is **measured**. [README.md](README.md) defines the classifiers. Four independent corroborations are at the end.

## Where it lives

The startup stub at image `0x00012` does `mov ax, 0x1ddb / mov ds, ax`, so DGROUP begins at image `0x1ddb0` (file `0x21db0`). `DS:` offsets below are what the code uses directly.

| What | Where | Notes |
|---|---|---|
| Level-up routine | image `0x09a50` | reached only after the gold is paid |
| Trainer quote / refusal | image `0x09d75` | "TO TRAIN TO LEVEL n" |
| Bonus-point screen | image `0x0492a` | click handler at `0x049ee`/`0x04a1a` |
| "Ready for level" test | image `0x065ba` | rewrites the field every shop visit |
| Percent helper | image `0x15862` | `mul bx / add ax,50 / div 100` |
| Stat-add helper | image `0x05bd9` | caps, and refuses to touch a zero field |
| Experience ladder | `DS:0xc75f` | 89 × 4 bytes, packed BCD |
| Spells per level | `DS:0xb8b5` | 6 classes × 40 words |
| Promotion levels | image `0x0f0e2` | written as constants at init |

[tools/disasm.py](../tools/disasm.py) prints far call targets as `seg*16 + off` with the operands swapped. Capstone renders a far pointer as `segment, offset`, so capstone's own `-> image` annotations are incorrect. The scratch scripts `tmp/xref.py` and `tmp/disann.py` use the corrected form.

## The character record

500 bytes, four of them shipped as the `PRE-CREATED PARTY` section of `WORLD.DAT` (`0x41D72F`, 5,000 bytes = 10 slots, the last four filled with SQUIRE, DIANA, YENDOR and JOSEPHINE at level 1).

| Offset | Field |
|---|---|
| `0x00` | name, 14 bytes |
| `0x0E` | class, 1–9, **+10 per promotion tier** |
| `0x10` | gender |
| `0x12`, `0x14` | portrait selection |
| `0x16` | level |
| `0x18` | experience, 4 bytes packed BCD |
| `0x1C` | condition bits (`0x40` = dead) |
| `0x1E` | "ready for level", and 0 when not trainable |
| `0x38`–`0x77` | **current** stat column |
| `0x78`–`0xB7` | **base** stat column |
| `0xB4`+ | transport permissions |

### Two columns, not one

Each column is 64 bytes. It holds two derived words, then the same 27 fields that the label run at `0x29EA4` names, in that order: STRENGTH, DEXTERITY, STAMINA, INTELLIGENCE, WISDOM, CHARISMA, five combat fields, HEALTH, MAGIC POINTS, one unnamed field, the twelve skills, and one more unnamed field.

The five combat fields have blank captions in the label run. The equipment assembly at image `0x0649e` names them by what it writes into each one. Indices 6 and 7 take the projectile skill and the missile weapon's damage. Indices 8 and 9 take the melee skill matching the weapon's type flag, and that weapon's damage. Index 10 takes armor. The F1 panel prints 8, 9 and 10 against the captions ACCURACY, DAMAGE and ABSORPTION, which confirms the reading. Indices 9 and 10 are also seeded from `0x38` and `0x3a`, which hold a fifth of strength and dexterity above 72 (image `0x05c44`). Both are zero for every character at creation.

**Current** (`0x3C`, which is index 0) is the value the game plays with. Damage subtracts from current health (`sub [bx+0x52], ax`, image `0x03737`). The NPC "challenge" screen indexes statistics as `character + 0x3c + 2*n`. Carry capacity is `10 × current strength`. The character panel prints **only this column** (`0x04ce6` takes both and renders `ax`), and it recolors the number when the number has been pushed above its base.

Only two pieces of code ever write the base attribute and skill words: character creation and the level-up's `+2` loops. Every call site of the stat-add helper is in the level-up (four of them: health, magic, the six attributes, the twelve skills), and a displacement scan over the base columns turns up nothing else. So a character's natural value for any stat is exactly **its creation value plus `2 × (level − 1)`**. No item, spell or challenge moves it.

**Base** (`0x7C`, which is index 0) is the natural value that the level-up grows, and it is the input to the level-up formulas. Healing clamps current health to base health, and the level-up writes to this column and nowhere else. Its five derived combat words at `0x88` to `0x90` are computed alongside the current column's, but they are never read back. A scan of displacements finds about 9 references to them, all of which are writes in the equipment routine or in the panel's pair render, against about 33 reads of the current column's `0x4C` to `0x50` spread through the combat and spell code.

Character creation rolls attributes at image `0x14e20` and *derives* the twelve skills from them at image `0x13b40`. Projectile, for instance, is 50% of strength plus 20% of dexterity, with per-class adjustments keyed on `[si+0x0e]`, writing each result into both columns. It rolls `45 + rand(15)` per attribute and writes the *same* value into both columns, so **at level 1 the two columns are identical**. The helper at image `0x174ac` masks to the argument's bit width and subtracts once if the result overshoots, so its range is `0..n` *inclusive*. The roll is therefore 45 to 60, and the party that ships with the game shows both endpoints (YENDOR has wisdom 45, and DIANA has wisdom and charisma 60). A skill that the class cannot use is left at **zero**, and that zero does real work, as described below.

### The condition word

`0x1c40` covers stoning, frozen, paralyze and dead. It is one mask with three effects. It stops training, it stops the character taking a turn, and it stops the character being targeted. [tools/levels.py](../tools/levels.py) calls it `INCAPACITATED` rather than `BLOCKS_TRAINING` for that reason. The five conditions outside the mask leave a character acting and targetable, and drain health or magic instead. The nine conditions, their protection words and what each costs to cure are in [combat.md](combat.md), along with everything else about a fight.

## What a level-up does

In order, at image `0x09a50`, after the gold has changed hands:

1. **`level += 1`**, clamped at 90.
2. **Health.** `base health += round(base stamina × 30%)`, then `current health := base health`. A level-up is therefore also a full heal.

The pools are **accumulated and never recomputed**. Max health and max magic are each written directly exactly once, at character creation, at images `0x14ebd` and `0x14f78`. Every later change is applied by the stat-add helper, which adds to what is already there. Base stamina is read in exactly one place in the whole executable, which is the health gain at image `0x09a65`. Base intelligence and wisdom are read only by the magic dispatch at `0x09a9a`. Every other instruction that touches the pools is a `TEST`, which does not write.

Retroactive recomputation would have to appear as either a write rebuilding the pool from the attribute, or a multiply of the attribute by the level. Neither exists: the level field is multiplied in exactly two places in the executable, both in a list-rendering routine where the operand is a record stride of 34.

So a point of stamina or intelligence affects only the additions made at *subsequent* trainings. That is what makes them compound, and what reduces a point bought at level 35 to about a tenth of the value of the same point at level 5.

The two models can be told apart in play. A level 40 character who rolled 52 stamina reads about **1,066** maximum health. Recomputing from the current stamina would give 1,521, and recomputing from the original roll would give 608. The cap for health and magic is 9,999, and everything else caps at 999.
3. **Bonus points** `= min(15, round(base charisma × 13%))`, stashed in `DS:0x0e2a`.
4. **Magic points**, which depend on the class, as the table below sets out. Fighter, merchant and rogue gain nothing.
5. **`base += 2` on each of the six attributes**, and **`base += 2` on each of the twelve skills**.
6. Spells, on even levels only, and promotion, at levels 10 and 30.
7. The message "YOU ARE NOW LEVEL n" with the health points and magic points, then the bonus point screen.

Step 5 is applied by the helper at `0x05bd9`, which **does nothing when the field is already zero**. That is the whole of the class restriction on skills. A fighter's CASTING is 0 at creation and stays 0 for forty levels, and a monk's THIEVERY does the same. There is no class check in the code, because the data enforces it.

Note what step 5 does *not* do: it raises the ceiling, not the number you play with. Level-ups on their own do not improve a single attribute or skill. Bonus points are the only way to move the current column.

### Magic points

`[si+0x0e]` has 10 subtracted from it until the result is 9 or below, so a promoted character levels exactly like its base tier. Classes 1 to 3 gain nothing. The rest blend intelligence and wisdom and then take 30%.

| Class | Code | Blend | Gain |
|---|---|---|---|
| Monk | 4 | 100% wisdom | `round(round(WIS×100%) × 30%)` |
| Alchemist | 5 | 75% wisdom + 25% intelligence | same shape |
| Paladin | 6 | 50% wisdom | |
| Mage | 7 | 100% intelligence | |
| Druid | 8 | 75% intelligence + 25% wisdom | |
| Marksman | 9 | 50% intelligence | |

These are the percentages that `README.DOC` describes in words, as in "Alchemist, 75% Cleric 25% Wizard". Both the blend and the final 30% read the **base** column. A mage with base intelligence 60 gains 18 magic points per level.

## Bonus points

**The formula is `min(15, round(charisma × 13 / 100))`, and the charisma it reads is `[si+0x86]`, which is the base column.**

That is neither the level-1 roll nor the number on the character sheet:

- it is not frozen at level 1, because step 5 adds +2 every level,
- it is not the displayed value, because the panel prints the current column, which is what bonus points and any drain or item bonus move.

So **spending bonus points on charisma buys you nothing at the next training.** Base charisma is exactly `roll + 2 × (level − 1)`, and the whole career is determined by the creation roll:

| Creation roll | First training | Total to level 40 | Reaches the 15 cap when training from |
|---|---|---|---|
| 45 (lowest) | 6 | 419 | level 35 |
| 52 | 7 | 451 | level 31 |
| 60 (highest) | 8 | 482 | level 27 |

`README.DOC`'s "up to 15" is real but late: 13% of charisma only reaches 15 at charisma 112.

### What they can be spent on

The click handler at `0x04a34` maps screen rows to fields with no class test anywhere:

- rows 4 to 9 are the six **attributes**: strength, dexterity, stamina, intelligence, wisdom and charisma,
- rows 10–21 → all twelve **skills**: survival, projectile, slashing, bashing, polearm, casting, mapping, navigation, bartering, repair, thievery, linguistics.

There are 18 targets. A left click adds a point and a right click takes one back. Health and magic points are not spendable targets, because they come from the formulas only.

The screen is bracketed by two block copies, and they explain everything about it that appears inconsistent. `revert` (image `0x0a659`) writes the base column over the current one on entry. `commit` (image `0x0a631`) writes the current column back over the base one on exit. Both move indices 0 to 10 and 13 to 26, skipping health and magic.

- **Points are permanent.** The commit is what stores them, and it is also what feeds them into the level-up formulas: a point of charisma raises base charisma, so it raises every later training's payout. The same holds for stamina into health and intelligence/wisdom into magic.
- **The guards are correct, not buggy.** Because the revert runs first, the current column starts the screen equal to the base column, so the equality test on the decrement path lets you take back exactly what you added and no more. The increment's only bound is the 999 stat cap.
- **A raw `inc` bypasses the zero rule**, and the commit then makes that stick: one point lifts a class-locked skill off zero, and from the next level-up the stat-add helper no longer skips it. One point at level 2 reaches 77 by level 40.
- **Resting reverts too** (image `0x0d7a1`), which is how a drained attribute recovers and why the working column can be treated as disposable.

## Getting to a trainer

`[si+0x1e]`, the "ready for level" field, is recomputed on every shop visit (image `0x065ba`). It is zero unless the character is both healthy, which the test `[si+0x1c] & 0x1c40` decides, and past the next rung of the ladder. The routine walks up from the current level while the experience at `[si+0x18]` still clears the threshold, so the field holds the *highest* level earned. Training still advances one level per paid session.

### The experience ladder

89 four-byte packed-BCD entries at `DS:0xc75f`, one per level from 2 to 90. **Only the first 39 are real.** Every entry from level 41 on is 99,999,999, which nothing in the game can pay, so **40 is the effective cap** and the 90 in the clamp is dead code. The spell tables stop at 40 too.

| Level | Experience | Level | Experience | Level | Experience | Level | Experience |
|---|---|---|---|---|---|---|---|
| 2 | 680 | 12 | 65,800 | 22 | 611,000 | 32 | 2,600,000 |
| 3 | 1,800 | 13 | 85,500 | 23 | 730,000 | 33 | 3,160,000 |
| 4 | 3,200 | 14 | 99,600 | 24 | 866,000 | 34 | 3,810,000 |
| 5 | 6,500 | 15 | 125,000 | 25 | 1,010,000 | 35 | 4,780,000 |
| 6 | 10,300 | 16 | 151,600 | 26 | 1,185,000 | 36 | 5,700,000 |
| 7 | 15,000 | 17 | 182,700 | 27 | 1,350,000 | 37 | 6,980,000 |
| 8 | 23,000 | 18 | 235,600 | 28 | 1,510,000 | 38 | 8,174,000 |
| 9 | 33,500 | 19 | 282,300 | 29 | 1,670,000 | 39 | 9,615,000 |
| 10 | 42,000 | 20 | 371,000 | 30 | 1,850,000 | 40 | 10,800,000 |
| 11 | 51,900 | 21 | 487,000 | 31 | 2,225,000 | 41+ | 99,999,999 |

Read as little-endian integers these are not round numbers. Read as packed BCD they are round, which is what fixes the encoding. It is the same convention that the enemy reward fields use.

The thresholds are cumulative totals rather than costs per level. The steepest jumps are at 20, 21 and 31, where the slope of the ladder roughly doubles. For scale, PALTIVAR gives 1,000,000 experience, the most of any monster in the tables, and that is most of one level at the top end, because the step from 39 to 40 is 1,185,000.

### The gold cost

The quote routine at image `0x091eb` takes a base price, multiplies it by the word at `+0x18` of the NPC record (`DS:0x0ec8` holds the NPC being talked to), and then adds that product into a 32-bit BCD accumulator **once per level the character already has**:

```
cost = base × NPC factor × current level
```

`current level` is the level trained *from*, not the one trained to. For training the base is 100:

| Trainer factor | L1→2 | L5→6 | L10→11 | L20→21 | L39→40 |
|---|---|---|---|---|---|
| 1 | 100 | 500 | 1,000 | 2,000 | 3,900 |
| 3 | 300 | 1,500 | 3,000 | 6,000 | 11,700 |

The factor is map data held per NPC, so the real price of a particular trainer has to be read off that NPC. The shape of the price is `100 × factor × level`. The party's gold is compared before the charge, and the session is refused with "YOU DON'T HAVE ENOUGH GOLD."

Two other prices share the routine:

- **A trainer will not train past its own level.** `[0xec8+0x16]` holds the cap. Above that level the trainer answers "UNFORTUNATELY, I CAN ONLY TRAIN YOU THROUGH LEVEL n".
- **Bonus points can also be bought outright** (image `0x097db`), from an NPC whose `+0x18` is *both* the number of points and the multiplier. The price is therefore flat per point, at `1000 × points × current level`.

Other services quote through the same routine. Replenishing health has a base of 20 and raising the dead a base of 100. Curing conditions uses a base summed over whichever condition bits are set, which is 5, 10, 20, 40, 50, 60, 20, 30 and 40 for bits 15 down to 7 (image `0x092b1`).

## Spells and promotions

`test [si+0x16], 1 / jne` skips odd levels, so **spells arrive only on even levels**. The index is `level/2 − 1` into 20 four-byte slots at `DS:0xb8b5 + 0x50 × class`, which is six rows in the order monk, alchemist, paladin, mage, druid, marksman. Each slot holds at most two spells, for each even level from 2 to 40, and zero means an empty slot. The values are 1-based spell numbers, so the record index is the value minus 1. The message "YOU HAVE LEARNED SOME SPELLS" prints if anything was granted.

The class code then gains 10 at **level 10** and again at **level 30** (`add word [si+0xe], 0xa` at image `0x09ce1` and `0x09ced`, against the constants written at image `0x0f0e2`), which is what turns MONK into CLERIC into PRIEST.

**The title is the whole of the promotion.** Every read of the class field on a character record strips the tier first, with `cmp ax,9 / sub ax,0xa` applied twice. It then dispatches on 1-9 exactly as it did before the promotion. That happens at the magic gain at `0x09a9a`, at the spell grant at `0x09c73` (which folds 4-9, 14-19 and 24-29 onto the same six rows), at the magic-class bitmask at `0x1dce7`, and at the magic regeneration at `0x1ae1a`. Every one of the 88 `cmp [si+0xe], n` sites in the image compares against 0-9, and not one of them tests a promoted value. The single place the tier survives is `0x04cc3`, which uses it to choose between three name tables and return. The tables are the base names, then nine at `DS:0x875b` (WARRIOR, TINKERER, THIEF, CLERIC, TRANSMUTER, CAVALIER, WIZARD, ENCHANTER, RANGER) and nine at `DS:0x87be` (CHAMPION, BLACKSMITH, ASSASSIN, PRIEST, HEALER, HERO, SORCERER, SAGE, KNIGHT), 11 bytes each. All nine classes are promoted, not only the six that cast.

## What corroborates this

- **The creation formulas against the shipped party.** The four PRE-CREATED PARTY characters in `WORLD.DAT` were generated by the creation code, so rebuilding their derived fields from their attributes alone is a check the tables cannot pass by chance. `tools/skills.py --check` rebuilds all twelve skills plus health and magic for all four (Merchant, Monk, Mage and Druid) and reproduces **56 of 56** fields exactly. That holds the blends, the per-class modifiers and the flat overrides to data the creation code itself wrote.

- **The spell table against the game's own screens.** The per-class levels in `data/spells.json` were read off the **F3** clue book pages by [tools/solve_spells.py](../tools/solve_spells.py), and this table was found in the data segment. All **165** TRAINING rows that the screens showed agree with it exactly, at the same level. `DS:0xb8b5` holds 182 training rows in all, so **17 of them no F3 page can show**: F3 has room for three classes and prints the first three in class order, and every one of the 17 is a druid or marksman row on a spell that already lists three. F4, which lists a class's whole spell list, has no such limit and shows 247 rows across the six classes.
- **A training, driven in the running game.** SQUIRE was given charisma 96 in both columns, enough experience for level 5 and 50,000 gold, placed beside the trainer in Athaneum, and trained once. Charisma came back 98 and `DS:0x0e2a` held **12**. 13% of 96 rounds to 12 and 13% of 98 rounds to 13, so the payout is read off base charisma before step 5 adds its 2, in the order given above. This is **measured**: the value was read out of the guest either side of the level-up.

- **`README.DOC` against the formulas.** The manual states that "CHArisma determines number of bonus points in training (up to 15)" and that "STRength determines how much weight you can carry", and it gives per-class cleric, wizard and fighter percentages. All three match the arithmetic exactly.

## The multiple-of-five rule

Both attribute bonuses run through the same `pct` helper (image `0x15862`), and it **rounds to nearest** rather than down, as `mul bx / add ax, 0x32 / div 100`. Twenty percent of the excess over 72 therefore steps by one for every five points, and it lands on the step at every multiple of five.

- **dexterity** over 72, a fifth of which is added to absorption,
- **strength** over 72, a fifth of it, added to melee damage.

A total that is not a multiple of five past the threshold therefore wastes up to two points. Rounding to nearest means that 398 and 400 both give 80. 403 gives 81 and wastes nothing, while 401 gives 80 and wastes one point. Aim at the *total* rather than at the points spent. The natural attribute at level 40 is 138, so the arithmetic runs on `138 + bought − 72`.

There are exactly two attribute bonuses in combat, and these are they. Nothing else an attribute does is a combat multiplier.

## The return on a bonus point

[tools/combat_model.py](../tools/combat_model.py), with [tests/test_combat_model.py](../tests/test_combat_model.py), carries the spending model. It is matched by level, setting a character of level *L* against the hardest regular monster of level *L*, which is possible because `data/enemies.json` carries a level for every monster. The row describes **one real monster**, the one with the most experience at that level, with bosses excluded by the food flag. It does not take each field at its maximum independently, because that combination describes no monster in the game.

Two figures out of the item decode ([items.md](items.md)) bound what the points buy:

- **Armor tops out at 111 absorption, or 161 enchanted.** Dexterity is the only other source, so a build aiming to be unhittable must purchase the difference.
- **The best one-handed weapon that can be bought does 30 damage.** 40 damage is the 2-Handed Sword +10, and carrying that weapon costs the shield, because a two-handed weapon and a shield cannot be carried together, and no class is barred from a shield. Ten damage does not pay for the shield's thirty absorption in any build.

From those: the hardest monster swings at accuracy 240, so **241 absorption can never be hit**, and reaching it from 161 of armor costs **332 dexterity points**. Against a budget of 497 to 525 that is affordable but it is most of the career.

**Buy strength until the margin equals five times the damage stat.** Past the point where accuracy already lands every blow, further weapon skill buys only the margin term in `pct(damage, margin)`, and strength buys the damage term.
