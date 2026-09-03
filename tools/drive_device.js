// Drive an Android device's Chrome over DevTools, through the adb proxy.
//
//   bun tools/adb_proxy.js &
//   bun tools/drive_device.js status
//
// Actions: reload | boot | wait | tap fx fy | dtap | hold fx fy ms | tapkey
// <label> | key <code> | holdkey | type <text> | shot <name> | page | eval
// <js> | status. Coordinates are fractions of the canvas, so they do not
// depend on the device's size.
//
// The device must be reachable through tools/adb_proxy.js, and the page must
// be in a foreground tab, since Chrome on Android freezes background ones.
import { chromium } from "playwright";
import { mkdirSync } from "fs";
import { decodePng } from "../cabinet/png.js";
const browser = await chromium.connectOverCDP("http://127.0.0.1:9222");
const ctx = browser.contexts()[0];
// The visible tab, not the first of many: a background tab in Chrome on
// Android is frozen, and a page reloaded there never loads its emulator.
const ours = ctx.pages().filter((p) => p.url().includes("localhost:8080"));
let page = null;
for (const p of ours) {
  const visible = await p.evaluate(() => document.visibilityState === "visible").catch(() => false);
  if (visible) { page = p; break; }
}
page ??= ours[0] ?? ctx.pages()[0];
for (const p of ours) if (p !== page) await p.close().catch(() => {});
await page.bringToFront().catch(() => {});
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const [action, ...args] = process.argv.slice(2);
// Where a shot lands, beside every other check's.
const OUT = process.env.YENDOR_OUT ?? "tmp/device";
mkdirSync(OUT, { recursive: true });
const canvasBox = async () => page.locator("#screen").boundingBox();
// How many distinct colors the screen is showing, which is how a booted game
// is told from a blank canvas. The screen is drawn by WebGL now, whose buffer
// is cleared once it has been composited, so there is no context on this side
// to read pixels out of: the element is screenshotted instead, the way
// tools/cabinet_check.js does it.
const colors = async () => {
  // Short timeout, and no colors where it fails: the canvas is hidden until
  // the game is running, and a screenshot of a hidden element waits for it to
  // appear, which would stall the poll below rather than answer it.
  const shot = await page.locator("#screen").screenshot({ timeout: 3000 }).catch(() => null);
  if (!shot) return 0;
  const { rgb } = decodePng(shot);
  const s = new Set();
  for (let i = 0; i < rgb.length; i += 3 * 37) s.add((rgb[i] << 16) | (rgb[i + 1] << 8) | rgb[i + 2]);
  return s.size;
};
const painted = async (limit = 240000) => {
  const t0 = Date.now();
  while (Date.now() - t0 < limit) { await sleep(4000); if (await colors() > 4) return Math.round((Date.now() - t0) / 1000); }
  return null;
};
const status = () => page.textContent("#status");
const cdp = await ctx.newCDPSession(page);
const touchAt = async (x, y, ms = 60) => {
  await cdp.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [{ x, y }] });
  await sleep(ms);
  await cdp.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
};
const touchEl = async (locator) => { const b = await locator.boundingBox(); await touchAt(b.x + b.width / 2, b.y + b.height / 2); };
switch (action) {
  case "reload": {
    await page.goto(`http://localhost:8080/?r=${Date.now()}`, { waitUntil: "domcontentloaded" });
    await page.waitForSelector("#touch .touch-main button", { timeout: 20000 });
    console.log("loaded;", await status());
    break;
  }
  case "boot": {
    await touchEl(page.locator("#boot"));
    console.log(`painted after ${await painted()}s;`, await status());
    break;
  }
  case "bootlog": {
    page.on("console", (m) => console.log("console", m.type(), m.text().slice(0, 300)));
    page.on("pageerror", (e) => console.log("pageerror", e.message.slice(0, 300)));
    page.on("requestfailed", (r) => console.log("requestfailed", r.url(), r.failure()?.errorText));
    page.on("response", (r) => { if (r.url().includes("emulators")) console.log("response", r.status(), r.url(), r.fromServiceWorker()); });
    await touchEl(page.locator("#boot"));
    await sleep(Number(args[0] ?? 60000));
    console.log("after wait:", await status());
    break;
  }
  case "wait": {
    console.log(`painted after ${await painted()}s;`, await status());
    break;
  }
  case "tap": {
    const box = await canvasBox();
    const x = box.x + box.width * Number(args[0]), y = box.y + box.height * Number(args[1]);
    await touchAt(x, y);
    await sleep(Number(args[2] ?? 2500));
    console.log("tapped", args[0], args[1], "taps", await page.evaluate(() => window.__cabinet.taps), await status());
    break;
  }
  case "dtap": {
    const box = await canvasBox();
    const x = box.x + box.width * Number(args[0]), y = box.y + box.height * Number(args[1]);
    await touchAt(x, y); await sleep(150); await touchAt(x + 2, y + 1);
    await sleep(Number(args[2] ?? 2500));
    console.log("double tapped", args[0], args[1], await status());
    break;
  }
  case "hold": {
    const box = await canvasBox();
    const x = box.x + box.width * Number(args[0]), y = box.y + box.height * Number(args[1]);
    await touchAt(x, y, Number(args[2] ?? 700));
    await sleep(2000);
    console.log("held", await status());
    break;
  }
  case "tapkey": {
    await touchEl(page.locator(`#touch button`, { hasText: args[0] }).first());
    await sleep(Number(args[1] ?? 1500));
    console.log("key", args[0], await status());
    break;
  }
  case "key": {
    const drawer = page.locator("#touch .touch-drawer");
    if (await drawer.isHidden()) { await touchEl(page.locator('#touch button[data-action="drawer"]')); await sleep(400); }
    await touchEl(page.locator(`#touch button[data-keys="${args[0]}"]`).last());
    await sleep(Number(args[1] ?? 1500));
    console.log("key", args[0], await status());
    break;
  }
  case "holdkey": {
    const b = await page.locator(`#touch button[data-keys="${args[0]}"]`).last().boundingBox();
    await touchAt(b.x + b.width / 2, b.y + b.height / 2, Number(args[1] ?? 600));
    await sleep(2500);
    console.log("held key", args[0], "keys sent", await page.evaluate(() => window.__cabinet.keys), await status());
    break;
  }
  case "type": {
    await touchEl(page.locator('#touch button[data-action="keyboard"]'));
    await sleep(500);
    await page.keyboard.type(args[0], { delay: 120 });
    if (args[1] === "enter") await page.keyboard.press("Enter");
    await sleep(2000);
    console.log("typed", args[0], await status());
    break;
  }
  case "shot": {
    await page.locator("#screen").screenshot({ path: `${OUT}/${args[0]}.png`, scale: "css" });
    console.log("shot", args[0], await status());
    break;
  }
  case "page": {
    await page.screenshot({ path: `${OUT}/${args[0]}.png`, scale: "css" });
    console.log("page shot", args[0]);
    break;
  }
  case "eval": console.log(await page.evaluate(args[0])); break;
  case "status": console.log(await status(), page.url(), await page.evaluate(() => [innerWidth, innerHeight, devicePixelRatio])); break;
}
await browser.close();
