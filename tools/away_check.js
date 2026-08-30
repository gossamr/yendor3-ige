// Does the cabinet stop the emulator when the player leaves, and start it
// again when they come back?
//
// Away is two conditions, and the engines report different ones. Both are
// driven here. A hidden page is one. A page still on screen but no longer
// focused is the other. That is what switching application looks like.
//
// Both are driven through stubs. No headless engine models real backgrounding:
// Playwright's Firefox reports a page as visible and focused with another tab
// in front of it. A frame counter that stalls there says the browser stopped
// painting, not that the page stopped the game. window.__cabinet.paused tells
// the two apart.
//
//   bun cabinet/serve.js --port=8080 &
//   bun tools/away_check.js --url=http://localhost:8080/
//                           [--browser=chromium|firefox|webkit]
import * as playwright from "playwright";

const arg = (n, d) => {
  const hit = process.argv.find((a) => a.startsWith(`--${n}=`));
  return hit === undefined ? d : hit.split("=").slice(1).join("=");
};
const url = arg("url", "http://localhost:8080/");
const engineName = arg("browser", "chromium");
const engine = playwright[engineName];
if (!engine) throw new Error(`no such browser: ${engineName}`);

const browser = await engine.launch();
const page = await browser.newPage({ viewport: { width: 1200, height: 800 } });
const problems = [];
page.on("pageerror", (e) => problems.push(`pageerror: ${e.message}`));

const fail = async (why) => {
  console.error(`AWAY CHECK FAILED (${engineName}): ${why}`);
  for (const p of problems) console.error("  -", p);
  await browser.close();
  process.exit(1);
};

await page.goto(url, { waitUntil: "domcontentloaded" });
await page.click("#boot");

const frames = () => page.evaluate(() => window.__cabinet?.frames ?? -1);
const paused = () => page.evaluate(() => window.__cabinet?.paused ?? null);

// A stalled counter only means something once it has been moving.
const startedAt = Date.now();
let running = false;
while (Date.now() - startedAt < 120000) {
  const a = await frames();
  await page.waitForTimeout(2000);
  if (a > 0 && await frames() > a) { running = true; break; }
}
if (!running) await fail("the game never started painting; nothing to measure");
console.log(`${engineName}: booted, ${await frames()} frames painted`);

// The frame counter cannot answer this. js-dos delivers a frame when the
// picture changes, and the game sits on a static screen most of the time. A
// flat counter means the screen is still, not the emulator. Sound messages
// keep coming whatever is on screen, and asyncifyStats reports them.
const sound = () => page.evaluate(async () =>
  (await window.__cabinet.ci.asyncifyStats()).messageSound);

/** Sound messages the emulator sent while the page sat in this state. */
const advanced = async () => {
  const a = await sound();
  await page.waitForTimeout(1500);
  return await sound() - a;
};

// document.hidden has no setter, and document.hasFocus() follows the real
// window. Both are stood in for. The events are real, and so is everything the
// page does in response.
await page.evaluate(() => {
  window.__away = { hidden: false, focus: true };
  Object.defineProperty(document, "hidden", {
    configurable: true, get: () => window.__away.hidden,
  });
  document.hasFocus = () => window.__away.focus;
});

const set = async (state, event, target) => {
  await page.evaluate(({ s, e, t }) => {
    Object.assign(window.__away, s);
    (t === "window" ? window : document).dispatchEvent(new Event(e));
  }, { s: state, e: event, t: target });
  await page.waitForTimeout(300);   // the handler reads focus a task later
};

const expect = async (what, wantPaused, wantRunning) => {
  const is = await paused();
  const n = await advanced();
  const moving = n > 2;
  console.log(`  ${what.padEnd(26)} paused=${String(is).padEnd(5)} ${n} sound messages`);
  if (is !== wantPaused) problems.push(`${what}: paused is ${is}, wanted ${wantPaused}`);
  if (moving !== wantRunning) {
    problems.push(`${what}: ${n} sound messages, wanted the emulator ${wantRunning ? "running" : "stopped"}`);
  }
};

await expect("running", false, true);

// The tab is no longer the one on screen.
await set({ hidden: true }, "visibilitychange", "document");
await expect("hidden", true, false);
await set({ hidden: false }, "visibilitychange", "document");
await expect("shown again", false, true);

// The tab is still on screen, but the browser is not the active application.
// Safari reports only this one. Watching visibility alone is not enough.
await set({ focus: false }, "blur", "window");
await expect("visible but unfocused", true, false);
await set({ focus: true }, "focus", "window");
await expect("focused again", false, true);

// Focus moving into the panel must not read as leaving. Checked against the
// real document.hasFocus(), which is the call being relied on.
await page.evaluate(() => {
  delete document.hidden;
  delete document.hasFocus;
});
await page.evaluate(() => document.querySelector("#panel").contentDocument
  .querySelector("nav button").focus());
await page.waitForTimeout(300);
const focusInPanel = await page.evaluate(() => document.hasFocus());
if (!focusInPanel) problems.push("document.hasFocus() is false with focus inside the panel");
await expect("focus in the panel", false, true);

if (problems.length) await fail(`${problems.length} problem(s)`);
console.log(`away ok in ${engineName}`);
await browser.close();
