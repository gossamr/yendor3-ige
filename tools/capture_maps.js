// Walk the game's F1 map list and screenshot every area's map.
//
// The clue book's maps are drawn pictures, not tile grids: the 37 x 64 table at
// 0x8CDDE holds tile-placement coordinates into a graphics bank, so there is no
// grid to decode. The map *is* the picture, which makes capturing it the
// decode: these frames are the data.
//
//   YENDOR_GAME_DIR=tmp/game-patched bun tools/capture_maps.js --out=tmp/maps
import { mkdirSync, writeFileSync } from "fs";
import { join } from "path";

import { loadEmulators, initFs, HEADLESS_ARGS } from "../cabinet/boot.js";
import { KEYS, tap } from "../cabinet/keys.js";
import { encodePng } from "../cabinet/png.js";

const arg = (n, d) => {
  const hit = process.argv.find((a) => a.startsWith(`--${n}=`));
  return hit === undefined ? d : hit.split("=").slice(1).join("=");
};
const outDir = arg("out", "tmp/maps");
const count = Number(arg("count", 37));
mkdirSync(outDir, { recursive: true });

// Optional: blank byte ranges of WORLD.DAT before booting, as "start:len,..."
// Used to find which page a legend group belongs to: blank a group's marker
// records and the page that loses its markers is the page that owns them.
const blank = arg("blank", "");

const emulators = await loadEmulators();
const files = await initFs({ extra: `/P ${HEADLESS_ARGS}` });
if (blank) {
  const world = files.find((f) => f.path && f.path.toUpperCase() === "WORLD.DAT");
  let total = 0;
  for (const part of blank.split(",")) {
    const [at, len] = part.split(":").map(Number);
    world.contents.fill(0, at, at + len);
    total += len;
  }
  console.log(`blanked ${total} bytes in ${blank.split(",").length} ranges`);
}
const ci = await emulators.dosboxNode(files);

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
// The list is gray and flat; a map is brown and busy.
const onList = () => Number(sig().split(",")[0]) < 75;

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
// Park the pointer in the title strip. The game draws its own cursor wherever
// the mouse happens to sit, and it landed in the middle of three maps; the
// title bar is cropped off anyway, so parking it there removes it for good.
const parkMouse = () => ci.sendMouseMotion(0.5, 0.0);
parkMouse();

await tap(ci, KEYS.f1, 120);
await sleep(1400);
shot("00-list");
console.log("list:", sig());

// Re-entering the list and stepping down from the top for each map is slower
// than walking it, but it cannot drift: a page that fails to open leaves the
// cursor where it was, and the next map would otherwise be captured under the
// wrong index, which matters here, because the trailing "LEVEL n" is read
// from the list order.
const only = arg("only", "");
const wanted = only ? only.split(",").map(Number) : null;

for (let i = 0; i < count; i++) {
  if (wanted && !wanted.includes(i)) continue;
  if (wanted) {
    await tap(ci, KEYS.f1, 120);
    await sleep(1300);
    for (let k = 0; k < i; k++) { await tap(ci, KEYS.down, 90); await sleep(150); }
  }
  await tap(ci, KEYS.enter, 120);
  await sleep(1300);
  parkMouse();
  await sleep(400);
  // Always save the frame. Judging "did a map open?" by mean brightness threw
  // away real pages: a town map is gray enough to look like the list, and five
  // areas went missing that way in two separate runs. Whether a frame is a map
  // is settled afterwards, by whether its title bar reads as an area name.
  if (!shot(`m${String(i).padStart(2, "0")}`)) console.log(`  ${i}: no frame`);
  else if (i % 6 === 0) console.log(`  captured ${i}  ${sig()}`);
  // ESC leaves the map for the list; it does not quit the clue book from here.
  await tap(ci, KEYS.esc, 120);
  await sleep(900);
  if (!onList()) {
    console.log(`  lost the list after ${i}; re-entering`);
    await tap(ci, KEYS.f1, 120);
    await sleep(1200);
    for (let k = 0; k <= i; k++) { await tap(ci, KEYS.down, 90); await sleep(140); }
  }
  await tap(ci, KEYS.down, 110);
  await sleep(220);
}

console.log(`done: screens in ${outDir}/`);
await ci.exit();
process.exit(0);
