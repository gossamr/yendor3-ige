// Change the map data and see what moves on screen.
//
// The tracer says a clue-book map page is drawn from 24 iterations, each
// reading one 3200-byte chunk of the area's region plus a 100-byte grid row.
// Which part of the picture each chunk drives is not something to reason about
// from byte histograms: blank one and look.
//
//   YENDOR_GAME_DIR=tmp/game-patched bun tools/probe_map_data.js \
//       --base=0x25800 --chunk=0 --out=tmp/maps/probe
import { mkdirSync, writeFileSync } from "fs";
import { join } from "path";

import { loadEmulators, initFs, GAME_DIR, HEADLESS_ARGS } from "../cabinet/boot.js";
import { KEYS, tap } from "../cabinet/keys.js";
import { encodePng } from "../cabinet/png.js";

const arg = (n, d) => {
  const hit = process.argv.find((a) => a.startsWith(`--${n}=`));
  return hit === undefined ? d : hit.split("=").slice(1).join("=");
};
const base = Number(arg("base", "0x25800"));
const chunk = Number(arg("chunk", -1));       // -1 leaves the data alone
const size = Number(arg("size", 3200));
const outDir = arg("out", "tmp/maps/probe");
const index = Number(arg("index", 0));
mkdirSync(outDir, { recursive: true });

// Copying one record over another is a *positive* test, and the blanking test
// needs one: blanking writes zeros, which selects tile 0, and where tile 0
// renders like the tile it replaced the diff shows nothing. Every "no change"
// from a blank is a lower bound. A copy has no such blind spot: if the source
// really drives that part of the page, the page changes to match the source.
const copyFrom = Number(arg("copyfrom", -1));
const copyTo = Number(arg("copyto", -1));

const files = await initFs({ extra: `/P ${HEADLESS_ARGS}` });
const world = files.find((f) => f.path && f.path.toUpperCase() === "WORLD.DAT");
if (copyFrom >= 0 && copyTo >= 0) {
  const src = base + copyFrom * size;
  const dst = base + copyTo * size;
  world.contents.copyWithin(dst, src, src + size);
  console.log(`copied 0x${src.toString(16)} -> 0x${dst.toString(16)} (${size} B)`);
} else if (chunk >= 0) {
  const at = base + chunk * size;
  world.contents.fill(0, at, at + size);
  console.log(`blanked 0x${at.toString(16)} .. 0x${(at + size).toString(16)}`);
}

const emulators = await loadEmulators();
const ci = await emulators.dosboxNode(files);
let frame = null;
ci.events().onFrame((rgb) => {
  if (rgb) frame = { rgb: rgb.slice(), w: ci.width(), h: ci.height() };
});
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
ci.sendMouseMotion(0.5, 0.0);
await tap(ci, KEYS.enter, 120);
await sleep(3000);

const name = copyFrom >= 0 ? `copy${copyFrom}to${copyTo}`
  : chunk >= 0 ? `chunk${String(chunk).padStart(2, "0")}` : "clean";
writeFileSync(join(outDir, `${name}.png`),
  encodePng(frame.w, frame.h, frame.rgb));
console.log(`wrote ${name}.png`);
await ci.exit();
process.exit(0);
