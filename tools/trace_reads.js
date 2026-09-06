// Which byte ranges of WORLD.DAT the game reads, by section.
//
// A driver for the read hook tools/trace_fs.js already puts on every FS.read.
// That hook is what found the map data; this points it at a different
// question. It boots, walks the clue book, and then reports which sections
// arrived in one request and how far into each the reads went, which is the
// difference between a table the game loads whole and one it reads a record at
// a time.
//
// It is what settled the three runs that sit past the end of a table in
// docs/world-dat.md: section 11 arrives whole at startup, section 30 comes two
// bytes at a time through its own stub, and the labels come in 1,024-byte
// blocks as the clue book wants captions.
//
//   bun tools/trace_reads.js --out=tmp/probe/reads.json
import { existsSync, writeFileSync, readFileSync } from "fs";

import { loadEmulators, initFs, HEADLESS_ARGS } from "../cabinet/boot.js";
import { KEYS, tap } from "../cabinet/keys.js";
import { buildTracedEmulator, TRACED_JS } from "./trace_fs.js";

const arg = (n, d) => {
  const hit = process.argv.find((a) => a.startsWith(`--${n}=`));
  return hit === undefined ? d : hit.split("=").slice(1).join("=");
};
const LOG = arg("out", "/workspace/tmp/probe/reads.json");
if (existsSync(LOG)) writeFileSync(LOG, "");
buildTracedEmulator(LOG, true, false);

const emulators = await loadEmulators();
emulators.wdosboxJs = TRACED_JS;
const ci = await emulators.dosboxNode(await initFs({ extra: `/P ${HEADLESS_ARGS}` }));

let frame = null;
ci.events().onFrame((rgb) => { if (rgb) frame = rgb.slice(); });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const mean = () => {
  if (!frame) return 0;
  let s = 0;
  for (let i = 0; i < frame.length; i += 3) s += frame[i];
  return Math.round(s / (frame.length / 3));
};

// Past the attract loop and into the menu.
for (let i = 0; i < 120 && Math.abs(mean() - 88) > 6; i++) {
  await tap(ci, KEYS.esc, 100);
  if (Math.abs(mean() - 88) <= 6) break;
  await tap(ci, KEYS.space, 100);
  await sleep(150);
}
await sleep(500);

// The clue book, then each of its six sections in turn. F1 is the maps, whose
// legend captions are the run the label section is read for.
// The clue book, then each of its six sections. F1's legend captions are what
// the label section is read for, so that section is the one worth walking.
await tap(ci, KEYS.f8, 150);
await sleep(1200);
for (const key of [KEYS.f1, KEYS.f2, KEYS.f3, KEYS.f4, KEYS.f5, KEYS.f6]) {
  await tap(ci, key, 150);
  await sleep(700);
  for (let i = 0; i < 4; i++) { await tap(ci, KEYS.down, 90); await sleep(150); }
  for (let i = 0; i < 3; i++) { await tap(ci, KEYS.space, 90); await sleep(180); }
  await tap(ci, KEYS.esc, 120);
  await sleep(350);
}
await sleep(800);
await ci.exit();
await sleep(400);

const log = JSON.parse(readFileSync(LOG, "utf8"));
const world = log.paths.findIndex((p) => p && p.toUpperCase().includes("WORLD.DAT"));
const reads = log.events.filter((e) => e[1] === world);
console.log(`WORLD.DAT reads logged: ${reads.length}`);

// The three runs docs/world-dat.md records as sitting past the end of a table.
const RUNS = [
  ["section 11 past record 71", 0x009559a + 71 * 4, 0x009559a + 1600],
  ["section 30 past spawn 1862", 0x0418eaf + 1862 * 2, 0x0418eaf + 10000],
  ["labels past record 137", 0x03d3ccd + 138 * 26, 0x03d3ccd + 6500],
];
for (const [name, lo, hi] of RUNS) {
  const hits = reads.filter((e) => e[2] < hi && e[2] + e[3] > lo);
  console.log(`${name}: ${lo.toString(16)}..${hi.toString(16)} -> ${hits.length} reads overlap`);
  for (const h of hits.slice(0, 6)) {
    console.log(`   at 0x${h[2].toString(16)} for ${h[3]} bytes, ${h[0]} ms in`);
  }
}
// What the game did read of each of the three sections, as a bound.
const SECTIONS = [
  ["section 11", 0x009559a, 1600],
  ["section 30", 0x0418eaf, 10000],
  ["label section", 0x03d3ccd, 6500],
];
for (const [name, base, size] of SECTIONS) {
  const inside = reads.filter((e) => e[2] < base + size && e[2] + e[3] > base);
  if (!inside.length) { console.log(`${name}: not read at all`); continue; }
  const top = Math.max(...inside.map((e) => e[2] + e[3])) - base;
  console.log(`${name}: ${inside.length} reads, furthest byte reached ${top} of ${size}`);
}
