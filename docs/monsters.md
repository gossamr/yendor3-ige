# The enemy record

The enemy record is 106 bytes, and there are seventy three of them at `WORLD.DAT 0x417075`, which is section 29 of the directory. Record 0 is a zero-filled sentinel, and record 62 is a placeholder named `NOT USED`, so the game lists 71 creatures. This document records settled findings only. What a creature *does* with these fields is in [combat.md](combat.md), and how it is drawn is in [pictures.md](pictures.md).

## Reading it

The record is copied into a 156-byte creature struct that carries a 50-byte header, so **record offset N is `[si+N+50]` in the code**. There are 80 of those structs, each one an active spawn, at `DS:0x122C` (image `0x1234E`). Three further copies, holding the creatures currently engaged, are at `DS:0x54B8`, `0x5554` and `0x55F0`.

A character is a separate 500-byte struct at `DS:0xD0D1`, and its fields land on the same displacements, so a reference has to be read rather than counted. [tools/xref.py](../tools/xref.py) lists every instruction that touches a displacement.

## The fields

Every field is a uint16 unless the size column states otherwise.

| Offset | Field | Notes |
|---|---|---|
| 0–25 | name | two 13-byte fields, space-padded |
| 26 | picture | the first of ten consecutive pictures, see [pictures.md](pictures.md) |
| 28 | family | *inferred*, see below |
| 30 | health | |
| 32 | level | 1 (WASP) to 45 (PALTIVAR) |
| 34 | accuracy | |
| 36 | dexterity | sets turn order, see [combat.md](combat.md) |
| 38 | absorption | |
| 40 | damage | |
| 42 | sound on a hit | index into the executable's 141-entry VOC table |
| 44 | sound on a miss | |
| 46 | shot picture | in `PICTURES.VGA` run 1 |
| 48 | shot sound | played where the shot lands |
| 50 | ranged accuracy | |
| 52 | ranged damage | |
| 54, 56 | effect offset | where a hit graphic is drawn on the creature |
| 58 | ordinary attack id | into the twelve-byte table at `DS:0x96DA` |
| 60 | special attack id | the same table |
| 62 | shot attack id | the same table, and 2 for all thirteen shooters |
| 64–69 | recolor | up to six `from << 4 \| to` pairs, stopping at a zero byte |
| 70–75 | shot recolor | the same, for the projectile |
| 76–79 | gold | packed BCD, most significant byte first |
| 80–83 | nuore | packed BCD |
| 84–87 | food | packed BCD |
| 88–91 | experience | packed BCD |
| 92–95 | steal | packed BCD: what a STEAL GOLD attack takes |
| 96 | flags | below |
| 98 | flags | below |
| 100 | immunity mask | below |
| 102 | resistance | below |
| 104 | | zero in all 73 records |

The five combat statistics, the four rewards and the twelve immunity and resistance rows were each checked against the game's own F2 page, for every creature the game lists. The result is 355 of 355 statistic readings, 71 of 71 on each reward, and 71 of 71 on every effect row. [tools/capture_monsters.js](../tools/capture_monsters.js) walks the pages and [tools/ocr.py](../tools/ocr.py) reads the values off the frames.

## Rewards are packed BCD

Most significant pair first. WASP's 15 experience is stored `00 00 00 15`, PALTIVAR's 1,000,000 as `01 00 00 00`. Nothing holds these as plain integers at any width or scale, which is why searching for them as integers finds nothing.

A steal takes the same form, and only the three creatures whose special attack is STEAL GOLD carry one: THIEF 100, ELF ASSASSIN and FROST DWARF TOWER 1,000.

## Immunity, offset 100

Six condition effects in the top bits, most significant first, and the damage types at the bottom of the word:

| Bit | 15 | 14 | 13 | 12 | 11 | 10 | 4 | 3 | 2 | 1 | 0 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| | poison | disease | paralysis | freezing | hexing | cursing | magic | fire | cold | electric | power |

Bits 9 to 5 are never set. Every undead creature reads `0xFC00`, which is immunity to all six conditions and to nothing else.

## Resistance, offset 102

Four values appear: `0x8000` on 13 creatures, `0x4000` on 8, `0x2000` on 12, `0x6000` on BLAZIOS alone, and zero on the other 38 (the placeholder included).

**The word is the set of damage types a creature resists.** Every blow builds a word describing itself. The applier ANDs that word with the creature's word and halves the damage once for each bit that survives. Image `0x0C690` does this for a blow and image `0x1D8AF` for a spell, and the chain at `0x1D72F` is the same test written out bit by bit.

**The game sorts the bits into its two rows itself.** The F2 page's twelve rows are twelve calls to two helpers, each passing the row's mask in `ax` and its label in `bx`. The ten immunity rows pass one bit each, exactly as the table above has them. The two resistance rows do not:

| Row | Mask | Bits |
|---|---|---|
| MAGIC DAMAGE (`0x07E6A`) | `0x3A00` | 13, 12, 11, 9 |
| PHYSICAL DAMAGE (`0x07E9C`) | `0xC000` | 15, 14 |

Which gives the vocabulary its shape:

| Bit | Row | Set on a blow when | Creatures |
|---|---|---|---|
| 15 | physical | it is a shot, or the fixed item damage (`0x0C8E4`) | 13 |
| 14 | physical | never | 9 |
| 13 | magic | the spell is one of the 63 ordinary damage spells | 13 |
| 12 | magic | never | 0 |
| 11 | magic | the weapon behind the shot is enchanted (`0x0C752`) | 0 |
| 9 | magic | the spell is one of the 7 anti-undead spells | 0 |

An enchanted weapon is filed under *magic*, which is the grouping explaining itself. The blow is partly magical, so magic resistance halves it. A shot's word is built at image `0x0C746` from the weapon's own properties, so a plain LONG BOW gives `0x8000` and a LONG BOW +3 gives `0x8800`, which is physical and magical together. A spell's word is the upper bits of its record 76, which across all 107 spells take three values: 0, `0x200` and `0x2000`.

**Measured.** [tools/fight_probe.js](../tools/fight_probe.js) sets a centipede's resistance word before boot, walks a party out to it and reads its health out of the emulator between blows. With the party's accuracy at the resolver's maximum margin every swing lands for the same number, so one blow shows a halving:

| Resistance | Melee swing | MAGIC ATTACK | Round |
|---|---|---|---|
| `0x0000` | 244 | 124 | 856 |
| `0x4000` | 244 | 124 | 856 |
| `0x8000` | 244 | 124 | 856 |
| `0x2000` | 244 | **62** | 794 |
| `0xFFFF` | 244 | **62** | 794 |

Bit 13 halves the spell. Bit 14 changes nothing. Bit 15 changes nothing against these two blows, neither of which is a shot. With every bit set at once a melee swing still lands in full, which is `0x00E73` and `0x00EC8` from the other side: a swing builds no word, so no resistance reaches it. The `0xFFFF` row also shows the chain halving once rather than once per bit.

**Bit 14 is the one physical bit that no blow sets.** Nine creatures carry it, and eight of those carry nothing else. Bit 12 is set by nothing and carried by no creature. Bits 11 and 9 are set by something and carried by no creature.

**Bits 15 and 14 print on the same row.** ACOKNIGHT carries bit 15 and KING BARIAG carries bit 14, and both show `RESISTANT` on PHYSICAL DAMAGE. BLAZIOS carries 14 and 13, and shows it on both rows.

Magic resistance has a second source, which is bit 4 of the immunity word, tested at image `0x07E6D` immediately after the magic row's own mask. Four creatures carry only that bit: BLAZIOS, CHAMELEON MAN, FIRE DWARF and SORCERER.

## Word 96

| Bit | Creatures | What |
|---|---|---|
| 0 | 26 | the picture is in run 3, the 190x110 one. Clear: run 2 (image `0x1035E`) |
| 1 | 12 | the shot's recolor list at 70 applies (image `0x125A2`) |
| 2 | 38 | the recolor list at 64 applies (image `0x10337`) |
| 4 | 23 | the walk cycle runs up and back down (image `0x153B1`) |
| 5 | 48 | the walk cycle runs up and snaps back (image `0x153A8`) |
| 6 | 0 | the creature does not animate (image `0x15398`) |
| 9 | 1 | BREAK SHIELD |
| 10 | | a DESTROY names the hand weapon at character `+0x142` (image `0x1457`) |
| 11 | | a DESTROY names the missile weapon at `+0x13A` (image `0x144C`) |
| 12 | 14 | PARTY ATTACK: the creature swings at all four characters in its turn |
| 13, 14, 15 | | how many of this creature can engage at once |

Every creature the game lists carries exactly one of bits 4 and 5. Bits 10 and 11 are read only when the attack is a BREAK or DESTROY, so the creature counts above would not mean anything for them.

**Bits 13, 14 and 15 govern the group.** Only three of the eight combinations appear:

| Bits 15,14,13 | Creatures | Most that can engage |
|---|---|---|
| `000` | 5 (MIMIC, both TOWERs, ALLIGATOR, CROCODILE) | 1 |
| `110` | 20 | 2 |
| `101` | 46 | 3 |

There is no encounter table and no count field. The group is assembled one creature at a time as each creature closes, at image `0x12B5C` to `0x12CA4`. The first creature ORs its `w96 & 0xE000` into the combat flags at `[0x5370]`. A newcomer needs bit 15 to join at all, and with two creatures already engaged, image `0x12C0C` re-reads bit 14 from both occupants and makes room for a third only if neither of them carries it.

## Word 98

| Bit | Creatures | What |
|---|---|---|
| 1, 2, 3 | 3, 12, 6 | not decoded, see below |
| 5 | 1 | MIMIC. The creature never sets its own active flag (image `0x12F94`) |
| 9, 10, 11, 12 | 10, 0, 0, 3 | how often it shoots: 25, 50, 75, 90 (image `0x129F8`) |
| 15 | 3 | drawn in color group 0, the gray one (image `0x10378`) |

Exactly the thirteen creatures with a ranged attack carry one of bits 9 to 12, and the three of those that cannot move (FUNGUS and the two dwarf towers) carry the 90. Image `0x12F85` runs when a creature spawns. It uses the distance band the creature appeared at to decide whether to set bit 0 of the creature's state word. Bits 6, 7 and 8 would move that threshold, and no creature carries them.

Bits 1, 2 and 3 are tested at images `0x154A4`, `0x154D7`, `0x154E5` and `0x154EE`, inside a block that either doubles the three movement deltas at `[0xE9C]`, `[0xE9E]` and `[0xEA0]` or refuses the move. **No call reaches that block**, neither a far call through the relocation table nor a near call or jump, so the entry point of the block has not been found and what the bits permit is not established. What is established is which creatures carry them. Bit 1 is carried by FUNGUS and the two dwarf towers, which are the three creatures that never move. Bit 3 is carried by WASP QUEEN, PIXIE, PIXIE LEADER, PALTIVAR, BLACK DRAGON and BLAZIOS. Bit 2 is carried by twelve other creatures. Bits 0, 4, 6, 7, 8, 13 and 14 are set by no creature.

## The family, offset 28

Creatures sharing this code share a kind, and the field takes eleven values across the 71 the game lists. Two are named by the game itself, since `INSECT` and `UNDEAD` are targets in the spell `AFFECTS` enumeration:

- **9**: WASP, WASP QUEEN, CENTIPEDE, MILLIPEDE, PRAYING MANTIS, FIRE MANTIS, SCORPION.
- **13**: GHOST, SPECTRE, GHOUL, WIGHT, SKELETON, SKELETAL WARRIOR, KING SLATOR.

The other nine codes do not read as a classification of species. Code 12 holds fifteen creatures with no species in common, among them a barrel, a fire elemental, a fairy and a giant eye. Code 0 holds two mushrooms, two buildings and a ball of light. Code 8 holds eleven humans, and code 10 holds SORCERER and WIZARD alone. Codes 6, 7 and 11 are unused. The field therefore groups creatures by something the game does with them rather than by what they are, and only the two groups that the game names are treated here as named.

## What the record does not hold

**The conditions an attack inflicts.** Offsets 58, 60 and 62 hold ids, and the mask lives in a twelve-byte entry at `DS:0x96DA` keyed by the id. That is why looking for the mask inside the record fails. ACOKNIGHT and FUNGUS share every word of the record and differ only in the id. The layout of the entry is in [combat.md](combat.md).

**A counter-attack.** The resolver at image `0x1586F` has five call sites and only two are in the melee loop: the player's swing at `0x00E73` and the creature's turn at `0x01353`. The swing resolves one attack, tests `[0xF36]` and returns without resolving anything back. A creature attacks more than once in a round only by being more than one creature, or by carrying PARTY ATTACK.
