// Prove the trainer reaches the running game's memory.
//
//   make trainer && bun cabinet/serve.js --port=8080 &
//   bun tools/trainer_check.js --url=http://localhost:8080/
//
// Boots the cabinet with ?trainer, waits for the game, then finds the data
// segment and reads the four party slots out of it. The names are the proof:
// they can only be right if the anchor, the handles and the record stride are
// all right.
import { chromium } from "playwright";
import { mkdirSync } from "fs";

const arg = (n, d) => {
  const hit = process.argv.find((a) => a.startsWith(`--${n}=`));
  return hit === undefined ? d : hit.split("=").slice(1).join("=");
};
const url = arg("url", "http://localhost:8080/");
const outDir = arg("out", "tmp/trainer");
mkdirSync(outDir, { recursive: true });

const problems = [];
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
page.on("pageerror", (e) => problems.push(`pageerror: ${e.message}`));
await page.goto(`${url}?trainer`, { waitUntil: "domcontentloaded" });

// The cabinet waits to be switched on: nothing boots until the power button
// in the header is pressed.
await page.waitForSelector("#boot", { timeout: 30000 });
await page.click("#boot");

// Reaching a party takes the menu walk, so drive it from here.
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
await sleep(20000);
const type = async (keys, gap = 700) => {
  for (const k of keys) { await page.keyboard.press(k); await sleep(gap); }
};
for (let i = 0; i < 40; i++) { await page.keyboard.press("Escape"); await sleep(200); }
await type(["a"], 4000);
await type(["6", "7", "8", "9"]);
await type(["d"], 3000);
await type(["e"], 14000);
await type(["r"], 3000);
await page.screenshot({ path: `${outDir}/00-in-game.png` });

const frame = page.frames().find((f) => f.url().includes("panel.html"));
if (!frame) problems.push("no clue-book frame");
else {
  const tab = frame.locator('nav button[data-key="tr"]');
  if (!(await tab.count())) problems.push("no trainer tab");
  else {
    // The tab reads the game on a timer, so there is nothing to press: give it
    // long enough to find the data segment, which means searching the heap.
    // Until it has one there is nothing to show, and the tab has to say so
    // rather than stand there as a shell of empty tables.
    await tab.click();
    if (await frame.locator('section[data-key="tr"] .trainer-body').isVisible()) {
      problems.push("the tab showed its controls before it had a game");
    }
    await frame.waitForSelector('section[data-key="tr"] table tbody tr',
                               { timeout: 60000 });
    if (!(await frame.locator('section[data-key="tr"] .trainer-body').isVisible())) {
      problems.push("the tab stayed hidden after it found the party");
    }
    const names = await frame.locator('section[data-key="tr"] tbody th').allInnerTexts();
    const fail = await frame.locator('section[data-key="tr"] .trainer-note').allInnerTexts();
    console.log("party:", names.join(", ") || fail.join("; "));
    const want = ["Squire", "Diana", "Yendor", "Josephine"];
    if (names.length !== 4 || want.some((n, i) => names[i] !== n)) {
      problems.push(`trainer read ${JSON.stringify(names)}, expected ${JSON.stringify(want)}`);
    }
    await frame.locator('section[data-key="tr"]').screenshot({ path: `${outDir}/01-trainer.png` });

    // What the tab is lives behind a button, so the button has to open it.
    await frame.locator('section[data-key="tr"] .trainer-about-open').click();
    const about = frame.locator('section[data-key="tr"] .trainer-about');
    if (!(await about.evaluate((d) => d.open))) problems.push("the about dialog did not open");
    await about.screenshot({ path: `${outDir}/04-about.png` });
    await about.locator("button").click();

    // Reading is half of it. Write a value the game did not have, read it back
    // out of the game's own memory, and the round trip is proved.
    const row = frame.locator('section[data-key="tr"] tbody tr').first();
    const field = row.locator("input.trainer-num").first();
    const was = await field.inputValue();
    await field.fill("777");
    await row.locator("button.toggle").first().click();
    // The value has to survive a tick: the tab overwrites every field it is
    // not being typed into with what the game says, so reading 777 back after
    // a refresh is the game holding it, not the input remembering it.
    await frame.waitForTimeout(2500);
    const now = await field.inputValue();
    console.log(`poke: ${was} -> ${now}`);
    if (now !== "777") problems.push(`poke did not stick: read back ${now}`);

    // And an item into the first empty carried slot.
    const carried = row.locator("td.trainer-state");
    const before = (await carried.innerText()).trim();
    // The item list is 631 long, so it comes with a filter: narrow it, then
    // pick out of what is left.
    const filter = frame.locator('section[data-key="tr"] .trainer-filter');
    await filter.fill("crossbow +10");
    const what = frame.locator('section[data-key="tr"] .trainer-what');
    const options = await what.locator("option").count();
    if (options !== 1) problems.push(`filter left ${options} items, expected 1`);
    await what.selectOption({ label: "Crossbow +10" });
    await frame.locator('section[data-key="tr"] .trainer-give').click();
    await frame.waitForTimeout(2500);
    const after = (await carried.innerText()).trim();
    console.log(`give: ${JSON.stringify(before)} -> ${JSON.stringify(after)}`);
    // The carried list is no longer shown, the column being what ails them,
    // so the item's arrival is proved by the game rather than by the panel.
    if (after !== "\u2014") problems.push(`condition column shows ${after}`);

    // The sheet: twenty-six numbers held twice. Open it from the row, write a
    // maximum, and read it back out of the game.
    await row.locator("th button.trainer-sheet").click();
    await frame.waitForSelector('section[data-key="tr"] .trainer-sheet-table');
    const rows = await frame.locator('section[data-key="tr"] .trainer-sheet-table tbody tr').count();
    if (rows !== 14) problems.push(`sheet has ${rows} rows, expected 14`);
    const strength = frame.locator('section[data-key="tr"] input[aria-label="Strength max"]');
    const wasStrength = await strength.inputValue();
    await strength.fill("41");
    await strength.dispatchEvent("change");
    await frame.waitForTimeout(2500);
    const nowStrength = await strength.inputValue();
    console.log(`strength max: ${wasStrength} -> ${nowStrength}`);
    if (nowStrength !== "41") problems.push(`stat did not stick: ${nowStrength}`);
    // Skills sit in the same table's second half.
    const thievery = frame.locator('section[data-key="tr"] input[aria-label="Thievery now"]');
    if (!(await thievery.count())) problems.push("no thievery field on the sheet");
    await frame.locator('section[data-key="tr"] .trainer-stats')
      .screenshot({ path: `${outDir}/03-sheet.png` });

    // The purse: three packed-BCD counters in the roster's header slot.
    const gold = frame.locator('section[data-key="tr"] input[aria-label="gold"]');
    const wasGold = await gold.inputValue();
    await gold.fill("12345");
    await frame.locator('section[data-key="tr"] .trainer-pay').click();
    await frame.waitForTimeout(2500);
    const nowGold = await gold.inputValue();
    console.log(`gold: ${wasGold} -> ${nowGold}`);
    if (nowGold !== "12345") problems.push(`gold did not stick: ${nowGold}`);
    // Where and when: both are words in the roster's header slot, and both are
    // read back from the game rather than from the control that set them.
    const whereText = () => frame.locator('section[data-key="tr"] .trainer-at').innerText();
    const startedAt = (await whereText()).trim();
    const where = frame.locator('section[data-key="tr"] .trainer-where');
    await where.selectOption({ label: "Copper Mine" });
    await frame.locator('section[data-key="tr"] .trainer-go').click();
    await frame.waitForTimeout(2500);
    const nowAt = (await whereText()).trim();
    console.log(`where: ${JSON.stringify(startedAt)} -> ${JSON.stringify(nowAt)}`);
    if (!/^Copper Mine/.test(nowAt)) problems.push(`teleport did not land: ${nowAt}`);

    const clock = frame.locator('section[data-key="tr"] input[type="time"]');
    const wasClock = await clock.inputValue();
    await clock.fill("23:45");
    await clock.dispatchEvent("change");
    await frame.waitForTimeout(2500);
    const nowClock = await clock.inputValue();
    console.log(`clock: ${wasClock} -> ${nowClock}`);
    if (nowClock !== "23:45") problems.push(`clock did not stick: ${nowClock}`);

    // The fight. This session never picks one, since the party is walked to a
    // roster and no further, so what is proved here is that both reads run
    // and report honestly: the three engaged buffers, and the eighty spawn
    // slots, which are only read when they are asked for. That they read the
    // right numbers off a monster is proved against a real one instead, by
    // tools/fight_probe.js.
    const fight = frame.locator('section[data-key="tr"] .trainer-mobs tbody tr');
    console.log(`engaged: ${await fight.count()}`);
    await frame.locator('section[data-key="tr"] .trainer-onmap').check();
    await frame.waitForTimeout(2500);
    console.log(`with the map: ${await fight.count()} monster rows`);
    const stillOk = await frame.locator('section[data-key="tr"] .trainer-note').innerText();
    if (stillOk.trim()) problems.push(`reading the spawn table failed: ${stillOk}`);

    // The memory window, watching the roster header that gold sits in. Change
    // the gold and the change has to show up in the log.
    // Everything below is in the debug block, which starts collapsed.
    await frame.locator('section[data-key="tr"] .trainer-debug summary').click();
    await frame.locator('section[data-key="tr"] .watch-go').click();
    await frame.waitForTimeout(2500);
    const dump = await frame.locator('section[data-key="tr"] .watch-dump').innerText();
    if (!/^cedd /.test(dump)) problems.push(`dump starts ${JSON.stringify(dump.slice(0, 24))}`);
    // 87,654,321 gold: a value picked to be somewhere the search can only find
    // by looking, rather than one the game might hold anywhere else.
    await gold.fill("87654321");
    await frame.locator('section[data-key="tr"] .trainer-pay').click();
    await frame.waitForTimeout(2500);
    const log = await frame.locator('section[data-key="tr"] .watch-log').innerText();
    console.log(`watch log: ${JSON.stringify(log.split("\n")[0] || "")}`);
    if (!/\+0xcf9[01]/.test(log)) problems.push(`the watch logged ${JSON.stringify(log)}`);

    // And the search, which is the same value looked for from the other end:
    // gold is four bytes of packed BCD at roster offset 180, so DS +0xcf91.
    await frame.locator('section[data-key="tr"] .watch-value').fill("87654321");
    await frame.locator('section[data-key="tr"] .watch-width').selectOption("bcd");
    await frame.locator('section[data-key="tr"] .watch-search').click();
    await frame.waitForTimeout(4000);
    const hits = await frame.locator('section[data-key="tr"] .watch-hits button').allInnerTexts();
    console.log(`search: ${hits.join(", ") || "nothing"}`);
    if (!hits.includes("DS +0xcf91")) problems.push(`search missed the gold: ${hits.join(", ")}`);

    // The write side of the same window: gold is four BCD bytes at DS +0xcf91,
    // so writing 00 00 00 42 there has to come back as 42 in the purse.
    const putAt = frame.locator('section[data-key="tr"] .watch-put-at');
    const putBytes = frame.locator('section[data-key="tr"] .watch-put-bytes');
    await putAt.fill("0xcf91");
    await putBytes.fill("00 00 00 42");
    await frame.locator('section[data-key="tr"] .watch-write').click();
    await frame.waitForTimeout(2500);
    const poked = await gold.inputValue();
    console.log(`memory write: gold -> ${poked}`);
    if (poked !== "42") problems.push(`the memory write did not land: gold ${poked}`);

    // Freezing is that write made on every tick, so setting the gold to
    // something else has to be undone by the next one.
    await putBytes.fill("00 00 00 99");
    await frame.locator('section[data-key="tr"] .watch-freeze').click();
    await gold.fill("5000");
    await frame.locator('section[data-key="tr"] .trainer-pay').click();
    await frame.waitForTimeout(3000);
    const held = await gold.inputValue();
    console.log(`frozen: set to 5000, reads ${held}`);
    if (held !== "99") problems.push(`the freeze did not hold: gold ${held}`);
    await frame.locator('section[data-key="tr"] .watch-thaw').click();
    if (await frame.locator('section[data-key="tr"] .watch-thaw').count()) {
      problems.push("thawing left the value frozen");
    }

    // Position: band and cell within the map the party is already on.
    await frame.locator('section[data-key="tr"] .debug-band').fill("5");
    await frame.locator('section[data-key="tr"] .debug-cell').fill("6");
    await frame.locator('section[data-key="tr"] .debug-place').click();
    await frame.waitForTimeout(2500);
    const placed = (await whereText()).trim();
    console.log(`placed: ${JSON.stringify(placed)}`);
    if (!/band 5 cell 6/.test(placed)) problems.push(`the party did not move: ${placed}`);

    // The monster editor has nothing to edit here, and has to say so rather
    // than show a stale record. Clearing the map is eighty writes that must
    // all land.
    const mobPick = frame.locator('section[data-key="tr"] .debug-mob');
    if (await mobPick.locator("option").count()) {
      problems.push("the monster picker offered a monster where there are none");
    }
    await frame.locator('section[data-key="tr"] .debug-clear').click();
    await frame.waitForTimeout(2500);
    const afterClear = (await frame.locator('section[data-key="tr"] .trainer-note').innerText()).trim();
    if (afterClear) problems.push(`clearing the map failed: ${afterClear}`);

    // The planner watches the same party and plans whichever character it is
    // given, from the level that character is at. A character out of the game
    // is not editable here: its numbers are the game's, and the fields that
    // would contradict them are disabled.
    await frame.locator('nav button[data-key="pl"]').click();
    // Nothing to press: the tab watches the party the way the trainer does,
    // more slowly, and fills itself in.
    const who = frame.locator('section[data-key="pl"] .plan-who');
    await who.waitFor({ state: "visible", timeout: 30000 });
    // The picker is keyed by party slot, and shows the name against it.
    const planned = await who.evaluate((s) => s.selectedOptions[0].textContent);
    console.log(`planner read: ${planned}`);
    if (planned.toLowerCase() !== names[0].toLowerCase()) {
      problems.push(`the planner loaded ${planned}, expected ${names[0]}`);
    }
    if (!(await frame.locator('section[data-key="pl"] .plan-class').isDisabled())) {
      problems.push("the planner let a character read out of the game be re-classed");
    }
    const plannedLevel = (await frame.locator(
      'section[data-key="pl"] .plan-level').innerText()).trim();
    const firstRow = await frame.locator(
      'section[data-key="pl"] .plan-career tbody tr[data-level]').first()
      .getAttribute("data-level");
    if (firstRow !== plannedLevel) {
      problems.push(`the career starts at ${firstRow}, not the character's ${plannedLevel}`);
    }
    // The slot being planned survives a reload of the panel; without it the
    // tab comes back on whoever the party lists first.
    const slots = await who.locator("option").allTextContents();
    if (slots.length > 1) {
      await who.selectOption({ label: slots[1] });
      await frame.waitForTimeout(800);
      // The frame alone, not the page: reloading the page would end the game.
      await frame.evaluate(() => location.reload());
      const again = frame.locator('section[data-key="pl"] .plan-who');
      await frame.locator('nav button[data-key="pl"]').click({ timeout: 30000 });
      await again.waitFor({ state: "visible", timeout: 30000 });
      const kept = await again.evaluate((s) => s.selectedOptions[0].textContent);
      if (kept !== slots[1]) {
        problems.push(`the planner came back on ${kept}, not the chosen ${slots[1]}`);
      }
      console.log(`planner kept the slot: ${kept}`);
    }

    await frame.locator('section[data-key="pl"]').screenshot({ path: `${outDir}/06-planner.png` });
    await frame.locator('nav button[data-key="tr"]').click();

    await frame.locator('section[data-key="tr"]').screenshot({ path: `${outDir}/02-poked.png` });
    await frame.locator('section[data-key="tr"] .trainer-debug')
      .screenshot({ path: `${outDir}/05-debug.png` });
  }
}
await browser.close();
if (problems.length) {
  console.log("TRAINER CHECK FAILED:");
  for (const p of problems) console.log("  - " + p);
  process.exit(1);
}
console.log(`trainer ok - screenshots in ${outDir}/`);
