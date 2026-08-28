// Walk the game's F2 monster list and screenshot every creature's stat screen.
//
// This is the "fast path": a patched executable plus /P lands on the main menu
// in about two seconds, so the whole list is a few minutes rather than an hour.
//
//   YENDOR_GAME_DIR=tmp/game-patched bun tools/capture_monsters.js \
//       --out=tmp/monsters --count=72
import { mkdirSync, writeFileSync } from "fs";
import { join } from "path";

import { loadEmulators, initFs, HEADLESS_ARGS } from "../cabinet/boot.js";
import { KEYS, tap } from "../cabinet/keys.js";
import { encodePng } from "../cabinet/png.js";

const arg = (n, d) => {
  const hit = process.argv.find((a) => a.startsWith(`--${n}=`));
  return hit === undefined ? d : hit.split("=").slice(1).join("=");
};
const outDir = arg("out", "tmp/monsters");
const count = Number(arg("count", 72));
mkdirSync(outDir, { recursive: true });

const emulators = await loadEmulators();
const ci = await emulators.dosboxNode(
  await initFs({ extra: `/P ${HEADLESS_ARGS}` }));

let frame = null;
ci.events().onFrame((rgb) => {
  if (rgb) frame = { rgb: rgb.slice(), w: ci.width(), h: ci.height() };
});
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

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

function shot(name) {
  if (!frame) return false;
  writeFileSync(join(outDir, `${name}.png`), encodePng(frame.w, frame.h, frame.rgb));
  return true;
}

// Reach the menu. With /P this is quick, but still poll rather than guess.
for (let i = 0; i < 200 && !atMenu(); i++) {
  await tap(ci, KEYS.esc, 100);
  if (atMenu()) break;
  await tap(ci, KEYS.space, 100);
  await sleep(150);
}
console.log("menu:", sig());

// Open the clue book and reach monster statistics.
await tap(ci, KEYS.f8, 120);
await sleep(800);
for (let i = 0; i < 8; i++) { await tap(ci, KEYS.space, 100); await sleep(200); }
await sleep(500);
shot("00-cluebook");
await tap(ci, KEYS.f2, 120);
await sleep(1200);
shot("01-list");
console.log("list:", sig());

// Walk the list: open each entry, capture, go back with LEFT (ESC would quit
// the clue book entirely), then step down one.
for (let i = 0; i < count; i++) {
  await tap(ci, KEYS.enter, 110);
  await sleep(700);
  const label = String(i).padStart(2, "0");
  if (!shot(`m${label}`)) console.log(`  ${label}: no frame`);
  else if (i % 10 === 0) console.log(`  captured ${label}  ${sig()}`);
  await tap(ci, KEYS.left, 110);
  await sleep(450);
  await tap(ci, KEYS.down, 110);
  await sleep(250);
}

console.log(`done: ${count} screens in ${outDir}/`);
await ci.exit();
process.exit(0);
