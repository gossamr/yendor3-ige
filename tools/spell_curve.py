"""Where a caster's damage actually improves, and what the spell tiers are.

Two questions the clue book cannot answer by listing:

  * At each level a class reaches, which damage spell now available gives the
    most damage per MP, and which the most per nuore? Those are different
    spells: the two rates rank spells almost independently (Spearman 0.24
    across the 70 damage spells) because nuore cost grows as roughly the
    two-thirds power of MP, so the big spells are cheap in nuore terms and dear
    in MP terms.
  * The game never names a tier, but the spells arrive in waves. The gaps in
    damage between consecutive spells are what reveal them.
"""

from __future__ import annotations

import json
import math
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLASSES = ["MONK", "ALCHEMIST", "PALADIN", "MAGE", "DRUID", "MARKSMAN"]


def load(path: Path | None = None) -> list[dict]:
    data = json.loads((path or ROOT / "data" / "spells.json").read_text())
    return [s for s in data if s["listed"] and s["damage"]]


def for_class(spells: list[dict], klass: str) -> list[tuple[int, dict]]:
    """(level, spell) for every damage spell this class can cast, by level."""
    out = []
    for s in spells:
        for c in s["classes"]:
            if c["class"] == klass:
                out.append((c["level"], s))
    return sorted(out, key=lambda p: p[0])


def frontier(spells: list[dict], klass: str, cost: str) -> list[dict]:
    """The upgrade points: each level where the best rate actually improves.

    Reporting every level would repeat the same spell for twenty rows; what a
    player wants is the short list of levels at which their best option
    changes.
    """
    best, out = 0.0, []
    for level, s in for_class(spells, klass):
        rate = s["damage"] / s[cost]
        if rate > best:
            best = rate
            out.append({"level": level, "spell": s["name"], "rate": rate,
                        "damage": s["damage"], "cost": s[cost]})
    return out


def tiers(spells: list[dict], gap: float = 1.6) -> list[list[dict]]:
    """Group spells into tiers by jumps in damage.

    A tier boundary is a place where the next spell's damage is more than `gap`
    times the previous one's: the waves are multiplicative, not additive, so a
    ratio finds them where a fixed step would not.
    """
    ordered = sorted(spells, key=lambda s: s["damage"])
    groups: list[list[dict]] = [[ordered[0]]]
    for prev, s in zip(ordered, ordered[1:]):
        if s["damage"] > prev["damage"] * gap:
            groups.append([])
        groups[-1].append(s)
    return groups


def ranks(xs: list[float]) -> list[float]:
    """Average ranks, which is what a Spearman over tied values needs.

    Dense ranks, numbering the distinct values, look like the same thing
    and are not: MP and nuore are full of ties, and dense ranks read their
    correlation as 0.99 where it is 0.995, and the efficiency one as 0.22
    where it is 0.24.
    """
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    out = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            out[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return out


def spearman(xs: list[float], ys: list[float]) -> float:
    return statistics.correlation(ranks(xs), ranks(ys))


def power_fit(xs: list[float], ys: list[float]) -> tuple[float, float, float]:
    """`y = a * x**b`, fitted in log space; returns (a, b, r squared)."""
    lx = [math.log(v) for v in xs]
    ly = [math.log(v) for v in ys]
    r = statistics.correlation(lx, ly)
    b = r * statistics.stdev(ly) / statistics.stdev(lx)
    return math.exp(statistics.fmean(ly) - b * statistics.fmean(lx)), b, r * r


def costs() -> None:
    """How the two costs relate, and therefore why the two rates do not."""
    priced = [s for s in json.loads(
        (ROOT / "data" / "spells.json").read_text())
        if s["listed"] and s["mp"] and s["nuore"]]
    mp = [s["mp"] for s in priced]
    nuore = [s["nuore"] for s in priced]
    a, b, r2 = power_fit(mp, nuore)
    error = statistics.median(
        abs(a * m ** b - n) / n for m, n in zip(mp, nuore))
    print(f"\n=== the two costs, over {len(priced)} spells ===\n")
    print(f"  rank agreement   Spearman {spearman(mp, nuore):.3f}, "
          f"Pearson {statistics.correlation(mp, nuore):.2f}")
    print(f"  nuore from MP    {a:.2f} * MP^{b:.2f}   "
          f"r2 {r2:.2f}, median error {error:.0%}")
    print(f"  spans            MP {max(mp) / min(mp):.0f}x, "
          f"nuore {max(nuore) / min(nuore):.0f}x")
    damage = load()
    print(f"  the two rates    Spearman "
          f"{spearman([s['damage'] / s['mp'] for s in damage], [s['damage'] / s['nuore'] for s in damage]):.2f}"
          f" over {len(damage)} damage spells")


def report() -> None:
    costs()
    spells = load()
    for cost, unit in (("mp", "MP"), ("nuore", "nuore")):
        print(f"\n=== best damage per {unit}, as each class levels ===")
        for klass in CLASSES:
            steps = frontier(spells, klass, cost)
            if not steps:
                continue
            print(f"\n{klass.title()}")
            for st in steps:
                print(f"  L{st['level']:<3} {st['spell']:24} "
                      f"{st['rate']:5.2f}/{unit:<5} ({st['damage']} for {st['cost']})")

    print("\n=== implicit tiers ===")
    for i, group in enumerate(tiers(spells), 1):
        lo, hi = group[0]["damage"], group[-1]["damage"]
        levels = sorted({c["level"] for s in group for c in s["classes"]})
        print(f"\nTier {i}: {lo}-{hi} damage, {len(group)} spells, "
              f"levels {levels[0]}-{levels[-1]}")
        print("   " + ", ".join(s["name"].title() for s in group))


if __name__ == "__main__":
    report()
