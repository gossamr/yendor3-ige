// Watch what the game does to its files while a scripted session is played.
//
// The question this answers: creating characters, entering the world and
// saving all touch CURGAME and SAVGAMEn, but *when*, and which of those writes
// survives a trip back to the main menu? Snapshotting the filesystem cannot
// tell you: by the time you look, the interesting event is over. So listen
// instead: tools/trace_fs.js can hook every FS mutation, and this drives the
// game through labeled steps and prints each open, write, truncate, rename
// and unlink under the step that caused it.
//
//   YENDOR_GAME_DIR=tmp/game-patched bun tools/trace_saves.js --out=tmp/saves
import { mkdirSync, writeFileSync, readFileSync, existsSync } from "fs";
import { join } from "path";

import { loadEmulators, initFs, HEADLESS_ARGS } from "../cabinet/boot.js";
import { KEYS, tap, click, moveTo } from "../cabinet/keys.js";
import { encodePng } from "../cabinet/png.js";
import { buildTracedEmulator, TRACED_X_JS } from "./trace_fs.js";

const arg = (n, d) => {
  const hit = process.argv.find((a) => a.startsWith(`--${n}=`));
  return hit === undefined ? d : hit.split("=").slice(1).join("=");
};
const outDir = arg("out", "tmp/saves");
const stopAfter = Number(arg("stop", 999));
mkdirSync(outDir, { recursive: true });

const LOG = "/workspace/tmp/fsops.json";
if (existsSync(LOG)) writeFileSync(LOG, "");
buildTracedEmulator(LOG, true, true, "wdosbox-x.js");

// DOSBox-X, not DOSBox: character creation cannot be finished from the
// keyboard, since the portrait is picked by clicking, and the mouse only reaches
// the guest under DOSBox-X with mouse_emulation=always (see docs/running.md).
const emulators = await loadEmulators();
emulators.wdosboxxJs = TRACED_X_JS;
const ci = await emulators.dosboxXNode(await initFs({ extra: `/P ${HEADLESS_ARGS}` }));

let frame = null;
ci.events().onFrame((rgb) => {
  if (rgb) frame = { rgb: rgb.slice(), w: ci.width(), h: ci.height() };
});
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const shot = (name) => {
  if (!frame) return;
  writeFileSync(join(outDir, `${name}.png`), encodePng(frame.w, frame.h, frame.rgb));
};
function sig() {
  if (!frame) return "";
  const px = frame.rgb;
  let r = 0, g = 0, b = 0;
  const seen = new Set();
  for (let i = 0; i < px.length; i += 3) {
    r += px[i]; g += px[i + 1]; b += px[i + 2];
    seen.add((px[i] >> 4 << 8) | (px[i + 1] >> 4 << 4) | (px[i + 2] >> 4));
  }
  const n = px.length / 3;
  return `${(r / n) | 0},${(g / n) | 0},${(b / n) | 0},${seen.size}`;
}
const atMenu = () => {
  const c = sig().split(",").map(Number);
  return [88, 78, 71].every((v, i) => Math.abs(c[i] - v) <= 6) && c[3] < 70;
};

// --- the listener -----------------------------------------------------------
// The worker flushes the log on a timer; drain whatever is new and print it
// against the step that is running. Reads are ignored here: this run is about
// what changes on disk, and the read log is enormous (PICTURES.VGA alone).
let seen = 0;
const all = [];
function drain(label) {
  if (!existsSync(LOG)) return;
  let trace;
  try { trace = JSON.parse(readFileSync(LOG, "utf8")); } catch { return; }
  const ops = trace.ops || [];
  for (const op of ops.slice(seen)) {
    const [t, name, path, note, at, len] = op;
    const file = String(path).split("/").pop();
    // DOSBox's own scaffolding (its Z: drive, its config) would bury the
    // signal; everything else is shown, because a file appearing under an
    // unexpected name is exactly what this run is looking for.
    if (/^(dosbox|\.|autoexec|z:)/i.test(file) || String(path).startsWith("/dev")) continue;
    const where = name === "write" ? `at ${at} len ${len}` : note;
    const line = `    ${String(t).padStart(7)}ms  ${name.padEnd(9)} ${file.padEnd(13)} ${where}`;
    console.log(line);
    all.push({ step: label, t, op: name, file, note: where });
  }
  seen = ops.length;
}

let stepNo = 0;
async function step(label, body) {
  stepNo += 1;
  if (stepNo > stopAfter) return false;
  drain(label);
  console.log(`\n[${String(stepNo).padStart(2, "0")}] ${label}`);
  await body();
  await sleep(1200);
  drain(label);
  shot(`${String(stepNo).padStart(2, "0")}-${label.replace(/\W+/g, "-")}`);
  console.log(`     screen ${sig()}`);
  return true;
}
const A = (c) => c.toUpperCase().charCodeAt(0);

// --- the session ------------------------------------------------------------
// The menus are all hotkeys: C create, F (or another initial) picks the class,
// R roll, I items, N name, K keep, Q leave creation; then A assemble, 1-9
// toggle a party member, D done, E enter the game.
await step("reach the main menu", async () => {
  for (let i = 0; i < 200 && !atMenu(); i++) {
    await tap(ci, KEYS.esc, 100);
    if (atMenu()) break;
    await tap(ci, KEYS.space, 100);
    await sleep(150);
  }
});

await step("C: character creation", async () => { await tap(ci, A("c"), 120); await sleep(6000); });
await step("F: fighter", async () => { await tap(ci, A("f"), 120); await sleep(3000); });
// PICK A PORTRAIT is the one step with no hotkey: the nine portraits are a
// grid at the left of the creation screen and one has to be clicked.
await step("click a portrait", async () => { await click(ci, 0.14, 0.36); await sleep(2500); });
await step("R: roll", async () => { await tap(ci, A("r"), 120); await sleep(2500); });
await step("I: items", async () => { await tap(ci, A("i"), 120); await sleep(2500); });
await step("N: name ZORBAX", async () => {
  await tap(ci, A("n"), 120);
  await sleep(2000);
  for (const ch of "ZORBAX") { await tap(ci, A(ch), 90); await sleep(180); }
  await tap(ci, KEYS.enter, 120);
  await sleep(2500);
});
await step("K: keep character", async () => { await tap(ci, A("k"), 120); await sleep(5000); });
await step("Q: leave creation", async () => { await tap(ci, A("q"), 120); await sleep(4000); });
await step("A: assemble a party", async () => { await tap(ci, A("a"), 120); await sleep(4000); });
await step("1: activate slot 1", async () => { await tap(ci, A("1"), 120); await sleep(2000); });
await step("D: done", async () => { await tap(ci, A("d"), 120); await sleep(3000); });
await step("E: enter the game", async () => { await tap(ci, A("e"), 120); await sleep(9000); });
// Entering the game lands with the disk panel already open, so close it first
// Pressing D there picks DOS, not the disk icon, and the run walks into the
// "exit to DOS?" dialog instead of saving.
await step("R: return", async () => { await tap(ci, A("r"), 120); await sleep(3000); });
await step("D: disk icon", async () => { await tap(ci, A("d"), 120); await sleep(3000); });
await step("S: save", async () => { await tap(ci, A("s"), 120); await sleep(5000); });
// The six slots are a clickable list; SAVE only arms it, the slot picks the file.
await step("click save slot 1", async () => { await click(ci, 0.5, 0.143); await sleep(6000); });
// N then Y is the only way back to the main menu from inside a game.
await step("N: new game", async () => { await tap(ci, A("n"), 120); await sleep(3000); });
await step("Y: confirm", async () => { await tap(ci, A("y"), 120); await sleep(6000); });
await step("A: assemble again", async () => { await tap(ci, A("a"), 120); await sleep(5000); });

await ci.exit();
await sleep(800);
drain("after exit");
writeFileSync(join(outDir, "ops.json"), JSON.stringify(all, null, 1));
console.log(`\n${all.length} filesystem events, screens in ${outDir}/`);
process.exit(0);
