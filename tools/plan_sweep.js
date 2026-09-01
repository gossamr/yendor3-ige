// The figures docs/panel.md quotes about what a rest is spent against, walked
// rather than asserted.
//
//   bun tools/plan_sweep.js [--file=web/restoration.html]
//
// The planner's model is a closure inside web/panel.js and nothing on the page
// reaches into it. That is right for shipping code, and it left the counts in
// the guide unreproducible: they were taken once, by hand, back when the tab
// offered six classes rather than nine. So this loads the built panel, injects
// a second copy of panel.js with the internals bound to `window.__plan` and the
// DOM entry point cut off, and walks every plan the tab can be asked for. It
// derives nothing. It runs the tab's own walk and counts the rows.
//
// The population is every class against every archetype, 9 by 6, 40 levels
// each. That includes pairings a player would not make, a fighter under the
// caster archetype among them. They stay in: the guide's claims are about the
// model rather than about advice, and the walk has to survive a goal its class
// can never reach.
import { chromium } from "playwright";
import { readFileSync } from "fs";
import { resolve } from "path";

const arg = (n, d) => {
  const hit = process.argv.find((a) => a.startsWith(`--${n}=`));
  return hit === undefined ? d : hit.split("=").slice(1).join("=");
};
const file = "file://" + resolve(arg("file", "web/restoration.html"));

// The tail of panel.js, which is where the module hands itself to the page.
// Replaced rather than appended to, so the injected copy defines the same
// constants without drawing a second panel over the first.
const ENTRY = `  document.readyState === "loading"
    ? addEventListener("DOMContentLoaded", init)
    : init();
})();`;
const src = readFileSync("web/panel.js", "utf8");
if (!src.includes(ENTRY)) {
  console.error("plan sweep: web/panel.js no longer ends the way this expects; "
    + "the hook has to be re-cut against its entry point.");
  process.exit(1);
}
const hooked = src.replace(ENTRY, `  window.__plan = {
    PLAN, ARCHETYPES, POLICIES, archetypeGoals, buildPlan, fitPolicies, walk,
    worstRestFoe, castAgainst, swing, roundsToKill, swingsBefore,
    engagedAgainst, killsPerRest,
  };
})();`);

const browser = await chromium.launch();
const page = await browser.newPage();
const problems = [];
page.on("pageerror", (e) => problems.push(`pageerror: ${e.message}`));
await page.goto(file);
await page.waitForSelector("nav button", { timeout: 15000 });
await page.addScriptTag({ content: hooked });

/* One row per level of every plan, carrying what the rate was measured with:
   which monster set it, how many of that monster were engaged, how many rounds
   it swung in before it died, and the two limbs of the rate. */
const rows = await page.evaluate(() => {
  const P = window.__plan;
  const out = [];
  for (const cls of P.PLAN.classes) {
    for (const [archetype] of P.ARCHETYPES) {
      for (const bosses of [false, true]) {
        for (const groups of [true, false]) {
          const stored = { archetype, goals: P.archetypeGoals(archetype),
                           code: cls.code, bosses, groups, source: "hand" };
          const settings = {};
          for (const key of P.POLICIES) settings[key] = null;
          const plan = P.buildPlan(stored, P.fitPolicies(stored, settings));
          const casts = !!plan.character.casts;
          for (const row of P.walk(plan)) {
            const { me, at, level } = row;
            const foe = P.worstRestFoe(plan, me, at);
            if (!foe) continue;
            /* The same blow killsAgainst prices the rate with: the cheapest
               spell that still kills this monster outright, or the swing. */
            const cast = casts
              ? P.castAgainst(plan, me, foe, undefined, plan.ignoreResist) : null;
            const dealt = casts ? (cast ? cast.landed : 0)
              : P.swing(me.damage, me.attack, foe.absorption);
            const rounds = P.roundsToKill(foe, dealt);
            out.push({
              cls: cls.name, archetype, bosses, groups, level, casts,
              engaged: P.engagedAgainst(plan, foe, rounds),
              swings: P.swingsBefore(me, foe, rounds),
              rounds,
              kills: P.killsPerRest(plan, me, at),
              /* What the pool buys of that spell, which is the limb the
                 evidence block prints as Casts. */
              spellCasts: cast && cast.spell.mp
                ? Math.floor(me.magic / cast.spell.mp) : null,
            });
          }
        }
      }
    }
  }
  return out;
});
await browser.close();

if (problems.length) {
  for (const p of problems) console.error("  -", p);
  process.exit(1);
}

const tally = (xs) => xs.reduce((m, x) => (m[x] = (m[x] || 0) + 1, m), {});
const pct = (n, d) => `${Math.round((100 * n) / d)}%`;

// How many of a monster a rate is counted against. Bosses out, since a rate is
// never counted against one, and Groups on, which is the switch's default.
const ordinary = rows.filter((r) => r.groups && !r.bosses);
const engaged = tally(ordinary.map((r) => r.engaged));
console.log(`${ordinary.length} levels, Groups on, bosses out`);
for (const n of [1, 2, 3]) {
  console.log(`  ${n} engaged: ${engaged[n] || 0} (${pct(engaged[n] || 0, ordinary.length)})`);
}
const several = ordinary.filter((r) => r.engaged > 1);
const band = tally(several.map((r) => (r.level <= 10 ? "1-10" : r.level <= 20
  ? "11-20" : r.level <= 30 ? "21-30" : "31-40")));
console.log(`  more than one, by level: ${JSON.stringify(band)}`);
const quick = several.filter((r) => r.rounds <= 3).length;
console.log(`  more than one, killed in 2 or 3 rounds: ${quick} of ${several.length}`);

// Switched off, every fight is one monster, whatever the record allows.
const alone = tally(rows.filter((r) => !r.groups).map((r) => r.engaged));
console.log(`Groups off: ${JSON.stringify(alone)}`);

// A monster killed before its turn never swings, so the health limb has no
// denominator and the rate is the pool alone. What the check is for: where
// that happens to a caster, kills before a rest has to equal the casts the
// pool buys, exactly.
const outrolled = rows.filter((r) => r.groups && r.swings === 0);
const casters = outrolled.filter((r) => r.casts);
const mismatched = casters.filter((r) => r.kills !== r.spellCasts);
console.log(`${outrolled.length} levels outrolled and killed inside the round, `
  + `Groups on, both boss settings`);
console.log(`  casters: ${casters.length}, of which kills != casts: ${mismatched.length}`);
console.log(`  not casters: ${outrolled.length - casters.length} (the rate has no limit there)`);
if (mismatched.length) {
  console.log(`  first: ${JSON.stringify(mismatched[0])}`);
  process.exit(1);
}
