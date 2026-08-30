// Boot the cabinet in a real browser and prove the game is running inside it.
//
//   bun cabinet/serve.js &            (must already be running)
//   bun tools/cabinet_check.js [--url=http://localhost:8080/] [--out=tmp/cabinet]
import { chromium } from "playwright";
import { mkdirSync, writeFileSync, unlinkSync } from "fs";

import { decodePng } from "../cabinet/png.js";

const arg = (n, d) => {
  const hit = process.argv.find((a) => a.startsWith(`--${n}=`));
  return hit === undefined ? d : hit.split("=").slice(1).join("=");
};
const url = arg("url", "http://localhost:8080/");
const outDir = arg("out", "tmp/cabinet");
mkdirSync(outDir, { recursive: true });

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
const problems = [];
page.on("pageerror", (e) => problems.push(`pageerror: ${e.message}`));
// The panel-rebuild watcher holds an open EventSource on /events. Navigating
// away aborts that response, and Chromium reports the abort as a failed
// resource, which is not a fault in the page: it is what leaving a streaming
// connection looks like. Everything else counts.
const navigationAbort = (text) =>
  /ERR_INCOMPLETE_CHUNKED_ENCODING|ERR_ABORTED/.test(text);
page.on("requestfailed", (r) => {
  if (r.url().endsWith("/events") && navigationAbort(r.failure()?.errorText ?? "")) return;
  problems.push(`request failed: ${r.url()} ${r.failure()?.errorText}`);
});
page.on("console", (m) => {
  if (m.type() !== "error") return;
  if (navigationAbort(m.text())) return;
  problems.push(`console: ${m.text()}`);
});

await page.goto(url, { waitUntil: "domcontentloaded" });

// The canvas is transferred to the worker, so its pixels can only be read back
// through an element screenshot.
const colors = async () => {
  const { rgb } = decodePng(await page.locator("#screen").screenshot());
  const seen = new Set();
  for (let i = 0; i < rgb.length; i += 3 * 37)
    seen.add((rgb[i] << 16) | (rgb[i + 1] << 8) | rgb[i + 2]);
  return seen.size;
};

// The shell must fit the window in every configuration: having to scroll to
// see the bottom of the game is a bug, not a preference.
for (const label of ["panel shown", "panel hidden"]) {
  const overflows = await page.evaluate(() =>
    document.documentElement.scrollHeight > window.innerHeight + 1 ||
    document.documentElement.scrollWidth > window.innerWidth + 1);
  if (overflows) problems.push(`the page scrolls with the ${label}`);
  if (label === "panel shown") await page.click("#toggle-panel");
}
// One header for the whole application: it spans both panes and the toggle
// must not shift when the panel collapses.
const barSpans = await page.evaluate(() =>
  Math.round(document.querySelector("#bar").getBoundingClientRect().width) ===
  Math.round(document.documentElement.clientWidth));
if (!barSpans) problems.push("the header does not span the full window");

const toggleX = () => page.evaluate(() =>
  Math.round(document.querySelector("#toggle-panel").getBoundingClientRect().x));
const xCollapsed = await toggleX();
await page.click("#toggle-panel");   // restore
if (await toggleX() !== xCollapsed) problems.push("the panel toggle moves with the panel");
const pressed = await page.getAttribute("#toggle-panel", "aria-pressed");
if (pressed !== "true") problems.push("panel toggle did not return to its pressed state");

// The edge between the panes is draggable, and where it was left is where it
// is on the next visit. The game keeps a floor whatever the drag asks for:
// a clue book wide enough to read is no use beside a screen too small to play.
{
  const width = () => page.evaluate(() =>
    Math.round(document.querySelector("#panel").getBoundingClientRect().width));
  const stage = () => page.evaluate(() =>
    Math.round(document.querySelector("#stage").getBoundingClientRect().width));
  const before = await width();
  const grip = await page.locator("#grip").boundingBox();
  await page.mouse.move(grip.x + grip.width / 2, grip.y + 100);
  await page.mouse.down();
  await page.mouse.move(10, grip.y + 100, { steps: 10 });   // as far as it goes
  await page.mouse.up();
  await page.waitForTimeout(200);
  const dragged = await width();
  if (dragged <= before) {
    problems.push(`the panel did not widen with the grip: ${before} -> ${dragged}`);
  }
  if (await stage() < 300) {
    problems.push(`dragging left the game ${await stage()}px, below its floor`);
  }
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.waitForSelector("#grip");
  if (await width() !== dragged) {
    problems.push(`the panel width was not kept: ${dragged} -> ${await width()}`);
  }
  // The frame is given its src by the page rather than by the markup, so the
  // checks below this one wait for it the way the first visit did.
  await page.waitForFunction(() => {
    const f = document.querySelector("#panel");
    return f && f.contentDocument
      && f.contentDocument.querySelector("nav button");
  }, { timeout: 20000 });
  await page.locator("#grip").dblclick();
  await page.waitForTimeout(200);
  if (await width() !== before) {
    problems.push(`a double-click did not restore the default width: ${await width()}`);
  }

  // A drag whose release the grip never hears. Mid-drag the panel is made
  // untouchable so the pointer cannot fall into the frame, and a drag left
  // open leaves it that way: the clue book stays dead until something presses
  // the grip again. Every way out of a drag has to close it.
  for (const [how, escape] of [
    ["the window losing focus", async () => page.evaluate(() => window.dispatchEvent(new Event("blur")))],
    ["a release off the grip", async () => page.evaluate(() =>
      document.dispatchEvent(new PointerEvent("pointerup", { bubbles: true })))],
  ]) {
    await page.evaluate(() => {
      const g = document.querySelector("#grip");
      const box = g.getBoundingClientRect();
      g.dispatchEvent(new PointerEvent("pointerdown", {
        bubbles: true, pointerId: 1, clientX: box.x + 3, clientY: box.y + 50 }));
    });
    await page.waitForTimeout(100);
    await escape();
    await page.waitForTimeout(150);
    const stuck = await page.evaluate(() =>
      getComputedStyle(document.querySelector("#panel")).pointerEvents === "none");
    if (stuck) problems.push(`a drag ended by ${how} left the panel untouchable`);
  }
}

// Full screen is the document's, so Escape and the browser's own controls
// leave it without this button being pressed: what is asserted is that the
// button follows the document rather than its own idea of the state.
if (await page.locator("#toggle-full").isHidden()) {
  problems.push("no full-screen button, in an engine that has full screen");
} else {
  await page.click("#toggle-full");
  await page.waitForTimeout(300);
  const inFull = await page.evaluate(() => !!document.fullscreenElement);
  if (!inFull) problems.push("the full-screen button did not reach full screen");
  if (await page.getAttribute("#toggle-full", "aria-pressed") !== String(inFull)) {
    problems.push("the full-screen button does not carry the document's state");
  }
  await page.keyboard.press("Escape");
  await page.waitForTimeout(300);
  if (await page.evaluate(() => !!document.fullscreenElement)) {
    await page.click("#toggle-full");
    await page.waitForTimeout(300);
  }
  if (await page.getAttribute("#toggle-full", "aria-pressed") !== "false") {
    problems.push("leaving full screen left the button pressed");
  }
}

// Embedded, the panel must not draw a second header under the application's.
const panelHeader = await page.frameLocator("#panel").locator("header").count()
  .catch(() => 0);
const headerShown = panelHeader
  ? await page.frames()[1].evaluate(() =>
      getComputedStyle(document.querySelector("header")).display !== "none")
  : false;
if (headerShown) problems.push("the embedded panel still renders its own header");

// The search box must stay reachable when the tab row wraps.
const searchOk = await page.frames()[1].evaluate(() => {
  const s = document.querySelector("#search").getBoundingClientRect();
  const nav = document.querySelector("nav").getBoundingClientRect();
  return s.width > 0 && s.right <= nav.right + 1;
});
if (!searchOk) problems.push("the panel search box is clipped out of the tab row");

// The panel is embedded in an iframe and must render on its own.
const frame = page.frameLocator("#panel");
await frame.locator("nav button").first().waitFor({ timeout: 15000 })
  .catch(() => problems.push("embedded Restoration panel did not render"));

await page.click("#boot");

// Wait for the canvas to show something other than a blank screen: sample it
// until more than one distinct color appears.
const started = Date.now();
let painted = false;
while ((Date.now() - started) / 1000 < 120) {
  await page.waitForTimeout(2000);
  if (await colors() > 4) { painted = true; break; }
}
if (!painted) problems.push("canvas never showed a picture; DOSBox did not start");

// Audio has to be wired up explicitly: the backend hands over samples but
// plays nothing on its own.
const audio = await page.evaluate(() => {
  const a = window.__cabinet.audio;
  return a ? { state: a.context.state, rate: a.context.sampleRate } : null;
});
if (!audio) problems.push("audio was never started");
else if (audio.state !== "running") problems.push(`audio context is ${audio.state}`);
else if (!audio.rate) problems.push("audio context has no sample rate");

// Volume sits behind its icon. The slider has to be one click away, and the
// icon has to keep showing the state after the menu closes: a control you
// cannot read at a glance is worse than the slider it replaced.
const menuOpen = () => page.isVisible("#volume-menu");
const isMuted = () => page.evaluate(() =>
  document.querySelector("#volume-control").classList.contains("muted"));

if (await menuOpen()) problems.push("the volume menu starts open");
// The two dropdowns must not be open at once: one covers the other.
await page.click("#saves-toggle");
await page.click("#volume-toggle");
if (await page.isVisible("#saves-menu")) {
  problems.push("opening one dropdown left the other open");
}
if (!await menuOpen()) problems.push("the volume menu did not open over the other");
await page.keyboard.press("Escape");

await page.click("#volume-toggle");
if (!await menuOpen()) problems.push("clicking the volume icon did not open the slider");
if (await page.getAttribute("#volume-toggle", "aria-expanded") !== "true") {
  problems.push("the volume icon does not report itself expanded");
}
await page.screenshot({ path: `${outDir}/volume.png`, clip: { x: 0, y: 0, width: 1440, height: 180 } });

// The slider is vertical, so loud is up. A browser that ignores the rule
// silently renders it horizontal, which is exactly the kind of failure a
// screenshot check would not catch.
const sliderBox = await page.locator("#volume").boundingBox();
if (!sliderBox || sliderBox.height <= sliderBox.width) {
  problems.push(`the volume slider is not vertical (${JSON.stringify(sliderBox)})`);
}
// It hangs under the icon, so it has to hang square under it. The menu is
// wider than the button, which is what makes an edge anchor look like a
// centered one until you measure it.
const menuBox = await page.locator("#volume-menu").boundingBox();
const toggleBox = await page.locator("#volume-toggle").boundingBox();
const center = (b) => b.x + b.width / 2;
if (Math.abs(center(menuBox) - center(toggleBox)) > 1) {
  problems.push(`the volume menu is not centered on its icon `
    + `(menu ${center(menuBox)}, icon ${center(toggleBox)})`);
}
// And it must stay inside the window: it sits at the end of the header.
const width = await page.evaluate(() => document.documentElement.clientWidth);
if (menuBox.x < 0 || menuBox.x + menuBox.width > width + 1) {
  problems.push(`the volume menu overflows the window (${JSON.stringify(menuBox)})`);
}

// Loud is up. A vertical range whose direction is not flipped runs the other
// way, which looks right in a screenshot and is wrong under the hand.
await page.fill("#volume", "50");
await page.focus("#volume");
await page.keyboard.press("ArrowUp");
const afterUp = await page.inputValue("#volume");
if (Number(afterUp) <= 50) {
  problems.push(`up does not raise the volume (50 -> ${afterUp})`);
}

await page.fill("#volume", "0");
await page.dispatchEvent("#volume", "input");
await page.waitForTimeout(150);
if (!await isMuted()) problems.push("volume control does not reflect a muted setting");
if (await page.textContent("#volume-value") !== "0") {
  problems.push("the volume readout does not follow the slider");
}

await page.keyboard.press("Escape");
if (await menuOpen()) problems.push("Escape did not close the volume menu");
if (!await isMuted()) problems.push("the icon stops showing muted once the menu closes");

await page.click("#volume-toggle");
await page.fill("#volume", "70");
await page.dispatchEvent("#volume", "input");
// Clicking anywhere else must put it away, or it covers the game.
await page.click("#bar strong");
if (await menuOpen()) problems.push("clicking outside did not close the volume menu");
if (await isMuted()) problems.push("volume control stayed muted after being turned up");

const statusText = await page.textContent("#status");
await page.screenshot({ path: `${outDir}/booted.png` });

// fsTree/fsReadFile is the cabinet's data channel; prove it is reachable. Saving
// is what walks it, and the readout is what it produced. Everything to do with
// saving lives behind one header button now, so open it first.
const openSaves = async () => {
  if (!await page.isVisible("#saves-menu")) await page.click("#saves-toggle");
};
await openSaves();
await page.click("#save-now");
await page.waitForTimeout(3000);
const saves = await page.textContent("#saves");
if (!saves || !saves.trim()) problems.push("filesystem read produced no output");
await page.screenshot({ path: `${outDir}/saves.png` });

// Save now always finishes the sentence it starts.
//
// This does not reproduce the case the button was fixed for. That needs two
// saves in a row to write the same files at the same total size. The emulator
// is stopped here so nothing changes between the presses, and the saves still
// came back with a count of zero. That was never the stuck path. What this
// holds is the invariant: no press leaves "saving..." standing.
await page.evaluate(() => window.__cabinet.ci.pause());
await page.waitForTimeout(500);
for (const press of ["first", "second"]) {
  await openSaves();
  await page.click("#save-now");
  await page.waitForTimeout(3000);
  const said = (await page.textContent("#status") ?? "").trim();
  if (/^saving/i.test(said)) {
    problems.push(`the ${press} Save now left the status at "${said}"`);
  }
}
await page.evaluate(() => window.__cabinet.ci.resume());
await page.waitForTimeout(500);

// Persistence: the game's disk must survive the tab closing, and a save must
// carry only what changed: the game data is 21MB and is never written to.
const persisted = await page.evaluate(async () => {
  const enc = new TextEncoder();
  await window.__cabinet.ci.fsWriteFile("CHECK.TXT", enc.encode("cabinet check"));
  await new Promise((r) => setTimeout(r, 500));
  return null;
});
await openSaves();
await page.click("#save-now");
await page.waitForTimeout(3000);
const stored = await page.evaluate(() => new Promise((resolve) => {
  const req = indexedDB.open("yendor3-cabinet", 1);
  req.onsuccess = () => {
    const q = req.result.transaction("state").objectStore("state").get("files");
    q.onsuccess = () => resolve(q.result
      ? Object.entries(q.result).map(([k, v]) => [k, v.byteLength])
      : []);
    q.onerror = () => resolve([]);
  };
  req.onerror = () => resolve([]);
}));
if (!stored.length) problems.push("nothing was persisted");
if (!stored.some(([name]) => name.toUpperCase().includes("CHECK.TXT"))) {
  problems.push("the written file was not persisted");
}
const totalKb = stored.reduce((t, [, n]) => t + n, 0) / 1024;
if (totalKb > 4096) {
  problems.push(`a save wrote ${totalKb.toFixed(0)}kB; only changed files should be stored`);
}
console.log(`persisted ${stored.length} files, ${totalKb.toFixed(1)} kB`);

// Every icon-only button must still say what it is. Dropping the text label
// is how a header quietly becomes unusable without sight of it.
const unnamed = await page.evaluate(() => {
  const bad = [];
  for (const b of document.querySelectorAll("#bar button")) {
    const named = (b.textContent || "").trim() || b.getAttribute("aria-label");
    if (!named) bad.push(b.id || b.outerHTML.slice(0, 40));
    if (!b.getAttribute("title")) bad.push(`${b.id} (no tooltip)`);
  }
  return bad;
});
for (const b of unnamed) problems.push(`header button without a name: ${b}`);

// The host pointer must be hidden over the game: the guest draws its own.
const hidden = await page.evaluate(() =>
  getComputedStyle(document.querySelector("#screen")).cursor === "none");
if (!hidden) problems.push("the host cursor is visible over the game area");

// A rebuild must reload the panel without disturbing the running game: the
// emulator lives in the parent document, so only the iframe may be replaced.
const beforeSrc = await page.getAttribute("#panel", "src");
// A marker on the parent window: if the parent reloaded, this is gone, and
// so would the running game be.
await page.evaluate(() => { window.__probe = "still here"; });
// Poll rather than wait a fixed 2.5s. The watcher debounces and the panel is
// most of half a megabyte, so a fixed wait raced the reload and made this
// check flap. Re-touch the file between rounds too: recursive fs.watch drops
// events often enough on this filesystem that one write is not a reliable
// trigger, and this check is about what the browser does with a rebuild, not
// about inotify.
let afterSrc = beforeSrc;
for (let attempt = 0; attempt < 3 && afterSrc === beforeSrc; attempt += 1) {
  writeFileSync("web/.reload-probe.json", JSON.stringify({ t: Date.now() }));
  for (let i = 0; i < 24 && afterSrc === beforeSrc; i += 1) {
    await page.waitForTimeout(250);
    afterSrc = await page.getAttribute("#panel", "src");
  }
}
const survived = await page.evaluate(() => window.__probe);
if (afterSrc === beforeSrc) problems.push("panel iframe was not reloaded on rebuild");
if (survived !== "still here") problems.push("the parent page reloaded; the game would have been lost");
// The game changes video mode as it runs, so the canvas buffer legitimately
// changes size; what matters is that it is still being painted. Poll for it:
// the game fades between screens, so a single sample can catch a frame that is
// legitimately almost black and read as "stopped".
let stillPainting = false;
for (let i = 0; i < 20 && !stillPainting; i += 1) {
  stillPainting = await colors() > 4;
  if (!stillPainting) await page.waitForTimeout(500);
}
if (!stillPainting) problems.push("the emulator stopped painting after the reload");
try { unlinkSync("web/.reload-probe.json"); } catch {}

// The Keep characters button, and the graft it sets up.
//
// Its guard first: with nothing created, it must say so rather than storing an
// empty roster that would then be spliced into WORLD.DAT at every boot.
// CURGAME is written once the game is past its splash chain, not at startup,
// so walk through the splashes the way a player would and wait for the file to
// appear. Clicking Keep before that tests the "not yet" branch instead.
let curgame = 0;
for (let i = 0; i < 40 && curgame !== 81037; i += 1) {
  curgame = await page.evaluate(async () => {
    const ci = window.__cabinet.ci;
    for (const key of [256, 32]) {                 // esc, then space
      ci.sendKeyEvent(key, true);
      await new Promise((r) => setTimeout(r, 80));
      ci.sendKeyEvent(key, false);
      await new Promise((r) => setTimeout(r, 200));
    }
    try { return (await ci.fsReadFile("CURGAME")).length; } catch { return -1; }
  });
  if (curgame !== 81037) await page.waitForTimeout(1000);
}
if (curgame !== 81037) problems.push(`CURGAME never reached its full size (${curgame})`);

// Now that the game has written CURGAME, the Save button can be held to what
// it claims: it must list the file, say it will not survive, and not store it.
// The game overwrites all 81,037 bytes at every launch, so a stored copy would
// be read by nothing.
await openSaves();
// The saves panel is far wider than its icon and sits near the end of the
// header, so it is the one that has to be slid back into the window. It should
// be centered on its button as far as the window allows, and no further.
const savesBox = await page.locator("#saves-menu").boundingBox();
const savesToggle = await page.locator("#saves-toggle").boundingBox();
const pageWidth = await page.evaluate(() => document.documentElement.clientWidth);
const MARGIN = 6;
const wanted = savesToggle.x + savesToggle.width / 2 - savesBox.width / 2;
const expected = Math.min(Math.max(wanted, MARGIN), pageWidth - MARGIN - savesBox.width);
if (Math.abs(savesBox.x - expected) > 1) {
  problems.push(`the saves menu is not placed under its button `
    + `(at ${savesBox.x}, expected ${expected})`);
}
if (savesBox.x < 0 || savesBox.x + savesBox.width > pageWidth + 1) {
  problems.push(`the saves menu overflows the window (${JSON.stringify(savesBox)})`);
}

await page.click("#save-now");
await page.waitForTimeout(3000);
const listing = await page.textContent("#saves");
if (!/CURGAME/.test(listing || "")) {
  problems.push(`the listing does not mention CURGAME (said: ${listing})`);
} else if (!/CURGAME.*rebuilt at launch, not kept/.test(listing)) {
  problems.push("the listing does not say CURGAME is rebuilt at launch");
}

const keys = await page.evaluate(() => new Promise((resolve) => {
  const req = indexedDB.open("yendor3-cabinet", 1);
  req.onsuccess = () => {
    const q = req.result.transaction("state").objectStore("state").get("files");
    q.onsuccess = () => resolve(Object.keys(q.result || {}));
    q.onerror = () => resolve([]);
  };
  req.onerror = () => resolve([]);
}));
if (keys.some((k) => k.toUpperCase().includes("CURGAME"))) {
  problems.push(`CURGAME was stored even though it is rebuilt at launch (${keys})`);
}
if (!keys.some((k) => k.toUpperCase().includes("CHECK.TXT"))) {
  problems.push(`the save stopped keeping files it should keep (${keys})`);
}
console.log("stored:", keys.join(", "));

await openSaves();
await page.click("#keep-characters");
// Poll: reading the roster goes through the worker, and the status line is
// shared with the panel-reload watcher, so a fixed wait can read the wrong
// message rather than a late one.
let guard = "";
for (let i = 0; i < 40; i += 1) {
  guard = await page.textContent("#status");
  if (/no created characters|^kept /i.test(guard)) break;
  await page.waitForTimeout(250);
}
if (!/no created characters/i.test(guard)) {
  problems.push(`Keep characters did not refuse an empty roster (said: ${guard})`);
}

// Then the path that matters: a stored roster has to reach the emulator, and
// it can only do that through WORLD.DAT: the game rebuilds CURGAME at every
// launch, so a character stored as a save file would never be read.
await page.evaluate(async () => {
  const r = await import("/cabinet/roster.js");
  const p = await import("/cabinet/persist.js");
  const roster = new Uint8Array(r.SLOTS * r.SLOT);
  roster.set(new TextEncoder().encode("ZORBAX"), r.SLOT);
  await p.saveRoster(roster);
});
// The slider is remembered, so the reload below is also the test of that:
// somebody who turned the sound down is not asked to do it again.
await openSaves();
await page.click("#volume-toggle");
await page.fill("#volume", "35");
await page.dispatchEvent("#volume", "input");
await page.keyboard.press("Escape");

await page.reload({ waitUntil: "domcontentloaded" });
const keptVolume = await page.inputValue("#volume");
if (keptVolume !== "35") problems.push(`the volume was not remembered (${keptVolume})`);
if (await page.textContent("#volume-value") !== "35") {
  problems.push("the volume readout does not show the remembered setting");
}
await page.click("#boot");
const rebooted = Date.now();
let repainted = false;
while ((Date.now() - rebooted) / 1000 < 120) {
  await page.waitForTimeout(2000);
  if (await colors() > 4) { repainted = true; break; }
}
if (!repainted) problems.push("the game did not start again with a kept roster stored");

// The same reboot proves the save path end to end: CHECK.TXT was written into
// the emulated disk, stored by the Save button, and must now be back on the
// emulated disk of a freshly booted emulator. Without that, persistence stores
// files nobody ever reads again.
const restored = await page.evaluate(async () => {
  try {
    return new TextDecoder().decode(await window.__cabinet.ci.fsReadFile("CHECK.TXT"));
  } catch (e) { return `ERROR: ${e.message}`; }
});
if (restored !== "cabinet check") {
  problems.push(`a persisted file did not come back after a reload (got ${JSON.stringify(restored)})`);
}

const roster = await page.evaluate(async () => {
  const r = await import("/cabinet/roster.js");
  const world = await window.__cabinet.ci.fsReadFile("WORLD.DAT");
  return r.slotsOf(world, r.ROSTER).map((s) => s.name);
});
if (!roster.includes("ZORBAX")) {
  problems.push(`the kept character never reached WORLD.DAT (roster: ${JSON.stringify(roster)})`);
}
for (const stock of ["SQUIRE", "DIANA", "YENDOR", "JOSEPHINE"]) {
  if (!roster.includes(stock)) problems.push(`the graft lost the stock character ${stock}`);
}
const keptStatus = await page.textContent("#status");
if (!/ZORBAX/.test(keptStatus)) {
  problems.push(`the status line does not name the kept character (said: ${keptStatus})`);
}
console.log("roster in WORLD.DAT:", roster.join(", "));

await browser.close();

console.log("status:", statusText);
console.log("filesystem:", (saves || "").split("\n")[0]);
if (problems.length) {
  console.error("SHIM CHECK FAILED:");
  for (const p of problems) console.error("  -", p);
  process.exit(1);
}
console.log(`cabinet ok - screenshots in ${outDir}/`);
