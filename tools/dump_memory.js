// Boot the game, open a map page, and dump the emulator's memory.
//
//   YENDOR_GAME_DIR=$PWD/tmp/game-debug bun tools/dump_memory.js
//
// js-dos exposes no way to read the guest's memory, so this goes in through
// the same seam tools/trace_fs.js uses: the emulator's JavaScript is rewritten
// with a hook that can hand back Module.HEAPU8, which is where DOSBox keeps
// the guest's RAM. Everything the game holds and never re-reads, the tables
// it loaded at startup, is in there.
//
// The page carries ids 0..340 in its cells, as tmp/probe_tiles.js does, so
// whatever the game consulted to turn those into pictures has been used by the
// time the dump is taken.
//
// Finding your way around the dump: the executable's load image can be located
// by searching for a run of its own bytes: file offset 0x14000 was at heap
// 0x19b68f0 in one run, so image 0 sat at 0x19a68f0. Nothing about that is
// stable between runs.
import { existsSync } from "fs";

import { loadEmulators, initFs, HEADLESS_ARGS } from "../cabinet/boot.js";
import { KEYS, tap } from "../cabinet/keys.js";
import { buildTracedEmulator, TRACED_JS } from "./trace_fs.js";

const arg = (n, d) => {
  const hit = process.argv.find((a) => a.startsWith(`--${n}=`));
  return hit === undefined ? d : hit.split("=").slice(1).join("=");
};
const OUT = arg("out", "/workspace/tmp/memory.bin");
const index = Number(arg("index", 2));
const area = 1, level = 11;
const CELL = 4, COLS = 40, ROWS = 24, LEVEL = 160, BAND = 3200, AREA = 76800;
const DRAWN = 0x3C4F02, AREA_BITS = 2400;

const files = await initFs({ extra: `/P ${HEADLESS_ARGS}` });
const world = files.find((f) => f.path && f.path.toUpperCase() === "WORLD.DAT");
const put = (at, v) => {
  world.contents[at] = v & 0xff; world.contents[at + 1] = (v >> 8) & 0xff;
};
// Which ids to lay across the page, and in what order. The game caches the
// tiles a page needs in first-use order, so the order here is what attributes
// a cached tile to an id: whichever id reaches a tile first is the one that
// put it in the cache.
const spec = arg("ids", "0..340");
const ids = spec.includes("..")
  ? (() => {
      const [a, b] = spec.split("..").map(Number);
      const out = [];
      for (let i = a; i <= b; i++) out.push(i);
      return out;
    })()
  : spec.split(",").map(Number);
if (process.argv.includes("--reverse")) ids.reverse();

let n = 0;
for (let band = 0; band < ROWS; band++) {
  for (let col = 0; col < COLS; col++) {
    const at = area * AREA + band * BAND + level * LEVEL + col * CELL;
    const drawn = col >= 3 && col < 37;
    put(at, drawn && n < ids.length ? ids[n++] : 0);
    put(at + 2, 0);
  }
  const bits = DRAWN + area * AREA_BITS + band * 100 + level * 5;
  for (let b = 0; b < 5; b++) world.contents[bits + b] = 0xff;
}
console.log(`laid ${Math.min(ids.length, 816)} ids, first ${ids.slice(0, 6)}`);

buildTracedEmulator("/workspace/tmp/fsread-dump.json", true);
const emulators = await loadEmulators();
emulators.wdosboxJs = TRACED_JS;
const ci = await emulators.dosboxNode(files);

let frame = null;
ci.events().onFrame((rgb) => { if (rgb) frame = { rgb: rgb.slice() }; });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const mean = () => {
  if (!frame) return 0;
  let s = 0;
  for (let i = 0; i < frame.rgb.length; i += 3) s += frame.rgb[i];
  return Math.round(s / (frame.rgb.length / 3));
};
for (let i = 0; i < 200 && Math.abs(mean() - 88) > 6; i++) {
  await tap(ci, KEYS.esc, 100);
  if (Math.abs(mean() - 88) <= 6) break;
  await tap(ci, KEYS.space, 100);
  await sleep(150);
}
await tap(ci, KEYS.f8, 120);
await sleep(800);
for (let i = 0; i < 8; i++) { await tap(ci, KEYS.space, 100); await sleep(200); }
await sleep(600);
await tap(ci, KEYS.f1, 120);
await sleep(1600);
for (let k = 0; k < index; k++) { await tap(ci, KEYS.down, 100); await sleep(160); }
await sleep(600);
// --on-read=N takes the dump inside the Nth read of the picture file, while
// the guest is still in whatever code asked for a tile. Without it the dump
// comes after the page is drawn, when the guest is idle in the BIOS.
const onRead = Number(arg("on-read", 0));
if (onRead > 0) {
  globalThis.__dumpOnRead = { match: "PICTURES", nth: onRead, path: OUT };
}

await tap(ci, KEYS.enter, 120);
await sleep(4000);

let size = -1;
if (onRead > 0) {
  size = globalThis.__dumpTaken ? 1 : -1;
  console.log(size > 0
    ? `dumped inside read ${onRead} of ${globalThis.__dumpTaken.path} -> ${OUT}`
    : `read ${onRead} of the picture file never happened`);
} else {
  size = globalThis.__dumpMemory ? globalThis.__dumpMemory(OUT) : -1;
  console.log(size > 0 ? `dumped ${size.toLocaleString()} bytes to ${OUT}`
                       : "no dump: the hook was not reachable");
}
await ci.exit();
process.exit(0);
