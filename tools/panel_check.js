// Render the Restoration panel in a real browser, assert each section actually
// populates, and write screenshots.
//
//   bun tools/panel_check.js [--out=tmp/panel]
import { chromium } from "playwright";
import { mkdirSync } from "fs";
import { resolve } from "path";

const arg = (n, d) => {
  const hit = process.argv.find((a) => a.startsWith(`--${n}=`));
  return hit === undefined ? d : hit.split("=").slice(1).join("=");
};
const outDir = arg("out", "tmp/panel");
const file = "file://" + resolve(arg("file", "web/restoration.html"));
mkdirSync(outDir, { recursive: true });

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });

const problems = [];
page.on("pageerror", (e) => problems.push(`pageerror: ${e.message}`));
page.on("console", (m) => { if (m.type() === "error") problems.push(`console: ${m.text()}`); });

await page.goto(file);
try {
  await page.waitForSelector("nav button", { timeout: 8000 });
} catch {
  console.error("PANEL CHECK FAILED: the page never rendered its navigation.");
  for (const p of problems) console.error("  -", p);
  await browser.close();
  process.exit(1);
}

// Assert on decoded content rather than on copy: prose gets reworded, but a
// section that has lost its data is a real regression.
const TABS = [
  ["f1", "Maps", /Dwarven Homeland/],
  ["f2", "Monsters", /Wasp/],
  ["f3", "Spells", /Sling Shot/],
  ["f5", "Items", /Weapons/],
  // The Guides tab opens on the first document, which is the manual.
  ["gd", "Guides", /Yendorian Tales/],
  ["pl", "Planner", /Career/],
];

// The documents inside the Guides tab, and one string apiece that only appears
// when that document actually rendered.
const DOCS = [
  ["manual", /Bonus points/],
  ["strategy", /Rolling characters/],
  ["walkthrough", /Athaneum/],
  // 10,800,000 is the level-40 rung, so it is the one number that proves the
  // ladder rendered rather than just its heading.
  ["leveling", /10,800,000/],
];

const pickDoc = async (key) => {
  await page.click(`.guide-picker button[data-doc="${key}"]`);
  await page.waitForTimeout(150);
};

for (const [key, label, expect] of TABS) {
  await page.click(`nav button[data-key="${key}"]`);
  await page.waitForTimeout(150);
  const sec = page.locator(`section[data-key="${key}"]`);
  const text = await sec.innerText();
  if (!expect.test(text)) problems.push(`${key} (${label}): expected content ${expect} missing`);
  if (text.trim().length < 200) problems.push(`${key} (${label}): section looks empty (${text.length} chars)`);
  await page.screenshot({ path: `${outDir}/${key}.png`, fullPage: false });
}

// --- the monster census ------------------------------------------------
//
// Every monster in the game stands on a cell of one map and is killed once,
// so a map's list and a monster's list are two readings of the same table
// (docs/encounters.md). What is checked is that both are drawn, that each
// carries you to the other, and that the two agree on the count. A chip pair
// that disagrees means one side is reading the census the wrong way round.

const chipCount = async (scope, name) => {
  const chip = page.locator(`${scope} .chip.census`, { hasText: name }).first();
  if (!(await chip.count())) return null;
  const text = await chip.innerText();
  const m = text.match(/×(\d+)/);
  return m ? Number(m[1]) : null;
};

await page.click('nav button[data-key="f1"]');
await page.waitForTimeout(150);
// Acoknight's Cave Level 1 is the first page in the picker, and the census
// gives it three kinds. The names and the counts are decoded, so this is the
// data; the heading over them is copy and is not checked.
const mapChips = await page.locator('section[data-key="f1"] .chip.census').count();
if (mapChips !== 3) {
  problems.push(`maps: ${mapChips} monsters on Acoknight's Cave Level 1, expected 3`);
}
const onMap = await chipCount('section[data-key="f1"]', "Fighter");
if (onMap !== 27) {
  problems.push(`maps: Acoknight's Cave Level 1 lists ${onMap} Fighters, expected 27`);
}

await page.locator('section[data-key="f1"] .chip.census', { hasText: "Fighter" })
  .first().click();
await page.waitForTimeout(200);
if (await page.getAttribute('nav button[data-key="f2"]', "aria-selected") !== "true") {
  problems.push("census: a monster chip did not open the Monsters tab");
}
const shown = await page.inputValue("select.picker");
if (shown !== "FIGHTER") {
  problems.push(`census: the monster chip landed on ${shown}, expected FIGHTER`);
}

// And back the other way, on the same pair, with the same count.
const onMonster = await chipCount('section[data-key="f2"]', "Acoknight's Cave Level 1");
if (onMonster !== onMap) {
  problems.push(`census: the map says ${onMap} Fighters and the monster says `
    + `${onMonster}`);
}
await page.screenshot({ path: `${outDir}/census.png` });

// A search filters every tab, so following a link has to clear it. "fighter"
// leaves the monster's own card standing and matches no map title, so
// without the clearing the jump lands on whichever page is first instead.
await page.fill("#search", "fighter");
await page.waitForTimeout(150);
await page.locator('section[data-key="f2"] .chip.census',
                   { hasText: "Acoknight's Cave Level 1" }).first().click();
await page.waitForTimeout(200);
if (await page.getAttribute('nav button[data-key="f1"]', "aria-selected") !== "true") {
  problems.push("census: a map chip did not open the Maps tab");
}
if (await page.inputValue("#search") !== "") {
  problems.push("census: following a link left the search filtering the target");
}
const landed = await page.locator('.maps-list [aria-current="true"]').innerText();
if (!/Acoknight's Cave Level 1/i.test(landed)) {
  problems.push(`census: the map chip landed on ${landed}`);
}

// Each document in the Guides tab renders on its own.
await page.click(`nav button[data-key="gd"]`);
await page.waitForTimeout(150);
for (const [key, expect] of DOCS) {
  await pickDoc(key);
  const text = await page.locator(".guide-doc").innerText();
  if (!expect.test(text)) problems.push(`guides/${key}: expected ${expect} missing`);
  if (text.trim().length < 200) {
    problems.push(`guides/${key}: looks empty (${text.length} chars)`);
  }
  await page.screenshot({ path: `${outDir}/guide-${key}.png` });
}

// The markdown has to come out as markup, not as its own source. A guide that
// renders "| Level | Experience |" as a paragraph is a parser regression.
await pickDoc("strategy");
const guideText = await page.locator(".guide-doc").innerText();
if (/\|\s*---/.test(guideText) || /^\s*#{2,}\s/m.test(guideText)) {
  problems.push("guides: raw markdown syntax is showing through");
}
const mdTables = await page.locator(".guide-doc .md-table").count();
if (mdTables < 10) problems.push(`guides: only ${mdTables} tables parsed out of strategy`);
const mdHeads = await page.locator(".guide-doc h3").count();
if (mdHeads < 10) problems.push(`guides: only ${mdHeads} headings parsed out of strategy`);
const toc = await page.locator(".guide-toc button").count();
if (toc < 10) problems.push(`guides: outline has ${toc} entries`);
// Ordered lists: one <ol>, every item, and a wrapped item keeping the rest of
// its own sentence. The same code decides whether a line beginning "10." is a
// list item or the middle of a paragraph, which is what used to break the
// spell section in two.
const ols = page.locator(".guide-doc ol");
if (await ols.count() !== 1) {
  problems.push(`guides: expected one ordered list, found ${await ols.count()}`);
} else {
  const items = await ols.first().locator("li").allInnerTexts();
  if (items.length !== 6) {
    problems.push(`guides: the decision list has ${items.length} items, expected 6`);
  }
  if (!items.some((t) => /buy staying power rather than speed/.test(t))) {
    problems.push("guides: a wrapped list item lost its continuation");
  }
}
// Bold and code spans inside table cells and prose.
if (!(await page.locator(".guide-doc strong").count())) {
  problems.push("guides: no bold spans parsed");
}
if (!(await page.locator(".guide-doc code").count())) {
  problems.push("guides: no code spans parsed");
}

// Paths into the source tree are for whoever is working on the project, not
// for whoever is playing the game. `<!-- panel:skip -->` keeps them in the
// file and off the page, and the marker itself must not show either.
for (const key of ["manual", "strategy"]) {
  await pickDoc(key);
  const text = await page.locator(".guide-doc").innerText();
  const leaked = text.match(/\b(tools|docs|web|cabinet)\/[\w.-]+/g);
  if (leaked) problems.push(`guides/${key}: source paths on the page: ${leaked}`);
  if (text.includes("panel:skip") || text.includes("<!--")) {
    problems.push(`guides/${key}: the skip marker is being rendered`);
  }
}

// The guides name each other by filename. In the panel that has to open the
// other document, not render as a dead path.
await pickDoc("manual");
// The control is named the way the picker names it, with no file extension.
const xref = page.locator('.guide-doc button.guide-link', { hasText: "Strategy" });
if (!(await xref.count())) {
  problems.push("guides: the manual's reference to STRATEGY.md is not a control");
} else if ((await xref.first().innerText()).includes(".md")) {
  problems.push("guides: the cross-reference still shows a filename");
} else {
  await xref.first().click();
  await page.waitForTimeout(200);
  const opened = await page.getAttribute(
    '.guide-picker button[data-doc="strategy"]', "aria-current");
  if (opened !== "true") problems.push("guides: the cross-reference did not open strategy");
}

// The ladder is the panel's own addition, so nothing upstream would catch it
// silently losing rows.
await pickDoc("leveling");
const lvTables = page.locator('section[data-key="gd"] table');
const rungs = await lvTables.nth(0).locator("tbody tr").count();
if (rungs !== 39) problems.push(`leveling: expected 39 rungs, found ${rungs}`);
const trainers = await lvTables.nth(1).locator("tbody tr").count();
if (trainers !== 5) problems.push(`leveling: expected 5 trainers, found ${trainers}`);
// The one trainer with a floor. If the payload loses it the chart silently
// claims that trainer covers the whole game.
const lvText = await page.locator('section[data-key="gd"]').innerText();
if (!/30 to 40/.test(lvText)) problems.push("leveling: the 30-to-40 trainer is missing");

// --- the planner -------------------------------------------------------
//
// The tab computes rather than prints, so what is checked is the arithmetic:
// that it spends no more than the game grants, that it measures against the
// monster it says it does, and that the two thresholds the strategy guide
// names come out of the decode rather than out of a constant someone typed.

await page.click('nav button[data-key="pl"]');
await page.waitForTimeout(300);
const planner = page.locator('section[data-key="pl"]');

// A row a level, from where the character stands to the cap.
const careerRows = await planner.locator(".plan-career tbody tr[data-level]").count();
if (careerRows !== 40) {
  problems.push(`planner: ${careerRows} levels in the career, expected 40`);
}

// Levels can be banked and points cannot: the bonus screen does not close
// with any in hand. So every level spends its whole grant and no more, and a
// plan that saves up for a stop two levels ahead is one nobody can follow.
const spend = await planner.locator(".plan-career tbody tr[data-level]").evaluateAll(
  (rows) => rows.map((tr) => {
    const cells = [...tr.querySelectorAll("td")];
    const points = cells[cells.length - 2].textContent.trim();
    const bought = [...cells[cells.length - 1].textContent.matchAll(/\+(\d+)/g)]
      .reduce((n, m) => n + Number(m[1]), 0);
    // The level the character stands at has no training in it and says so.
    return { level: tr.dataset.level, grant: points === "\u2014" ? null : Number(points),
             bought };
  }));
const misspent = spend.filter((r) => (r.grant === null ? r.bought !== 0
                                                        : r.bought !== r.grant));
if (misspent.length) {
  const r = misspent[0];
  problems.push(`planner: level ${r.level} is granted ${r.grant} points and `
    + `spends ${r.bought}; a training screen closes with none in hand`);
}
const career = spend.reduce((n, r) => n + (r.grant || 0), 0);
if (career < 400) {
  problems.push(`planner: a whole career grants ${career} points, short of the `
    + "450 a middling charisma roll pays out");
}

// The character the tab projects has to be the one the offline model builds.
// A level-40 fighter at the roll cap holds 1162 health, which is what
// tools/combat_model.py's health_pool gives; health is accumulated a level at
// a time and reads no lever, so it is the figure that pins the projection.
// Handing that accumulator the attribute as it stands instead of the roll it
// grew from counts the climb twice and 1162 becomes 2094.
await page.selectOption(".plan-class", "1");
await page.waitForTimeout(300);
await page.selectOption(".plan-add", { label: "Survive a round" });
await page.click(".plan-add ~ button");
await page.waitForTimeout(600);

// The evidence is the tab's claim to be believed, so it has to name the
// monster each number came off.
await page.click(".plan-evidence");
await page.waitForTimeout(600);
const evidence = await planner.locator(".plan-evidence-row").count();
if (!evidence) problems.push("planner: the evidence control showed no working");

// The health the projection carries at the cap, out of the goal that reads it.
const atForty = await planner
  .locator('.plan-career tbody tr[data-level="40"] + tr .plan-evidence-block',
           { hasText: "Survive a round" }).first()
  .innerText().catch(() => "");
if (!/Health\s*\n?1162\b/.test(atForty)) {
  problems.push("planner: a level-40 character does not hold the 1162 health "
    + `combat_model computes: ${JSON.stringify(atForty)}`);
}

// Absorption 186 shuts out freezing, paralysis and stoning, and the four
// monsters behind it are named. That number is read off their own records by
// tools/planner.py; if the decode moves and the number does not, this is the
// check that says so. Asserted inside the goal's own block, so a 186 belonging
// to some other goal cannot stand in for it.
// The bar rises as the four arrive -- Wizard at 19, Purple Dragon at 26, Fire
// Giant at 28, Ice Dwarf at 30 -- so a level-30 character answers all four at
// 186 and a level-20 character answers the Wizard alone at 139. Those numbers
// are read off the monsters' own records by tools/planner.py; if the decode
// moves and they do not, this is the check that says so.
const conditionsAt = async (level) => planner.locator(
  `.plan-career tbody tr[data-level="${level}"] + tr .plan-evidence-block`,
  { hasText: "Condition proof" }).first().innerText().catch(() => "");
const late = await conditionsAt(30);
if (!/needs 186\b/.test(late)) {
  problems.push(`planner: level 30 does not answer all four at 186: ${JSON.stringify(late)}`);
}
for (const monster of ["Wizard", "Purple Dragon", "Fire Giant", "Ice Dwarf"]) {
  if (!late.includes(monster)) {
    problems.push(`planner: ${monster} is missing from the condition evidence`);
  }
}
const early = await conditionsAt(20);
if (!/needs 139\b/.test(early)) {
  problems.push("planner: level 20 is not measured against the Wizard alone: "
    + JSON.stringify(early));
}
if (/Ice Dwarf/.test(early)) {
  problems.push("planner: level 20 is priced against a monster it cannot meet");
}

// A monster's shot is an attack of its own, and the two dwarf towers never
// close, so their melee rows are not what a character answers. The Fire Dwarf
// Tower arrives at 16 and shoots at 160; reading its blow instead puts the bar
// at the Dwarf Scout's 119 and prices a fight the tower does not have. The
// working has to say the shot set it, or an attribution to a monster whose own
// card reads 10 is a contradiction.
const takeHitAt = async (level) => planner.locator(
  `.plan-career tbody tr[data-level="${level}"] + tr .plan-evidence-block`,
  { hasText: "Take hit" }).first().innerText().catch(() => "");
const tower = await takeHitAt(16);
if (!/Accuracy\s*\n?160\b/.test(tower) || !tower.includes("Fire Dwarf Tower")) {
  problems.push("planner: level 16 is not measured against the Fire Dwarf "
    + `Tower's shot: ${JSON.stringify(tower)}`);
} else if (!/shot/i.test(tower)) {
  problems.push("planner: the bar the tower's shot set is not marked as a shot");
}

// With bosses counted, a character at the cap is measured against Paltivar,
// which is the basis every endgame figure in STRATEGY.md is quoted against:
// accuracy 240, absorption 170. It is level 45 and reaches a level-40 plan
// only through the rule that a monster above the cap is one a character at
// the cap meets.
await page.click(".plan-evidence");
await page.check("#plan-bosses");
await page.waitForTimeout(300);
await page.selectOption(".plan-archetype", "untouchable");
await page.waitForTimeout(400);
await page.click(".plan-evidence");
await page.waitForTimeout(600);
const last = planner.locator('.plan-career tbody tr[data-level="40"] + tr');
const endgame = await last.innerText();
for (const [what, expected] of [["Accuracy", "240"], ["Absorption", "170"]]) {
  // The working is a comparison now: a label, its value, then the monster the
  // value came off, each on its own line under the Them column.
  const line = new RegExp(`${what}\\s*\\n${expected}\\s*\\nPaltivar`);
  if (!line.test(endgame)) {
    problems.push(`planner: level 40 is not measured against Paltivar's `
      + `${what.toLowerCase()} of ${expected} with bosses counted`);
  }
}
await page.screenshot({ path: `${outDir}/planner.png`, fullPage: false });
await page.uncheck("#plan-bosses");
await page.waitForTimeout(200);

// Number keys select a tab, and must not fire while a field has focus.
await page.click(`nav button[data-key="f2"]`);
await page.waitForTimeout(100);
await page.keyboard.press("5");
await page.waitForTimeout(200);
if (await page.getAttribute('nav button[data-key="gd"]', "aria-selected") !== "true") {
  problems.push("the 5 key did not open the Guides tab");
}
await page.keyboard.press("2");
await page.waitForTimeout(200);
if (await page.getAttribute('nav button[data-key="f2"]', "aria-selected") !== "true") {
  problems.push("the 2 key did not open the Monsters tab");
}
// Typing a query that contains a digit must stay in the box.
await page.click("#search");
await page.keyboard.type("2");
await page.waitForTimeout(200);
if (await page.getAttribute('nav button[data-key="f2"]', "aria-selected") !== "true") {
  problems.push("a digit typed into the search box navigated away");
}
if (await page.inputValue("#search") !== "2") {
  problems.push("a digit typed into the search box did not reach it");
}
await page.keyboard.press("Escape");
await page.waitForTimeout(150);
if (await page.inputValue("#search") !== "") problems.push("Escape did not clear the search");
await page.fill("#search", "");

// The selection survives a reload, which the cabinet does on every rebuild.
const storable = await page.evaluate(() => {
  try { localStorage.setItem("probe", "1"); return true; } catch (e) { return false; }
});
if (storable) {
  await page.click(`nav button[data-key="gd"]`);
  await pickDoc("strategy");
  await page.reload();
  await page.waitForSelector(".guide-doc", { timeout: 8000 });
  const selected = await page.getAttribute(
    '.guide-picker button[data-doc="strategy"]', "aria-current");
  if (selected !== "true") problems.push("the chosen guide was lost on reload");
  const tab = await page.getAttribute('nav button[data-key="gd"]', "aria-selected");
  if (tab !== "true") problems.push("the chosen tab was lost on reload");
  await page.evaluate(() => localStorage.clear());
  await page.reload();
  await page.waitForSelector("nav button", { timeout: 8000 });
} else {
  console.log("note: localStorage unavailable here, skipped the reload check");
}

// Search must filter, and must survive a query that matches nothing.
await page.click(`nav button[data-key="f2"]`);
await page.fill("#search", "skeleton");
await page.waitForTimeout(200);
const filtered = await page.locator('section[data-key="f2"] .picker option').count();
if (filtered === 0 || filtered > 6) problems.push(`search 'skeleton' matched ${filtered} monsters`);
await page.screenshot({ path: `${outDir}/search.png` });

await page.fill("#search", "zzzznotathing");
await page.waitForTimeout(200);
const empty = await page.locator('section[data-key="f2"] .empty').count();
if (!empty) problems.push("empty search state not shown");

// Every monster the game lists is drawn from its own record, so a card must
// carry a picture that actually decoded: an <img> whose source failed to
// parse still has a box, and only naturalWidth tells the two apart.
await page.fill("#search", "titan lord");
await page.waitForTimeout(200);
const art = await page.locator('section[data-key="f2"] .monster-art').evaluate(
  (img) => ({ w: img.naturalWidth, h: img.naturalHeight,
              attr: [img.width, img.height] })).catch(() => null);
if (!art) problems.push("monsters: no picture on the card");
else if (!art.w || !art.h) problems.push("monsters: the picture did not decode");
else if (art.w !== art.attr[0] || art.h !== art.attr[1]) {
  problems.push(`monsters: the picture is ${art.w}x${art.h} but the card says `
    + `${art.attr.join("x")}`);
}
await page.screenshot({ path: `${outDir}/monster-art.png` });

// The thirteen monsters that shoot get a block showing what they shoot.
await page.fill("#search", "elf assassin");
await page.waitForTimeout(200);
const shot = await page.locator('section[data-key="f2"] .shot-art').evaluate(
  (img) => img.naturalWidth).catch(() => 0);
if (!shot) problems.push("monsters: no projectile picture on a ranged monster");
// The section headings are uppercased in CSS, so innerText comes back shouting.
const rangedText = (await page.locator('section[data-key="f2"] .card')
  .innerText()).toLowerCase();
for (const expected of ["ranged attack", "% of turns", "fires on"]) {
  if (!rangedText.includes(expected)) {
    problems.push(`monsters: the ranged block has no "${expected}"`);
  }
}
await page.screenshot({ path: `${outDir}/monster-ranged.png` });

// The 72nd record is the game's own placeholder. It decodes, but it is not a
// monster and the clue book does not list it.
await page.fill("#search", "");
await page.waitForTimeout(200);
const monsters = await page.locator('section[data-key="f2"] .picker option').count();
if (monsters !== 71) problems.push(`monsters: ${monsters} listed, expected 71`);
// Sorted by level: the list opens on a level-1 monster and ends on the
// level-45 one. The option itself does not say, so the card is what is read.
const picker = page.locator('section[data-key="f2"] .picker');
const cardNote = page.locator('section[data-key="f2"] .card .note').first();
for (const [index, level] of [[0, 1], [monsters - 1, 45]]) {
  await picker.selectOption({ index });
  await page.waitForTimeout(150);
  const note = (await cardNote.innerText()).trim();
  if (note !== `Level ${level}` && !note.startsWith(`Level ${level} `)) {
    problems.push(`monsters: option ${index} of ${monsters} is "${note}", `
      + `expected level ${level}`);
  }
}
await picker.selectOption({ index: 0 });
await page.waitForTimeout(150);
const f2Text = await page.locator('section[data-key="f2"]').innerText();
if (/Not Used/i.test(f2Text)) problems.push("monsters: the placeholder record is listed");

// The spell view has to show what the clue book shows: who can cast a spell
// and at what level, whether it harms or heals, and single target versus area.
await page.fill("#search", "");
await page.click(`nav button[data-key="f3"]`);
await page.waitForTimeout(200);
const spellText = await page.locator('section[data-key="f3"]').innerText();
for (const expected of ["MP", "nuore", "Anytime"]) {
  if (!spellText.includes(expected)) problems.push(`spells: no "${expected}" shown`);
}
if (!/Monk \d+/.test(spellText)) problems.push("spells: no class levels shown");

// The game's three casting conditions are shown as one word each, and the
// reach chip is suppressed where it would only repeat the condition.
for (const w of ["Melee", "OOC", "Anytime"]) {
  if (!spellText.includes(w)) problems.push(`spells: no "${w}" condition shown`);
}
for (const raw of ["in hand to hand", "at a distance"]) {
  if (spellText.split("\n").some((l) => l.trim() === raw)) {
    problems.push(`spells: raw "${raw}" shown instead of a short label`);
  }
}
if (!spellText.includes("Ranged")) problems.push("spells: no Ranged reach shown");

// Damage and healing carry a per-resource rate. The two rates rank spells
// almost independently (Spearman 0.24), so both are shown: one does not
// stand in for the other.
// Scoped to the cards: the cost analysis further down the tab also carries
// .eff figures, and while its disclosure is closed they read as empty text.
const rates = await page.locator('section[data-key="f3"] .spell .eff').allInnerTexts();
if (rates.length < 100) problems.push(`spells: only ${rates.length} efficiency figures`);
if (!rates.some((t) => t.endsWith("/MP")) || !rates.some((t) => t.endsWith("/nuore"))) {
  problems.push("spells: efficiency is missing one of the two resources");
}
if (rates.some((t) => !/^\d+\.\d+\/(MP|nuore)$/.test(t))) {
  problems.push(`spells: malformed efficiency figure (${rates.find((t) => !/^\d+\.\d+\//.test(t))})`);
}
// Fireball is 95 damage for 50 MP and 28 nuore.
const fireball = await page.locator('section[data-key="f3"] .spell', { hasText: "Fireball" })
  .first().locator(".eff").allInnerTexts();
if (fireball.join(" ") !== "1.9/MP 3.4/nuore") {
  problems.push(`spells: Fireball rates read ${JSON.stringify(fireball)}`);
}
// A spell with no figure to divide, as Perfect Health restores "all health",
// must not invent a rate.
const perfect = await page.locator('section[data-key="f3"] .spell', { hasText: "Perfect Health" })
  .first().locator(".eff").count();
if (perfect) problems.push("spells: a rate was shown for a spell with no magnitude");
// A spell that restores a figure must show that figure, whatever words its
// description happens to use: Great Heal says "restore 500 points", not
// "health", and was filed as a utility spell because of it.
for (const [name, pill] of [["Great Heal", "500"], ["Restore Health", "200"]]) {
  const chip = await page.locator('section[data-key="f3"] .spell', { hasText: name })
    .first().locator(".chip.heal").allInnerTexts();
  if (!chip.includes(pill)) {
    problems.push(`spells: ${name} shows ${JSON.stringify(chip)}, expected a ${pill} heal pill`);
  }
}
// The Single/Area chip carries the scope, so the meta row must not repeat it.
for (const dupe of ["one monster", "all monsters", "one character", "monster",
                    "monsters", "character", "characters", "Foe", "Friend",
                    "Single", "Area", "scroll"]) {
  if (spellText.split("\n").some((l) => l.trim() === dupe)) {
    problems.push(`spells: "${dupe}" is shown as its own line, not as chip state`);
  }
}
// Scope, reach and how a class learns the spell are all iconographic; damage
// type rides the damage number, which takes the element's hue.
const icons = await page.locator('section[data-key="f3"]').evaluate((root) => {
  const chip = (name) => [...root.querySelectorAll(".spell")]
    .find((e) => e.querySelector("h4").textContent.trim() === name)
    ?.querySelector(".chip.harm");
  const color = (name) => {
    const c = chip(name);
    return c ? getComputedStyle(c).color : null;
  };
  return {
    scope: root.querySelectorAll(".chip.scope .icon.scope").length,
    // Scope must not re-encode friend-or-foe: that is the harm/heal color.
    sided: root.querySelectorAll(".chip.foe, .chip.friend").length,
    shapes: root.querySelectorAll(".icon.shape").length,
    scrolls: root.querySelectorAll(".cast-class .icon.scroll").length,
    glyphs: root.querySelectorAll(".chip.harm .icon.element-glyph").length,
    // An icon with no drawing in it is a silent failure, not a visible one.
    empty: [...root.querySelectorAll(".icon")].filter((e) => !e.children.length).length,
    fire: color("Fireball"),
    cold: color("Cold Slash"),
    electric: color("Lightning Bolt"),
    untyped: color("Turn Undead"),
  };
});
if (!icons.scope) problems.push("spells: no scope icons rendered");
if (icons.sided) problems.push("spells: scope still re-encodes friend-or-foe as color");
if (!icons.shapes) problems.push("spells: no reach shape icons rendered");
if (!icons.scrolls) problems.push("spells: no scroll icons on scroll-taught classes");
if (icons.glyphs < 20) problems.push(`spells: only ${icons.glyphs} damage-type glyphs`);
if (icons.empty) problems.push(`spells: ${icons.empty} icons drew nothing`);
// Each element is its own hue: fire and cold must not read as the same thing.
const hues = { fire: icons.fire, cold: icons.cold, electric: icons.electric,
               untyped: icons.untyped };
for (const [name, value] of Object.entries(hues)) {
  if (!value) problems.push(`spells: no damage chip found for the ${name} sample`);
}
if (new Set(Object.values(hues).filter(Boolean)).size !== Object.keys(hues).length) {
  problems.push(`spells: damage types share a color (${JSON.stringify(hues)})`);
}
// Small text on this ground needs real contrast; the sampled blood red had 2.5:1.
const contrast = await page.evaluate((rgb) => {
  const parse = (c) => c.match(/\d+(\.\d+)?/g).slice(0, 3).map(Number);
  const lum = (c) => {
    const [r, g, b] = parse(c).map((v) => {
      const x = v / 255;
      return x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4;
    });
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  };
  const bg = getComputedStyle(document.body).backgroundColor;
  const [a, b] = [lum(rgb), lum(bg)].sort((x, y) => y - x);
  return (a + 0.05) / (b + 0.05);
}, icons.untyped);
if (contrast < 4.5) {
  problems.push(`spells: untyped damage sits at ${contrast.toFixed(2)}:1 on the ground`);
}

// A monster-restricted spell is named by the monster, not by "<kind> only".
for (const stale of ["undead only", "insect only"]) {
  if (spellText.toLowerCase().includes(stale)) {
    problems.push(`spells: target qualifier still reads "${stale}"`);
  }
}

// Filtering by class narrows the list and orders it by that class's level.
const before = await page.locator('section[data-key="f3"] .spell').count();
await page.click('section[data-key="f3"] .chipbar button:nth-child(5)');
await page.waitForTimeout(250);
const after = await page.locator('section[data-key="f3"] .spell').count();
if (!(after > 0 && after < before)) {
  problems.push(`class filter did not narrow the list (${before} -> ${after})`);
}
const levels = await page.locator('section[data-key="f3"] .lvl').allInnerTexts();
const asNumbers = levels.map((t) => Number(t.replace("L", "")));
if (asNumbers.some((n, i) => i && n < asNumbers[i - 1])) {
  problems.push("filtered spells are not ordered by the level that class needs");
}
await page.click('section[data-key="f3"] .chipbar button:nth-child(1)');

// The cost analysis sits under the Spells tab's class chips, disclosed. It is
// the same six classes the chips filter, seen a second way, so it is scoped by
// the same control rather than getting a tab and a chipbar of its own.
await page.click(`nav button[data-key="f3"]`);
await page.waitForTimeout(250);
// A closed <details> still has its content in the DOM, so ask whether it is
// open rather than whether the content exists.
if (await page.locator('section[data-key="f3"] details.curve-box[open]').count()) {
  problems.push("the cost analysis is open before it is asked for");
}
// A one-word control should be the size of one word, not a band across the
// column: a full-width bar reads as a section header, not something to press.
const summaryBox = await page.locator('section[data-key="f3"] details.curve-box > summary')
  .boundingBox();
const columnBox = await page.locator('section[data-key="f3"]').boundingBox();
if (summaryBox.width > columnBox.width / 3) {
  problems.push(`the Efficiency control spans ${Math.round(summaryBox.width)}px `
    + `of a ${Math.round(columnBox.width)}px column`);
}

await page.click('section[data-key="f3"] details.curve-box > summary');
await page.waitForTimeout(250);
const curve = await page.locator('section[data-key="f3"]').evaluate((root) => ({
  classes: root.querySelectorAll(".curve-class").length,
  steps: root.querySelectorAll(".curve-step").length,
  rows: root.querySelectorAll("table.tiers tbody tr").length,
  text: root.innerText,
}));
// Six magic classes, listed once per resource.
if (curve.classes !== 12) problems.push(`curve: ${curve.classes} class columns, expected 12`);
if (curve.steps < 30) problems.push(`curve: only ${curve.steps} upgrade steps`);
if (curve.rows !== 3) problems.push(`curve: ${curve.rows} tier rows, expected 3`);
for (const expected of ["Sling Shot", "Eradicate", "even levels only"]) {
  if (!curve.text.includes(expected)) problems.push(`curve: missing "${expected}"`);
}
// Each step must beat the one before it: that is what makes it a step.
const monotonic = await page.locator('section[data-key="f3"] .curve-class')
  .evaluateAll((cols) => cols.every((col) => {
    const rates = [...col.querySelectorAll(".eff")].map((e) => Number(e.dataset.rate));
    return rates.every((r, i) => !i || r > rates[i - 1]);
  }));
if (!monotonic) problems.push("curve: an upgrade step does not improve on the previous");

// Picking a class narrows the analysis as well as the list: one control, not
// two, and the analysis follows the class you already chose.
await page.click(`section[data-key="f3"] .chipbar button:nth-child(5)`);
await page.waitForTimeout(250);
const scoped = await page.locator('section[data-key="f3"]').evaluate((root) => ({
  open: !!root.querySelector("details.curve-box[open]"),
  classes: root.querySelectorAll(".curve-class").length,
  named: [...root.querySelectorAll(".curve-class h4")].map((h) => h.textContent),
}));
if (!scoped.open) problems.push("the cost analysis closed when the class changed");
if (scoped.classes !== 2) {
  problems.push(`a single class should show 2 curve columns, showed ${scoped.classes}`);
}
if (!scoped.named.every((n) => n === "Mage")) {
  problems.push(`the analysis shows ${JSON.stringify(scoped.named)}, expected only Mage`);
}
// One column must not stretch to fill the row: a spell name at one end and its
// rate at the other is unreadable as a pair.
const col = await page.locator('section[data-key="f3"] .curve-class').first().boundingBox();
const tab = await page.locator('section[data-key="f3"]').boundingBox();
if (col.width > tab.width * 0.6) {
  problems.push(`a lone curve column spans ${Math.round(col.width)}px `
    + `of a ${Math.round(tab.width)}px tab`);
}
await page.screenshot({ path: `${outDir}/f3-costs.png` });
await page.click(`section[data-key="f3"] .chipbar button:nth-child(1)`);

// Maps: every area's page is a picture captured from the game, so the check
// that matters is that the image actually loads and is the right size, since a
// broken path shows as an empty box, not an error.
await page.click(`nav button[data-key="f1"]`);
await page.waitForTimeout(300);
const mapCount = await page.locator('section[data-key="f1"] .list button').count();
if (mapCount < 30) problems.push(`maps: only ${mapCount} areas listed`);
// The page is drawn from its grid, not shipped as a bitmap: the canvas is
// sized in game pixels and must actually have something painted on it.
const painted = (sel) => page.locator(sel).evaluate((e) => {
  const d = e.getContext("2d").getImageData(0, 0, e.width, e.height).data;
  let ink = 0, sum = 0;
  for (let i = 0; i < d.length; i += 4) { if (d[i + 3]) ink += 1; sum += d[i] + d[i + 1] + d[i + 2]; }
  return { w: e.width, h: e.height, ink, sum, label: e.getAttribute("aria-label") };
});
const firstMap = await painted('section[data-key="f1"] canvas.map-canvas');
// 40 cells x 8px, not the clue book's 34: the stored row is 40 wide and the
// three cells at each end are real squares the book crops.
if (firstMap.w !== 320 || firstMap.h !== 192) {
  problems.push(`maps: canvas is ${firstMap.w}x${firstMap.h}, expected 320x192`);
}
if (firstMap.ink !== firstMap.w * firstMap.h) problems.push("maps: the canvas has unpainted pixels");
if (!firstMap.label) problems.push("maps: the map canvas has no accessible name");
// Picking a different area has to change the picture, not just the caption.
await page.click('section[data-key="f1"] .list button:nth-child(3)');
await page.waitForTimeout(250);
const secondMap = await painted('section[data-key="f1"] canvas.map-canvas');
if (secondMap.sum === firstMap.sum) problems.push("maps: selecting an area did not redraw the map");
// The map must come before the picker: with 37 areas listed first you had to
// scroll past all of them to see the thing the tab exists for.
const order = await page.locator('section[data-key="f1"]').evaluate((root) => {
  const img = root.querySelector(".map-canvas");
  const list = root.querySelector(".maps-list");
  if (!img || !list) return null;
  return img.compareDocumentPosition(list) & Node.DOCUMENT_POSITION_FOLLOWING;
});
if (!order) problems.push("maps: the area list is not after the map");
// And it must not be able to push the map away again.
const listScrolls = await page.locator('section[data-key="f1"] .maps-list')
  .evaluate((e) => e.scrollHeight > e.clientHeight + 1);
if (!listScrolls) problems.push("maps: the area list is not capped and scrollable");
// The caption names the map and nothing else. Storage coordinates and the
// packer's fidelity figure are decoder bookkeeping, not something a reader of
// the page can act on.
const capText = await page.locator('section[data-key="f1"] .map figcaption').innerText();
if (!/\w/.test(capText)) problems.push("maps: the caption is empty");
if (/WORLD\.DAT|block \d+|slot \d+|% of the game's page/.test(capText)) {
  problems.push(`maps: the caption carries decoder bookkeeping (${capText})`);
}
// The 140 slots are one grid, and there is a picture of it: a globe on the
// caption line the map's name starts, which opens the picture over the panel
// rather than leaving for it. It holds the right of that line, so it is in the
// same place whichever map is showing.
const globe = page.locator('section[data-key="f1"] .map figcaption button.map-globe');
if (!(await globe.count())) problems.push("maps: no globe on the caption line");
const globeAt = await page.locator('section[data-key="f1"] .map figcaption').evaluate((cap) => {
  const name = cap.querySelector("strong").getBoundingClientRect();
  const icon = cap.querySelector(".map-globe").getBoundingClientRect();
  const box = cap.getBoundingClientRect();
  return { gap: Math.round(box.right - icon.right),
           sameLine: Math.abs((name.top + name.height / 2) - (icon.top + icon.height / 2)) < 8 };
});
if (!globeAt.sameLine) problems.push("maps: the globe is not on the name's line");
if (globeAt.gap > 2) problems.push(`maps: the globe is ${globeAt.gap}px off the right edge`);
const world = page.locator('section[data-key="f1"] dialog.world-map');
if (await world.evaluate((d) => d.open)) problems.push("maps: the world map starts open");
await globe.click();
if (!(await world.evaluate((d) => d.open))) problems.push("maps: the globe did not open the world");
const worldImg = await page.locator(".world-map-img").evaluate((i) => ({
  natural: i.naturalWidth, shown: Math.round(i.clientWidth),
}));
if (worldImg.natural !== 6400) {
  problems.push(`maps: the world map is ${worldImg.natural}px wide, expected 6400`);
}
// Fitted to the dialog to begin with, and at its own size on a click.
if (worldImg.shown >= worldImg.natural) problems.push("maps: the world map does not open fitted");
await page.click(".world-map-zoom");
const zoomed = await page.locator(".world-map-img").evaluate((i) => Math.round(i.clientWidth));
if (zoomed !== worldImg.natural) problems.push(`maps: actual size showed ${zoomed}px`);
await page.click(".world-map-close");
if (await world.evaluate((d) => d.open)) problems.push("maps: the world map would not close");
// Arrow keys walk the areas: with 37 of them, tabbing to the one below is not
// a reasonable ask.
const firstTitle = await page.locator('section[data-key="f1"] .map figcaption strong').innerText();
await page.locator('section[data-key="f1"] .maps-list [aria-current="true"]').focus();
await page.keyboard.press("ArrowDown");
await page.waitForTimeout(200);
const afterKey = await page.locator('section[data-key="f1"] .map figcaption strong').innerText();
if (afterKey === firstTitle) problems.push("maps: arrow keys do not change the area");
await page.keyboard.press("ArrowUp");
await page.waitForTimeout(200);

// Each gold square on the page is a legend line, and the map alone does not
// say which. The marker records do, so the badge on the square and the number
// in the list have to agree: that agreement is the whole feature.
const withMarks = await page.evaluate(() => Object.keys(window.RESTORATION.map_marks).length);
const areas = await page.locator('section[data-key="f1"] .maps-list button')
  .evaluateAll((bs) => bs.map((b) => b.textContent.trim()));
let listed = 0;
for (const title of areas) {
  await page.click(`section[data-key="f1"] .maps-list button:text-is("${title}")`);
  await page.waitForTimeout(60);
  const shape = await page.locator('section[data-key="f1"]').evaluate((root) => ({
    heading: (root.innerText.match(/On this map \((\d+)\)/) || [])[1],
    badges: [...root.querySelectorAll(".map-mark")].map((b) => b.textContent),
    items: [...root.querySelectorAll("ol.map-own li")].map((li) => li.value),
    offpage: root.querySelectorAll("ol.map-own .map-offpage").length,
    frame: root.querySelector(".map-frame") ? 1 : 0,
  }));
  if (!shape.frame) problems.push(`maps: ${title} has no map frame to place badges on`);
  if (shape.heading === undefined) continue;      // a page with no markers at all
  listed += 1;

  // Every line is numbered; every line that has a square on the printed page
  // carries a badge with the same number.
  if (Number(shape.heading) !== shape.items.length) {
    problems.push(`maps: ${title} lists ${shape.items.length} lines, heading says ${shape.heading}`);
  }
  if (shape.badges.length !== shape.items.length - shape.offpage) {
    problems.push(`maps: ${title} draws ${shape.badges.length} badges for `
      + `${shape.items.length - shape.offpage} on-page lines`);
  }
  const drawn = shape.badges.map(Number).sort((a, b) => a - b);
  if (new Set(drawn).size !== drawn.length) {
    problems.push(`maps: ${title} repeats a marker number (${drawn})`);
  }
  if (drawn.some((n) => !shape.items.includes(n))) {
    problems.push(`maps: ${title} has a badge with no matching line (${drawn})`);
  }
}
if (listed !== withMarks) {
  problems.push(`maps: ${listed} pages list their markers, the data has ${withMarks}`);
}

// A badge has to sit on the square it names. The canvas is scaled by CSS, so
// this is the check that catches a percentage computed against the wrong box.
await page.click(`section[data-key="f1"] .maps-list button:text-is("Copper Mine")`);
await page.waitForTimeout(120);
const placed = await page.locator('section[data-key="f1"]').evaluate((root) => {
  const frame = root.querySelector(".map-frame").getBoundingClientRect();
  const canvas = root.querySelector(".map-canvas").getBoundingClientRect();
  return [...root.querySelectorAll(".map-mark")].map((b) => {
    const r = b.getBoundingClientRect();
    return {
      inFrame: r.left >= frame.left - 2 && r.right <= frame.right + 2
        && r.top >= frame.top - 2 && r.bottom <= frame.bottom + 2,
      sameBox: Math.abs(frame.width - canvas.width) < 2
        && Math.abs(frame.height - canvas.height) < 2,
    };
  });
});
if (!placed.length) problems.push("maps: Copper Mine draws no badges");
if (placed.some((b) => !b.inFrame)) problems.push("maps: a badge sits outside the map");
if (placed.some((b) => !b.sameBox)) {
  problems.push("maps: the badge frame is not the same box as the canvas, so the "
    + "percentages are measured against the wrong thing");
}

const barText = await page.locator('section[data-key="f1"] .legend-bar .toggle')
  .innerText().catch(() => "");
if (barText && Number((barText.match(/\((\d+)\)/) || [0, 999])[1]) >= 137) {
  problems.push("maps: the unplaced list is the whole legend again");
}
const legendShown = await page.locator('section[data-key="f1"] .grid2:not(.map-own)').count();
if (legendShown) problems.push("maps: the legend is expanded before it is asked for");
if (barText) {
  await page.click('section[data-key="f1"] .legend-bar .toggle');
  await page.waitForTimeout(150);
  if (!await page.locator('section[data-key="f1"] .grid2:not(.map-own)').count()) {
    problems.push("maps: the legend toggle does not open it");
  }
}

// The legend stops at 138 labels; past that the section runs into the spell
// text, and a wrong bound shows up here as prose among the place names.
const legendText = await page.locator('section[data-key="f1"]').innerText();
if (legendText.includes("1234567890")) {
  problems.push("maps: the developer column ruler is shown as a legend label");
}
for (const stray of ["To a Single Player", "Of Cold Damage"]) {
  if (legendText.includes(stray)) problems.push(`maps: legend has run into the spell text ("${stray}")`);
}

// Items: the eight clue-book categories act as selectors the way the spell
// classes do, the list is searchable, and each field is printed in the ink the
// game prints it in.
await page.click(`nav button[data-key="f5"]`);
await page.waitForTimeout(250);
const allItems = await page.locator('section[data-key="f5"] .item').count();
if (allItems !== 170) problems.push(`items: ${allItems} listed, expected 170`);
const itemChips = await page.locator('section[data-key="f5"] .chipbar button').allInnerTexts();
if (itemChips.length < 6) problems.push(`items: only ${itemChips.length} category chips`);
// Every filter in the panel is the same control: the item categories must be
// styled exactly like the spell class selector, not fall back to a plain
// browser button.
const chipStyle = async (key) => page.locator(`section[data-key="${key}"] .chipbar button`)
  .first().evaluate((e) => {
    const s = getComputedStyle(e);
    return [e.className, s.color, s.backgroundColor, s.borderColor].join("|");
  });
await page.click(`nav button[data-key="f3"]`);
await page.waitForTimeout(200);
const spellChipStyle = await chipStyle("f3");
await page.click(`nav button[data-key="f5"]`);
await page.waitForTimeout(200);
const itemChipStyle = await chipStyle("f5");
if (spellChipStyle !== itemChipStyle) {
  problems.push(`filters are styled differently: spells ${spellChipStyle} vs items ${itemChipStyle}`);
}
await page.click('section[data-key="f5"] .chipbar button:nth-child(2)');
await page.waitForTimeout(200);
const armor = await page.locator('section[data-key="f5"] .item').count();
if (!(armor > 0 && armor < allItems)) {
  problems.push(`items: category filter did not narrow the list (${allItems} -> ${armor})`);
}
// Every armor piece shows an absorption; nothing else does.
const absOutside = await page.locator('section[data-key="f5"]').evaluate((root) =>
  [...root.querySelectorAll(".item")].filter((e) => !/abs\b/.test(e.innerText)).length);
if (absOutside) problems.push(`items: ${absOutside} armor pieces show no absorption`);
// Attribute enhancers has no items: the book gives it a rules page instead,
// and leaving the category out entirely would lose it.
const enhancerChip = itemChips.findIndex((t) => /attribute/i.test(t));
if (enhancerChip < 0) problems.push("items: no attribute-enhancers category");
else {
  await page.click(`section[data-key="f5"] .chipbar button:nth-child(${enhancerChip + 1})`);
  await page.waitForTimeout(200);
  const rulesText = await page.locator('section[data-key="f5"]').innerText();
  for (const expected of ["Scrolls", "Wands", "Gems", "to an attribute", "to a skill"]) {
    if (!rulesText.includes(expected)) problems.push(`items: enhancer rules missing "${expected}"`);
  }
}
// Transportations is the other category with no item list: three things that
// appear nowhere in the item records.
const rideChip = itemChips.findIndex((t) => /transport/i.test(t));
if (rideChip < 0) problems.push("items: no transportations category");
else {
  await page.click(`section[data-key="f5"] .chipbar button:nth-child(${rideChip + 1})`);
  await page.waitForTimeout(200);
  const rides = await page.locator('section[data-key="f5"]').innerText();
  for (const expected of ["Pegasus", "Giant Eagle", "Magic Dragon",
                          "Uses", "When", "Anytime"]) {
    if (!rides.includes(expected)) problems.push(`items: transports missing "${expected}"`);
  }
  await page.screenshot({ path: `${outDir}/items-transports.png` });
}

// A field the game prints on several rows comes through as several spans, so
// the whole of an effects entry is on the card, not just its first line.
await page.click('section[data-key="f5"] .chipbar button:nth-child(1)');
await page.waitForTimeout(150);
await page.fill("#search", "sword of light");
await page.waitForTimeout(250);
const lightSword = await page.locator('section[data-key="f5"] .item').first().innerText();
for (const expected of ["10 Strength", "10 Dexterity", "30 Slashing"]) {
  if (!lightSword.includes(expected)) {
    problems.push(`items: Sword of Light card is missing "${expected}"`);
  }
}
await page.fill("#search", "");
await page.waitForTimeout(150);
await page.screenshot({ path: `${outDir}/items-sample.png` });

// Search has to reach the item fields, not just the names.
await page.fill("#search", "slashing");
await page.waitForTimeout(250);
const bySkill = await page.locator('section[data-key="f5"] .item').count();
if (!(bySkill > 0 && bySkill < allItems)) {
  problems.push(`items: searching a field value matched ${bySkill} items`);
}
await page.fill("#search", "");
await page.waitForTimeout(200);

// The inks are the game's own: value yellow, damage red, container blue,
// skill green. Distinct colors, and each actually used.
const inks = await page.locator('section[data-key="f5"]').evaluate((root) => {
  const one = (sel) => {
    const e = root.querySelector(sel);
    return e ? getComputedStyle(e).color : null;
  };
  return { value: one(".ink.value"), harm: one(".ink.harm"),
           fits: one(".ink.fits"), skill: one(".ink.skill") };
});
for (const [name, value] of Object.entries(inks)) {
  if (!value) problems.push(`items: nothing rendered in the ${name} ink`);
}
if (new Set(Object.values(inks).filter(Boolean)).size !== 4) {
  problems.push(`items: field inks are not distinct (${JSON.stringify(inks)})`);
}

await page.fill("#search", "");
await page.click(`nav button[data-key="gd"]`);
await pickDoc("walkthrough");

// The reading view is one continuous document: pages are how the text was
// stored, not how it reads, and a location runs across them.
const wt = "section[data-key='gd']";
if (await page.locator(`${wt} .pageno`).count()) {
  problems.push("the reflowed walkthrough still shows page numbers");
}
const sections = await page.locator(`${wt} .wt-section h4`).count();
const located = await page.evaluate(() => window.RESTORATION.walkthrough_index.length);
if (sections !== located) {
  problems.push(`reflowed walkthrough has ${sections} locations, the index has ${located}`);
}

// Location 3 begins on page 1 and finishes on page 2. Reading it a page at a
// time split it in half, which is the bug this view exists to avoid.
const third = await page.locator(`${wt} .wt-section`).nth(2).textContent();
if (!/Room of portals/i.test(third) || !/Flagell will now send you/i.test(third)) {
  problems.push("a location that spans a page break is still split");
}

await page.click(`${wt} .toggle`);
await page.waitForTimeout(200);
const raw = await page.locator(`${wt} pre.raw`).count();
if (!raw) problems.push("walkthrough raw-layout toggle did not switch to <pre>");
// ...and the original view keeps its pages, which is the point of having it.
if (await page.locator(`${wt} .pageno`).count() !== raw) {
  problems.push("the original layout lost its page numbering");
}
await page.screenshot({ path: `${outDir}/f6-raw.png` });

await browser.close();

if (problems.length) {
  console.error("PANEL CHECK FAILED:");
  for (const p of problems) console.error("  -", p);
  process.exit(1);
}
console.log(`panel ok - screenshots in ${outDir}/`);
