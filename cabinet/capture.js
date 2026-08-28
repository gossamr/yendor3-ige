// Boot the game headlessly and write frames to PNG.
//
// Exists so the game can be verified, and its real UI colors sampled, without
// a browser in the loop.
//
//   bun capture.js [--seconds=60] [--out=../tmp/shots] [--skip] [--every=4]
//   bun capture.js --keys=tab            press keys once the game is up
import { mkdirSync, writeFileSync } from "fs";
import { join } from "path";

import { loadEmulators, initFs, HEADLESS_ARGS } from "./boot.js";
import { KEYS, tap, skipSplash } from "./keys.js";
import { encodePng } from "./png.js";

const arg = (name, dflt) => {
  const hit = process.argv.find((a) => a.startsWith(`--${name}=`));
  return hit === undefined ? dflt : hit.split("=").slice(1).join("=");
};
const flag = (name) => process.argv.includes(`--${name}`);

const seconds = Number(arg("seconds", 60));
const every = Number(arg("every", 4));
const outDir = arg("out", "../tmp/shots");
const keySeq = arg("keys", "").split(",").filter(Boolean);

mkdirSync(outDir, { recursive: true });

const emulators = await loadEmulators();
const ci = await emulators.dosboxNode(await initFs({ extra: arg("args", HEADLESS_ARGS) }));
console.log(`booted ${ci.width()}x${ci.height()}`);

let last = null;
let frames = 0;
ci.events().onFrame((rgb) => {
  if (rgb) { last = rgb.slice(); frames++; }
});
if (flag("verbose")) ci.events().onStdout((m) => process.stdout.write(`[dos] ${m}`));

const shots = [];
function shoot(tag) {
  if (!last) return;
  const name = join(outDir, `${String(shots.length).padStart(2, "0")}-${tag}.png`);
  writeFileSync(name, encodePng(ci.width(), ci.height(), last));
  shots.push(name);
  console.log("  shot", name, `${ci.width()}x${ci.height()}`);
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// Let the DOS prompt and the loader get going before touching anything.
await sleep(8000);
shoot("boot");

if (flag("skip")) {
  console.log("skipping splash screens...");
  await skipSplash(ci);
  shoot("after-skip");
}

for (const k of keySeq) {
  if (!(k in KEYS)) throw new Error(`unknown key '${k}'; known: ${Object.keys(KEYS)}`);
  console.log("  key", k);
  await tap(ci, KEYS[k]);
  await sleep(1500);
  shoot(`key-${k}`);
}

const started = Date.now();
while ((Date.now() - started) / 1000 < seconds) {
  await sleep(every * 1000);
  shoot(`t${Math.round((Date.now() - started) / 1000)}`);
}

console.log(`captured ${frames} frames, wrote ${shots.length} images`);
await ci.exit();
process.exit(0);
