// Click a map page's gold markers and screenshot the caption the game prints.
//
// The map page's title bar says SELECT LEGEND OR ESC: clicking a marker names
// it there. That is the check on the marker decode, and what caught the
// caption being field 3 of the record rather than the record's own position.
//
//   MARKS=$(python -c "import json;print(json.dumps(
//       json.load(open('data/map_marks.json'))['ELFIN CITY']))") \
//   YENDOR_GAME_DIR=tmp/game-patched bun tools/capture_legend.js --index=20
//
// Two things this needs: the DOSBox-X backend, because plain DOSBox never
// delivers mouse coordinates to the guest, and a *double* click, because a
// single one does not select.
import { mkdirSync, writeFileSync } from "fs";
import { join } from "path";
import { loadEmulators, initFs, HEADLESS_ARGS } from "../cabinet/boot.js";
import { KEYS, tap, click } from "../cabinet/keys.js";
import { encodePng } from "../cabinet/png.js";

const index = Number((process.argv.find((a) => a.startsWith("--index=")) || "").split("=")[1] || 20);
const out = "tmp/legend";
mkdirSync(out, { recursive: true });

const emulators = await loadEmulators();
const ci = await emulators.dosboxXNode(await initFs({ extra: `/P ${HEADLESS_ARGS}` }));
let frame = null;
ci.events().onFrame((rgb) => { if (rgb) frame = { rgb: rgb.slice(), w: ci.width(), h: ci.height() }; });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const shot = (n) => frame && writeFileSync(join(out, `${n}.png`), encodePng(frame.w, frame.h, frame.rgb));
function sig() {
  if (!frame) return "";
  const px = frame.rgb; let r = 0;
  for (let i = 0; i < px.length; i += 3) r += px[i];
  return Math.round(r / (px.length / 3));
}
for (let i = 0; i < 200 && Math.abs(sig() - 88) > 6; i++) {
  await tap(ci, KEYS.esc, 100); await tap(ci, KEYS.space, 100); await sleep(150);
}
await tap(ci, KEYS.f8, 120); await sleep(800);
for (let i = 0; i < 8; i++) { await tap(ci, KEYS.space, 100); await sleep(200); }
await sleep(600);
await tap(ci, KEYS.f1, 120); await sleep(1600);
for (let k = 0; k < index; k++) { await tap(ci, KEYS.down, 100); await sleep(160); }
await sleep(800);
await tap(ci, KEYS.enter, 120); await sleep(2600);
shot("map");
// "SELECT LEGEND" means click a gold square. The marker positions are decoded,
// so click each one and see whether the game has a caption for it.
const marks = JSON.parse(process.env.MARKS || "[]");
for (const [i, m] of marks.entries()) {
  const px = 24 + m.col * 8 + 4;
  const py = 8 + m.row * 8 + 4;
  // The guest cursor sits a little right of and below the pointer (see
  // cabinet/mouse.js), so aim high-left of the square's center; and lists in this
  // game select on a double click.
  await click(ci, (px - 3) / 320, (py - 3) / 200);
  await sleep(400);
  shot(`mark-${i + 1}-single`);
  ci.sendMouseButton(0, true); await sleep(90); ci.sendMouseButton(0, false);
  await sleep(1200);
  shot(`mark-${i + 1}-double`);
}
await ci.exit();
process.exit(0);
