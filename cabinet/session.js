// A long-lived emulator session driven by a command file.
//
// The game's three splash screens take ~12s of wall-clock before the main menu
// appears, and they cannot be skipped: they are timer-driven, the executable
// parses no switch that bypasses them, disabling sound hangs on the second
// one, and raising DOSBox cycles makes them slower rather than faster. The
// only real remedy is to stop paying that cost per interaction: boot once,
// then drive the same instance for as long as you need.
//
//   bun session.js &                       # boot and wait for commands
//   echo "key a" >> ../tmp/session.cmd     # queue a command
//   echo "shot party" >> ../tmp/session.cmd
//   cat ../tmp/session.log
//
// Actions: wait <sec> | shot <name> | click <x> <y> | dclick <x> <y> |
//          rclick <x> <y> | drclick <x> <y> | key <name> | type <letters> |
//          ls | read <path> | quit
//
// Two switches matter for anything mouse-driven or save-related:
//
//   --backend=x   DOSBox-X, the only backend whose mouse reaches the guest.
//   --trace       log every filesystem mutation the game makes, as it happens.
//                 A save, a delete or a truncate then shows up in the log
//                 beside the command that caused it, which is how the
//                 character-roster question was settled.
import { appendFileSync, mkdirSync, readFileSync, writeFileSync, existsSync } from "fs";
import { join } from "path";

import { loadEmulators, initFs, HEADLESS_ARGS } from "./boot.js";
import { KEYS, BUTTONS, tap, click, moveTo } from "./keys.js";
import { encodePng } from "./png.js";
import { buildTracedEmulator, TRACED_JS, TRACED_X_JS } from "../tools/trace_fs.js";

const arg = (n, d) => {
  const hit = process.argv.find((a) => a.startsWith(`--${n}=`));
  return hit === undefined ? d : hit.split("=").slice(1).join("=");
};

const TMP = join(import.meta.dir ?? ".", "..", "tmp");
const CMD = join(TMP, "session.cmd");
const LOG = join(TMP, "session.log");
const SHOTS = join(TMP, "shots");

mkdirSync(SHOTS, { recursive: true });
writeFileSync(CMD, "");
writeFileSync(LOG, "");
const log = (m) => { console.log(m); appendFileSync(LOG, m + "\n"); };

const backend = arg("backend", "dos");
const tracing = process.argv.includes("--trace");
const FSLOG = join(TMP, "session-fs.json");
if (tracing) {
  if (existsSync(FSLOG)) writeFileSync(FSLOG, "");
  buildTracedEmulator(FSLOG, true, true,
    backend === "x" ? "wdosbox-x.js" : "wdosbox.js");
}

const emulators = await loadEmulators();
if (tracing) {
  if (backend === "x") emulators.wdosboxxJs = TRACED_X_JS;
  else emulators.wdosboxJs = TRACED_JS;
}
const initial = await initFs({ extra: arg("args", HEADLESS_ARGS) });
const ci = backend === "x"
  ? await emulators.dosboxXNode(initial)
  : await emulators.dosboxNode(initial);

let frame = null;
ci.events().onFrame((rgb) => {
  if (rgb) frame = { rgb: rgb.slice(), w: ci.width(), h: ci.height() };
});

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let shotN = 0;

/** Cheap frame fingerprint: mean color plus a coarse color count. */
function sig() {
  if (!frame) return null;
  const px = frame.rgb;
  let r = 0, g = 0, b = 0;
  const seen = new Set();
  for (let i = 0; i < px.length; i += 3) {
    r += px[i]; g += px[i + 1]; b += px[i + 2];
    seen.add((px[i] >> 4 << 8) | (px[i + 1] >> 4 << 4) | (px[i + 2] >> 4));
  }
  const n = px.length / 3;
  return `${(r / n) | 0},${(g / n) | 0},${(b / n) | 0},${seen.size},${frame.w}x${frame.h}`;
}

/**
 * Fraction of the top band that is violet.
 *
 * Every splash screen is black-backed artwork; the main menu and the in-game
 * screens are the only ones framed by the game's violet chrome bar. That bar
 * is therefore a far more reliable "are we at the menu" test than mean color
 * (the SW Games splash averages the same as the menu) or dwell time (the
 * attract loop makes splashes hold for as long as the menu does).
 */
function violetTopBand() {
  if (!frame) return 0;
  const { rgb, w, h } = frame;
  const rows = Math.max(4, Math.round(h * 0.06));
  let hit = 0, total = 0;
  for (let y = 1; y < rows; y++) {
    for (let x = 0; x < w; x++) {
      const i = (y * w + x) * 3;
      const r = rgb[i], g = rgb[i + 1], b = rgb[i + 2];
      total++;
      if (r > 35 && b > 45 && g < Math.min(r, b) * 0.75) hit++;
    }
  }
  return total ? hit / total : 0;
}

/**
 * Block until the screen stops changing.
 *
 * Boot timing swings with host load, so fixed waits are unreliable: the splash
 * chain can take 12s on an idle machine and 40s under contention. Every splash
 * is animated or fading while the menus and in-game screens are static, so
 * "unchanged for N seconds" is a far better signal than a stopwatch.
 */
async function waitStable(seconds = 4, timeout = 120) {
  const started = Date.now();
  let last = null, since = Date.now();
  while ((Date.now() - started) / 1000 < timeout) {
    await sleep(500);
    const s = sig();
    if (s !== last) { last = s; since = Date.now(); continue; }
    if ((Date.now() - since) / 1000 >= seconds) {
      return { stable: true, sig: s, after: ((Date.now() - started) / 1000).toFixed(1) };
    }
  }
  return { stable: false, sig: last, after: timeout };
}

const atMenu = () => {
  const c = (sig() || "").split(",").map(Number);
  return [88, 78, 71].every((v, i) => Math.abs(c[i] - v) <= 6) && c[3] < 70;
};

/**
 * Hammer input until the main menu appears, then stop at once.
 *
 * Stopping immediately matters twice over: an ESC that lands after the menu is
 * up backs straight out to the attract loop, and the menu itself starts the
 * introduction after a few idle seconds. So callers must act on the menu the
 * moment this returns.
 */
async function gotoMenu(timeout = 120) {
  const until = Date.now() + timeout * 1000;
  while (Date.now() < until) {
    if (atMenu()) return true;
    for (const k of ["esc", "space", "enter"]) {
      await tap(ci, KEYS[k], 120);
      if (atMenu()) return true;
    }
    await sleep(250);
  }
  return false;
}

async function run(line) {
  const [op, ...rest] = line.trim().split(/\s+/);
  switch (op) {
    case "": return;
    case "wait": await sleep(Number(rest[0]) * 1000); return log(`waited ${rest[0]}s`);
    case "stable": {
      const r = await waitStable(Number(rest[0] || 4), Number(rest[1] || 120));
      return log(`stable=${r.stable} after ${r.after}s sig=${r.sig}`);
    }
    case "restoration": {
      // One atomic command: reach the menu and open the clue book with no gaps.
      // The menu starts the introduction after only a few idle seconds, so any
      // dead time between "menu reached" and the F8 press loses the window.
      const section = rest[0] || "f2";
      const ok = await gotoMenu(180);
      if (!ok) return log(`restoration: never reached menu (sig=${sig()})`);
      await tap(ci, KEYS.f8, 120);
      // The clue book opens on a title card that, like the splash screens,
      // waits for input rather than timing out.
      for (let i = 0; i < 10; i++) {
        await tap(ci, KEYS.space, 120);
        await sleep(250);
      }
      await sleep(500);
      if (!(section in KEYS)) return log(`unknown section key ${section}`);
      await tap(ci, KEYS[section], 120);
      await sleep(1500);
      return log(`restoration ${section} -> sig=${sig()}`);
    }
    case "gomenu": {
      const ok = await gotoMenu(Number(rest[0] || 120));
      return log(ok ? `menu reached, sig=${sig()}` : `gomenu TIMED OUT sig=${sig()}`);
    }
    case "hammer": {
      // Replicates the only input sequence observed to advance the splash
      // chain: bare mouse button presses (no motion, no sync) interleaved with
      // long key holds. The splash screens poll for input rather than timing
      // out, so they sit forever until something registers.
      const secs = Number(rest[0] || 15);
      const until = Date.now() + secs * 1000;
      while (Date.now() < until) {
        for (const k of ["esc", "space", "enter"]) await tap(ci, KEYS[k], 120);
        ci.sendMouseButton(0, true);
        await sleep(80);
        ci.sendMouseButton(0, false);
        await sleep(300);
      }
      return log(`hammered ${secs}s -> sig=${sig()}`);
    }
    case "sig": return log(`sig=${sig()} violet=${violetTopBand().toFixed(3)}`);
    case "waitmenu": {
      const timeout = Number(rest[0] || 200);
      const started = Date.now();
      let held = 0;
      while ((Date.now() - started) / 1000 < timeout) {
        await sleep(400);
        held = violetTopBand() > 0.25 ? held + 1 : 0;
        if (held >= 5) {
          return log(`menu after ${((Date.now() - started) / 1000).toFixed(1)}s violet=${violetTopBand().toFixed(3)}`);
        }
      }
      return log(`waitmenu TIMED OUT (violet=${violetTopBand().toFixed(3)})`);
    }
    case "waitfor": {
      // Wait for a screen whose mean color matches, then for it to settle.
      // The Webfoot splash is a static star field, so "unchanged" alone is not
      // enough to tell it from a menu: the color has to match too.
      const [want, tol = 3, timeout = 180] = [rest[0], Number(rest[1] || 3), Number(rest[2] || 180)];
      const target = want.split(",").map(Number);
      const started = Date.now();
      let held = 0;
      while ((Date.now() - started) / 1000 < timeout) {
        await sleep(500);
        const cur = (sig() || "").split(",").map(Number);
        const near = target.every((v, i) => Math.abs(cur[i] - v) <= tol);
        held = near ? held + 1 : 0;
        if (held >= 6) {
          return log(`waitfor ${want} matched after ${((Date.now() - started) / 1000).toFixed(1)}s sig=${sig()}`);
        }
      }
      return log(`waitfor ${want} TIMED OUT after ${timeout}s, sig=${sig()}`);
    }
    case "watch": {
      const n = Number(rest[0] || 30);
      for (let i = 0; i < n; i++) { await sleep(1000); log(`  t${i + 1}s sig=${sig()} violet=${violetTopBand().toFixed(3)}`); }
      return;
    }
    case "shot": {
      if (!frame) return log("no frame yet");
      const f = join(SHOTS, `${String(shotN++).padStart(2, "0")}-${rest[0] || "shot"}.png`);
      writeFileSync(f, encodePng(frame.w, frame.h, frame.rgb));
      return log(`shot ${f} ${frame.w}x${frame.h}`);
    }
    case "click": await click(ci, Number(rest[0]), Number(rest[1])); return log(`click ${rest[0]},${rest[1]}`);
    case "dclick":
    case "drclick": {
      // Lists in this game select on a double click, not a single one: the
      // save-slot list and the clue book both ignore a single click. The
      // second press is sent bare, with no motion in front of it: motion
      // between the two is what stops the pair registering as a double click.
      //
      // Double right click is the one gesture with a use of its own rather
      // than a stronger version of the single: on a portrait it toggles every
      // inventory panel at once (README.DOC line 273).
      const b = op === "drclick" ? BUTTONS.right : BUTTONS.left;
      const [x, y] = [Number(rest[0]), Number(rest[1])];
      await click(ci, x, y, b);
      await sleep(120);
      ci.sendMouseButton(b, true);
      await sleep(90);
      ci.sendMouseButton(b, false);
      await sleep(250);
      return log(`${op} ${x},${y}`);
    }
    case "move": await moveTo(ci, Number(rest[0]), Number(rest[1])); return log(`move ${rest[0]},${rest[1]}`);
    case "rclick": await click(ci, Number(rest[0]), Number(rest[1]), BUTTONS.right); return log(`rclick ${rest[0]},${rest[1]}`);
    case "key": {
      if (!(rest[0] in KEYS)) return log(`unknown key ${rest[0]}`);
      await tap(ci, KEYS[rest[0]]);
      return log(`key ${rest[0]}`);
    }
    case "type": {
      const missing = [];
      for (const c of (rest[0] || "").toLowerCase()) {
        if (c in KEYS) await tap(ci, KEYS[c]);
        else missing.push(c);
      }
      // Silently dropping an unknown character makes a driver script look like
      // the game ignored the key, which wastes a whole session to diagnose.
      return log(`typed ${rest[0]}${missing.length ? ` (no key for ${missing.join("")})` : ""}`);
    }
    case "ls": {
      const tree = await ci.fsTree();
      return log("fsTree " + JSON.stringify(tree).slice(0, 4000));
    }
    case "read": {
      try {
        const b = await ci.fsReadFile(rest[0]);
        writeFileSync(join(TMP, "read-" + rest[0].replace(/[\\/]/g, "_")), b);
        return log(`read ${rest[0]} ${b.length} bytes`);
      } catch (e) { return log(`read ${rest[0]} FAILED: ${e.message}`); }
    }
    case "quit": log("bye"); await ci.exit(); process.exit(0);
    default: return log(`unknown action '${op}'`);
  }
}

log(`booted ${ci.width()}x${ci.height()}${tracing ? " (tracing)" : ""}; append commands to ${CMD}`);

// Listen to the filesystem rather than polling it: the tracer appends every
// open, write, truncate, rename and unlink, and these get drained into the
// session log so each one lands under the command that caused it.
let fsSeen = 0;
function drainFs() {
  if (!tracing || !existsSync(FSLOG)) return;
  let trace;
  try { trace = JSON.parse(readFileSync(FSLOG, "utf8")); } catch { return; }
  for (const [t, op, path, note, at, len] of (trace.ops || []).slice(fsSeen)) {
    const file = String(path).split("/").pop();
    if (/^(dosbox|\.|autoexec|jsdos|mapper|us\.kl|\d+\.sav|web_user)/i.test(file)) continue;
    log(`  fs ${String(t).padStart(7)}ms ${op} ${file} ${op === "write" ? `at ${at} len ${len}` : note}`);
  }
  fsSeen = (trace.ops || []).length;
}

let consumed = 0;
for (;;) {
  await sleep(250);
  drainFs();
  if (!existsSync(CMD)) continue;
  const lines = readFileSync(CMD, "utf8").split("\n");
  while (consumed < lines.length - 1) {
    const line = lines[consumed++];
    if (line.trim()) { log(`> ${line.trim()}`); await run(line); drainFs(); }
  }
}
