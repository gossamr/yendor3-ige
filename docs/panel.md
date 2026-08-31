# The Restoration panel

The panel renders the clue book as a modern page, built from `data/*.json`. This document records settled findings only. It states what the panel is, and the invariants that [tools/panel_check.js](../tools/panel_check.js) asserts.

## The two builds

One CSS file and one JavaScript file produce both builds.

| | Size | Tables | Distributable |
|---|---|---|---|
| `web/restoration.html` | 1.8 MB | inlined | no, because it holds the game's content |
| `web/panel.html` | 418 kB | fetched at run time | yes |

Both sizes are what `make panel` last wrote, and both move as the panel does. [tools/build_panel.py](../tools/build_panel.py) prints the byte count.

Most of `restoration.html` is the packed map pages, and it opens from disk with no server. `panel.html` is the build that the cabinet loads into its iframe, both from [cabinet/serve.js](../cabinet/serve.js) and from the static `build/pages` site. A host page that sets `window.RESTORATION` before the panel runs suppresses the fetch.

There are six tabs: Maps, Monsters, Spells, Items, Guides and Planner, and a seventh, Cheats, where the page was asked for with `?cheats`. The clue book's own F4 page, Magic Users, has no tab of its own. That page is an index of the spell list by class, which is what the class chips on the Spells tab already provide. No tab draws its own heading.

## The invariants

[tools/panel_check.js](../tools/panel_check.js) renders the page in a browser and fails if any of the following does not hold.

**Maps.**

- The map is drawn on a canvas from `data/map_pages.json`, never shipped as a bitmap.
- The map comes first in source order, before the 37 area names, and the picker is capped and scrollable beside it.
- The caption reads `WORLD.DAT block N, slot M`, not "area/level".
- Legend labels are in one of two states and never in both. The 17 attributed pages show their own labels, and the remaining pages offer only the labels that no page has claimed.

**Monsters and maps, the census.** Every monster stands on a cell of one map and is killed once ([encounters.md](encounters.md)), so a monster's card lists the maps it stands on and a map lists the monsters on it, both counted. Each side carries you to the other, and the check fails if the two disagree on a count. Following either clears the search box, because the search filters every tab and would otherwise send the jump to whatever still matched.

**Spells.**

- One meaning per color. The scope indicator is a neutral shape, either one dot or three, and hue carries the damage element. Whether a spell harms or heals is the same distinction as whether it targets an enemy or a friend, because all 70 damaging spells act on monsters, undead or insects, and all 19 restorative spells act on characters. The element is therefore the only thing that color encodes and nothing else does.
- `#a62424` and `#5959c7` are the game's own inks, and measure 2.5:1 and 3.2:1 against this ground. The panel lifts them for legibility and keeps the hue.
- The cost analysis sits behind an Efficiency disclosure on this tab, scoped by the same class chips that filter the list. [tools/spell_curve.py](../tools/spell_curve.py) computes the same figures offline.

**Items.** The categories use the same `toggle` control as the spell classes. The check fails if the two filter bars diverge.

**Planner.**

- The career runs one row a level from where the character stands to level 40, and the points spent by a level never exceed the points the game has granted by it.
- The evidence names the monster every number came off. With bosses counted, level 40 is measured against Paltivar's accuracy of 240 and absorption of 170.
- Absorption 186 shuts out freezing, paralysis and stoning, and the four monsters behind it are named.

**A finger.** Where the pointer is coarse, every tab is at least 44 pixels tall and every text field is 16 pixels, which is the size below which a phone zooms the page to a field on focus. [tools/mobile_check.js](../tools/mobile_check.js) taps a tab in an emulated phone and fails if one is shorter than 40 pixels.

## The Cheats tab

`?cheats` adds it, and it holds two things behind the same selector the Guides tab uses.

**The trainer** reads and writes the running game's memory, which needs the hooked emulator that `make trainer` builds. Without it the tab holds the save editor alone. [README.md](../README.md) has what it edits.

**The save editor** edits one of the cabinet's saved games. It needs no hook: a save is 81,037 bytes and its first 5,000 are the roster, which is the same 500-byte character record the trainer reads out of memory, at the same displacements ([saves.md](saves.md)). The panel does not reach for the file. The cabinet owns both places a save lives, so the panel asks it: which slots there are, the bytes of one, and the bytes back.

The bytes go back to the emulated disk and to the browser's storage. The disk is what the game's LOAD opens, so an edit that only reached storage would do nothing until the next boot; storage is what the next boot restores, so an edit that only reached the disk would go with the tab. `CURGAME` is not offered, because the game truncates it and rewrites all 81,037 bytes at every launch and the edit would be destroyed unread.

[tools/trainer_check.js](../tools/trainer_check.js) drives both halves in a browser against a running game. For the editor it saves a slot in the game, finds it in the list, places an item in a character's first empty slot, writes the file and reads it back off the emulated disk.

**A write through the running emulator reaches the game.** `ci.fsWriteFile` was measured: a save was put on the disk before boot, loaded in the game, rewritten through the emulator with a character's eight carried slots and its shield cleared, and loaded again. The panel came back with those slots empty and the shield gone.

**The panel is the one the game draws for P.** Eight carried slots three across, then what the character holds down one side, what it carries down the other, and what it wears between them. The game draws the worn pieces on the figure and has artwork for every item; the panel has names and no artwork, so the worn slots stand where the figure does. The ninth cell of the carried grid is drawn empty in the game and is not drawn at all here.

An equipment slot offers the items whose own record names that slot, and a carried slot offers all of them, which is where the game's own equip dispatch puts an item it has nowhere else for. Placing an item writes the slot and its second word and nothing else: the game does its own arithmetic as a character equips something, adding a weapon's damage into the damage rows, and those rows are on the sheet beside the panel. The one rule that is enforced is the one the game enforces in both directions, that a two-handed weapon and a shield cannot be worn together.

**A container is eight more slots.** A bag, a box or a backpack keeps its contents in a record of section 2, named by the slot's second word, and the editor draws that record as a grid of its own under the panel. The game opens a container on its own rather than in the character's column, and that panel is not reproduced: these are the same cells as the carried slots. A container inside a container gets a grid too, since a bag fits in a backpack.

What a container's slot offers is what the item's own FITS IN row names, so a bag takes 201 of the 631 records and a backpack 615, which are the totals [items.md](items.md) reads off the container mask. Placing a container gives it a record the way the game does and clearing one hands the record back, so what was inside is gone with it ([saves.md](saves.md) has the allocator). The counter stops at record 1,295, where the next record would be written over section 3.

## The planner

The Planner tab evaluates goals against one character, level by level. A goal is a number the character has to hold from a level on; the tab says where it holds, where it breaks, what it costs, and which monster set the bar.

**Where the model runs.** The arithmetic is in [web/panel.js](../web/panel.js), because the answer depends on the character in front of it. [tools/combat_model.py](../tools/combat_model.py) is the same model offline, and the tables in `MANUAL.md` and `STRATEGY.md` are computed there. What does not depend on the character is decoded by [tools/planner.py](../tools/planner.py) into the payload's `planner` block: the class table, the armor sets and their prices, the shop's weapons, the incapacitating monsters, and the constants the four formulas read.

**A rate is measured against one monster, a threshold against the worst of each.** Landing every swing on the best-armored thing of a level and being untouchable by the fastest are separate promises, and each has to hold, so a threshold is priced against the highest value of each stat separately. A rate -- kills or spells before a rest -- is not a promise but a fight repeated, and pricing it that way describes a fight nobody has: at level 30 it puts three monsters in front of the character, each carrying the Ice Dwarf's damage, the Ghoul's accuracy and the Fire Giant's health, and every character in the game manages one kill against it. The rates are therefore measured against each monster that is extreme in something, five or six a level, and the worst answer wins: still the worst case, and a fight that exists. The evidence names it.

**A boss counts at the level it is met and not after.** Every other monster keeps standing on its map, so a character meets it from its own level onward and the bars accumulate. A boss is one fight: carrying it forward priced every later level against something the party had already killed, so a level-38 character was told its one-cast kill was about King Slator, who is level 36 and dead. He sets the bars at 36. Paltivar is level 45 and so is met at the cap, which is where the tab has always put him.

**A rate is never counted against a boss, even with bosses counted.** A rate is a fight repeated until the character has to rest, and there is one Paltivar: how many of him fit between two rests is not a question. The switch is about the thresholds, which are promises about a single fight and do have to answer him. So with it on, level 40 is priced against Paltivar's accuracy and absorption and still counts its kills against the Black Dragon.

**The wisps count for the order of the round and for being hit, and for nothing else.** They are fought with weapons bought for them alone, which disintegrate on leaving the plane they stand on, and all 41 of them stand on that one map. What that changes is the damage side: how much has to be dealt to a wisp, and how much absorption stands in the way of dealing it, are questions about a weapon the rest of the plan is not carrying, so a wisp sets neither the health bar nor the absorption bar nor the damage bar, and a rate is never counted against one. It changes nothing about who acts first or about being hit, so a wisp still sets the dexterity a character has to answer to strike first -- 200 at levels 30 and 31, more than anything else there -- and still sets the accuracy it has to armor against.

**What a level is measured against.** Per stat, the highest value among every monster met by that level, which is every listed monster of that level or below. That is not one monster: a character that lands every swing on the hardest monster of its level and misses the one wearing the most armor has not met the goal. Bosses -- the ten food-carriers and Paltivar -- are excluded unless asked for. A monster above the level cap is one a character at the cap meets, which is how Paltivar reaches a level-40 plan.

**A shooter has two attacks and distance says which.** Accuracy and damage come twice in the record, once for the blow and once for the shot, and a monster shoots only while it has not closed: engaged, it swings, and the two never land in the same round. So the pairs are read whole, and melee damage is never priced behind ranged accuracy. A threshold takes each attack's own figure, since one stat at a time is what a threshold asks about; a rate takes whichever whole attack costs the character most, which for a shooter is the worst round of the fight rather than every round of it. The working says `shot` where the shot set the bar.

The two dwarf towers are what this changes for the thresholds. Neither can close, so the melee rows they carry are never reached: the Fire Dwarf Tower shoots at 160 for 115 and swings at 10 for 10. Its shot sets the accuracy bar from level 16 to 25 and the damage bar at 16 and 17, and the Frost Dwarf Tower's 180 sets the accuracy bar again at 29.

For the rates, the other eleven shooters divide three ways. Six carry a shot no better than their blow in either figure -- Castle Guard, Bandit, Dark Elf, Elf Assassin, Dwarf Transmuter and Genie -- so the blow is the worse round at any armor. Fungus is the one whose shot beats its blow in both, 147 for 150 against 144 for 140, and it cannot close either, so the shot is the only round it has. The remaining four trade damage for accuracy, three to five points of accuracy against five to twenty-one of damage, and which round is worse turns on the character's armor, since accuracy is worth more the more of it the armor eats: the shot takes over from 60 absorption for Creeping Fungus, from 90 for Dwarf Alchemist and Sorcerer, and from 100 for Elf Watchman.

**Untouchable and condition proof are both goals.** Both test the same thing, that a monster's margin is below zero, and they differ in which monsters. Untouchable reads everything met by the level. Condition proof reads only the four that freeze, paralyze or petrify -- and only those met by that level, like every other goal, since a character of 24 is not fighting the Ice Dwarf. So the bar rises as they arrive: nothing to answer before 19, the Wizard's 139 from 19, the Purple Dragon's 171 from 26, the Fire Giant's 174 from 28, and 186 from 30, where it stops for good.

Condition proof is therefore the cheaper goal at every level, since its monsters are a subset of untouchable's, and the two coincide wherever the worst thing met is one of the four. What it buys is different: untouchable is not being hit, condition proof is not losing a turn, and losing a turn is what ends a party. The alternative to two goals is a control for enumerating the monsters to be untouchable by, which is a worse question to ask of the player when the game already says which ones take a turn away.

**Where the character comes from.** By hand it is the class as it rolls at the cap, wearing what the gold affords, planned from the first training. With `?cheats`, where the hooked emulator is there to answer, it is read out of the running game, once, on the press, and planned forward from the level it is at, since the points it has already spent are in the numbers on its sheet and cannot be spent again.

A character read from the game is read out of both of its columns. The fight comes from CURRENT, which is what the game rolls with and what equipment is added into: worn armor is in its absorption and a ring that lifts casting is in its casting. The career comes from BASE, which is what the level-up formulas read: charisma decides the next grant, stamina the health it adds, intelligence and wisdom the pool. Health and magic are the pair whose two columns mean now and maximum instead, and the maximum is the one a plan is about.

**What a character attacks with.** One resolver settles every attack in the game, so a spell rolls against absorption exactly as a swing does, reading CASTING where the swing reads the weapon skill. The goals about landing an attack -- 100% hit, 100% damage, one-round kill -- therefore read whichever of the two the character uses, buy that one, and are labeled with it. Monk, alchemist, mage and druid roll higher in casting and default to it; paladin and marksman are level between the two and default to the weapon. Any class holding both offers the choice, because the guide does not settle it: `STRATEGY.md` section 13 prices both ends of a paladin -- 175 on one target with the weapon, 210 a target across three engaged with the spell, and nothing halves a swing -- and says only that splitting between them fails. Fighter, merchant and rogue have no spell list and no choice. For a caster the damage behind those goals is the best spell it knows rather than the weapon it is not swinging, so a monster that resists or is immune to that spell is priced in.

**The policies are fitted to the goals.** What the character carries, which skill it attacks with, how long it feeds the pool and where its leftovers go are not settings the player has to guess right. A goal that fails only because the plan is holding a two-hander, or is not feeding the pool at all, has not failed: the plan was wrong. So whatever the player has not chosen, the planner chooses, by walking the career under each candidate and keeping whichever holds the goals for the most levels, taken in the order the goals are listed so that the first one settles a tie. Choosing a value pins it and it is never overruled, since a player asking what a two-handed berserker cannot hold is asking a real question; Fit to goals lets go of every pin. A field the planner chose says so.

Three of the four have a control. How long the pool is fed does not, and deliberately: what to carry, what to swing and where the leftovers go are questions a player has an answer to, and the level to stop feeding the pool at is a scheduling detail with forty values, no one of which means anything on its own. It is always fitted. The Pool cost table says what the fit chose and what the levels either side of it would have been worth, and its last column is kills before a rest rather than dead levels, because what a pool buys is how long the character keeps going: whether any one cast kills outright says something about the casting and the spell list and nothing about the pool, which is the same pool whether the kill took one cast or three.

The magic pool is the case that forces this. It is not retroactive, so points spent at the level a goal wants them buy almost nothing, and a pool target can only be reached by having fed the pool from the first training. The pool goal therefore states the target and the pool policy is what serves it: asked for 500 the planner buys none, since a mage reaches 1,162 unaided; asked for 2,000 it feeds the pool through level 12; asked for 4,000 it feeds it the whole way and still reports the goal missed, which is the truth.

**How the points are spent.** Every attribute and skill climbs 2 a level whatever happens; the rest is bought out of the training grant, which is 13% of base charisma a level, capped at 15.

A goal's level is a deadline, not a start. "Condition proof from 24" is a promise about level 24, so a goal not yet due is priced at the level it comes due and bought toward from wherever the plan is now; a stop is never reached by beginning to buy on the day it falls due. Goals are served in the order they are listed, and a goal that already holds buys only what the levels after it will ask for that their own grants will not cover. A goal that no purchase can reach at any level -- asked of the goal alone, against a character that has bought nothing, so that a goal is not called hopeless merely because the goal above it took the money -- is served last: it still takes what is left over, because it is the goal that was asked for, but it does not starve a goal that could have been met.

Levels can be banked and points cannot. Experience sits there until a trainer is paid, but the bonus screen does not close with points in hand, so a level's grant is spent at that level or not at all. There is no saving up for a stop two levels ahead: what a stop costs has to have been going into that lever all along. Each level therefore spends its whole grant, in one order: charisma, then the pool; then what a goal that is due needs now and what the levels after it ask for that their own grants will not cover, down the list; then toward what a goal further up the career will ask for, in the same order; then strength to the crossover; then whatever is left into the lever the attack goals use.

The look-ahead in that second clause is the whole of what no banking amounts to, and it buys the least that keeps a goal payable. A goal wanting 82 dexterity at level 30 against a 15-point training there has to arrive holding 67, and nothing before level 30 says so: the bar at 29 is 64 and the goal reads as held. Buying only to today's bar broke it at 30 and held it again at 31, which read as the list order being ignored -- the points its lever wanted had gone to a goal below it, at the levels where this one looked satisfied. What a goal needs today is still priced against the character as it stands; only the look-ahead is priced from a character that has bought nothing, which quotes a goal reading a second lever a little high and errs toward buying early.

The pool and stamina are the two levers whose worth depends on when they are bought: each training adds a share of the attribute as it stood then, so a point of either is worth what the trainings after it make of it and nothing at the level it is paid for. Every other lever is worth the same at level 5 and at level 35. Feeding the pool is therefore something a goal does before it comes due, from the first training or not at all, and how long it runs for is the Pool through policy.

The pool takes the whole training, ahead of every goal, and that is not a place in the order but the absence of one. A goal that gives way at level 5 buys the same thing at level 6 for the same price. The pool does not: a level where a goal takes the grant first does not cost the pool that grant, it costs the pool that grant compounded over every training left in the career. Nothing is allowed in front of it a level at a time, and what the whole of it is worth against what the goals want is the Pool through policy, decided once and fitted.

**Every goal that reads the pool feeds it**, not only the two that are nothing else. Kills per rest ends a rest when the pool runs dry as surely as when the blow stops killing, so a plan of kills per rest 5 from level 20 buys the pool from the first training and the casting after it. Reaching for the pool at the level the goal comes due is reaching for it at the end, where it is worth a tenth of what it was worth at the start.

Feeding stops as soon as the target is met at the level it comes due, measured there rather than at the level being spent: a target met today is missed tomorrow when a costlier spell is learned, and stopping on today's answer starts it again late.

A target no policy can reach is fed anyway, and this is the one place the rule for the other levers is reversed. Points put into an unreachable stop on the weapon skill are dead, so they go last; points put into the pool are the pool. A request for 2000 that the class can only carry to 1907 is a request for the 1907, and refusing to feed it threw away 738 of them at no gain to any goal above it. The target is still marked out of reach rather than merely missed.

**Goals that read more than one number buy more than one lever.** Most read one: first strike is dexterity, a hundred per cent hit is the skill the character attacks with. Kills per rest is not. A rest ends because the blow stopped killing, because the pool ran dry, or because the character took back more than it could stand, and those are three different levers -- casting or weapon skill, the pool, and dexterity. Buying only the first is what a caster with a full pool and no armor looks like. A swing reads strength too, since the margin decides what lands and the damage decides what it delivers.

### What a rest is spent against

**The party is four and the fight is one monster at a time.** `DS:0xd0c9` holds four record handles and the monster's target picker rolls uniformly over them, so a monster takes a quarter of its swings at any one character ([combat.md](combat.md)). The same four are swinging at whatever is in front, so the rounds a kill takes are the party's and not one character's. Counting one character's rounds against a quarter of the monster's attention made the party four for the damage taken and one for the damage dealt.

**Three is a cap on the engaged buffers, not an opening position.** The maps place 1,862 monsters on 1,862 distinct cells, never two to a cell, and 1,279 of them have no other monster on any of the eight cells around them. Each is copied into a buffer as it closes, one at a time ([monsters.md](monsters.md)). So what is faced is however many close while the one in front is being killed, and a party that kills what closes in the round it closes never sees a second one. How fast they close is not a property of the monster and is not in its record: it is where the party stands against where the monsters do. A party caught in the open between several of them can be converged on from more than one side at once, which is a position going wrong rather than what an encounter is, so the model prices the sequential arrival at one more a round and only a kill as slow as the cap fills it. Reading the cap as a constant instead priced every fight three monsters deep from the first round, which is not a standard encounter but a party that cannot kill anything, surrounded.

Across the six archetypes and all six classes that leaves 65% of levels facing one, 25% facing two and 10% facing three, and every level above one is an early one where a kill still takes three to five rounds.

**A monster killed before its turn takes nothing back.** The turn list is rebuilt every round and sorted on dexterity, descending, a tie going to the party, and `0x01285` marks a dead monster skipped for the rest of the round. So first strike and a one-round kill together cost no health at all, and kills per rest is then the pool and nothing else. That is the check the model has to pass: over every class and both boss settings there are 22 levels where a character outrolls what it fights and the party kills inside the round, and at all 22 kills per rest equals casts per rest exactly.

Each level the walk prices every lever a goal names and buys whichever answers the goal for the fewest points. Where none of them answers it at any price, what is left is spread over them a step at a time, to whichever raises the goal most, weighed at the cap rather than here: the pool is worth nothing at the level it is bought, so a lever measured on the spot could never be chosen however badly the goal needed the casts. Steps rather than points, because the attribute bonus is a staircase of one absorption every five of the attribute, and a lever asked what one point buys answers nothing four times in five.

**The goals are kept per character.** A party's four do not share a plan: the mage is not planned against the stops the fighter beside it wants. A read party is kept by slot, which is the identity the game has, since a character can be renamed and two can carry the same name. One built here has no slot and is kept by class, which is the whole of what a hand character is before goals are set against it. The two stores never collide, so planning a party leaves the hand-built mage as it was, and switching back to it brings its goals with it. What follows the player from one character to the next is the tab's own state: whether bosses count and whether the working is shown. The goals, the archetype, the pinned policies and the share of the gold stay with the character. A plan saved before the store existed reads through as the default until the first edit files it under whoever was being looked at.

A character read out of the game is planned from the level it is at, since the points it has already spent are inside the numbers on its sheet. One built here is the class as it rolls and is planned from the first training, because a level-30 character holding thirty levels of grants is not a character the game can produce.

A lever only ever rises, since points are permanent, and three goals share the dexterity lever, so what they need is taken as a maximum rather than added up. The pool attribute is the exception that is dated as well as counted: the pool is not retroactive, so a point of intelligence is worth what the trainings after it make of it.
