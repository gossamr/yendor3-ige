// Boot the game with the filesystem tracer, open one clue-book map, and record
// exactly which byte ranges of which files were read while it loaded.
//
//   YENDOR_GAME_DIR=tmp/game-patched bun tools/trace_map_load.js --index=0
import { writeFileSync, readFileSync, existsSync } from "fs";

import { loadEmulators, initFs, HEADLESS_ARGS } from "../cabinet/boot.js";
import { KEYS, tap } from "../cabinet/keys.js";
import { buildTracedEmulator, TRACED_JS } from "./trace_fs.js";

const arg = (n, d) => {
  const hit = process.argv.find((a) => a.startsWith(`--${n}=`));
  return hit === undefined ? d : hit.split("=").slice(1).join("=");
};
const index = Number(arg("index", 0));
const LOG = "/workspace/tmp/fsread.json";
const OUT = arg("out", "/workspace/tmp/map-load.json");

buildTracedEmulator(LOG, true);
const emulators = await loadEmulators();
emulators.wdosboxJs = TRACED_JS;
const ci = await emulators.dosboxNode(await initFs({ extra: `/P ${HEADLESS_ARGS}` }));

let frame = null;
ci.events().onFrame((rgb) => { if (rgb) frame = { rgb: rgb.slice() }; });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
function sig() {
  if (!frame) return "";
  const px = frame.rgb;
  let r = 0;
  for (let i = 0; i < px.length; i += 3) r += px[i];
  return Math.round(r / (px.length / 3));
}
const atMenu = () => Math.abs(sig() - 88) <= 6;

for (let i = 0; i < 200 && !atMenu(); i++) {
  await tap(ci, KEYS.esc, 100);
  if (atMenu()) break;
  await tap(ci, KEYS.space, 100);
  await sleep(150);
}
await tap(ci, KEYS.f8, 120);
await sleep(800);
for (let i = 0; i < 8; i++) { await tap(ci, KEYS.space, 100); await sleep(200); }
await sleep(600);
// Mark before the list is even asked for: the area's region is read while the
// clue book prepares the page, which happens inside the F1 keypress, not after.
const openedList = Date.now();
await tap(ci, KEYS.f1, 120);
await sleep(1600);
// starts at ENTER can miss it entirely, which it did.)
for (let k = 0; k < index; k++) { await tap(ci, KEYS.down, 100); await sleep(160); }
await sleep(1200);

// Open several maps in one session, marking the window around each: the
// per-map offsets and the deltas between them are what reveal the record.
const count = Number(arg("count", 6));
const windows = [];
for (let i = index; i < index + count; i++) {
  const before = windows.length ? Date.now() : openedList;
  await tap(ci, KEYS.enter, 120);
  await sleep(2600);
  const after = Date.now();
  windows.push({ i, before, after });
  await tap(ci, KEYS.esc, 120);
  await sleep(900);
  await tap(ci, KEYS.down, 110);
  await sleep(250);
}

await ci.exit();
await sleep(600);

if (!existsSync(LOG)) { console.error("no trace written"); process.exit(1); }
const trace = JSON.parse(readFileSync(LOG, "utf8"));
const all = trace.events.map(([t, p, at, len]) =>
  ({ t: trace.t0 + t, path: trace.paths[p], at, len }));

const report = [];
for (const win of windows) {
  const hits = all.filter((e) => e.t >= win.before && e.t <= win.after);
  const ranges = {};
  for (const e of hits) {
    const list = (ranges[e.path] ||= []);
    const last = list[list.length - 1];
    if (last && e.at <= last[1] + 64) last[1] = Math.max(last[1], e.at + e.len);
    else list.push([e.at, e.at + e.len]);
  }
  report.push({ index: win.i, ranges });
  console.log(`\nmap ${win.i}:`);
  for (const [path, list] of Object.entries(ranges)) {
    const name = path.split("/").pop();
    for (const [a, b] of list) {
      console.log(`  ${name.padEnd(13)} 0x${a.toString(16)} .. 0x${b.toString(16)}  (${b - a})`);
    }
  }
}
writeFileSync(OUT, JSON.stringify(report, null, 1));
process.exit(0);
