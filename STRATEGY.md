# Yendorian Tales 3, party planning

What to roll, where to spend bonus points, what each party composition can
handle, and which spells to actually cast. Note this strategy guide contains
spoilers.

Every figure here is generated from your own copy of the game. All of it comes
from reading the code, none of it from testing in play. Mechanics are in
`MANUAL.md`.

<!-- panel:skip -->
`tools/ladder.py` and `tools/party.py` generate the tables.

---

## 1. Rolling characters

Attributes roll 45 to 60, independently, and re-roll every time you pick a
class. The question is which low roll you can live with.

One extra point at creation, for a fighter:

| Attribute | What it buys |
|---|---|
| Charisma | about 4.2 bonus points over a career, plus 0.9 bartering |
| Dexterity | 4.6 skill points across seven skills, plus a bonus point saved late |
| Strength | 2.6 skill points, plus 1 more weight unit carried |
| Intelligence | 1.2 skill points |
| Stamina | 0.6 skill points, plus about 12 maximum health by level 40 |
| Wisdom | 0.1 skill points and nothing else |

Charisma edges out dexterity, and its points go wherever you want them where
dexterity's are fixed. Against that, dexterity rolled at creation is dexterity
you do not buy later at five points per point of absorption, and every build ends
buying a hundred-odd points of it for turn order anyway.

### What each class can dump

| Class | Wants | Can shrug off |
|---|---|---|
| Fighter | DEX, CHA, STA, STR | WIS is worthless, INT nearly so |
| Merchant | DEX, CHA, STA, STR, INT | WIS |
| Rogue | DEX, CHA, STA, STR | WIS is worthless, INT nearly so |
| Monk | WIS, DEX, CHA, STA | INT |
| Alchemist | all six | nothing |
| Paladin | WIS, DEX, CHA, STA | INT |
| Mage | INT, DEX, CHA, STA | WIS |
| Druid | INT, DEX, CHA, STA | WIS is thin but still feeds magic |
| Marksman | INT, DEX, CHA, STA | WIS |

Wisdom does almost nothing for a Fighter or a Rogue. It drives 10% of mapping
and nothing else they can use, since both are locked out of linguistics and have
no magic. Reroll over a 45 there.

Charisma buys no skill for a Monk, Mage or Marksman, whose bartering is fixed or
locked. It still sets their bonus points every level, so nobody dumps it.

The Alchemist has no dump stat and starts at zero in nothing, so it needs a
better roll than the others.

---

## 2. Cover the four selectable skills

Bartering, repair, thievery and linguistics are the four you can highlight on the
character screen, one per character. You want somebody genuinely capable in each,
and four characters is exactly enough slots.

Starting values at 60 in every attribute:

| Class | Bartering | Repair | Thievery | Linguistics |
|---|---|---|---|---|
| Fighter | 55 | 60 | 50 | **0** |
| Merchant | 65 | 65 | 60 | 55 |
| Rogue | 60 | 63 | 65 | **0** |
| Monk | 40 | 50 | **0** | 60 |
| Alchemist | 60 | 60 | 60 | 60 |
| Paladin | 60 | **0** | 60 | 55 |
| Mage | 40 | 60 | 55 | 63 |
| Druid | 60 | 60 | **0** | 65 |
| Marksman | **0** | 55 | 60 | 55 |

Read it for the zeroes. Leveling skips a skill sitting at zero, so it stays
there all game unless a bonus point lifts it off. The five-point spreads are
permanent but small, worth two or three levels of head start.

Merchant, Rogue, Druid and a free slot covers all four at 65 apiece with no
points spent. The fourth slot goes to whoever heals.

One point spent at your first training lifts any zero and it then grows like
everything else, reaching 77 by level 40. Spent at level 20 it only reaches 41,
which is below the rungs repair and linguistics pay at, so buy it early or not
at all.

### Bartering is not a reason to take a Merchant

Bartering climbs 2 a level like everything else, so a Merchant's five-point head
start buys each rung two or three levels early and nothing more. Every class but
the Marksman gets to every rung eventually. Take a Merchant for the repairs and
the literacy.

Points do real work here, but only early. Twenty of them take a 60 straight to
80, turning a 55%-of-value sale into 75%, at a point in the game when gold is
tight and the levels would not deliver it until 11. The same twenty at level 30
buy almost nothing. A Monk or Mage barterer starts at a flat 40 and costs about
ten levels; a Marksman starts at zero and costs the whole game unless somebody
spends the point.

### Somebody has to heal levels 6 to 14

No party can afford armor through that window, and every one takes 16 to 78
damage per creature killed. Party Heal is the only spell that covers it, at 100
to all four for 45 magic.

| Class | Party Heal at |
|---|---|
| Monk, Alchemist | **level 9** |
| Druid, Paladin, Marksman | level 16 |
| Fighter, Merchant, Rogue, Mage | never |

Level 16 is after the window closes. Bring a monk or an alchemist.

---

## 3. Charisma first

Bonus points are 13% of your charisma, rounded, capped at 15. Charisma also
rises 2 a level on its own, so a point spent early raises every later payout.

**Put everything into charisma until it reads 98, then stop.**

| Roll | Spend through | Then top up | Spent | Never buy | Free after | Net gain | Return |
|---|---|---|---|---|---|---|---|
| 45 | level 6 | none | 41 | 419 | 497 | **+78** | 1.9x |
| 50 | level 5 | 4 at level 6 | 38 | 443 | 508 | +65 | 1.7x |
| 52 | level 5 | 1 at level 6 | 36 | 451 | 511 | +60 | 1.7x |
| 55 | level 4 | 10 at level 5 | 35 | 462 | 516 | +54 | 1.5x |
| 60 | level 4 | 2 at level 5 | 30 | 482 | 525 | **+43** | 1.4x |

Net gain is measured after paying for the charisma, and on every roll it is
larger than the bill. Spend 41 points on a 45 roll and you finish with 78 more
free points than if you had spent nothing. That is the whole case for buying.

Every even value from 98 to 104 ends the career on exactly the same budget, so
where you stop above 98 does not matter. Where you stop below it does: 96 costs
a point on every roll but 45. What that point buys is a place in the queue for
the next step of the staircase.

Charisma climbs 2 a level and the climb lands before the payout is read, so a
roll of 60 that stops at 96 reaches 104 at level 9. Two points more, taken at
level 5, put it on 98 and bring 104 forward to level 8, which is one training at
13 points instead of 12. That is the whole of the difference, and it is why 98
beats 96 by a point on every roll but 45, where the climb arrives on 96 already
and the two points buy nothing.

The worse your roll, the more it returns, so the gap between rolls shrinks from
63 points to 28. A 45 that buys beats a 60 that does not.

Do not keep going to 112. Buying past level 7 lands every roll on the same
budget, which throws away a good roll entirely. Charisma reaches 112 on its own
by level 27 to 35 depending on where you started.

You spend the early game about 30 points poorer than someone who bought accuracy
instead, and you break even at level 11 or 12. That debt falls where nothing
needs the money: through the first ten levels your weapon skill sits at margin
53 to 58 against creatures of your own level.

If you are rerolling for one attribute, reroll for dexterity. It feeds seven of
the twelve skills. Do not reroll 59 for 60, which is worth two points across an
entire career once you follow the buying policy.

### An odd roll wants its first point in charisma

The payout is a staircase, not a slope. It steps up at these charisma values:

    43  50  58  66  74  81  89  97  104  112

Charisma climbs by exactly 2 a level, so its parity never changes on its own.
Roll an even number and you are even at every training you ever attend. Six of
the ten steps sit on even values, four on odd, so the even line collects more
of them.

One point at your first training moves you across for good:

| Your roll | Net points gained, after paying the one |
|---|---|
| 45, 47, 49 | +5 |
| 51, 53, 55, 57 | +4 |
| 59 | +3 |
| any even roll | +2 |

This is the first of the charisma purchases above, not a separate policy. It
only pays at the start. The same point spent at level 20 returns about half as
much, and in the 30s it does not repay at all.

---

## 4. Margin

Every attack, yours and theirs:

> **margin = accuracy − absorption**
>
> A negative margin always misses. Otherwise you hit
> `(margin + 1 + min(8, margin)) / 64` of the time, and a hit does `margin`%
> of your damage.

| Margin | 0 | 8 | 13 | 20 | 30 | 40 | 55+ |
|---|---|---|---|---|---|---|---|
| Chance to hit | 2% | 27% | 34% | 45% | 61% | 77% | 100% |

Armor cuts both terms. It lowers how often you are hit and how hard, so 20
points of absorption cuts incoming damage about threefold, not by 20.

Accuracy stops paying at margin 55. Up to there each point is worth more than
the last. After it, a point buys 1% of your weapon damage.

Accuracy and your weapon multiply each other, so when one of the two is badly
behind, that is the one to fix. Damage climbs further in absolute terms over a
career, but absorption feeds the quadratic side of the arithmetic, so gold spent
on armor buys more than the same gold spent on damage. A starting character
wears about 5 absorption and reaches 111 across the slots for 13,075 gold, or
161 with every piece enchanted.

Magic points work like charisma: the blend reads intelligence and wisdom as they
stand, so a point spent early widens the pool at every training after it and
only repays if bought early.

The die is loaded low. That d55 is really a d64 folded over, so rolls 1 to 8
come up twice as often as anything else. Low margins land more than you would
expect from the numbers.

Watch the per-hit column, not the average. The rarely-hit stop in section 6
averages 21
damage a round and takes 78 in a round where all three creatures connect.

### What never missing costs

Margin is your accuracy minus their absorption, and both sides move. Every
training adds 2 to your attack skill for free. Creature absorption climbs about
3.9 a level, so the margin erodes by about 1.9 a level on its own, and a
level-40 fighter who bought nothing swings at 143 into 158 and cannot hit
anything at all. Buying the margin back is a fixed bill, and a small one:

| Class | Points to hold margin 55 for the whole career |
|---|---|
| Monk, Mage | 65 |
| Fighter, Rogue, Alchemist, Druid | 70 |
| Merchant, Paladin, Marksman | 75 |

Sixty-five to seventy-five out of about five hundred. Pay it first. What a
fighter has to have spent by each level:

| By level | 4 | 12 | 14 | 18 | 20 | 26 | 30 | 39 | 40 |
|---|---|---|---|---|---|---|---|---|---|
| Points | 2 | 5 | 11 | 19 | 23 | 34 | 44 | 64 | 70 |

Level 39 is the one to plan for. Creature absorption jumps 20 there, the
largest step in the game, and after the free +2 that is 18 points out of the 70
in a single level. It arrives when there is no more armor to buy.

Spend as the points arrive. A point of weapon skill is permanent, so buying it
at level 5 delivers everything buying it at level 30 would, plus whatever it
does in between.

Bosses are not uniformly easier. The four end-game ones, ranked by what holding
margin 55 against each costs a fighter at level 40, against the 70 that regular
play asks:

| | Titan Lord | Chaotic Minotaur | Blazios | Paltivar |
|---|---|---|---|---|
| Its absorption | 140 | 157 | 165 | 170 |
| Points to hold 55 | 52 | 69 | 77 | 82 |

Only the Titan Lord is a soft target. Paltivar carries more armor than any
regular creature in the game and wants 12 points past the career bill.

---

## 5. Dexterity, part one: first strike

> **Two numbers, and they are not the same.** Every dexterity figure in this
> guide is **bonus points bought** unless a row says otherwise. What your
> character sheet shows is the total: your natural dexterity plus what you
> bought. Natural dexterity is your roll at level 1 and climbs 2 a level, which
> is 138 by level 40 from a roll of 60. So the 212 the rarely-hit stop costs reads
> as 350 in the game.
>
> Turn order and absorption are both settled on the sheet total, never on the
> points. The points are what you are spending.

The game re-sorts turn order by dexterity every round. You need to match the
creature, not beat it. Ties go to the party.

| Level | 15 | 20 | 25 | 30 | 35 | 40 |
|---|---|---|---|---|---|---|
| What you face | 111 | 134 | 155 | 190 | 215 | 250 |
| Your natural dexterity | 88 | 98 | 108 | 118 | 128 | 138 |
| Points to buy | 27 | 37 | 47 | 72 | 87 | 112 |
| Sheet total after buying | 115 | 135 | 155 | 190 | 215 | 250 |

The last row is what you check against the first. It overshoots at 15 and 20
because the absorption bonus reads dexterity in fives, so the purchase is
rounded up to the next multiple of five and the spare points are free
absorption.

Creature dexterity climbs from 92 at level 10 to 250 at level 40 while yours
climbs from 78 to 138, so left alone you are slower than what you fight for the
whole game. At 127 points bought, a sheet total of 265, you match the fastest
thing in the game and the requirement stops for good.

Buy this at every level, on every character. Do not buy past what is in front of
you. Extra dexterity does nothing for turn order until the creatures catch up.

---

## 6. Dexterity, part two: pick a stopping point

Four places worth stopping. Level 40 against 3 Black Dragons, four of the
build, damage columns per character.

The stops sit along one line, dexterity spent, and the table runs from least
bought to most. Each is called by its name below rather than by a position, so
nothing here is above or below anything else.

| Build | Dex bought | On the sheet | Absorb | Hit you | Per hit | Worst round | Rounds | Kills arrivals | Lost fight |
|---|---|---|---|---|---|---|---|---|---|
| Berserker | 127 | 265 | 170 | 100% | 176 | 528 | 2.4 | yes | 50% of health |
| Half the time | 137 | 275 | 202 | 50% | 74 | 222 | 2.9 | yes | 10% |
| Rarely hit | 212 | 350 | 217 | 27% | 26 | 78 | 3.8 | no | 4% |
| Untouchable | 332 | 470 | 241 | 0% | none | none | 6.7 | no | none |

**Berserker.** Turn order and nothing else, everything left into weapon skill
and strength. Two-handed weapon, no shield. It kills each creature in the round
that creature arrives, at every level from 15 to 40, so played well it takes
nothing at all. Played badly it eats 528 in a single round with no roll to save
it. Give it a healer.

**Half the time.** Ten more points of dexterity than the berserker, and it
changes the build completely. What it actually spends is the two-handed weapon:
a one-hander and a shield is 30 damage instead of 40, and the shield is worth
30 absorption. The extra half round is the whole cost.

It keeps the thing the berserker is for. It still kills each arrival in the
round it arrives, at **every level from 15 to 40**, which the rarely-hit stop
does not manage at 30 or at 40. And when the engagement goes wrong it takes a fifth of
what the berserker takes, 10% of its health against 50%.

If you were going to run a berserker, run this instead unless you want the
two-handed weapon for its own sake.

**Rarely hit.** Where most characters should stop, and the cheapest place to be
genuinely safe. Everything that closes gets a swing at you and you survive
them. 212 points bought holds margin 8, which is the 27% the stop is named for.
Stopping at 187 points leaves you at margin 13, and the loaded die makes that
34%, so the last 25 points are the ones that actually buy the band. They come
out of strength and weapon skill and cost about 8% of your kill speed.

It buys that safety by giving up the one-round kill at 30 and at 40, which is
the trade against the stop above it: fewer hits taken per fight, more fights
where something gets to swing at all.

**Untouchable.** Nothing can touch you. Takes seven rounds to clear what the
berserker clears in two.

### A stop is an absorption number, and it is the same for everyone

Absorption is your armor plus a fifth of your dexterity over 72, and neither
term reads your class. No item in the game is restricted by class, and natural
dexterity climbs 2 a level for everybody. So the rarely-hit stop is 217
absorption at level 40 for a fighter, a mage or a healer alike, and it costs
all three the same 212 points.

The shield is what moves it, not the class. Carrying a two-hander drops your
armor by 30, and buying that back costs 362 points rather than 212, which is
more than the untouchable stop costs a shielded character. That is why the berserker is
defined as the two-handed build sitting on first strike: the stop is closed to
it rather than declined.

A caster has fewer places to stop. It reaches the same two
absorption numbers and has nothing worth buying above them, which is section 7.

Nobody at any stop buys stamina, the six non-combat skills, or whichever of
intelligence and wisdom is not feeding a pool. The free +2 a level reaches all
of those.

Stamina is the one that looks arguable. A point of it at creation is worth 16
health out of the 1,066 a level-40 character holds, and health is the weaker of
the two ways to stay alive: absorption cuts how often you are hit and how hard,
where health only pays out once. Armor buys the first with gold and you have
more gold than points.

The non-combat skills are measured against fixed numbers, and +2 a level clears
every one of them. Buying is only worth it when you want a rung years before it
is due, or when the skill sits at zero and will never arrive at all. If you do
buy, buy to the rung exactly, because they are step functions and a point past
one does nothing until the next. Survival, mapping and navigation are party
averages, so in a party of four each rung costs four points rather than one,
spent on anybody.

### Your weapon type is a one-time decision

Every hand weapon reads one of slashing, bashing or polearm as your accuracy,
and only the skill you spend points on pulls ahead of the free +2 a level. A
level-40 fighter who has spent heavily on slashing has 419 in it and 138 in
bashing, so picking up a club drops the margin by 281, which is the difference
between a short fight and no hit possible.

Pick the type at level 1 and stay with it. The more you have spent, the worse a
substitution gets.

### Strength: buy to the crossover

Damage on a hit is `margin`% of your weapon plus your strength bonus, so a
point of accuracy adds `(weapon + strength bonus) / 100` and a point of strength
adds `margin / 500`. Accuracy wins while **margin is under 5 times your damage
stat**, and strength wins above it. Buy to the crossover and stop.

The budget is what is left after first strike, which is where attack points
actually come from:

| Level | Budget | After first strike | Best strength | Margin | Gain over none |
|---|---|---|---|---|---|
| 10 | 64 | 47 | 7 | 94 | 4.7% |
| 17 | 165 | 137 | 18 | 159 | 2.7% |
| 24 | 270 | 221 | 24 | 226 | 1.7% |
| 30 | 360 | 288 | 37 | 262 | 3.6% |
| 40 | 510 | 398 | **57** | 326 | **4.4%** |

Worth buying from about level 10 on, for anyone spending heavily on a weapon
skill, and the share grows as the budget outruns what the weapon can use. At
level 40 a 57-point purchase turns a 40-damage two-hander into 63, where the
same 57 points of skill would add 57 to a margin already at 326. It is a
correction of a few per cent either way, which is what sitting on a crossover
looks like.

None of this rescues a cheap weapon. With a knife the crossing arrives at margin
80, almost immediately, which is telling you to buy a weapon rather than
strength. Gold buys damage at a few hundred gold a point; strength buys it at
five training points.

### The rarely-hit stop's price moves

| Level | 15 | 16 | 20 | 25 | 30 | 35 | 40 |
|---|---|---|---|---|---|---|---|
| Points to buy | 27 | 25 | 72 | 87 | 162 | 87 | 212 |
| Sheet total | 115 | 115 | 170 | 195 | 280 | 215 | 350 |
| % of your budget | 20% | 17% | 34% | 31% | 45% | 20% | 42% |

Free at 15 and 16, where plain armor holds the band by itself and nothing at 16
can hit you at all. Expensive at 26 and 30, where creature accuracy jumps.
Cheap again at 33 to 35 once enchanted armor lands. Check the number at each of
those levels instead of buying to a fixed total.

### Untouchable is cheap early

| Level | 12 | 13 | 14 | 15 | 16 | 17 | 18 |
|---|---|---|---|---|---|---|---|
| Points for immunity | out of reach | out of reach | out of reach | 57 | 25 | 53 | 96 |
| Sheet total | | | | 145 | 115 | 145 | 190 |

Four creatures can take a character out of a fight entirely: the Wizard at 19
and Ice Dwarf at 30 freeze, the Purple Dragon at 26 paralyzes, the Fire Giant at
28 turns you to stone. **Absorption of 186 shuts all four out**, and that costs
202 points of dexterity at level 30, 67 at 35 and 57 at 40 as armor catches up.

Immunity to the creatures *at your level* opens up at 15, and costs less there
than the rarely-hit stop does at 30. The 332 points on the untouchable stop
buy something
different, permanent immunity: a sheet total of 470, worth 241 absorption, one
point past Paltivar's 240.

The catch is speed. From 18 to 31 you cannot kill an arrival in one round and
fights run 3 to 4 rounds. It clears up at 32 when enchanted armor frees points.

---

## 7. Building a caster

A caster splits its points three ways where a martial splits them two.
Intelligence is the pool, casting is the margin, and dexterity is turn order,
and the order you buy them in matters more than the ratio.

Intelligence compounds. A point adds to the pool at every training still to
come, so one bought at level 5 is worth about ten magic and the same point at
35 is worth one. Casting does not compound: a point is +1 whenever you buy it.
That argues for buying intelligence first, and the only question is when to
stop.

Stop early. Margin scales spell damage exactly as it scales a weapon's, so a
caster that keeps buying pool ends up with a large pool and a spell that lands
for nothing. Levels from 12 to 40 at which no spell you own kills a creature of
your own level in one cast:

| Intelligence through | Dead levels | Span |
|---|---|---|
| nothing, or level 8 | 0 | |
| level 12 | 4 | 12 to 15 |
| level 14 | 9 | 12 to 21 |
| level 18 | 13 | 12 to 24 |
| level 20 | 18 | 12 to 29 |

The fallback in a dead level is Magic Attack at 9 damage, which is 38 casts
against a Black Dragon. What it costs while you are in one:

| Level | Creature health | All casting | Through 12 | Through 18 |
|---|---|---|---|---|
| 12 | 87 | 1 cast | 18 | 18 |
| 14 | 117 | 1 | 17 | 27 |
| 16 | 138 | 1 | 1 | 34 |
| 18 | 154 | 1 | 1 | 42 |
| 20 | 165 | 1 | 1 | 27 |
| 24 | 263 | 1 | 1 | 24 |

Hit rate does not show this. All casting and through 12 connect every time at
every level above; through 18 dips to 78% for three levels around 18 and is
back at 100% by 20, while still needing 27 casts. Read casts per kill instead.

**Buy intelligence through level 8 to 12, then casting, then dexterity from
level 35.** Through 8 costs nothing and through 12 costs four levels, which is worth
it: over a career, kills between rests come to 588 for a switch at 8 and 743
for one at 12. Past 12 you are buying endgame pool with mid-game levels you
cannot fight through.

Dexterity comes last, and late, and the number below is a level rather than a
dexterity. A caster that acts before the creatures ends
the fight on its own turn, so its initiative is a purchase for the whole party
and nobody else's matters. Started at level 35 it adds about 7% to a career on every
intelligence setting. Started at level 30 or earlier it costs more than it returns,
because it comes out of the casting that makes the spell land.

### A caster has two stops, not three

The three martial stopping points, on a mage holding intelligence 78 and
splitting the remaining 432 between dexterity and casting:

| Build | Dex bought | Casting | Margin | Absorb | Hit you | Area damage | One-rounds the group |
|---|---|---|---|---|---|---|---|
| First strike | 112 | 320 | 310 | 197 | 58% | 542 | no |
| Rarely hit | 212 | 220 | 210 | 217 | 27% | 368 | no |
| Untouchable | 332 | 100 | 90 | 241 | 0% | 158 | no |

First strike is 58% here where the berserker in section 6 is at 100% for the
same purchase. The difference is the shield: a caster has no reason to carry a
two-hander, so it keeps the 30 absorption the berserker trades away.

**No column one-rounds, and the reason is resistance.** The Black Dragon halves
spell damage. Earthquake reads 1,085 a target off its own record and delivers
542 into 635 of health, so the group survives the cast, gets a turn, and a
second cast finishes it. Nothing a single caster can buy changes that: the
first-strike column already spends everything on casting.

That is not a reason to buy the untouchable stop. At 332 points of dexterity
there are 100 left for casting, the margin falls to 90, and the spell lands for
158 against 635 — four casts rather than two, in a fight the absorption was
bought to shorten. A build that cannot kill is not safe, only slow.

The first two are the same absorption numbers a martial buys, 197 and 217, at
the same price. What differs is that the untouchable stop is not worth buying,
so a caster is choosing between two.

Take first strike and put the rest in casting. Buy the rarely-hit stop only if
the caster keeps drawing fire, which happens when the pool runs out and the
fight goes long, not while the spells last.

### Resistance is a tax on the caster half of a party

Thirteen of the 71 creatures halve spell damage and thirteen halve shots.
**Nothing halves a hand-to-hand swing.** A martial's output is the only kind in
the game that is never reduced.

Across levels 15 to 40 the creature the guide measures against halves spells at
three of the twenty-six and halves shots at four. That is a small share of
ordinary play and a large share of the fights you plan for: of the four
end-game bosses, Paltivar and Blazios halve spells and the Chaotic Minotaur
halves shots.

You cannot dodge the halving by spell choice. Of the seventy damage spells,
fifty-nine declare themselves ordinary damage spells and are halved; the four
that declare nothing deal between 10 and 45.

### Immunity is a different thing, and more common

A creature immune to a damage type takes **nothing at all** from it, not half,
and only from that one type. Thirty of the 71 carry at least one, and the
creature this guide measures against carries one at twelve of the twenty-six
levels from 15 to 40, so it comes up four times as often as halving does.

It removes spells from your list rather than reducing them. Fire, cold,
electric and power are the four types a spell can carry, and 39 of the 70
damage spells carry none of them, so there is always something left to throw.
What it costs is the spell you wanted: a caster leaning on one element finds it
does nothing against the creatures built to stop it, and has to know its second
choice.

No element is safer than another. Of the 71 creatures, 14 stop electric, 11
stop power, and 10 each stop fire and cold, and the ones that carry more than
one almost always pair electric with power. The only spells nothing can be
immune to are the ones that carry no element at all.

So do not build a caster around a single element. Keep an elementless spell of
useful size on the list and you always have something that lands.

What it costs, at level 40 against three Black Dragons:

| Party | Magic a fight | Fights per rest | Without resistance |
|---|---|---|---|
| 4 martials | none | 22 | 22, unchanged |
| 3 martials + healer | none | 110 | 110, unchanged |
| 4 casters | 800 | 10.5 | 400 magic, 21 fights |
| 3 casters + healer | 800 | 7.8 | 400 magic, 16 fights |

The martial rows do not move. The caster rows halve. Before this was in the
model a caster party looked like it outlasted a martial one; it does not.

---

## 8. Building a healer

A healer that goes down takes the party with it. There is no front rank in this
game, the target picker rolls 0 to 3 and re-rolls only for empty or fallen
slots, so it takes its share like everybody else.

**Wisdom first, through the early levels.** It is the only purchase that feeds
both halves of the job, since the same pool pays for healing and for the spells
a monk attacks with, which early on outdamage its weapon. Heals restore fixed
amounts, so casting does nothing for that half.

Stop where a caster stops and for the same reason. Dead levels for a monk, on
the same count as section 7:

| Wisdom through | Dead levels | Span |
|---|---|---|
| nothing | 0 | |
| level 8 | 5 | 12 to 16 |
| level 12 | 6 | 12 to 17 |
| level 14 | 8 | 12 to 21 |
| level 18 | 18 | 12 to 29 |

A monk carries a few dead levels whatever it does, because its damage list
starts thinner than a mage's. Buying past 12 turns that into half the game.

**Then dexterity, and wait for level 35 to buy it.** Not for the damage. Four
creatures can take a character out of a fight entirely, and a healer frozen in
the round a Purple Dragon lands is the end of the party. Absorption of 186
shuts all four out, and what that costs collapses once the enchanted armor
lands:

| At level | 30 | 35 | 40 |
|---|---|---|---|
| Armor gold affords | 136 | 161 | 161 |
| Dexterity points to reach 186 | 202 | 67 | 57 |

Two hundred points out of the 360 you hold at 30 is more than half a career for
a threshold that costs 67 five levels later. Through the window, buy first
strike and lean on the protection items, which cover three of the four
conditions cheaply.

**Then casting with the rest.** Stopping at dexterity rather than carrying on
is what keeps the pool available to the party. Three Black Dragons all on the
healer:

| How it splits its 510 points | Absorb | Hit you | Taken a round | Rounds to die |
|---|---|---|---|---|
| casting 200 / dexterity 190 | 212 | 34% | 43 | 25 |
| casting 300 / dexterity 90 | 192 | 66% | 209 | 5 |
| casting 390 / dexterity 0 | 174 | 94% | 458 | 2 |

The last row dies in the third round of the fight the build exists to survive.
Its own healing does not save it either, since damage on the healer costs the
pool twice, once to take it and once to heal it.

Its output is a fraction of a martial build's in any split. The contribution is
the pool, and the points are there to protect the pool.

---

## 9. The allocation, level by level

The first fourteen levels are common to every build. Nothing defensive is
available: armor is worth 78 absorption at level 14, and the cheapest immunity
costs more than the whole budget.

| Levels | What everybody buys |
|---|---|
| 1 | one point into each skill sitting at zero that anyone will use |
| 2 to 5 | charisma until it reads 100, about 40 points |
| 6 to 14 | first strike, 24 points; weapon skill or the pool attribute with the remaining 56 |

The budget is 120 points by level 14 and 510 by level 40, on a charisma roll of
52 that follows the buying policy in section 3. Where the 510 end up, against
three Black Dragons at level 40:

| Build | Weapon skill | Strength | Dex bought | On the sheet | Absorb | Hit you | Per hit |
|---|---|---|---|---|---|---|---|
| Berserker | 351 | 32 | 127 | 265 | 170 | 100% | 176 |
| Half the time | 316 | 57 | 137 | 275 | 202 | 50% | 74 |
| Rarely hit | 266 | 32 | 212 | 350 | 217 | 27% | 26 |
| Untouchable | 176 | 2 | 332 | 470 | 241 | 0% | none |

The berserker is the only one carrying a two-handed weapon, 40 damage instead
of 30, bought with the Gold Shield's 30 absorption. That is what makes it the
only one hit every single time. Its 127 points read as 265 on the sheet, which
matches Paltivar's 265, and a tie goes to the party, so nothing in the game
acts before it.

### Where spare points go

You will have more than this spends, from a better charisma roll or from
reading this at level 30 with points in hand. What fifteen more do:

| Build | Into weapon skill | Into strength | Into dexterity | Spend them on |
|---|---|---|---|---|
| Berserker | 2.4 to 2.3 rounds | 2.4 to 2.2 | 528 to 475 taken a round | dexterity, or take the next stop |
| Half the time | 2.9 to 2.7 | 2.9 to 2.7 | 111 to 87 taken a round | dexterity |
| Rarely hit | 3.8 to 3.6 | 3.8 to 3.6 | 21 to 8 taken a round | dexterity |
| Untouchable | 6.7 to 6.2 | 6.7 to 6.3 | nothing, already at 0 | weapon skill |

Weapon skill and strength are level in the middle rows because those builds
already sit on the crossover, where the two are worth the same by definition.
Split spare points between them however you like and keep the margin near five
times your damage stat.

The untouchable build is the one exception on dexterity. At 332 points bought it
holds 241 absorption against a game whose hardest swing is 240, so there is no defensive
purchase left at any price.

Dexterity past first strike does not pay before level 15. Armor is worth at
most 78 absorption through levels 6 to 14, so points spent on absorption buy
almost nothing while the same points shorten the fight, and a shorter fight is
the better defense while your armor is worthless.

---

## 10. What each role does

**Martial.** Unlimited damage, one target, free. Never runs out.

**Caster.** Area spells hit every engaged creature, so damage scales with the
group. Magic points and nuore limit it.

**Healer.** No damage. Its pool decides how many fights you can string together.

More characters means more damage, and usually less damage each. An ordinary
creature picks one target a round, so a fourth party member takes a quarter of
the incoming off everybody else.

Fourteen of the 71 creatures carry PARTY ATTACK, and they break that. One of
them swings at all four of you inside its own turn, so each character eats the
whole group and a fifth party member would not help. Three Black Dragons deal
519 per character, 2,076 across the party. It is the single field that most
changes what a fight costs, and it does not track how hard the creature hits.

---

## 11. Compositions

Level 40, 3 Black Dragons, all engaged. Martials on the rarely-hit stop.

| Party | Rounds | One-round? | Taken each | Magic | Fights/rest | Runs out of |
|---|---|---|---|---|---|---|
| 4 martials | 5 | no | 48 (5%) | none | 22 | health |
| 3 martials + healer | 6 | no | 62 (6%) | none | 110 | health |
| 2 martials + caster + healer | 2 | no | 14 (1%) | 400 | 5 | magic |
| martial + 2 casters + healer | 1 | yes | none | 800 | 5 | magic |
| 3 casters + healer | 1 | yes | none | 800 | 8 | magic |
| 4 casters | 1 | yes | none | 800 | 10 | magic |

**It takes two casters to wipe a group here, not one.** The Black Dragon halves
spell damage, so a single caster leaves the group standing on 93 health apiece
and takes a second round to finish. The second caster is the one that buys the
one-round kill; the third and fourth buy pool rather than speed.

Regular fights will not tell you which party is better. From 15 to 39 even four
martials only take about 1% of their health per fight. Bosses show the
difference.

### Bosses

There are eleven, which the game marks by giving them food to carry. Paltivar
is the exception, carrying none. They run from the Wasp Queen at level 2 to
Paltivar at 45, so most of them are fights of their own level rather than
end-game walls. The four below are the last four, holding 2,000 to 3,400
health.

Three of the four resist something. Paltivar and Blazios halve spell damage;
the Chaotic Minotaur halves shots; the Titan Lord carries the one physical bit
nothing currently sets, so today it resists nothing in practice.

Rounds, then damage one character takes, then magic the party spends:

| Party | Paltivar | Chaotic Minotaur | Blazios | Titan Lord |
|---|---|---|---|---|
| 4 martials | 8 rds, 340 taken | 6, 12 | 6, 148 | 4, 4 |
| 3 martials + healer | 10, 436 | 8, 17 | 8, 207 | 5, 5 |
| 2 martials + caster + healer | 5, 194, 2000 mp | 3, 5, 1200 | 4, 89, 1600 | 2, 1, 800 |
| martial + 2 casters + healer | 3, 97, 2400 mp | 2, 2, 1200 | 3, 59, 2000 | 1, 0, 800 |
| 4 casters | 2, 147, 2800 mp | 1, none, 1200 | 2, 109, 2400 | 1, none, 800 |
| 4 paladins | 5, 588, 1224 mp | 2, 18, 576 | 4, 326, 1080 | 2, 40, 360 |

Nothing kills Paltivar on the first action any more. Four casters take two
rounds and 2,800 magic, which is most of a full party's pool for one fight, and
they take 147 damage each doing it. Martials grind it for eight rounds and lose
a third of their health.

Paladins are the opposite shape. On a regular group they are the most efficient
party in the game, one round for 288 magic and about 15 fights between rests
against a mage party's 10. Against a boss they fall apart: half the pool and a
smaller spell means five rounds on Paltivar and 588 damage each, four times what
four mages take. Take them for the run between the bosses, not for the boss.

**The Chaotic Minotaur is the cheap column, and it hits the hardest.** Its 450
damage is the most anything in the game deals, and it still costs a party less
than any of the other three. Two things stack, and neither of them is its
damage.

It has no PARTY ATTACK. It rolls one target and swings at that character, where
the other three swing at every character inside the same turn. Spread across
four of you, that is a quarter of the attacks arriving on any one of you.

Its accuracy is 225 where Blazios carries 235. At the rarely-hit stop, which is
217 absorption, that is margin 8 rather than 18, and margin sets the chance of being hit and the size
of the hit together, so the gap widens again.

Against the same party Blazios deals 89 a round and the Minotaur deals 7.

Check the two separately on any boss you meet. A high damage figure says
nothing on its own.

Every healer in a party costs you a round or two, since it deals no damage.
Against Paltivar that is 96 extra damage per character.

---

## 12. Which spell to cast

**Check the WHEN line first.** 26 of the 70 damage spells read *out of hand to
hand*, and they do nothing once something has closed on you. That includes
Finger of Flame and Power Surge, otherwise the mage's most efficient area
spells.

**Two casters, not one, and then stop buying spell size.** At level 40 one
caster cannot end a Black Dragon group in a round however much it spends,
because the group halves what spells do to it. Two casters throwing Tremor at
215 each can, for 430 between them. A third and fourth add pool rather than
speed: still one round, still 430, but 15 and 20 fights between rests instead
of 10.

**Do not just cast the biggest thing you own.** Earthquake at 400 each is 800
for the same dead group that Tremor clears for 430, and it halves how long you
last between rests. The biggest spell is for the fight you are losing.

**Against something that resists spells, more casting does not fix it.** The
halving lands after your margin has already scaled the damage, so a caster who
has spent everything on casting is halved just as hard as one who has not.
What answers it is another caster, or a character swinging a hand weapon.

**Do not use area spells on single creatures.** Mimic, both Towers, Alligator
and Crocodile always fight alone. A single-target spell is cheaper against them.

Damage per magic point peaks in the first few levels and never improves. Bigger
spells buy range and speed.

---

## 13. Paladins and marksmen: do not split them

Both get a weapon skill and a spell list, with half a caster's magic pool. Split
your points between the two and both halves fail.

Paladin, level 40, 510 points:

| Points to magic | Attribute | Casting | Weapon | Swing, one target | Spell, one target | Spell × 3 |
|---|---|---|---|---|---|---|
| 0 | 0 | 0 | 398 | 175 | cannot land one | none |
| 25% | 78 | 21 | 299 | 121 | none | none |
| 50% | 78 | 121 | 199 | 76 | 70 | 212 |
| 75% | 78 | 220 | 100 | 32 | 140 | 420 |
| 100% | 78 | 320 | 0 | 0 | 210 | 630 |

The two damage columns to compare are the two headed *one target*: a swing hits
one creature and so does one target's share of an area spell. The last column is
the same cast totalled over the three creatures engaged, which is the spell's
real advantage and not a like-for-like number. The spell columns are what
actually lands, so they carry the Black Dragon's halving of spell damage; the
swing column does not, because nothing halves a swing.

Half the weapon points gives you 43% of the swing. Half the casting points gives
you 33% of the spell. Margin scales damage, so halving your investment costs you
more than half the output, on both sides at once.

Against a creature that resists spells the split looks less lopsided than it is.
Committing everything to casting gives you 210 a target where the same points in
the weapon give 175, so on one creature the two ends are close, and the spell
only pulls away because it lands on all three at once.

With no casting at all the pool is dead weight. Natural casting 138 against 158
absorption is a negative margin, and nothing lands.

Run them as pure casters and they are good on ordinary groups: four paladins
clear one in a round for 288 magic and get about 15 fights between rests, where
four mages get 10. Bosses are the other way round, and section 11 has the
figures.

---

## 14. Resources

**Health** limits martial parties. Adding a healer takes four martials from 22
fights per rest to 110.

**Magic** limits caster parties, and resistance is what makes it bite. Spell
choice matters more than spell size: the same dead group costs 430 or 800
depending on what you throw.

**Gold** stops being a constraint long before experience does. The whole run
from level 1 to 40 costs 630,000 at the cheapest trainer available for each
level, which is inside a single good late-game haul. Bonus points bought from a
merchant are the exception: 1,000 gold per point per level you already have, so
one point at level 39 costs 39,000 where the same point at level 2 costs 2,000.
Buy them in the first few levels or not at all.

Watch level 26. Every trainer that charges 500 per level of yours stops at 25,
and the only two that go past it charge 1,000. The same level-up doubles in
price, from 12,000 to reach 25 to 25,000 for the very next one.

**Nuore** is not a real constraint, even though all 98 spells cost it. Three
Black Dragons drop 231 and a four-caster party spends 152 clearing them. It is a
party counter rather than carried weight, and shops sell it at 10 gold a unit
against five-figure drops. A fight costs 36 to 152 across levels 15 to 40, and
only two levels run a deficit: the Dwarf Alchemist at 17 and the Sorcerer at 21,
both of which halve spell damage and so take an extra cast.

**Stock up before Paltivar.** It drops no nuore and no gold, the only fight in
the game that pays experience alone. It also halves spell damage, so four
casters need two rounds and spend 608 nuore killing it, and get nothing back.

---

## 15. Order of decisions

1. **Cover the four skills and bring a healer.** Merchant, Rogue, Druid plus a
   monk or alchemist does both. Decided at character creation and not
   revisitable.
2. **Charisma to 100, then first strike.** Charisma raises every later training
   payout. Turn order comes due every level.
3. **Stop buying the pool attribute by level 12.** Casters and healers only.
   Past that you spend the mid-game with a large pool and a spell that lands
   for nothing.
4. **Pick a stop per character, not per party.** One berserker with a healer
   babysitting it, everyone else at the rarely-hit stop, is a strong mid-game
   party.
5. **Two casters, then stop.** One cannot end a group in a round against
   anything that resists spells; a third and fourth buy staying power rather
   than speed.
6. **Re-plan at 15, 18, 26, 30 and 39.** Level 15 is when armor becomes
   affordable. The rest are where creatures gain more in a level than your free
   +2.

---

## What this does not cover

Every fight here starts with all creatures already engaged, which is the worst
case. Arrival rate, positioning, condition attacks and item effects are all
missing.

The career figures in section 7 count creatures killed between rests, summed
over every level. That measure rewards a large endgame pool and says nothing
about when the pool arrives, which is why the dead-level count sits beside it
rather than under it.

Two numbers are assumptions rather than measurements. Roughly half your gold
goes to armor, and you carry the best weapon that buys. If you play
differently, every figure that depends on armor moves with you.

<!-- panel:skip -->
Both are set in `tools/combat_model.py`.
