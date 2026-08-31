// Boot the cabinet as a phone and prove it can be played by touch.
//
//   bun cabinet/serve.js &            (must already be running)
//   bun tools/mobile_check.js [--url=http://localhost:8080/] [--out=tmp/mobile]
//
// A phone is emulated: a narrow viewport, a device scale factor, and a
// pointer that is a finger. Chromium answers `(pointer: coarse)` for that, so
// the page takes the touch path on its own. Every tap here is a real touch
// event, not a click, since a click is what the page must never see from a
// finger.
import { chromium, devices } from "playwright";
import { mkdirSync } from "fs";

import { decodePng } from "../cabinet/png.js";
import { KEY_CODES as window_keys } from "../cabinet/keymap.js";

const arg = (n, d) => {
  const hit = process.argv.find((a) => a.startsWith(`--${n}=`));
  return hit === undefined ? d : hit.split("=").slice(1).join("=");
};
const url = arg("url", "http://localhost:8080/");
const outDir = arg("out", "tmp/mobile");
mkdirSync(outDir, { recursive: true });

const browser = await chromium.launch();
const problems = [];
const fail = (m) => { problems.push(m); console.error("  -", m); };

const phone = (name) => ({ ...devices[name], defaultBrowserType: undefined });

async function open(device, label) {
  const ctx = await browser.newContext(device);
  const page = await ctx.newPage();
  page.on("pageerror", (e) => fail(`${label}: pageerror: ${e.message}`));
  page.on("console", (m) => {
    if (m.type() !== "error") return;
    if (/ERR_INCOMPLETE_CHUNKED_ENCODING|ERR_ABORTED/.test(m.text())) return;
    fail(`${label}: console: ${m.text()}`);
  });
  await page.goto(url, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(800);
  return { ctx, page };
}

/** The layout must fit the screen: nothing scrolls, and the game is visible. */
async function fits(page, label) {
  const shape = await page.evaluate(() => {
    const box = (s) => document.querySelector(s)?.getBoundingClientRect();
    const screen = box("#screen"), touch = box("#touch"), bar = box("#bar");
    return {
      overflowX: document.documentElement.scrollWidth > innerWidth + 1,
      overflowY: document.documentElement.scrollHeight > innerHeight + 1,
      screenH: screen?.height ?? 0, screenW: screen?.width ?? 0,
      screenBottom: screen?.bottom ?? 0,
      touchShown: !!touch && getComputedStyle(document.querySelector("#touch")).display !== "none",
      touchBottom: touch?.bottom ?? 0,
      barW: Math.round(bar.width), barH: Math.round(bar.height),
      touchW: Math.round(touch?.width ?? 0),
      sideways: matchMedia("(orientation: landscape) and (max-height: 520px)").matches,
      winW: innerWidth, winH: innerHeight,
      touchBody: document.body.classList.contains("touch"),
    };
  });
  if (shape.overflowX) fail(`${label}: the page scrolls sideways`);
  if (shape.overflowY) fail(`${label}: the page scrolls down`);
  if (!shape.touchBody) fail(`${label}: the page did not notice the pointer is a finger`);
  if (shape.screenH < 150) fail(`${label}: the game is ${shape.screenH}px tall`);
  if (!shape.touchShown) fail(`${label}: the keys are not shown`);
  if (shape.touchBottom > shape.winH + 1) fail(`${label}: the keys run off the bottom of the screen`);
  if (shape.sideways) {
    // Everything of ours stands beside the game, which is the full height.
    if (shape.barH !== shape.winH) fail(`${label}: the header is ${shape.barH}px tall in a ${shape.winH}px window`);
    if (shape.screenH < shape.winH - 2) fail(`${label}: the game is ${shape.screenH}px tall in a ${shape.winH}px window`);
    const room = shape.winW - shape.barW - shape.touchW;
    if (shape.screenW < room - 2) fail(`${label}: the game is ${shape.screenW}px wide with ${room}px between the columns`);
  } else {
    if (shape.screenW < shape.winW - 2) fail(`${label}: the game is ${shape.screenW}px wide in a ${shape.winW}px window`);
    if (shape.barW !== shape.winW) fail(`${label}: the header is ${shape.barW}px wide in a ${shape.winW}px window`);
  }
  return shape;
}

const colors = async (page) => {
  const { rgb } = decodePng(await page.locator("#screen").screenshot());
  const seen = new Set();
  for (let i = 0; i < rgb.length; i += 3 * 37)
    seen.add((rgb[i] << 16) | (rgb[i + 1] << 8) | rgb[i + 2]);
  return seen.size;
};

async function boot(page, label) {
  await page.tap("#boot");
  const started = Date.now();
  while ((Date.now() - started) / 1000 < 120) {
    await page.waitForTimeout(2000);
    if (await colors(page) > 4) return true;
  }
  fail(`${label}: the game never painted`);
  return false;
}

/** Record what the emulator is sent, so a gesture can be read back. */
const spy = (page) => page.evaluate(() => {
  const ci = window.__cabinet.ci;
  window.__sent = [];
  for (const name of ["sendKeyEvent", "sendMouseButton", "sendMouseMotion", "sendMouseRelativeMotion"]) {
    const real = ci[name].bind(ci);
    ci[name] = (...a) => { window.__sent.push([name, ...a]); return real(...a); };
  }
});
const sent = (page) => page.evaluate(() => window.__sent.splice(0));
/** Wait for the game to have been sent `n` taps: a tap queues behind the
 *  cursor calibration, which can be probing when the finger lands. */
const tapped = (page, n) => page.waitForFunction((n) => window.__cabinet.taps >= n, n, { timeout: 20000 })
  .catch(() => {});
/** Wait until the log holds an event `test` accepts, then return the log. */
async function until(page, test, ms = 20000) {
  const started = Date.now();
  const log = [];
  while (Date.now() - started < ms) {
    log.push(...await sent(page));
    if (log.some(test)) return log;
    await page.waitForTimeout(100);
  }
  return log;
}

// --- portrait: the layout, then every gesture -------------------------------
{
  const label = "Pixel 7";
  const { ctx, page } = await open(phone("Pixel 7"), label);
  await fits(page, label);
  await page.screenshot({ path: `${outDir}/portrait-ready.png` });

  if (await boot(page, label)) {
    await page.waitForTimeout(3000);   // the cursor calibration asked for at boot
    await fits(page, `${label} running`);
    await page.screenshot({ path: `${outDir}/portrait-running.png` });
    await spy(page);

    // On a phone the book starts put away and the game's keys are out; the
    // Pad key puts them away and brings them back, lit while they are out.
    if (!(await page.evaluate(() => document.querySelector("#app").classList.contains("panel-hidden")))) {
      fail(`${label}: the book starts over the game`);
    }
    if (!(await page.isVisible('#touch .touch-pad'))) fail(`${label}: the pad does not start shown`);
    const padLit = () => page.getAttribute('#touch button[data-action="pad"]', "aria-pressed");
    if (await padLit() !== "true") fail(`${label}: the Pad key is not lit with the keys out`);
    await page.tap('#touch button[data-action="pad"]');
    await page.waitForTimeout(200);
    if (await page.isVisible('#touch .touch-pad')) fail(`${label}: the Pad key did not put the keys away`);
    if (await padLit() !== "false") fail(`${label}: the Pad key stays lit with the keys away`);
    await page.tap('#touch button[data-action="pad"]');
    await page.waitForTimeout(200);
    if (!(await page.isVisible('#touch .touch-pad'))) fail(`${label}: the pad does not come back`);
    for (const code of ["F1", "F4", "KeyR", "KeyP", "KeyA", "ArrowUp"]) {
      if (!(await page.isVisible(`#touch .touch-game button[data-keys="${code}"]`))) fail(`${label}: no ${code} key`);
    }
    // Actions on the left, arrows on the right.
    const [actions, pad] = await Promise.all([
      page.locator("#touch .touch-actions").boundingBox(), page.locator("#touch .touch-pad").boundingBox()]);
    if (!(actions.x + actions.width <= pad.x + 1)) fail(`${label}: the arrows are not to the right of the actions`);
    await fits(page, `${label} with the pad`);
    await page.screenshot({ path: `${outDir}/portrait-pad.png` });

    // A key on the pad is held for as long as the finger is on it.
    const up = page.locator('#touch .touch-pad button[data-keys="ArrowUp"]');
    const box = await up.boundingBox();
    const cdp = await ctx.newCDPSession(page);
    const touch = async (type, points) => cdp.send("Input.dispatchTouchEvent", {
      type, touchPoints: points.map(([x, y], i) => ({ x, y, id: i })) });
    const center = [box.x + box.width / 2, box.y + box.height / 2];
    await touch("touchStart", [center]);
    await page.waitForTimeout(150);
    let log = await sent(page);
    if (!log.some(([n, k, d]) => n === "sendKeyEvent" && k === window_keys.ArrowUp && d === true)) {
      fail(`${label}: holding the forward key sent nothing: ${JSON.stringify(log)}`);
    }
    if (log.some(([n, , d]) => n === "sendKeyEvent" && d === false)) {
      fail(`${label}: the key was released while the finger was still on it`);
    }
    await touch("touchEnd", []);
    await page.waitForTimeout(100);
    log = await sent(page);
    if (!log.some(([n, k, d]) => n === "sendKeyEvent" && k === window_keys.ArrowUp && d === false)) {
      fail(`${label}: lifting the finger did not release the key`);
    }

    // A sidestep is two keys down and up in the right order.
    const side = await page.locator('#touch button[data-keys="ControlLeft ArrowLeft"]').boundingBox();
    await touch("touchStart", [[side.x + 5, side.y + 5]]);
    await page.waitForTimeout(80);
    await touch("touchEnd", []);
    await page.waitForTimeout(80);
    log = (await sent(page)).filter(([n]) => n === "sendKeyEvent").map(([, k, d]) => `${k}:${d}`);
    const K = window_keys;
    const want = [`${K.ControlLeft}:true`, `${K.ArrowLeft}:true`, `${K.ArrowLeft}:false`, `${K.ControlLeft}:false`];
    if (log.join(" ") !== want.join(" ")) fail(`${label}: sidestep sent ${log.join(" ")}, wanted ${want.join(" ")}`);

    // A tap on the screen: the cursor homed and stepped to the spot, then a
    // left press and release. Four seconds later, with no other gesture, it
    // is parked in the far corner out of the way.
    const screen = await page.locator("#screen").boundingBox();
    const spot = [screen.x + screen.width * 0.5, screen.y + screen.height * 0.5];
    await touch("touchStart", [spot]);
    await page.waitForTimeout(60);
    await touch("touchEnd", []);
    await tapped(page, 1);
    log = await sent(page);
    const names = log.map(([n, a, b]) => n === "sendMouseButton" ? `${n}:${a}:${b}` : n);
    const home = names.indexOf("sendMouseRelativeMotion");
    const step = names.lastIndexOf("sendMouseRelativeMotion");
    const press = names.indexOf("sendMouseButton:0:true");
    const release = names.indexOf("sendMouseButton:0:false");
    if (home < 0 || step === home || press < step || release < press) {
      fail(`${label}: a tap sent ${names.join(" ")}`);
    }
    const [homeX, homeY] = log[home].slice(1);
    if (homeX > -3000 || homeY > -3000) fail(`${label}: the tap did not home the cursor first: ${homeX},${homeY}`);
    const taps = await page.evaluate(() => window.__cabinet.taps);
    if (taps !== 1) fail(`${label}: taps counted ${taps}, wanted 1`);
    await page.waitForTimeout(4600);
    log = await sent(page);
    const parked = log.find(([n, x, y]) => n === "sendMouseRelativeMotion" && x > 3000 && y > 3000);
    if (!parked) fail(`${label}: the cursor was not parked after the tap: ${JSON.stringify(log)}`);

    // A double tap: the second press carries no motion in front of it. After
    // a pause, or the first of these two would pair with the tap above.
    await page.waitForTimeout(600);
    await touch("touchStart", [spot]); await page.waitForTimeout(40); await touch("touchEnd", []);
    await page.waitForTimeout(120);
    await touch("touchStart", [[spot[0] + 3, spot[1] + 2]]); await page.waitForTimeout(40); await touch("touchEnd", []);
    await tapped(page, 3);
    await page.waitForTimeout(100);
    log = await sent(page).then((l) => l.filter(([n]) => n !== "sendKeyEvent"));
    const seq = log.map(([n, a, b]) => n === "sendMouseButton" ? `${a ? "R" : "L"}${b ? "v" : "^"}` : "m");
    const presses = seq.filter((s) => s === "Lv").length;
    const between = seq.slice(seq.indexOf("L^") + 1, seq.lastIndexOf("Lv"));
    if (presses !== 2) fail(`${label}: a double tap pressed ${presses} times: ${seq.join(" ")}`);
    else if (between.includes("m")) fail(`${label}: motion between the two presses of a double tap: ${seq.join(" ")}`);

    // A finger held still is the right button, down until it lifts.
    await page.waitForTimeout(500);
    await touch("touchStart", [[spot[0] + 60, spot[1]]]);
    log = await until(page, ([n, b, d]) => n === "sendMouseButton" && b === 1 && d === true, 3000);
    if (!log.some(([n, b, d]) => n === "sendMouseButton" && b === 1 && d === true)) {
      fail(`${label}: a long press did not press the right button`);
    }
    if (log.some(([n, b, d]) => n === "sendMouseButton" && b === 1 && d === false)) {
      fail(`${label}: the right button was released while the finger was still down`);
    }
    await touch("touchEnd", []);
    log = await until(page, ([n, b, d]) => n === "sendMouseButton" && b === 1 && d === false, 3000);
    if (!log.some(([n, b, d]) => n === "sendMouseButton" && b === 1 && d === false)) {
      fail(`${label}: lifting the finger did not release the right button`);
    }

    // The Right key arms the next tap.
    await page.waitForTimeout(500);
    const right = await page.locator('#touch button[data-action="right"]').boundingBox();
    await touch("touchStart", [[right.x + 5, right.y + 5]]); await page.waitForTimeout(40); await touch("touchEnd", []);
    const armed = await page.getAttribute('#touch button[data-action="right"]', "aria-pressed");
    if (armed !== "true") fail(`${label}: the Right key does not show it is armed`);
    await touch("touchStart", [[spot[0] - 60, spot[1]]]); await page.waitForTimeout(40); await touch("touchEnd", []);
    await tapped(page, 4);
    log = await sent(page);
    if (!log.some(([n, b, d]) => n === "sendMouseButton" && b === 1 && d === true)) {
      fail(`${label}: the tap after the Right key was not a right click`);
    }
    if (await page.getAttribute('#touch button[data-action="right"]', "aria-pressed") !== "false") {
      fail(`${label}: the Right key stayed armed after the tap`);
    }

    // The drawer, and the device's keyboard.
    await page.tap('#touch button[data-action="drawer"]');
    await page.waitForTimeout(100);
    if (!(await page.isVisible('#touch .touch-drawer button[data-keys="F1"]'))) {
      fail(`${label}: the drawer did not open`);
    }
    await fits(page, `${label} with the drawer open`);
    await page.screenshot({ path: `${outDir}/portrait-drawer.png` });
    await page.tap('#touch button[data-action="keyboard"]');
    await page.waitForTimeout(100);
    if (await page.evaluate(() => document.activeElement?.id) !== "typer") {
      fail(`${label}: the keyboard key did not focus the typing field`);
    }
    await page.keyboard.type("Ab 1");
    await page.keyboard.press("Enter");
    await page.keyboard.press("Backspace");
    await page.waitForTimeout(2000);   // seven keys at 160 ms each
    log = (await sent(page)).filter(([n]) => n === "sendKeyEvent").map(([, k, d]) => `${k}:${d}`).join(" ");
    const typed = [`${K.ShiftLeft}:true`, `${K.KeyA}:true`, `${K.KeyA}:false`, `${K.ShiftLeft}:false`,
                   `${K.KeyB}:true`, `${K.KeyB}:false`, `${K.Space}:true`, `${K.Space}:false`,
                   `${K.Digit1}:true`, `${K.Digit1}:false`, `${K.Enter}:true`, `${K.Enter}:false`,
                   `${K.Backspace}:true`, `${K.Backspace}:false`].join(" ");
    if (log !== typed) fail(`${label}: typing sent ${log}\n    wanted ${typed}`);

    // The clue book still works by touch: a tab, and the search box. It is
    // a page over the game, brought out by its button.
    await page.tap('#touch button[data-action="drawer"]');
    await page.tap("#toggle-panel");
    await page.waitForTimeout(300);
    const covers = await page.evaluate(() => {
      const p = document.querySelector("#panel").getBoundingClientRect();
      const a = document.querySelector("#app").getBoundingClientRect();
      return Math.abs(p.width - a.width) < 2 && Math.abs(p.height - a.height) < 2;
    });
    if (!covers) fail(`${label}: the book does not cover the game when opened`);
    const frame = page.frames().find((f) => f.url().includes("panel.html"));
    if (!frame) fail(`${label}: no clue book frame`);
    else {
      await frame.waitForSelector("nav button", { timeout: 20000 });
      await frame.locator('nav button[data-key="f2"]').tap();
      await page.waitForTimeout(300);
      const shown = await frame.evaluate(() => document.querySelector('section[data-key="f2"]:not([hidden])') !== null);
      if (!shown) fail(`${label}: tapping the Monsters tab did not open it`);
      const heights = await frame.evaluate(() =>
        // The tab row is the page's own nav; a guide's outline is another.
        [...document.querySelector("body > nav").querySelectorAll(":scope > button")]
          .map((b) => `${b.textContent.trim()}:${Math.round(b.getBoundingClientRect().height)}`));
      const tall = Math.min(...heights.map((h) => Number(h.split(":").pop())));
      if (tall < 40) fail(`${label}: a tab is ${tall}px tall, too small for a finger: ${heights.join(" ")}`);
    }
    await page.screenshot({ path: `${outDir}/portrait-book.png` });

    // Put away, the pad stays away on the next visit.
    await page.tap("#toggle-panel");
    await page.tap('#touch button[data-action="pad"]');
    await page.reload({ waitUntil: "domcontentloaded" });
    await page.waitForTimeout(500);
    if (await page.isVisible('#touch .touch-pad')) fail(`${label}: the pad was not remembered as put away`);
  }
  await ctx.close();
}

// --- on its side: the game is the screen, the book lies over it -------------
{
  const label = "Pixel 7 landscape";
  const { ctx, page } = await open(phone("Pixel 7 landscape"), label);
  const shape = await fits(page, label);
  const hidden = await page.evaluate(() => document.querySelector("#app").classList.contains("panel-hidden"));
  if (!hidden) fail(`${label}: the clue book starts open, on top of the game`);
  if (await page.getAttribute("#toggle-panel", "aria-pressed") !== "false") {
    fail(`${label}: the book button does not show the book is away`);
  }
  if (shape.screenBottom > shape.winH + 1) fail(`${label}: the game runs off the bottom`);
  await page.screenshot({ path: `${outDir}/landscape-ready.png` });
  // Full screen and the book are separate switches: the book stays away.
  await page.tap("#toggle-full");
  await page.waitForTimeout(300);
  if (!(await page.evaluate(() => document.querySelector("#app").classList.contains("panel-hidden")))) {
    fail(`${label}: full screen brought the book out`);
  }
  await page.tap("#toggle-full");
  await page.waitForTimeout(300);
  await page.tap("#toggle-panel");
  await page.waitForTimeout(300);
  const over = await page.evaluate(() => {
    const p = document.querySelector("#panel").getBoundingClientRect();
    const a = document.querySelector("#app").getBoundingClientRect();
    return Math.abs(p.width - a.width) < 2 && Math.abs(p.height - a.height) < 2;
  });
  if (!over) fail(`${label}: the book does not cover the game when opened`);
  await page.screenshot({ path: `${outDir}/landscape-book.png` });
  await page.tap("#toggle-panel");
  await ctx.close();
}

// --- a small phone: still one screen ---------------------------------------
{
  const label = "iPhone SE";
  const { ctx, page } = await open(phone("iPhone SE"), label);
  await fits(page, label);
  await page.screenshot({ path: `${outDir}/se-ready.png` });
  await ctx.close();
}

// --- installable ------------------------------------------------------------
{
  const label = "manifest";
  const { ctx, page } = await open(phone("Pixel 7"), label);
  const manifest = await page.evaluate(async () => {
    const link = document.querySelector('link[rel="manifest"]');
    const m = await (await fetch(link.href)).json();
    const icons = await Promise.all(m.icons.map(async (i) =>
      (await fetch(new URL(i.src, link.href))).status));
    const start = (await fetch(new URL(m.start_url, link.href))).status;
    const sw = await navigator.serviceWorker.ready.then((r) => !!r.active).catch(() => false);
    return { display: m.display, icons, start, sw };
  });
  if (manifest.display !== "standalone") fail(`${label}: display is ${manifest.display}`);
  if (manifest.icons.some((s) => s !== 200)) fail(`${label}: an icon is missing: ${manifest.icons}`);
  if (manifest.start !== 200) fail(`${label}: start_url answers ${manifest.start}`);
  if (!manifest.sw) fail(`${label}: no service worker took the page`);
  await ctx.close();
}

await browser.close();
if (problems.length) {
  console.error(`MOBILE CHECK FAILED: ${problems.length} problem(s)`);
  process.exit(1);
}
console.log(`mobile check passed; screenshots in ${outDir}/`);
