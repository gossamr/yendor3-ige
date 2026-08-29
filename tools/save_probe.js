// Play a scripted session and take the game's own state file after every step.
//
//   bun tools/save_probe.js --out=tmp/save-probe/walk --steps='north:^;north:^;south:v'
//   bun tools/save_probe.js --out=tmp/save-probe/base --save
//
// The save file is 81,037 bytes and only its first 5,000, the roster, were
// known. Two things found here make the rest reachable:
//
//   * SAVGAMEn is a byte-for-byte copy of CURGAME. Saving is a file copy, so
//     the save format *is* CURGAME's format.
//   * CURGAME is not written once at the end. The game keeps it as a
//     random-access store and writes single records back to it as they change
//     100 bytes at offset 9,500 when the party crosses a screen, and so on.
//
// Together those mean the file can be read while it is being played: snapshot
// it after each step and diff the snapshots, and every field announces itself
// by changing when the thing it holds changes. That is cheaper and far more
// legible than reading it once at the end, which is why this takes CURGAME
// after every step rather than saving.
//
// `--steps` is `label:keys` pairs separated by `;`. In keys, `^v<>` are the
// arrows, `_` is enter, `.` is a pause, `*` clicks the first row of a list,
// and anything else is that letter. `--save` also writes a SAVGAMEn at the end,
// to check the copy is still a copy.
import { mkdirSync, writeFileSync, appendFileSync, readFileSync, readdirSync, existsSync } from "fs";
import { join } from "path";

import { loadEmulators, initFs, HEADLESS_ARGS } from "../cabinet/boot.js";
import { KEYS, tap, click } from "../cabinet/keys.js";
import { encodePng } from "../cabinet/png.js";
import { buildTracedEmulator, TRACED_X_JS } from "./trace_fs.js";

const arg = (n, d) => {
  const hit = process.argv.find((a) => a.startsWith(`--${n}=`));
  return hit === undefined ? d : hit.split("=").slice(1).join("=");
};
const flag = (n) => process.argv.includes(`--${n}`);
const outDir = arg("out", "tmp/save-probe/run");
const slot = Number(arg("slot", 1));
const pace = Number(arg("pace", 900));
mkdirSync(outDir, { recursive: true });
const log = join(outDir, "log.txt");
writeFileSync(log, "");
const say = (s) => { console.log(s); appendFileSync(log, s + "\n"); };

const FSLOG = join(outDir, "fsops.json");
buildTracedEmulator(FSLOG, true, true, "wdosbox-x.js");
const emulators = await loadEmulators();
emulators.wdosboxxJs = TRACED_X_JS;

// --load=DIR puts save files on the emulated disk before boot, so a save made
// somewhere else can be opened and read. The game only offers LOAD for a slot
// that exists, and it reads SAVGAMEn straight off the disk, so dropping the
// files in is the whole of it.
const files = await initFs({ extra: HEADLESS_ARGS });
const from = arg("load", "");
if (from) {
  for (const name of readdirSync(from)) {
    if (!/^SAVGAME\d$/i.test(name)) continue;
    const contents = new Uint8Array(readFileSync(join(from, name)));
    const at = files.findIndex((f) => f.path && f.path.toUpperCase() === name.toUpperCase());
    if (at >= 0) files[at] = { path: name, contents };
    else files.unshift({ path: name, contents });
    say(`loaded ${name} (${contents.length.toLocaleString()} bytes) onto the disk`);
  }
}
const ci = await emulators.dosboxXNode(files);
let frame = null;
ci.events().onFrame((rgb) => {
  if (rgb) frame = { rgb: rgb.slice(), w: ci.width(), h: ci.height() };
});
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const sig = () => {
  if (!frame) return [0, 0, 0, 0];
  const px = frame.rgb; let r = 0, g = 0, b = 0; const seen = new Set();
  for (let i = 0; i < px.length; i += 3) {
    r += px[i]; g += px[i + 1]; b += px[i + 2];
    seen.add((px[i] >> 4 << 8) | (px[i + 1] >> 4 << 4) | (px[i + 2] >> 4));
  }
  const n = px.length / 3; return [r / n | 0, g / n | 0, b / n | 0, seen.size];
};
const atMenu = () => {
  const c = sig();
  return Math.abs(c[0] - 88) <= 6 && Math.abs(c[1] - 78) <= 6 && c[3] < 70;
};
const A = (c) => c.toUpperCase().charCodeAt(0);
const KEY = { "^": KEYS.up, v: KEYS.down, "<": KEYS.left, ">": KEYS.right, _: KEYS.enter };

// --- the step machinery -----------------------------------------------------
// A step is a label, the keys it presses, and the state file as it stood when
// the keys had settled. The snapshots are what get diffed; everything else --
// the screenshot, the filesystem ops, is there to say what the diff means.
let stepNo = 0;
let fsSeen = 0;
const index = [];

function fsSince(label) {
  if (!existsSync(FSLOG)) return [];
  let trace;
  try { trace = JSON.parse(readFileSync(FSLOG, "utf8")); } catch { return []; }
  const ops = (trace.ops || []).slice(fsSeen);
  fsSeen = (trace.ops || []).length;
  return ops
    .filter((o) => /CURGAME|SAVGAME/i.test(String(o[2])))
    .map((o) => ({ op: o[1], file: String(o[2]).split("/").pop(), at: o[4], len: o[5], note: o[3] }));
}

// Saving is six presses and a typed name, and the last 12,480 bytes of the
// file are only ever written by it: CURGAME carries whatever the launch put
// there. So a run that wants to see that block has to save, and a run that
// wants to see it change has to save twice.
async function saveTo(n, name) {
  await press("d");
  await press("s");
  await press(String(n));
  await press(name);
  await tap(ci, KEYS.enter, 120); await sleep(2500);
  await tap(ci, A("y"), 120); await sleep(7000);
  try {
    const bytes = await ci.fsReadFile(`SAVGAME${n}`);
    writeFileSync(join(outDir, `SAVGAME${n}`), Buffer.from(bytes));
    say(`     SAVGAME${n}: ${bytes.length.toLocaleString()} bytes`);
  } catch { say(`     SAVGAME${n} was never written`); }
  // The panel closes itself once the save is confirmed. Pressing R to leave it
  // therefore lands on REST, and the party then stands at a yes/no prompt that
  // swallows every key the rest of the run presses.
}

async function press(keys) {
  for (const k of keys) {
    if (k === ".") { await sleep(pace); continue; }
    if (k === "*") { await click(ci, 0.18, 0.195); }
    else await tap(ci, KEY[k] === undefined ? A(k) : KEY[k], 120);
    await sleep(pace);
  }
}

async function step(label, keys, settle = 1200) {
  stepNo += 1;
  const tag = `${String(stepNo).padStart(2, "0")}-${label.replace(/\W+/g, "-")}`;
  const save = /^!save(\d)$/.exec(keys);
  const load = /^!load(\d)$/.exec(keys);
  if (save) await saveTo(Number(save[1]), arg("name", "PROBE"));
  else if (load) { await press(`dl${load[1]}`); await sleep(3000); await press("y"); await sleep(9000); }
  else if (/^!f[1-8]$/.test(keys)) await tap(ci, KEYS[keys.slice(1)], 120);
  else if (/^!click/.test(keys)) {
    const [x, y] = keys.slice(6).split(",").map(Number);
    await click(ci, x, y);
  }
  else if (/^!pick(\d)$/.test(keys)) {
    await press(`l${keys.slice(5)}`); await sleep(3000); await press("y");
  }
  else await press(keys);
  await sleep(settle);
  const touched = fsSince(label);
  let bytes = null;
  try { bytes = await ci.fsReadFile("CURGAME"); } catch { /* not there yet */ }
  if (bytes) writeFileSync(join(outDir, `${tag}.bin`), Buffer.from(bytes));
  if (frame) writeFileSync(join(outDir, `${tag}.png`), encodePng(frame.w, frame.h, frame.rgb));
  index.push({ step: stepNo, label, keys, tag, bytes: bytes ? bytes.length : 0, touched });
  const writes = touched.filter((t) => t.op === "write")
    .map((t) => `${t.file}@${t.at}+${t.len}`).join(" ");
  say(`[${String(stepNo).padStart(2, "0")}] ${label.padEnd(22)} ${keys.padEnd(14)}`
    + ` ${bytes ? bytes.length : "-"}  ${writes}`);
  return bytes;
}

// --- getting into a game ----------------------------------------------------
// With a save on the disk the game does not offer its main menu at all: it
// comes up in the disk panel with LOAD, NEW GAME and DOS. So a run that loads
// cannot look for the menu, and must not press D there: that is DOS.
if (arg("start", "new") === "load") {
  for (let i = 0; i < 10; i++) {
    await tap(ci, KEYS.esc, 100);
    await tap(ci, KEYS.space, 100);
    await sleep(400);
  }
  await step("load a slot", `!pick${slot}`, 14000);
} else {
  for (let i = 0; i < 200 && !atMenu(); i++) {
    await tap(ci, KEYS.esc, 100);
    if (atMenu()) break;
    await tap(ci, KEYS.space, 100);
    await sleep(150);
  }
  say("at the main menu");
  await step("assemble", "a", 4000);
  await step("pick the party", arg("party", "6789"), 2000);
  await step("done", "d", 3000);
  await step("enter the world", "e", 13000);
  await step("close the disk panel", "r", 3000);
}

// --- what this run is for ---------------------------------------------------
const steps = arg("steps", "");
for (const spec of steps ? steps.split(";") : []) {
  const at = spec.indexOf(":");
  const label = at < 0 ? spec : spec.slice(0, at);
  const keys = at < 0 ? "" : spec.slice(at + 1);
  await step(label, keys, Number(arg("settle", 1500)));
}

// --- and, if asked, a real save --------------------------------------------
if (flag("save")) await step(`save ${slot}`, `!save${slot}`, 2000);

if (flag("dump")) {
  const at = join(outDir, "heap.bin");
  const n = globalThis.__dumpMemory ? globalThis.__dumpMemory(at) : -1;
  say(n > 0 ? `heap: ${n.toLocaleString()} bytes -> ${at}` : "heap: hook unreachable");
}
writeFileSync(join(outDir, "index.json"), JSON.stringify({ steps: index }, null, 1));
say(`${index.length} steps -> ${outDir}`);
await ci.exit();
process.exit(0);
