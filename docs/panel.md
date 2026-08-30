# The Restoration panel

The panel renders the clue book as a modern page, built from `data/*.json`. This document records settled findings only. It states what the panel is, and the invariants that [tools/panel_check.js](../tools/panel_check.js) asserts.

## The two builds

One CSS file and one JavaScript file produce both builds.

| | Size | Tables | Distributable |
|---|---|---|---|
| `web/restoration.html` | 1.8 MB | inlined | no, because it holds the game's content |
| `web/panel.html` | 379 kB | fetched at run time | yes |

Both sizes are what `make panel` last wrote, and both move as the panel does. [tools/build_panel.py](../tools/build_panel.py) prints the byte count.

Most of `restoration.html` is the packed map pages, and it opens from disk with no server. `panel.html` is the build that the cabinet loads into its iframe, both from [cabinet/serve.js](../cabinet/serve.js) and from the static `build/pages` site. A host page that sets `window.RESTORATION` before the panel runs suppresses the fetch.

There are six tabs: Maps, Monsters, Spells, Items, Guides and Planner. The clue book's own F4 page, Magic Users, has no tab of its own. That page is an index of the spell list by class, which is what the class chips on the Spells tab already provide. No tab draws its own heading.

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

## The planner

The Planner tab evaluates goals against one character, level by level. A goal is a number the character has to hold from a level on; the tab says where it holds, where it breaks, what it costs, and which monster set the bar.

**Where the model runs.** The arithmetic is in [web/panel.js](../web/panel.js), because the answer depends on the character in front of it. [tools/combat_model.py](../tools/combat_model.py) is the same model offline, and the tables in `MANUAL.md` and `STRATEGY.md` are computed there. What does not depend on the character is decoded by [tools/planner.py](../tools/planner.py) into the payload's `planner` block: the class table, the armor sets and their prices, the shop's weapons, the incapacitating monsters, and the constants the four formulas read.

**A rate is measured against one monster, a threshold against the worst of each.** Landing every swing on the best-armoured thing of a level and being untouchable by the fastest are separate promises, and each has to hold, so a threshold is priced against the highest value of each stat separately. A rate -- kills or spells before a rest -- is not a promise but a fight repeated, and pricing it that way describes a fight nobody has: at level 30 it puts three monsters in front of the character, each carrying the Ice Dwarf's damage, the Ghoul's accuracy, the Wisp's health and its party attack, and every character in the game manages one kill against it. The rates are therefore measured against each monster that is extreme in something, five or six a level, and the worst answer wins: still the worst case, and a fight that exists. The evidence names it.

**What a level is measured against.** Per stat, the highest value among every monster met by that level, which is every listed monster of that level or below. That is not one monster: a character that lands every swing on the hardest monster of its level and misses the one wearing the most armor has not met the goal. Bosses -- the ten food-carriers and Paltivar -- are excluded unless asked for. A monster above the level cap is one a character at the cap meets, which is how Paltivar reaches a level-40 plan.

**Untouchable and condition proof are both goals.** Both test the same thing, that a monster's margin is below zero, and they differ in which monsters. Untouchable reads everything met by the level. Condition proof reads only the four that freeze, paralyse or petrify -- and only those met by that level, like every other goal, since a character of 24 is not fighting the Ice Dwarf. So the bar rises as they arrive: nothing to answer before 19, the Wizard's 139 from 19, the Purple Dragon's 171 from 26, the Fire Giant's 174 from 28, and 186 from 30, where it stops for good.

Condition proof is therefore the cheaper goal at every level, since its monsters are a subset of untouchable's, and the two coincide wherever the worst thing met is one of the four. What it buys is different: untouchable is not being hit, condition proof is not losing a turn, and losing a turn is what ends a party. The alternative to two goals is a control for enumerating the monsters to be untouchable by, which is a worse question to ask of the player when the game already says which ones take a turn away.

**Where the character comes from.** By hand it is the class as it rolls at the cap, wearing what the gold affords, planned from the first training. With `?trainer` it is read out of the running game, once, on the press, and planned forward from the level it is at, since the points it has already spent are in the numbers on its sheet and cannot be spent again.

A character read from the game is read out of both of its columns. The fight comes from CURRENT, which is what the game rolls with and what equipment is added into: worn armor is in its absorption and a ring that lifts casting is in its casting. The career comes from BASE, which is what the level-up formulas read: charisma decides the next grant, stamina the health it adds, intelligence and wisdom the pool. Health and magic are the pair whose two columns mean now and maximum instead, and the maximum is the one a plan is about.

**What a character attacks with.** One resolver settles every attack in the game, so a spell rolls against absorption exactly as a swing does, reading CASTING where the swing reads the weapon skill. The goals about landing an attack -- 100% hit, 100% damage, one-round kill -- therefore read whichever of the two the character uses, buy that one, and are labelled with it. Monk, alchemist, mage and druid roll higher in casting and default to it; paladin and marksman are level between the two and default to the weapon. Any class holding both offers the choice, because the guide does not settle it: `STRATEGY.md` section 13 prices both ends of a paladin -- 175 on one target with the weapon, 210 a target across three engaged with the spell, and nothing halves a swing -- and says only that splitting between them fails. Fighter, merchant and rogue have no spell list and no choice. For a caster the damage behind those goals is the best spell it knows rather than the weapon it is not swinging, so a monster that resists or is immune to that spell is priced in.

**The policies are fitted to the goals.** What the character carries, which skill it attacks with, how long it feeds the pool and where its leftovers go are not settings the player has to guess right. A goal that fails only because the plan is holding a two-hander, or is not feeding the pool at all, has not failed: the plan was wrong. So whatever the player has not chosen, the planner chooses, by walking the career under each candidate and keeping whichever holds the goals for the most levels, taken in the order the goals are listed so that the first one settles a tie. Choosing a value pins it and it is never overruled, since a player asking what a two-handed berserker cannot hold is asking a real question; Fit to goals lets go of every pin. A field the planner chose says so.

The magic pool is the case that forces this. It is not retroactive, so points spent at the level a goal wants them buy almost nothing, and a pool target can only be reached by having fed the pool from the first training. The pool goal therefore states the target and the pool policy is what serves it: asked for 500 the planner buys none, since a mage reaches 1,162 unaided; asked for 2,000 it feeds the pool through level 12; asked for 4,000 it feeds it the whole way and still reports the goal missed, which is the truth.

**How the points are spent.** Every attribute and skill climbs 2 a level whatever happens; the rest is bought out of the training grant, which is 13% of base charisma a level, capped at 15.

A goal's level is a deadline, not a start. "Condition proof from 24" is a promise about level 24, so a goal not yet due is priced at the level it comes due and bought towards from wherever the plan is now; a stop is never reached by beginning to buy on the day it falls due. Goals are served in the order they are listed, and a goal that already holds stops consuming, since nothing is bought twice. A goal that no purchase can reach at any level -- asked of the goal alone, against a character that has bought nothing, so that a goal is not called hopeless merely because the goal above it took the money -- is served last: it still takes what is left over, because it is the goal that was asked for, but it does not starve a goal that could have been met.

Levels can be banked and points cannot. Experience sits there until a trainer is paid, but the bonus screen does not close with points in hand, so a level's grant is spent at that level or not at all. There is no saving up for a stop two levels ahead: what a stop costs has to have been going into that lever all along. Each level therefore spends its whole grant, in one order: the pool first, then what an active goal needs now, down the list; then toward what a goal further up the career will ask for, in the same order; then strength to the crossover; then whatever is left into the lever the first goal uses.

The pool goes first because it is the only lever whose worth depends on when it is bought. Every other one is worth the same at level 5 and at level 35, so a goal that waits for it loses nothing. Feeding the pool a share at a time, in its place in the order, spreads it over levels where it buys almost nothing, so it is bought from the first training or not at all. It stops as soon as the target is met at the level it comes due, measured there rather than at the level being spent: a target met today is missed tomorrow when a costlier spell is learned, and stopping on today's answer starts it again late. A target no policy can reach buys nothing. The order of the goals is what decides which one gives way when a single training will not cover both.

A character read out of the game is planned from the level it is at, since the points it has already spent are inside the numbers on its sheet. One built here is the class as it rolls and is planned from the first training, because a level-30 character holding thirty levels of grants is not a character the game can produce.

A lever only ever rises, since points are permanent, and three goals share the dexterity lever, so what they need is taken as a maximum rather than added up. The pool attribute is the exception that is dated as well as counted: the pool is not retroactive, so a point of intelligence is worth what the trainings after it make of it.
