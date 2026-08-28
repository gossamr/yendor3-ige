// Walk the game's F5 inventory-item screens and shoot every item's detail page.
//
// The F5 section is two levels deep, unlike F2 and F3: a list of the eight
// categories, then a list of items within one. So the walk is per category, and
// pressing F5 again returns to the category list rather than backing out one
// screen at a time.
//
//   YENDOR_GAME_DIR=tmp/game-patched bun tools/capture_items.js \
//       --out=tmp/items --per=70
import { mkdirSync, writeFileSync } from "fs";
import { join } from "path";

import { loadEmulators, initFs, HEADLESS_ARGS } from "../cabinet/boot.js";
import { KEYS, tap } from "../cabinet/keys.js";
import { encodePng } from "../cabinet/png.js";

const arg = (n, d) => {
  const hit = process.argv.find((a) => a.startsWith(`--${n}=`));
  return hit === undefined ? d : hit.split("=").slice(1).join("=");
};
const outDir = arg("out", "tmp/items");
const perCategory = Number(arg("per", 70));
const categories = Number(arg("categories", 8));
const firstCategory = Number(arg("from", 0));
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

/** A cheap fingerprint of the name area, to notice when the list has wrapped. */
function titleHash() {
  if (!frame) return "";
  let h = 2166136261;
  for (let y = 2; y < 12; y++) {
    for (let x = 0; x < 200; x++) {
      const i = (y * frame.w + x) * 3;
      h = Math.imul(h ^ frame.rgb[i], 16777619) >>> 0;
    }
  }
  return String(h);
}

const shot = (name) => {
  if (!frame) return false;
  writeFileSync(join(outDir, `${name}.png`), encodePng(frame.w, frame.h, frame.rgb));
  return true;
};

for (let i = 0; i < 200 && !atMenu(); i++) {
  await tap(ci, KEYS.esc, 100);
  if (atMenu()) break;
  await tap(ci, KEYS.space, 100);
  await sleep(150);
}
console.log("menu:", sig());

await tap(ci, KEYS.f8, 120);
await sleep(800);
for (let i = 0; i < 8; i++) { await tap(ci, KEYS.space, 100); await sleep(200); }
await sleep(500);

/** The category list, the item list and a detail page differ in mean color. */
const onCategoryList = () => Number(sig().split(",")[0]) <= 58;

let total = 0;
for (let cat = firstCategory; cat < categories; cat++) {
  // F5 does *not* reset from inside a detail page, being honored only at the
  // clue book's own level, so walk back out with LEFT until the category list
  // is on screen, then press it.
  for (let i = 0; i < 5 && !onCategoryList(); i++) {
    await tap(ci, KEYS.left, 110);
    await sleep(500);
  }
  await tap(ci, KEYS.f5, 120);
  await sleep(1200);
  if (!onCategoryList()) console.log(`  warning: not on the category list (${sig()})`);
  for (let i = 0; i < cat; i++) { await tap(ci, KEYS.down, 100); await sleep(160); }
  await tap(ci, KEYS.enter, 120);
  await sleep(1000);
  if (cat === 0) shot("00-list");

  const seen = new Set();
  for (let i = 0; i < perCategory; i++) {
    await tap(ci, KEYS.enter, 110);
    await sleep(650);
    const h = titleHash();
    // The list wraps rather than stopping, so a repeated title means done.
    if (seen.has(h)) { console.log(`  cat ${cat}: ${i} items`); break; }
    seen.add(h);
    shot(`c${cat}i${String(i).padStart(3, "0")}`);
    total += 1;
    await tap(ci, KEYS.left, 110);
    await sleep(420);
    await tap(ci, KEYS.down, 110);
    await sleep(220);
  }
  console.log(`category ${cat} done, ${seen.size} screens, ${sig()}`);
}

console.log(`done: ${total} screens in ${outDir}/`);
await ci.exit();
process.exit(0);
