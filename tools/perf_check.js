// What the cabinet costs, measured rather than assumed.
//
//   bun tools/adb_proxy.js &                       # for --device
//   bun tools/perf_check.js --device
//   bun tools/perf_check.js --url=http://localhost:8080/ --paths
//   bun tools/perf_check.js --url=http://localhost:8080/ --boot
//
// Three measurements, because they answer different questions.
//
//   (default)  Drive the subject into the world and sample while it plays,
//              --runs=N times. With --device, CPU comes from the phone over
//              adb, where 100 is one core; without one, only frames are
//              counted, since a container's CPU says little about a phone's.
//              More than one run prints a median and a range under a rule.
//              Each pass also times two inputs to the picture that answers
//              them: a key, which reaches the guest directly, and a finger on
//              the game, which goes through the page's gesture path first.
//
// The subject is whatever the page installs as window.__perf; the cabinet does
// it in cabinet/perf.js. Nothing here reaches past that, so what is measured
// is the page rather than one page's internals.
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
// A save to start from. Taken on the first run that has none and written
// here, then put back before every later one, because loading a save is a
// few keys and assembling a party is a screen at a time.
const savePath = arg("save", "tmp/perf-save.json");
const device = has("device");
const proxy = arg("proxy", "http://127.0.0.1:9222");
// How long a sample runs. On a device it is the CPU sampler's floor: `top -n 3
// -d 3` needs three intervals to average over. Without one there is nothing to
// average, only frames to count, so the window is as short as a frame rate
// needs and the run is a minute shorter.
const WINDOW = Number(arg("window", device ? 9 : 3));
const STEP_WINDOW = WINDOW + (device ? 3 : 1);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
// Wall clock from the start of the run, on every line, so each step's cost
// is visible in the output.
const started = Date.now();
const at = () => +((Date.now() - started) / 1000).toFixed(1);

/** The page to drive: the device's foreground tab, or a fresh desktop one. */
async function open() {
  if (!device) {
    const browser = await chromium.launch();
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
    return { browser, page, close: () => browser.close() };
  }
  // Both of these are somebody else's process, and the failure when one is
  // missing is reported as a stack trace, so it is caught and named here.
  const browser = await chromium.connectOverCDP(proxy).catch((e) => {
    throw new Error(`no device at ${proxy}: ${e.message}\n`
      + "Start it with: bun tools/adb_proxy.js &");
  });
  const ctx = browser.contexts()[0];
  const host = new URL(url).host;
  const ours = ctx.pages().filter((p) => p.url().includes(host));
  // The tab a run left parked at about:blank is taken before a new one is
  // opened: each tab the phone keeps is memory the sample would count.
  const parked = ctx.pages().filter((p) => p.url() === "about:blank");
  const page = ours[0] ?? parked[0] ?? await ctx.newPage();
  // One tab, or the sampling counts a second copy of the game.
  for (const p of ctx.pages()) if (p !== page) await p.close().catch(() => {});
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
/**
 * Chrome's memory on the device: resident set summed over its processes, in
 * MB, and how many renderer processes it has. Every tab left open is a
 * renderer, so the count says whether a run cleaned up after itself.
 */
async function deviceMemory() {
  const proc = Bun.spawn(["adb", "shell", "top -b -n 1 -o RES,CMDLINE"], { stdout: "pipe", stderr: "ignore" });
  const text = await new Response(proc.stdout).text();
  let mb = 0, renderers = 0;
  for (const line of text.split("\n")) {
    const hit = line.trim().match(/^([\d.]+)([KMG])?\s+(\S*chrome\S*)/);
    if (!hit) continue;
    const unit = { K: 1 / 1024, M: 1, G: 1024 }[hit[2] ?? "K"];
    mb += Number(hit[1]) * unit;
    if (hit[3].includes("sandboxed_process")) renderers++;
  }
  return mb ? { memMB: Math.round(mb), renderers } : {};
}

async function deviceTemp() {
  const proc = Bun.spawn(["adb", "shell", "dumpsys battery"], { stdout: "pipe", stderr: "ignore" });
  const text = await new Response(proc.stdout).text();
  const hit = text.match(/temperature:\s*(\d+)/);
  return hit ? +(Number(hit[1]) / 10).toFixed(1) : null;
}

/**
 * The silicon's own temperatures, from the thermal zones: the hottest CPU
 * core, the hotter GPU zone, and the power management chip. Heat lags load
 * by minutes, so a subject measured after another starts with the other's
 * warmth, and these say how much.
 */
async function deviceZones() {
  const proc = Bun.spawn(["adb", "shell",
    "for z in /sys/class/thermal/thermal_zone*; do echo \"$(cat $z/type) $(cat $z/temp)\"; done"],
    { stdout: "pipe", stderr: "ignore" });
  const text = await new Response(proc.stdout).text();
  const zones = {};
  for (const line of text.split("\n")) {
    const [type, temp] = line.trim().split(/\s+/);
    if (type && temp && !Number.isNaN(Number(temp))) zones[type] = Number(temp) / 1000;
  }
  const pick = (re) => {
    const v = Object.entries(zones).filter(([k]) => re.test(k)).map(([, t]) => t);
    return v.length ? +Math.max(...v).toFixed(1) : null;
  };
  return { cpuC: pick(/^cpu\d-.*-usr$/), gpuC: pick(/^gpu\d-usr$/), pmicC: pick(/^pm\d+_tz$/) };
}

async function boot(page, query) {
  // The contract is opt-in, so asking for it is the harness's job. Merged
  // rather than appended, since a mode may already carry a query of its own.
  const target = new URL(query, url);
  target.searchParams.set("perf", "1");
  await page.goto(target.href, { waitUntil: "domcontentloaded" });

  // A kept save goes into storage before the emulator starts. cabinet.js reads
  // what persist.js holds as it boots and hands those files to the backend
  // with the rest of the disk, so this lands on the disk the game finds.
  // Written once the game is running it is a file the game has already decided
  // is not there.
  const kept = await Bun.file(savePath).json().catch(() => null);
  if (kept) {
    // A subject without the cabinet's storage has no disk to put a save on,
    // and says so through hasSave() rather than by failing here.
    await page.evaluate(`(async () => {
      const p = await import("/cabinet/persist.js");
      await p.putFile("SAVGAME1", new Uint8Array(${JSON.stringify(kept)}));
    })()`).catch((err) => console.error(`the save was not placed: ${err.message}`));
  }

  // The page waits to be asked. Any gesture will do; the power button is the
  // one the cabinet has, and a page without one takes a click anywhere.
  await page.click("#boot", { timeout: 20000 }).catch(() => page.click("body").catch(() => {}));
  // A real gesture first, because it carries the activation an audio context
  // wants. Where it does not reach the button, which happens driving a phone
  // over DevTools, the listener is called outright: booting needs the click,
  // not the activation, and a refused resume is already handled.
  await page.waitForFunction("window.__perf", null, { timeout: 15000 }).catch(() =>
    page.evaluate('document.querySelector("#boot")?.click()'));
  await page.waitForFunction("window.__perf", null, { timeout: 300000 })
    .catch(() => { throw new Error(`${url} installs no window.__perf. `
      + "cabinet/perf.js has the names a measurement drives."); });
  await page.waitForFunction("window.__perf.ready()", null, { timeout: 300000 });
  // Whether the game booted with a save on its disk, asked of the game rather
  // than inferred from having written one: this decides which way in enter()
  // takes, and a silent miss would read as a slow entry rather than a fault.
  const onDisk = await page.evaluate("window.__perf.hasSave()");
  if (kept && !onDisk) console.error("a save was kept but the game booted without it");
  return onDisk;
}

/** CPU and delivered frames over one window, with the subject doing `during`. */
async function sample(page, label, seconds, during) {
  // A page with no contract, the about:blank tare, has no frames to count.
  const frames = () => page.evaluate("window.__perf ? window.__perf.frames() : 0");
  const before = await frames();
  const load = device ? deviceCpu(seconds) : sleep(seconds * 1000);
  const work = during ? during() : null;
  const cpu = (await load) ?? {};
  const after = await frames();
  if (work) await work;
  const row = { at: at(), label, ...cpu, fps: +((after - before) / seconds).toFixed(1) };
  if (device) Object.assign(row, await deviceMemory(), { tempC: await deviceTemp() }, await deviceZones());
  // Printed as it is taken, not held to the end of the run: a measurement
  // that shows nothing for minutes looks the same as one that has hung.
  console.log(JSON.stringify(row));
  return row;
}

// How often a step key is sent, in ms. The default is faster than either
// subject steps, so the keyboard buffer stays full and the frames counted are
// the subject's own rate; `--pace=210` is the old one-key-per-step drive.
const PACE = Number(arg("pace", "70"));

/**
 * Wait until the subject has drawn nothing for `quiet` ms, or `cap` ms in
 * all. Stepping leaves keys in the game's buffer, and the game works through
 * them before it takes any other input, so a reaction timed before the
 * picture goes quiet is timing the queue.
 */
async function quiet(page, quietMs = 1500, cap = 30000) {
  const frames = () => page.evaluate("window.__perf ? window.__perf.frames() : 0");
  const until = Date.now() + cap;
  let last = await frames(), since = Date.now();
  while (Date.now() < until) {
    await sleep(200);
    const now = await frames();
    if (now !== last) { last = now; since = Date.now(); }
    else if (Date.now() - since >= quietMs) return;
  }
  console.error("the picture did not go quiet within the cap");
}

/** Steps for as long as the sample lasts, keys at PACE. */
const stepping = (page, seconds) =>
  () => page.evaluate(`window.__perf.step(${Math.round(seconds * 1000 / PACE)}, ${PACE})`);

const median = (xs) => {
  const v = xs.filter((x) => typeof x === "number").sort((a, b) => a - b);
  if (!v.length) return null;
  const mid = v.length >> 1;
  return +(v.length % 2 ? v[mid] : (v[mid - 1] + v[mid]) / 2).toFixed(1);
};

/**
 * One line per label: the median of each figure, and its range.
 *
 * A single pass is not a baseline. The same configuration has measured 120 and
 * 172 at the main menu, so a difference smaller than the spread is not a
 * difference, and the spread has to be on the page for anyone to see that.
 */
function summarize(runs) {
  const labels = runs[0].map((r) => r.label);
  for (const label of labels) {
    const rows = runs.map((run) => run.find((r) => r.label === label)).filter(Boolean);
    const out = { label, runs: rows.length };
    for (const field of ["cpu", "renderer", "fps", "memMB", "renderers", "tempC", "cpuC", "gpuC", "pmicC", "ms"]) {
      const xs = rows.map((r) => r[field]).filter((x) => typeof x === "number");
      if (!xs.length) continue;
      out[field] = median(xs);
      if (xs.length > 1) out[`${field}Range`] = [Math.min(...xs), Math.max(...xs)];
    }
    console.log(JSON.stringify(out));
  }
}

const { page, close } = await open();
try {
  if (has("paths")) {
    await page.goto(url, { waitUntil: "domcontentloaded" });   // no contract needed
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
      const before = await page.evaluate("window.__perf.frames()");
      await sleep(10000);
      const after = await page.evaluate("window.__perf.frames()");
      console.log(JSON.stringify({
        query: query || "(default)", bootMs, frames10s: after - before,
        info: await page.evaluate("window.__perf.info()"),
      }));
    }
  } else {
    const runs = [];
    for (let run = 0; run < Number(arg("runs", "1")); run++) {
      const loaded = await boot(page, arg("query", ""));
      // boot() returns on the first picture, which is a splash rather than
      // the menu: the game is still starting. Keys sent before the menu is up
      // land on whatever is, and every key after them is a screen out of
      // step, which reads as a run that entered the world and found no frames
      // in it. Ten seconds is what the menu takes.
      await sleep(Number(arg("settle", "10000")));
      console.log(`booted at ${at()}s`, loaded ? "with a save on the disk" : "with no save");
      if (!run) console.log("subject:",
        JSON.stringify(await page.evaluate("({name: window.__perf.name, info: window.__perf.info()})")));
      const rows = [await sample(page, "before entering, still", WINDOW)];
      const steps = await page.evaluate(`window.__perf.enter(${Number(arg("world", "0"))}, ${Number(arg("gaps", "1"))})`);
      console.log(`entered at ${at()}s`, JSON.stringify(steps));
      // The first run that had to assemble a party keeps a save, so every
      // later run loads it and enters in three keys. A subject with no disk
      // to save on has no saveGame and is left alone.
      if (!loaded && !(await Bun.file(savePath).exists())) {
        const bytes = await page.evaluate(
          "window.__perf.saveGame ? window.__perf.saveGame(1).then(() => window.__perf.takeSave(1)) : null");
        if (bytes) {
          await Bun.write(savePath, JSON.stringify(bytes));
          console.log(`kept a save at ${savePath}, ${bytes.length} bytes`);
        }
      }

      rows.push(await sample(page, "standing in the world", WINDOW));
      const stepped = await sample(page, "stepping", STEP_WINDOW, stepping(page, STEP_WINDOW));
      rows.push(stepped);
      // Stepping that draws nothing means the party never reached the world,
      // so the rest of the run is measuring a menu. Say so rather than report
      // a column of zeros as a result.
      if (!stepped.fps) console.error("stepping drew no frames: enter() did not reach the world");
      // How long an input waits for the picture that answers it. Timed in the
      // page, because a round trip out to here is longer than the thing being
      // measured.
      // A finger on the game and a key, which are what a player uses. `tap`
      // goes through the page's whole gesture path and ends at the picture
      // that answers it; a key reaches the guest's keyboard buffer directly,
      // so the pair says what the mouse path costs. `pointer` measures a bare
      // motion and is available but not run.
      // A reaction row: the median of the answered inputs, and how many of
      // them answered. A null is an input that drew nothing inside the
      // contract's timeout, which is a fact about the subject, not a gap in
      // the sample.
      const reaction = (label, all) => {
        const ms = all.filter((x) => typeof x === "number");
        const row = {
          at: at(), label, ms: median(ms), answered: ms.length, of: all.length,
          ...(ms.length ? { msRange: [Math.min(...ms), Math.max(...ms)] } : {}),
        };
        console.log(JSON.stringify(row));
        rows.push(row);
      };
      // Each reaction is measured against a quiet game: nothing queued from
      // the stepping before it, nothing still drawing from the row before.
      await quiet(page);
      reaction("key to picture", await page.evaluate("window.__perf.react('key', 4)"));
      await quiet(page);
      // Taps come in pairs that undo each other, and the two halves are
      // different things: on the cabinet the first opens the disk panel and
      // the second presses RETURN in it, which pauses and resumes the game.
      // So each half is its own row, named by what the subject says a pair is.
      const taps = await page.evaluate("window.__perf.react('tap', 6)");
      const names = (await page.evaluate("window.__perf.info().taps")) ?? ["first", "second"];
      reaction(`finger, ${names[0]}`, taps.filter((_, i) => i % 2 === 0));
      reaction(`finger, ${names[1]}`, taps.filter((_, i) => i % 2 === 1));
      // The floor the subject is measured against: the page still open, its
      // work stopped.
      await page.evaluate("window.__perf.stop()");
      await sleep(2000);
      rows.push(await sample(page, "stopped", WINDOW));
      // The tare: Chrome with nothing in it. Every row above is read against
      // this, since the phone is never at zero on its own.
      await page.goto("about:blank");
      await sleep(2000);
      rows.push(await sample(page, "idle, about:blank", WINDOW));
      runs.push(rows);
    }
    if (runs.length > 1) { console.log("--"); summarize(runs); }
    // Never leave a phone running the game: a core held busy is a battery
    // getting warm for nothing.
    await page.goto("about:blank");
    console.log("stopped; tab parked at about:blank");
  }
} finally {
  // Closing a DevTools connection to a phone can hang after the tab is
  // parked, and a run whose numbers are printed has nothing left to wait for.
  await Promise.race([close(), sleep(5000)]);
  process.exit(0);
}
