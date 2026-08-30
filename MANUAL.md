# Yendorian Tales 3, the missing manual

What the game does not tell you. Everything here was read out of
`REGISTER.EXE` rather than guessed at from play, and the panel prints the same
tables straight from your own copy of the game.

<!-- panel:skip -->
`docs/leveling.md` carries the addresses and the evidence; `tools/levels.py`
and `tools/skills.py` print the tables.

This is the mechanics: what the game does and what the numbers mean. What to
roll, where to put bonus points and how to build a party are in `STRATEGY.md`.

The skill recipes are checked against the game's own data: the four ready-made
characters it ships with were built by this arithmetic, and rebuilding all
fifty-six of their derived numbers from their attributes alone reproduces every
one exactly. The rest is read from the code and has not been watched running.

---

## Leveling up

A level does not arrive on its own: you earn the experience, walk to a
trainer, and pay. What you get for the money is the bulk of your character's
growth, plus a handful of bonus points to place on top of it.

### 1. Earn the experience

Your character is ready for a new level the moment the party's kills push your
experience past the next rung of the ladder. The character screen says so:

> Training: currently level 7, ready for level 8

What that means in practice:

- **Experience is shared.** When the party wins a fight, the number on the
  reward screen is added to *every* eligible character in full, so a character
  in a party of four gains exactly as fast as one adventuring alone.
- **You must be upright to collect it.** A character who is dead, stoned,
  frozen or paralyzed at the end of the fight is skipped and gets *nothing*
  from that kill. The same four states also stop you being counted as ready to
  train.
- **The ladder is a running total** of experience earned.
- **There is a fixed amount of it.** Every monster in the game stands on one
  cell of one map, and a monster you kill does not come back. There are 1,862
  of them and they pay 13,322,378 experience between them. That is the whole of
  what the game holds. Walk away from a monster you have not killed and it
  returns to its post, so nothing is lost by leaving; nothing is gained by
  going back over ground you have cleared.
- **You can bank several levels.** The screen shows the highest level you have
  earned, but a trainer sells one level per visit. Fall four levels behind and
  you pay four times.

### 2. Find a trainer who is good enough

Every trainer has a level of their own and will not take you past it:

> Unfortunately, I can only train you through level 12.

So a run of levels usually means a trip to a bigger town. Look for the better
trainer *before* banking a lot of experience.

### 3. Pay

Training costs **100 gold × the trainer's own price factor × the level you are
training away from**. The factor varies from trainer to trainer, so the number
you actually see depends on who you are standing in front of; the shape is
always the same, and it climbs steadily with your level:

**Every trainer in the game carries a factor of 5 or 10.** The factor-5
trainers all stop at level 25, so through level 24 there are two prices for a
level-up and from 25 on there is only the one:

| Training | Factor 5 | Factor 10 |
|---|---|---|
| 1 → 2 | 500 | 1,000 |
| 5 → 6 | 2,500 | 5,000 |
| 10 → 11 | 5,000 | 10,000 |
| 20 → 21 | 10,000 | 20,000 |
| 24 → 25 | 12,000 | 24,000 |
| 25 → 26 | no trainer | 25,000 |
| 39 → 40 | no trainer | 39,000 |

The panel's Leveling tab lists every trainer, the levels it covers and its
factor.

Turn up short and you get "You don't have enough gold." Nothing is spent and
nothing is lost.

### 4. What the level itself gives you

The moment the gold changes hands:

- **Your level goes up by one.**
- **You are healed to full.** Your maximum health rises by **30% of your
  stamina**, and your current health is set to the new maximum. A trip to the
  trainer is also a free stay at the inn.
- **Spellcasters gain magic points.** See the table below. Fighters,
  Merchants and Rogues gain none, ever.
- **Every attribute and every usable skill goes up by 2.** Over thirty-nine
  trainings that comes to **+78 in everything**.
- **On even levels you may learn spells**, up to two of them, and the game
  says "You have learned some spells".
- **At level 10 and again at level 30 you are promoted** and take a new title.
- **You are given bonus points to spend.**

---

## Bonus points

Bonus points are the part of a level-up you choose. Leveling hands you +2 in
everything regardless, which over a career outweighs every point you ever place
by about three to one, and nearly every threshold in the game arrives on that
free growth alone.

What points are for is the handful of places that free growth does not reach.

### Levels and points both stick

A level adds 2 to every attribute and every usable skill. Bonus points add
wherever you put them. Both are permanent, and a single stat caps at 999.

**Over a full career that free +2 comes to +78.** Thirty-nine trainings carry
you from level 1 to level 40, and every one of them adds 2 to all six
attributes and to each of the twelve skills you are not sitting at zero in. A
character who rolled between 45 and 60 finishes somewhere between 123 and 138
in everything.

That is 1,404 points of growth handed over for free, against roughly 500 you
ever get to place yourself, **about three to one in leveling's favor**. It
is also why the game's own thresholds sit where they do: bartering pays rungs
at 101, 125 and 150, and linguistics at 115, 120 and 125.

Health and magic points are the exception. They do not take the +2. They grow
by their own percentages instead, 30% of stamina and a share of intelligence
or wisdom.

What limits you is the budget: about 500 points across a whole run, against 18
stats you might want to raise.

A stat knocked down by a poison or a curse is not permanent damage. Resting
puts it back.

### Where they come from

> Bonus points = 13% of your charisma, rounded, and never more than 15.

Practically, from the 45 to 60 charisma a new character rolls:

| Charisma | 45 | 55 | 65 | 75 | 85 | 95 | 105 | 112+ |
|---|---|---|---|---|---|---|---|---|
| Points | 6 | 7 | 8 | 10 | 11 | 12 | 14 | 15 |

Your charisma rises by 2 every level like everything else, so the points per
training grow with you: about 6 to 8 at first, and the 15-point ceiling arrives
somewhere around level 27 to 35 depending on your starting roll. Over a full run
from level 1 to level 40 you will be handed roughly **420 to 480 points in
total**.

The 13% is read from your **base** charisma, the value leveling and bonus
points raise. A point spent on charisma therefore raises the payout at every
training after it.

### What you can spend them on

Eighteen things, and any character can raise any of them:

**Attributes.** Strength, dexterity, stamina, intelligence, wisdom, charisma.

**Skills.** Survival, projectile, slashing, bashing, polearm, casting,
mapping, navigation, bartering, repair, thievery, linguistics.

Left-click a line to put a point in, right-click to take it back out, and
click Close when you are done. Health and magic points are not on the list.
Those come only from the formulas above.

---

## Where your skills come from

**Skills are not rolled.** Every one of the twelve is computed from your
attributes at the moment the character is made, by a fixed recipe, plus a flat
adjustment for your class. Two characters of the same class with the same
attributes get identical skills every time. There is no luck in this step at
all.

So the attribute roll decides your starting skills as well as your
attributes.

**And it happens once.** The recipes run when your attributes are rolled and
never again, so raising strength later does *not* raise your bashing, and
twenty bonus points into dexterity will not move thievery by a single point.
After creation, attributes and skills are separate: skills grow on their own,
2 a level, and by bonus points spent directly on them.

Three things do keep tracking your attributes: your carrying capacity, which is
always your current strength in weight units, stored as ten times strength
against weights in tenths, plus strength's contribution to your
damage and dexterity's to your absorption. Those are recalculated every time
you spend a point, change equipment or gain a level. Nothing else is.

### The recipes

Each part is rounded on its own before they are added, which is where a stray
point either way comes from.

| Skill | Built from | Class adjustment |
|---|---|---|
| Survival | 10% strength + 30% dexterity + 60% stamina | Fighter +5, Merchant +4, Rogue +3, Marksman +2, Paladin +1 |
| Projectile | 80% strength + 20% dexterity | Fighter +5, Rogue +5; Monk, Alchemist, Mage, Druid −5 |
| Slashing | 20% strength + 80% dexterity | Fighter +5; Monk, Alchemist, Mage, Druid −7; Paladin, Marksman −5 |
| Bashing | 100% strength | Fighter +5; Monk, Alchemist, Mage, Druid −7; Paladin, Marksman −5 |
| Polearm | 50% strength + 50% dexterity | Fighter +5; Monk, Alchemist, Mage, Druid −7; Paladin, Marksman −5 |
| Mapping | 90% intelligence + 10% wisdom | Mage +5, Druid +3, Marksman +3; Fighter, Alchemist, Paladin −5 |
| Navigation | 100% dexterity | Paladin +5, Marksman +5, Merchant +3, Rogue +3 |
| Bartering | 85% charisma + 15% intelligence | Merchant +5, Fighter −5 |
| Repair | 80% dexterity + 20% intelligence | Merchant +5, Rogue +3; Monk −10, Marksman −5 |
| Thievery | 100% dexterity | Rogue +5; Mage −5, Fighter −10 |
| Linguistics | 70% intelligence + 30% wisdom | Druid +5, Mage +3; Merchant, Paladin, Marksman −5 |

Casting is set up differently at creation, described below. Only its starting value
is unusual: from then on it is an ordinary skill, gaining 2 a level and taking
bonus points like any other.

Some things worth reading off that table:

- **Dexterity feeds more skills than any other attribute.** Slashing,
  polearm, navigation, repair and thievery outright, and projectile and
  survival partly.
- **Strength is a fighter's attribute twice over.** Bashing is pure strength,
  and projectile leans on it more than on dexterity.
- **Intelligence does double duty for a caster**: magic points *and* mapping
  and linguistics.
- **Charisma pays twice too.** It is 85% of bartering, and it sets your bonus
  points every level.

### Skills your class starts at zero in

For a few class-and-skill pairs the recipe is thrown away and a fixed number
stored instead. Leveling skips any skill sitting at zero, so an untouched zero
is still zero at level 40.

| Skill | Locked at 0 for | Fixed at 40 for |
|---|---|---|
| Casting | Fighter, Merchant, Rogue | none |
| Bartering | Marksman | Monk, Mage |
| Repair | Paladin | none |
| Thievery | Monk, Druid | none |
| Linguistics | Fighter, Rogue | none |

None of the zeroes is permanent: one bonus point starts any of them growing at
the usual 2 a level. Bought at the first training the skill reaches 77 by level
40; bought at level 20 it reaches 41, which is below the rungs that repair and
linguistics pay at.

The two 40s are a different case. A Monk or a Mage always starts with bartering
at exactly 40, however charismatic they are. It climbs normally from there.

Note what this costs a party. A Monk or Druid who never spends the point
cannot pick a lock at all, and a Rogue starts a full 15 points ahead of a
Fighter (+5 against −10), so who you bring still decides whether locked chests
are a nuisance or an errand.

Linguistics is the same case: a party of Fighters and Rogues starts with
nobody who can read, and stays that way unless somebody spends a point to
start the skill growing.

### Casting, magic points and starting health

Casting and your starting magic points come from one number, blended per class
the same way the per-level magic gain is:

| Class | Blend | Casting | Starting magic |
|---|---|---|---|
| Monk | all wisdom | blend + 10 | a quarter of the blend |
| Mage | all intelligence | blend + 10 | a quarter of the blend |
| Alchemist | 75% wisdom + 25% intelligence | blend + 5 | a quarter |
| Druid | 75% intelligence + 25% wisdom | blend + 5 | a quarter |
| Paladin | half wisdom | roughly double the blend | a quarter |
| Marksman | half intelligence | roughly double the blend | a quarter |
| Fighter, Merchant, Rogue | none | 0 | 0 |

So a Mage with 60 intelligence starts at casting 70 with 15 magic points, and
a Paladin with 60 wisdom starts at casting 60 with 7.

That blend decides the starting number and nothing after it. **Casting is a
normal skill from there**: it appears on the bonus-point screen like the other
eleven, takes points one at a time, and gains 2 at every level. A Mage starting
at 70 reaches 148 by level 40, so casting meets the same breakpoints a weapon
skill does.

**Starting health is 25% of stamina**, while every level after that pays 30%
of stamina. So the first level-up more than doubles your health, and no later
one comes close in proportion.

---

## Using items

Three gestures, and the one that uses an item is the right button:

- **Left-click** picks an item up and drops it. That is also how you equip:
  drag it onto the right slot (helmet on the head, weapon left of the legs,
  shield right of them, projectiles left of the head, container right of it),
  or drop it on the portrait and the game puts it in the first slot that will
  take it.
- **Double-left-click** on an item shows its description. On a spell it casts
  it; on a portrait it opens the character's stats.
- **Right-click** uses it: drink the potion, open or close the container,
  repair the broken item. In the playing area it uses whatever is in front of
  you, which is what `SPACE` does from the keyboard. On a portrait it toggles
  that character's inventory panel, and double-right-click toggles all four
  (`P`).

Nothing else uses an item. The keyboard has three shortcuts and they are for
named quest items only: `K` keyring, `M` party map, `T` hourglass.

### Learning a spell from a scroll

Right-click a magic scroll and the game asks whether to `USE ITEM?` or
`LEARN SPELL?`. Learning consumes the scroll and is permanent: the spell joins
that character's list and is cast from there afterwards.

A character can learn a scroll's spell once their class has reached the level
the clue book lists beside SCROLL on the spell's page. Those levels run lower
than the training levels for the same spell, a median of 13 against 18, and 15
spells have no training route at all, so for those the scroll is the only way to
get them.

## What things cost

Every service an NPC sells is quoted by one formula:

> **price = a base for the service × that NPC's own factor × your current level**

The base is the only part that changes between services. The factor varies
from NPC to NPC, so the same service costs different amounts in different
towns. And because your *level* multiplies everything, **every service gets
steadily more expensive as you grow**.

| Service | Base |
|---|---|
| Train one level | 100 |
| Raise the dead | 100 |
| Replenish health | 20 |
| Buy a bonus point | 1,000 per point |
| Cure conditions | see below |
| Completely restore | cures + 20 if hurt + 100 if dead |

The factors carried by the NPCs who charge for anything are 2, 3, 4, 5, 10, 40
and 50, so the same service can differ twenty-five fold between two towns.
Trainers carry 5 or 10.

Buying bonus points is the exception: for that NPC the field that would be the
factor holds the number of points handed over instead, so the price is a flat
1,000 per point per level.

The panel's Leveling tab lists every trainer, what each will train you through,
and what a training costs at each level.

### Curing conditions

The shop adds up a weight for each condition you are actually suffering, and
that sum is the base:

| Condition | Base | | Condition | Base |
|---|---|---|---|---|
| Sickness | 5 | | Stoning | 60 |
| Poison | 10 | | Jinxing | 20 |
| Disease | 20 | | Hexing | 30 |
| Paralyze | 40 | | Cursing | 40 |
| Frozen | 50 | | | |

All nine at once is a base of 275, which goes through the same factor and level
multipliers as everything else. **Stoning, frozen
and paralyze are also the three that stop you training or earning experience**,
so those are the ones to clear first; the rest can wait for a cheaper level.
They are also among the most expensive to cure, at 60, 50 and 40, matched only by
cursing.

"Completely restore" charges the cure total plus 20 if you need healing plus
100 if you are dead, quoted through the same formula and paid in one
transaction.

### Supplies are the exception

Food and nuore are **10 gold a unit, flat**, with no NPC factor and no level
multiplier, minimum ten units a purchase. Alone among the services, they cost
the same at level 40 as at level 1.

### What bartering actually does

Bartering does not discount a price. It sets **a spread either side of the
item's own value**, and it moves both halves at once:

> you pay **(100 + spread)%** to buy, and are paid **(100 − spread)%** to sell

The spread comes off a seven-rung ladder, and the rungs are far apart:

| Bartering | Spread | You pay | You get | A 1,000-gold item |
|---|---|---|---|---|
| up to 54 | 55% | 155% | 45% | pay 1,550, get 450 |
| 55-64 | 45% | 145% | 55% | pay 1,450, get 550 |
| 65-79 | 35% | 135% | 65% | pay 1,350, get 650 |
| 80-100 | 25% | 125% | 75% | pay 1,250, get 750 |
| 101-124 | 15% | 115% | 85% | pay 1,150, get 850 |
| 125-149 | 8% | 108% | 92% | pay 1,080, get 920 |
| 150+ | 2% | 102% | 98% | pay 1,020, get 980 |

Selling is where it bites. Between the worst rung and the best, the same item
fetches **more than twice** the gold.

**Only the selected barterer's skill is read**, meaning the character you
highlighted or the one you name when the shop asks. Nobody else's bartering matters.

### When each class reaches a rung

Bartering climbs 2 a level like every other skill, so a class reaches each rung
on its own at a fixed level:

| Barterer | Starts | 80 (25% spread) | 101 (15%) | 125 (8%) |
|---|---|---|---|---|
| Merchant | 65 | level 9 | level 19 | level 31 |
| Rogue, Alchemist, Paladin, Druid | 60 | level 11 | level 22 | level 34 |
| Fighter | 55 | level 14 | level 24 | level 36 |
| Monk, Mage | 40 | level 21 | level 32 | out of reach |
| Marksman | 0 | never, unless a point is spent first | | |

A five-point class adjustment is worth two or three levels of head start on each
rung. Bonus points bring a rung forward and do nothing else.

### Not yet worked out

The exact base costs for repairing and enhancing an item are computed from
tables that have not been decoded, though both are scaled by the same shop
factor as everything else.

---

## Resting, food and nuore

Your party shares three pools: **gold**, **food** and **nuore**. None of them
belongs to a character; all three are spent from one purse.

### What resting does

A rest takes **eight hours** and **eats one food per character who is able to
take it**. Anyone dead, stoned, frozen or paralyzed neither rests nor eats.

What you get back is a share of your maximum, set by how well you ate:

> restored = (100 ÷ able characters) × food actually eaten, as a percentage of
> **each character's own maximum** health and magic

Feed everybody and it is a full recovery of health *and* magic, for the whole
party, for the price of four units of food. Come up short and everyone gets
the same reduced fraction: two food between four characters restores half.

### Rest with a condition and you waste the food

**Six of the nine conditions block the restore completely**: sickness,
poison, disease, jinxing, hexing and cursing. You still spend the eight hours,
you still eat the food, and you recover nothing at all.

Worse, two of them charge you for the privilege:

| Condition while resting | What it costs |
|---|---|
| Sickness | cured by the rest |
| Jinxing | cured by the rest |
| **Disease** | **−36 health**, and it can kill you outright |
| **Cursing** | **−48 magic** |
| Poison, hexing | no restore, no further harm |

So the order is: cure first, rest second. Resting a diseased character
repeatedly will kill them, and the cure costs 20 base, a fraction of the
raise-dead you would otherwise be paying for.

### Nuore

Nuore is the party's shared magic fuel. **Every spell costs two things**: magic
points from the caster, and nuore from the party pool. A cast is refused if
either is short, so a caster with a full magic bar and an empty purse of nuore
cannot cast at all.

In practice magic points run out first, since what a fight drops normally
covers what it cost to cast. Nuore is bought like food, **10 gold a unit,
minimum ten units, no markup and no level multiplier**. Some fights carry no
rewards at all and refund nothing.

---

## What the skill numbers mean

The clue book gives you numbers with no scale. Here is what they are measured
against.

### The one roll behind most of them

Picking a lock, disarming a trap, shrugging off a poisoning and sizing up a
monster all go through the same piece of arithmetic:

> **your chance = skill + 5 × (your level − the difficulty)**, never less
> than 5. A d100 is then rolled and you succeed if it comes up at or under
> that chance.

That d100 is loaded the same way the attack roll is. It draws 0 to 127 and
folds 101 to 127 back onto 1 to 27, so the low numbers come up twice as often
and every chance succeeds more than its face value:

| Your chance | 5 | 20 | 40 | 50 | 60 | 80 | 100 |
|---|---|---|---|---|---|---|---|
| Actually succeeds | 9% | 32% | 53% | 61% | 69% | 84% | always |

Two things follow:

- **A level is worth five skill points** on every one of these, on top of
  the 2 the skill itself gains. A character five levels above a lock is fifty
  points better at opening it than one standing level with it.
- **You always have a chance and never a certainty below 100.** The floor of 5
  means even a hopeless attempt works about one time in twelve. A chance of
  100 or more is a certainty.

### Thievery: locks and traps

Both use the roll above against the lock's or trap's own difficulty, and both
read the **selected** thief. A failed lockpick breaks the lockpick; a failed
disarm sets the trap off.

Every skill gains 2 a level, but thievery gains twice over: the check adds
five points per level on top. A well-leveled character with mediocre thievery
will out-pick a specialist who has stood still.

### Repair: five brackets

The repair check reads your skill alone and ignores your level. The skill still
climbs 2 a level, so you move up the brackets as you go. There are **five
brackets**, and which one you fall in decides the odds outright:

| Repair skill | Bracket |
|---|---|
| under 50 | worst |
| 50-64 | second |
| 65-79 | third |
| 80-94 | fourth |
| 95 and over | best |

The odds also depend on how hard the item is to mend. For the easiest kind of
item, the brackets run: 20% destroyed / 31% repaired at the bottom, and **100%
repaired, no risk, at 95+**. For the hardest kind they run from *99% destroyed*
at the bottom to 100% repaired at 95+.

So a failed repair is not always harmless: below 50 skill it destroys the item
one time in five on the easiest items and almost every time on the hardest.
There is also a daily limit, and the game tells you how many uses remain
today.

### Linguistics: four grades, and a floor you must clear

Linguistics ignores your level too. There are three languages of increasing
difficulty, and for each one your skill buys one of four grades of
translation, or nothing at all:

| | Nothing | Grade 4 | Grade 3 | Grade 2 | Full |
|---|---|---|---|---|---|
| Easy tongue | under 80 | 80-84 | 85-89 | 90-94 | 95+ |
| Middle tongue | under 90 | 90-94 | 95-99 | 100-114 | 115+ |
| Hard tongue | under 100 | 100-114 | 115-119 | 120-124 | 125+ |

A fresh character starts around 55 to 65, so **nobody can read anything at the
start of the game**. It gains 2 a level like everything else, so the easy
tongue comes into range on its own somewhere around level 9 to 16, and the
hardest around level 31 to 38. Bonus points only buy that sooner, roughly 20
of them to read the easy tongue immediately.

### The three skills the whole party shares

Survival, mapping and navigation are **averaged across the party**, and only
across the members still standing, since anyone dead, stoned, frozen or
paralyzed drops out of the average altogether. Losing your best mapper mid-dungeon
takes the map with them.

Each average buys graded results:

| Average | Mapping | Navigation | Survival |
|---|---|---|---|
| 45 | first map detail | | |
| 50 | more | | |
| 60 | more | | first monster details |
| 65 | | wider travel range | |
| 70 | more | | |
| 75 | | | more details |
| 80 | full map detail | wider still | full details |
| 95 | | widest range | |

Because these are averages, **it makes no difference which character holds the
points**. In a party of four, four points spent anywhere lift the average by
one, whether they all go into your mapper or one each across the party. That is
the exact opposite of the four selectable skills, where only the chosen
specialist's own number is read and spreading points is wasted.

They also climb on their own, 2 a level each, which for an average means 2 a
level flat. A party starting near 60 reaches the fullest map at about level 11,
the widest travel range at about level 18, and everything survival will tell
you at about level 10. All three arrive without any points spent. Points
here only bring a rung forward, at four of them, from anybody, per point of
average.

### Conditions, and the protections that stop them

An attack that inflicts a condition is resisted by the same d100 roll, with
your **protection** against that specific condition standing in for the skill.
Each of the nine has its own protection value, and only the matching one helps:

| Condition | Cure costs | Stops you training |
|---|---|---|
| Sickness | 5 | |
| Poison | 10 | |
| Disease | 20 | |
| Jinxing | 20 | |
| Hexing | 30 | |
| Paralyze | 40 | **yes** |
| Cursing | 40 | |
| Frozen | 50 | **yes** |
| Stoning | 60 | **yes** |

The three that stop you training are among the most expensive to cure, and they stop
you collecting experience from a fight and drop you out of the party averages
as well.

**A condition never scales. It lands whole or not at all.** Absorption is not
consulted anywhere in the resist chain; only the nine protection values are. So
once an attack connects, thick armor does nothing to soften what it inflicts.

**But an attack that misses inflicts nothing.** The effect is applied inside a
branch that the game only reaches when the attack did damage. A miss jumps
past it and the resist roll never happens. That is true in both directions,
you against a monster and a monster against you.

So the absorption that makes you unhittable makes you **immune to every
condition in the game at the same time**, and it is the only defense that does.
Protections reduce your chances one condition at a time; a negative margin
removes the question.

Only a handful of monsters inflict the three conditions that take a character
out of a fight. A character carrying one is skipped by the turn list entirely, earns nothing from the fight,
drops out of the party averages, and cannot be trained until it is cured, and
stoning is the most expensive cure in the game.

Because a miss inflicts nothing, absorption above the accuracy of whatever
carries the attack shuts it out completely.

---

## Combat, and the five numbers behind it

The character screen shows **accuracy**, **damage** and **absorption** without
saying where any of them comes from. There are actually five such numbers,
with two more for shooting that the screen does not print, and they are rebuilt
from scratch every time you change equipment.

| Number | Built from |
|---|---|
| Ranged accuracy | your **projectile** skill |
| Ranged damage | your equipped **missile weapon** |
| Accuracy | the **weapon skill matching the weapon in your hand** |
| Damage | that weapon's damage, plus a strength bonus |
| Absorption | your armor, plus a dexterity bonus |

### Your weapon decides which skill counts

Every hand weapon is stamped as a slashing, bashing or polearm weapon, and
**the matching skill becomes your accuracy**. A knife draws on slashing, a club
on bashing, a bo stick on polearm. You fight at the skill the weapon calls
for.

All twelve skills gain their 2 a level whether you use them or not, so an
unused weapon skill keeps pace with the one you fight with. What it does not
receive is bonus points, so the two diverge by however many you have spent.

The character sheet gives no warning when you swap: the accuracy number simply
sits lower. The original manual's pairing of knife with slashers, club with
bashers and bo stick with polearm is naming which skill each weapon will read.

### The strength and dexterity bonuses start at zero

Strength adds to your damage and dexterity to your absorption. No other
attribute touches a combat number. Both work the same way, **only
above 72** and then only a fifth of the excess, so one table serves for each:

| The attribute | What it adds |
|---|---|
| up to 72 | **0** |
| 75 | 1 |
| 80 | 2 |
| 90 | 4 |
| 100 | 6 |
| 138 (a level-40 character) | 13 |

Characters roll between 45 and 60, so both bonuses start at zero. The +2 a
level carries you over 72 somewhere between level 7 and level 15 without any
effort, and to about +13 by level 40.

**The bonus lands only on multiples of five.** It is a step function
and the steps land on 75, 80, 85, 90, 95 and so on. Every value in between
buys nothing at all:

| Dexterity | 75 | 76 | 77 | 78 | 79 | 80 |
|---|---|---|---|---|---|---|
| Absorption | **1** | 1 | 1 | 1 | 1 | **2** |
| Points wasted | 0 | 1 | 2 | 3 | 4 | 0 |

The steps sit there rather than at 77, 82 and 87, where the excess over 72
divides by five exactly, because the game rounds to nearest rather than down.
Its percentage helper adds half the divisor before dividing, so an excess of 3
becomes `3 × 20 + 50 = 110`, then `÷ 100 = 1`. **You are handed the
point at six-tenths of it.** Climbing to a clean 1.0 at dexterity 77 costs two
more points for the same absorption.

A dexterity that does not end in a 0 or a 5 therefore has between one and four
dead points sitting in it.

The two bonuses sit against different ceilings. Thirteen damage joins a weapon
that reaches 40. Thirteen absorption joins armor that stops at 161, and once
every slot is filled and enchanted the fifth-of-the-excess is the only source of
absorption left.

### How an attack is settled

One piece of arithmetic decides every attack in the game: your sword, your
sling, your spells, and everything swung back at you.

> **margin = your accuracy − their absorption**
>
> A negative margin can never hit. Otherwise roll a d55: you hit if the margin
> is at least the roll. **On a hit you deal `margin`% of your damage**, and
> never less than 1.

The margin does both jobs. It is your chance to connect *and* the fraction of
your damage that lands, so the two multiply:

| Margin | Chance to hit | Damage dealt | Average output |
|---|---|---|---|
| 10 | 30% | 10% of your damage | 3% |
| 20 | 45% | 20% | 9% |
| 30 | 61% | 30% | 18% |
| 40 | 77% | 40% | 31% |
| 50 | 92% | 50% | 46% |
| **55** | **always hits** | 55% | 55% |
| 100 | always | 100% | 100% |
| 200 | always | **200%** | 200% |

**Twenty points of margin roughly triples your output**, because it buys you
the hit and the damage at the same time. Once the margin reaches 55 you can no
longer miss, and every point past that is pure damage.

The d55 is not an even die. The game builds its random numbers by masking to
the next power of two and folding the overshoot back, so a d55 is really a d64
with 56 to 63 landing on 1 to 8, so those eight numbers come up twice as often
as any other. The chance of a hit is `(margin + 1 + min(8, margin)) / 64`, which
is the column above. Two things follow: the first eight points of margin are
worth about twice what the ninth is, and a margin of 55 still ends the misses.

Note that the margin is a *percentage of your damage*, so **accuracy and your
weapon multiply each other**. Neither is worth much alone: a 2-Handed Sword +10
in the hands of someone fighting at margin 20 delivers 8 of its 40, while
perfect accuracy with a knife delivers all of 3. An upgrade to either one
raises the value of the other by the same proportion.

**The weapon is the half that runs out.** Gold takes it from 3 to 40 over the
career and then stops, while accuracy keeps climbing to whatever you pay for.
Past the point where the weapon is already delivering in full, further accuracy
is only buying the margin term.

Which numbers get used depends on how you attack:

| Attack | Accuracy | Damage |
|---|---|---|
| Hand weapon | your accuracy | your damage |
| Missile weapon | your ranged accuracy | your ranged damage |
| **Spell** | **your casting skill** | the spell's damage |
| A monster's attack | its own accuracy | its own damage |

### What absorption does

Absorption is subtracted from the attacker's accuracy *before* the roll, so it
does two jobs at once, the same way the margin does: it makes you harder to hit
**and** it shrinks what lands when you are hit.

That compounds. Against an attacker with accuracy 80 and damage 20:

| Your absorption | Chance it hits you | Damage if it does | Average taken |
|---|---|---|---|
| 20 | always | 12 | **12.0** |
| 40 | 77% | 8 | 6.1 |
| 50 | 61% | 6 | 3.7 |
| 60 | 45% | 4 | 1.8 |
| 70 | 30% | 2 | 0.6 |
| 80 | 2% | 1 | **0.02** |

Twenty points of armor cuts the damage you take by about **three times**, not
by twenty. Past the attacker's accuracy it stops them almost entirely.

It is the same number against a sword, an arrow and a fireball. One defense
covers everything, so armor bought for one threat is armor against all of
them.

Note what that means for casters. **Casting scales the damage of every spell
you throw as well as deciding whether it lands.** A caster with poor casting
misses more and hits for less when it connects.

### The margin is the only multiplier

The resolver rolls once and multiplies once. The margin is that multiplier, and
it is continuous, so a large accuracy advantage pays on every swing.

Damage only ever moves the other way. Monsters carry special attacks that
replace their damage with a fixed amount or leave a wound that bleeds for a set
number of turns, and a monster can resist what you are hitting it with.

### Resistance halves damage

Some monsters shrug off a kind of attack and take **half** the damage from it.
It is always half. A monster that resists two things about the same attack
still takes half, not a quarter.

What can be resisted:

| Attack | Can it be halved? |
|---|---|
| A spell | yes |
| A shot | yes |
| A hand-to-hand swing | **no, never** |

**A hand weapon is the one attack in the game that nothing shrugs off.** No
monster resists it and no monster can.

An enchanted bow counts as magic as well as a shot, so anything that resists
either one halves it. Against a monster that shrugs off magic, the enchantment
on a bow works against you.

Resistance is listed on the monster's page in the clue book, and on the
panel's Monsters tab.

When a character's health reaches zero they are marked dead, drop out of the
party averages, stop earning experience, and lose whichever of the four
selectable skills they were carrying, so a death can take your barterer or your
lockpicker out of the party as well.

### Who gets attacked

The party is one point on the map. Range is measured once, from the party's
position to the monster's, so hand-to-hand and shooting are properties of the
encounter rather than of a character: everyone is the same distance from
everything.

A monster choosing a victim rolls a number from 0 to 3, indexes the party by
it, and rolls again if that slot is empty or holds someone dead, stoned, frozen
or paralyzed. **Every able character is equally likely to be hit, whatever slot
they are in.**

Two things follow. Health and absorption are worth the same on any character,
because none of them can be put where the blows land. A fighter cannot stand
between a monster and your mage. And a caster's survivability is a real
purchase rather than a hedge: with four characters in the pool, a quarter of
everything thrown at the party arrives at the one with the lowest absorption.

### Shooting and attacking are exclusive

Your two attack commands split on that same distance, and only one of them is
live at a time. `S` shoots, and works only while nothing has closed to
hand-to-hand. `A` attacks, and works only while something has. Each tests the
same flag in the opposite sense, so **pressing the wrong one does nothing at
all**: no message, no turn spent, no wasted round. Two of the magic
projectiles refuse to fire in hand-to-hand for the same reason.

The two also differ in who acts. Shooting is the whole party: it walks the four
slots, takes a shot from every able character carrying a projectile, and
resolves them one after another, each with that character's own ranged
accuracy and ranged damage, drawing the four shots under the four panels.
Hand-to-hand is one character against one monster. Up to three monsters can
be engaged at once and you choose which to swing at, but the swing is a single
character's, settled with their accuracy and their damage.

### Turn order

The game builds one list holding everybody, your party first and then the
monsters, and bubble-sorts it into **descending order of current dexterity**.
That is the whole of initiative, and **the list is rebuilt every round**. The
round driver at image `0x00a20` calls the builder each time through, so this is
not a question of who opens the fight but of who acts first in every round of
it.

Three details fall out of how it is built:

- **Anyone dead, stoned, frozen or paralyzed is left out of the list
  entirely.** They do not get a slow turn; they get no turn.
- **Ties go to the party.** Characters are added before monsters and the sort
  only moves an entry when the one behind it is *strictly* faster, so a monster
  matching your dexterity still acts after you.
- It reads your dexterity as it stands, which both leveling and bonus points
  raise.

Dexterity stopped feeding your skills at creation, so a point bought now goes
to two places at once: this list, and absorption at a fifth of whatever the
point puts over 72.

**Dexterity buys priority.** The list holds one entry per able character and one
per engaged monster, four and up to three, so at most seven, and the round
walks it forward once. However fast you are, you act once and then wait.

When an actor dies their entry is flagged and skipped, so a monster killed
before its entry comes up loses the whole round. A party that kills each
monster in the round it arrives takes no damage at all.

What the game asks of you climbs faster than the +2 a level you get for free,
so left alone **you are slower than what you fight**. Keeping pace has to be
bought, a little at a time.

### Where accuracy and defense actually come from

The three numbers have separate sources:

| | Main source | Secondary | Range across a career |
|---|---|---|---|
| **Accuracy** | your weapon skill | a few items grant 5-10 points of a skill | 60 at level 1, 131-148 at level 40 |
| **Damage** | your weapon | strength, above 72 | 3 to 30 one-handed, 40 in two hands |
| **Absorption** | your armor | dexterity, above 72 | 0 to 161 from armor, and dexterity carries it past that |

Two of the secondary sources are small. Nine of the game's 304 items add
anything to a skill, the largest being 5 polearm and 10 casting; and the
strength bonus reaches 13 by level 40, against a weapon that reaches 30.

Dexterity is the exception, because armor has a ceiling and the weapon does
not. The slots hold 161 absorption and no more, so at the top of the game
dexterity stops being a trickle and becomes the only supply.

So **damage is bought and accuracy comes from levels and points, while defense
starts as gold and finishes as points.** Gold moves your weapon and your armor
by two orders of magnitude over a playthrough and barely touches how often you
connect.

A starting character wears about 5 absorption and can reach 111 across the
slots for 13,075 gold, or 161 with every piece enchanted.

Accuracy is your weapon skill. It starts at your blend plus your class's
adjustment, 65 for a fighter who rolled well and 38 for a mage who did not, and
gains 2 a level like everything else. Bonus points bring that growth forward.
The skill your weapon reads is the one collecting it.

---

## Reference tables

### Magic points per level

Your class blends intelligence and wisdom, then takes 30% of the blend. The
percentages are the ones the original manual describes in words.

| Class | Blend | Magic points per level |
|---|---|---|
| Fighter, Merchant, Rogue | none | none |
| Monk | all wisdom | 30% of wisdom |
| Alchemist | 75% wisdom, 25% intelligence | 30% of the blend |
| Paladin | half wisdom | 30% of the blend |
| Mage | all intelligence | 30% of intelligence |
| Druid | 75% intelligence, 25% wisdom | 30% of the blend |
| Marksman | half intelligence | 30% of the blend |

A Mage with 60 intelligence gains 18 magic points a level; a Paladin with 60
wisdom gains 9.

The blend reads your intelligence and wisdom as they stand, which both leveling
and bonus points raise, so a point of intelligence in a Mage widens the pool at
every training after it.

### Promotions

| Level 1-9 | Level 10-29 | Level 30+ |
|---|---|---|
| Fighter | Warrior | Champion |
| Merchant | Tinkerer | Blacksmith |
| Rogue | Thief | Assassin |
| Monk | Cleric | Priest |
| Alchemist | Transmuter | Healer |
| Paladin | Cavalier | Hero |
| Mage | Wizard | Sorcerer |
| Druid | Enchanter | Sage |
| Marksman | Ranger | Knight |

The title is all that changes. See "Promotions are a new name, and nothing
else" below.

### Spells

Spells arrive **only on even levels**, at most two at a time, from level 2 to
level 40. Which spells depends on your class and not on your promotion. The
game's own clue book shows at most three classes per spell, so it under-reports
Druid and Marksman. The panel's Spells tab lists every class that can cast a
spell and the level each one gets it.

<!-- panel:skip -->
`tools/levels.py` prints the same list.

### Caps, hard and soft

**Hard caps.** Past these the number does nothing at all, and points spent on
it are wasted:

| | Hard cap | What happens there |
|---|---|---|
| Any attribute or skill | **999** | the game refuses to raise it |
| Health, magic points | **9,999** | as above |
| Level | **40** | every rung past it demands 99,999,999 experience |
| Bonus points per training | **15** | reached at charisma 112 |
| Charisma, for bonus points | **112** | the 15 above; more buys nothing |
| Any skill check (locks, traps, conditions) | **chance 100** | success becomes certain |
| Bartering | **150** | the last rung, a 2% spread |
| Repair | **95** | the last bracket |
| Linguistics | **125** | full translation of the hardest tongue |
| Mapping average | **80** | the fullest map |
| Navigation average | **95** | the widest range |
| Survival average | **80** | everything the game will tell you |

**Soft caps.** Here the return changes sharply but never reaches zero, so
carrying on is a judgment rather than a mistake:

| | Soft cap | What changes |
|---|---|---|
| Accuracy | **margin 55** | you stop missing; each further point drops from about 2% of your damage to a flat 1% |
| Thievery | the level term | every level hands you 5 points of check for free, so late characters need fewer |

**Floors.** Numbers that do nothing *until* you reach them: strength adds no
damage and dexterity no absorption until 72, and neither adds a whole point
until 75; linguistics reads nothing below 80; repair has no bracket below 50.

### The experience ladder

Experience is a running total, so each rung is what you need in hand rather
than what the level costs. **Level 40 is the end.** Every level past it demands
99,999,999 experience, which nothing in the game can pay.

The curve steepens sharply at 20 and again at 31. The whole ladder, with the
step between rungs and what a training costs at each, is on the panel's
Leveling tab.

---

## Other ways to raise a character

- **Buying bonus points.** Some merchants sell them outright, at 1,000 gold
  per point per level you already have. That is the only way to add points
  between trainings. The price rises with your level like every other service,
  from 1,000 gold at level 1 to 39,000 at level 39.
- **Challenges.** Certain characters set the party a challenge on one named
  attribute. The challenger record carries that attribute and an amount, so a
  reward on winning is likely, but this was not traced far enough to promise
  what it is.

## Promotions are a new name, and nothing else

At level 10 your class is renamed, and again at level 30: a Monk becomes a
Cleric and then a Priest, a Mage a Wizard and then a Sorcerer, a Fighter a
Warrior and then a Champion. All nine classes have the two extra titles.

It is worth knowing that this is *all* it is. Nothing about the promotion
changes what you can cast, how many magic points you gain, or any other
number. The game stores the promotion inside the class number, and every
piece of code that asks what class you are takes the promotion back out before
it answers. Do not hold a level back, or pick a class, expecting a promotion to
unlock something.

## Changing class after you roll

The creation menu lets you change class after rolling, which is how you put a
good roll on the class that suits it: roll until you like the numbers, then see
which class they fit. As shipped this does not work, because picking the replacement
class rerolls everything, and the roll you were trying to keep is gone. (The
class *list* is safe; the reroll happens on the pick, so RETURN costs you
nothing.)

The `keep-roll-on-class-change` patch fixes it, and `make patched` applies it:

    make patched          # writes tmp/game-patched, leaving game/ untouched

Changing class then keeps the six attributes and recomputes everything that
actually depends on class: the twelve skills, health, magic points and casting.
ROLL ATTRIBUTES still rerolls when you want it to.

## Keeping the characters you create

Characters you create do not last. Keep one, play, save the game, and the next
time you reach the main menu, Assemble a Party offers only the four the game
ships with. Nothing you did was wrong: the game keeps its roster in `CURGAME`,
and it rebuilds the whole of that file from scratch at every launch and again
whenever you pick NEW GAME. Nor does it ever read the roster back out of that
file, so no amount of backing `CURGAME` up will help.

The roster the game *restores from* lives in `WORLD.DAT`. Put a character
there and it is in Assemble a Party for good:

    make characters FROM=game/CURGAME

Run that after a session in which you kept someone. It writes into free roster
slots only. The four stock characters and your earlier creations are left
alone, so they build up over several sessions, five in all. The original file is
kept beside it as `WORLD.DAT.orig`.

In the browser cabinet, the **Keep characters** button does the same thing: it
reads the roster out of the running game and stores it, and the characters are
in the roster from the next start. It cannot take effect on the game already
running, because `WORLD.DAT` was handed to the emulator when it booted.

---

*Written from the game's code. If a number here disagrees with the game, the
game is right and this file has a bug.*

<!-- panel:skip -->
*`docs/leveling.md` shows where each number came from.*
