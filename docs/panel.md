# The Restoration panel

The panel renders the clue book as a modern page, built from `data/*.json`. This document records settled findings only. It states what the panel is, and the invariants that [tools/panel_check.js](../tools/panel_check.js) asserts.

## The two builds

One CSS file and one JavaScript file produce both builds.

| | Size | Tables | Distributable |
|---|---|---|---|
| `web/restoration.html` | 1.7 MB | inlined | no, because it holds the game's content |
| `web/panel.html` | 330 kB | fetched at run time | yes |

Both sizes are what `make panel` last wrote, and both move as the panel does. [tools/build_panel.py](../tools/build_panel.py) prints the byte count.

Most of `restoration.html` is the packed map pages, and it opens from disk with no server. `panel.html` is the build that the cabinet loads into its iframe, both from [cabinet/serve.js](../cabinet/serve.js) and from the static `build/pages` site. A host page that sets `window.RESTORATION` before the panel runs suppresses the fetch.

There are five tabs: Maps, Monsters, Spells, Items and Guides. The clue book's own F4 page, Magic Users, has no tab of its own. That page is an index of the spell list by class, which is what the class chips on the Spells tab already provide. No tab draws its own heading.

## The invariants

[tools/panel_check.js](../tools/panel_check.js) renders the page in a browser and fails if any of the following does not hold.

**Maps.**

- The map is drawn on a canvas from `data/map_pages.json`, never shipped as a bitmap.
- The map comes first in source order, before the 37 area names, and the picker is capped and scrollable beside it.
- The caption reads `WORLD.DAT block N, slot M`, not "area/level".
- Legend labels are in one of two states and never in both. The 17 attributed pages show their own labels, and the remaining pages offer only the labels that no page has claimed.

**Spells.**

- One meaning per color. The scope indicator is a neutral shape, either one dot or three, and hue carries the damage element. Whether a spell harms or heals is the same distinction as whether it targets an enemy or a friend, because all 70 damaging spells act on monsters, undead or insects, and all 19 restorative spells act on characters. The element is therefore the only thing that color encodes and nothing else does.
- `#a62424` and `#5959c7` are the game's own inks, and measure 2.5:1 and 3.2:1 against this ground. The panel lifts them for legibility and keeps the hue.
- The cost analysis sits behind an Efficiency disclosure on this tab, scoped by the same class chips that filter the list. [tools/spell_curve.py](../tools/spell_curve.py) computes the same figures offline.

**Items.** The categories use the same `toggle` control as the spell classes. The check fails if the two filter bars diverge.
