// What the cabinet costs, measured rather than assumed.
//
//   bun tools/adb_proxy.js &                       # for --device
//   bun tools/perf_check.js --device
//   bun tools/perf_check.js --url=http://localhost:8080/ --paths
//   bun tools/perf_check.js --url=http://localhost:8080/ --boot
//
// Three measurements, because they answer different questions.
//
//   (default)  Drive the game into the world and sample while it plays. With
//              --device, CPU comes from the phone over adb, where 100 is one
//              core; without one, only frames are counted, since a container's
//              CPU says little about a phone's.
//   --paths    The painter and the frame read, head to head on one machine on
//              identical input. This is the microbenchmark for what
//              cabinet/screen.js changed; it needs no emulator.
//   --boot     Time to the first frame and frames over ten seconds, with and
//              without ?jspi=1. Boot is almost all emulator, so it is the
//              cheapest proxy for how fast the guest runs.
//
// A still screen measures nothing: js-dos delivers a frame only when the
// picture changes, so a menu reports zero frames however hard the host is
// working. That is why the default mode walks the party.
import { chromium } from "playwright";

const arg = (n, d) => {
  const hit = process.argv.find((a) => a.startsWith(`--${n}=`));
  return hit === undefined ? d : hit.split("=").slice(1).join("=");
};
const has = (n) => process.argv.includes(`--${n}`);
const url = arg("url", "http://localhost:8080/");
const device = has("device");
const proxy = arg("proxy", "http://127.0.0.1:9222");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/** The page to drive: the device's foreground tab, or a fresh desktop one. */
async function open() {
  if (!device) {
    const browser = await chromium.launch();
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
    return { browser, page, close: () => browser.close() };
  }
  // Both of these are somebody else's process, and the failure when one is
  // missing reads as a stack trace rather than as the sentence it is.
  const browser = await chromium.connectOverCDP(proxy).catch((e) => {
    throw new Error(`no device at ${proxy}: ${e.message}\n`
      + "Start it with: bun tools/adb_proxy.js &");
  });
  const ctx = browser.contexts()[0];
  const host = new URL(url).host;
  const ours = ctx.pages().filter((p) => p.url().includes(host));
  if (!ours.length) {
    // A tab is opened rather than demanded, but the page it wants has to be
    // there: the device reaches a server on the host, through adb reverse.
    console.error(`no tab on ${host}. Serve the cabinet, `
      + `"adb reverse tcp:8080 tcp:8080", and open ${url} on the device.`);
  }
  const page = ours[0] ?? await ctx.newPage();
  // One tab, or the sampling counts a second copy of the game.
  for (const p of ours) if (p !== page) await p.close().catch(() => {});
  await page.bringToFront().catch(() => {});
  return { browser, page, close: async () => {} };
}

/** Chrome's CPU on the device, summed over its processes, and the renderer's share. */
async function deviceCpu(seconds) {
  const proc = Bun.spawn(["adb", "shell", `top -b -n 3 -d ${seconds / 3} -o %CPU,CMDLINE`],
    { stdout: "pipe", stderr: "ignore" });
  const text = await new Response(proc.stdout).text();
  let total = 0, renderer = 0;
  for (const row of text.split("\n")) {
    if (!row.includes("com.android.chrome") || row.includes("grep")) continue;
    const value = parseFloat(row.trim().split(/\s+/)[0]);
    if (!isFinite(value)) continue;
    total += value;
    if (/SandboxedProcessService/.test(row)) renderer += value;
  }
  return { cpu: +(total / 3).toFixed(1), renderer: +(renderer / 3).toFixed(1) };
}

/** Battery temperature in C, which is the CPU cost seen from the other side. */
async function deviceTemp() {
  const proc = Bun.spawn(["adb", "shell", "dumpsys battery"], { stdout: "pipe", stderr: "ignore" });
  const text = await new Response(proc.stdout).text();
  const hit = text.match(/temperature:\s*(\d+)/);
  return hit ? +(Number(hit[1]) / 10).toFixed(1) : null;
}

async function boot(page, query) {
  await page.goto(url.replace(/\/$/, "/") + query, { waitUntil: "domcontentloaded" });
  // The page waits to be asked. Any gesture will do; the power button is the
  // one that is always there.
  await page.click("#boot", { timeout: 20000 }).catch(() => page.click("body").catch(() => {}));
  await page.waitForFunction("window.__cabinet && window.__cabinet.frames > 0", null,
    { timeout: 300000 });
}

const key = (page, k, hold = 90) => page.evaluate(`(async () => {
  const { KEYS, tap } = await import("./cabinet/keys.js");
  await tap(window.__cabinet.ci, KEYS[${JSON.stringify(k)}], ${hold});
})()`);

/** Into the world, the way tools/fight_probe.js does it. The waits are its. */
async function enterGame(page) {
  await key(page, "a"); await sleep(4000);
  for (const k of ["6", "7", "8", "9"]) { await key(page, k); await sleep(700); }
  await key(page, "d"); await sleep(3000);
  await key(page, "e"); await sleep(13000);
  await key(page, "r"); await sleep(2500);   // leave the disk panel it lands on
}

/** CPU and delivered frames over one window, with the party doing `during`. */
async function sample(page, label, seconds, during) {
  const before = await page.evaluate("window.__cabinet.frames");
  const load = device ? deviceCpu(seconds) : sleep(seconds * 1000);
  const work = during ? during() : null;
  const cpu = (await load) ?? {};
  const after = await page.evaluate("window.__cabinet.frames");
  if (work) await work;
  const row = { label, ...cpu, fps: +((after - before) / seconds).toFixed(1) };
  if (device) row.tempC = await deviceTemp();
  console.log(JSON.stringify(row));
  return row;
}

const walking = (page, seconds) => async () => {
  const until = Date.now() + seconds * 1000;
  for (let i = 0; Date.now() < until; i++) await key(page, i % 2 ? "down" : "up", 60);
};

const { page, close } = await open();
try {
  if (has("paths")) {
    await page.goto(url, { waitUntil: "domcontentloaded" });
    // The painters run on a buffer this script makes, so no emulator is
    // involved and none needs to be running.
    const rows = await page.evaluate(async () => {
      const { makeRenderer } = await import("./cabinet/screen.js");
      const W = 640, H = 400, N = 300;
      const rgb = new Uint8Array(W * H * 3);
      for (let i = 0; i < rgb.length; i++) rgb[i] = (i * 7) & 255;
      const time = (label, fn, n) => {
        for (let i = 0; i < 20; i++) fn();
        const t0 = performance.now();
        for (let i = 0; i < n; i++) fn();
        return { label, msPerCall: +((performance.now() - t0) / n).toFixed(3) };
      };
      const out = [];
      for (const webgl of [true, false]) {
        const r = makeRenderer(document.createElement("canvas"), { webgl });
        out.push(time(`paint ${r.kind}`, () => r.draw(rgb, W, H), N));
      }
      const c = document.createElement("canvas");
      c.width = W; c.height = H;
      const ctx = c.getContext("2d", { alpha: false });
      ctx.putImageData(ctx.createImageData(W, H), 0, 0);
      out.push(time("read getImageData", () => ctx.getImageData(0, 0, W, H).data, 100));
      out.push(time("read delivered frame", () => rgb.slice(), 100));
      return out;
    });
    for (const row of rows) console.log(JSON.stringify(row));
  } else if (has("boot")) {
    for (const query of ["", "?jspi=1"]) {
      const t0 = Date.now();
      await boot(page, query);
      const bootMs = Date.now() - t0;
      const before = await page.evaluate("window.__cabinet.frames");
      await sleep(10000);
      const after = await page.evaluate("window.__cabinet.frames");
      console.log(JSON.stringify({
        query: query || "(default)", bootMs, frames10s: after - before,
        engine: await page.evaluate("window.__cabinet.engine"),
      }));
    }
  } else {
    await boot(page, arg("query", ""));
    await sleep(10000);
    console.log("engine:", JSON.stringify(await page.evaluate("window.__cabinet.engine")));
    await sample(page, "main menu, still", 9);
    await enterGame(page);
    await sample(page, "standing in the world", 9);
    await sample(page, "walking", 12, walking(page, 12));
    // The floor the emulator is measured against: the page still open, its
    // worker stopped.
    await page.evaluate("window.__cabinet.ci.pause()");
    await sleep(2000);
    await sample(page, "emulator stopped", 9);
    // Never leave a phone running the game: a core held busy is a battery
    // getting warm for nothing.
    await page.goto("about:blank");
    console.log("stopped; tab parked at about:blank");
  }
} finally {
  await close();
}
