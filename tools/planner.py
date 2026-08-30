"""The tables the Planner tab needs and the decode does not already carry.

The panel evaluates a character's goals level by level, and it does that in the
browser because the answer depends on the character in front of it: with the
trainer on, that is the sheet read out of the running game. The formulas are
small enough to run there. The tables they read are not, so they are exported
here.

Nothing in this module is a new derivation. `combat_model` and `levels` are
where the model lives; this is the shape it travels in. Two things follow from
that:

- Every number is computed, none is typed. The absorption that shuts out the
  four incapacitating monsters is read off their records rather than quoted
  from `STRATEGY.md`, so a re-decode moves both together.
- What the panel does with the tables -- which goals it offers, which
  archetypes group them -- is not here. That is ours rather than the game's,
  and it lives in `web/panel.js` beside the rest of the panel's own content.

What the panel derives for itself, and so is absent here: the worst monster at
each level, which is a scan of `enemies` it already holds; the experience
ladder and the bonus-point staircase, which are in `leveling`; and the odds
curve, `pct` and the attribute bonus, which are four lines of arithmetic
apiece.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import combat_model as C
import levels as L
import skills as S

# The conditions that take a character out of the fight rather than costing it
# something. `docs/combat.md` has what each does; what matters here is that a
# character under one of them is not acting, so the absorption that shuts them
# out is a threshold worth planning to.
INCAPACITATING = ("FROZEN", "PARALYZE", "STONING")

# Attack skills a character fights with. The six non-combat skills are measured
# against fixed rungs rather than against a monster, so no goal reads them.
ATTACK_SKILLS = ("projectile", "slashing", "bashing", "polearm")


def constants() -> dict:
    """The arithmetic the panel runs, as numbers rather than as code."""
    return {
        "per_level": C.PER_LEVEL,
        "roll_cap": C.ROLL_CAP,
        "level_cap": C.LEVEL_CAP,
        # rand(55), folded: see levels.roll_odds. The panel folds it the same
        # way, and this is the only input that fold needs.
        "attack_roll": L.ATTACK_ROLL,
        # Absorption from dexterity: a fifth of whatever is over 72.
        "bonus_threshold": L.BONUS_THRESHOLD,
        "bonus_pct": L.BONUS_PCT,
        # Training points a level-up grants: 13% of base charisma, capped.
        "bonus_cap": L.BONUS_CAP,
        "pct_bonus_from_charisma": L.PCT_BONUS_FROM_CHARISMA,
        # Health is a quarter of stamina at creation and 30% of it a level
        # after that, on the stamina as it stands at the time.
        "health_at_creation": S.HEALTH_PCT_OF_STAMINA,
        "pct_health_from_stamina": L.PCT_HEALTH_FROM_STAMINA,
        # Magic points are 30% of the class's attribute blend, added the same
        # non-retroactive way.
        "pct_magic": L.PCT_MAGIC,
    }


def classes() -> list[dict]:
    """Each class at level 1 on a roll of the cap: what it starts with.

    A weapon skill is the roll plus a per-class modifier, so the modifier is
    what is exported and any roll can be applied to it. Casting is not a blend
    of that shape -- it comes out of its own dispatch and can start above the
    roll -- so it is exported as the value itself, at the cap.

    `magic_blend` is how the class turns intelligence and wisdom into pool, and
    an empty one is a class that never casts.
    """
    out = []
    for code, name in enumerate(L.CLASSES):
        if name is None:
            continue
        casting, magic = S.casting_and_magic(code, C.ROLL_CAP, C.ROLL_CAP)
        out.append({
            "code": code,
            "name": name,
            "modifier": {s: S.MODIFIER[s].get(code, 0) for s in ATTACK_SKILLS},
            "casting": casting,
            "magic": magic,
            "magic_blend": [["intelligence" if w == L.INT else "wisdom", p]
                            for w, p in L.MAGIC_BLEND.get(code, [])],
        })
    return out


def armor() -> dict:
    """What gold can have bought by a level, as the curve's own inputs.

    Exported rather than evaluated because the split between armor and
    everything else a party buys is the player's, and the panel offers it as a
    control. `combat_model.armor_afforded` is this arithmetic; the panel runs
    the same three lines over these numbers.

    Each set is (absorption, gold): the best purchasable item per slot, and the
    same slots with every piece enchanted as far as it goes. Armor is cheap to
    the first and about a hundred times dearer past it, because past it the
    money buys enchantment rather than another piece.
    """
    return {
        "gold_per_xp": C.GOLD_PER_XP,
        "party": C.PARTY,
        # Training is the competing cost and it is quadratic in level: 100 gold
        # times the level, once per level already held.
        "train_base": L.TRAIN_BASE_PRICE,
        "shield": {"plain": list(C.UNENCHANTED), "top": list(C.ENCHANTED)},
        "two_handed": {"plain": list(C.UNENCHANTED_2H),
                       "top": list(C.ENCHANTED_2H)},
    }


def weapons(items: list[dict] | None = None) -> dict:
    """Shop stock, best damage first: what the same gold buys to swing with.

    Only series with enchanted forms, which is every weapon a merchant
    actually stocks; the three weapons of Light are quest loot and are priced
    as what a shop pays for one. `combat_model.shop_weapons` is the filter.

    The two lists are kept apart because carrying a two-hander costs the
    shield, which is 30 absorption against 10 damage, and the panel prices the
    two choices separately.
    """
    single = C.shop_weapons(items=items)
    both = C.shop_weapons(items=items, two_handed=True)
    names = {name for _damage, _price, name in single}
    row = lambda r: {"damage": r[0], "price": r[1], "name": r[2]}
    return {
        "one_handed": [row(r) for r in single],
        "two_handed": [row(r) for r in both if r[2] not in names],
    }


def incapacitating(enemies: list[dict]) -> dict:
    """The monsters that end a character's fight, and the absorption that
    shuts them all out.

    Freezing, paralysis and stoning take the character out entirely, where the
    other six conditions cost it something and leave it swinging. Absorption
    one point over the highest accuracy among them means none of the three can
    land at all, which is a threshold rather than a scale: a point under it and
    every one of them is still in play.
    """
    rows = [e for e in enemies
            if e["listed"] and set(e["attacks"]) & set(INCAPACITATING)]
    rows.sort(key=lambda e: e["accuracy"])
    return {
        "absorption": max((e["accuracy"] for e in rows), default=0) + 1,
        "monsters": [{"name": e["name"], "level": e["level"],
                       "accuracy": e["accuracy"],
                       "condition": next(a for a in e["attacks"]
                                         if a in INCAPACITATING)}
                      for e in rows],
    }


def build(payload: dict) -> dict:
    """The `planner` block of the panel's tables."""
    return {
        "constants": constants(),
        "classes": classes(),
        "armor": armor(),
        "weapons": weapons(payload["items"]),
        "incapacitating": incapacitating(payload["enemies"]),
    }


if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent
    data = {name: json.loads((root / "data" / f"{name}.json").read_text())
            for name in ("enemies", "items")}
    block = build(data)
    print(json.dumps(block["constants"], indent=1))
    print(f'{len(block["classes"])} classes, '
          f'{len(block["weapons"]["one_handed"])} one-handed weapons, '
          f'{len(block["weapons"]["two_handed"])} two-handed')
    inc = block["incapacitating"]
    print(f'absorption {inc["absorption"]} shuts out '
          + ", ".join(f'{c["name"].title()} ({c["condition"].lower()}, '
                      f'level {c["level"]})' for c in inc["monsters"]))
