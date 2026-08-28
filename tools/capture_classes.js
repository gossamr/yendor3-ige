// Walk the clue book's F4 pages: for each magic class, the full list of spells
// it can cast, paged to the end.
//
// This is the check on the class decode. F3 prints at most three class rows per
// spell, so it cannot show every (class, spell) pair; F4 lists them by class and
// can. `tools/read_class_spells.py` reads these captures back.
//
//   YENDOR_GAME_DIR=tmp/game-patched bun tools/capture_classes.js
import { mkdirSync, writeFileSync } from "fs";
import { join } from "path";
import { loadEmulators, initFs, HEADLESS_ARGS } from "../cabinet/boot.js";
import { KEYS, tap } from "../cabinet/keys.js";
import { encodePng } from "../cabinet/png.js";
const out = "tmp/f4"; mkdirSync(out, { recursive: true });
const emulators = await loadEmulators();
const ci = await emulators.dosboxNode(await initFs({ extra: `/P ${HEADLESS_ARGS}` }));
let frame = null;
ci.events().onFrame((rgb) => { if (rgb) frame = { rgb: rgb.slice(), w: ci.width(), h: ci.height() }; });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const shot = (n) => frame && writeFileSync(join(out, `${n}.png`), encodePng(frame.w, frame.h, frame.rgb));
const key = () => frame ? frame.rgb.join(",").length + ":" + frame.rgb.reduce((a, b) => a + b, 0) : "";
function sig() { if (!frame) return 0; const p = frame.rgb; let r = 0;
  for (let i = 0; i < p.length; i += 3) r += p[i]; return Math.round(r / (p.length / 3)); }
for (let i = 0; i < 200 && Math.abs(sig() - 88) > 6; i++) {
  await tap(ci, KEYS.esc, 100); await tap(ci, KEYS.space, 100); await sleep(150);
}
await tap(ci, KEYS.f8, 120); await sleep(800);
for (let i = 0; i < 8; i++) { await tap(ci, KEYS.space, 100); await sleep(200); }
await sleep(600);
await tap(ci, KEYS.f4, 120); await sleep(1800);
for (let k = 0; k < 6; k++) {
  // Going back lands on the top of the class list, so walk down to the class
  // wanted each time rather than assuming the cursor stayed put.
  for (let i = 0; i < k; i++) { await tap(ci, KEYS.down, 110); await sleep(200); }
  await tap(ci, KEYS.enter, 130); await sleep(1600);
  let last = "";
  for (let page = 0; page < 12; page++) {
    const now = key();
    if (now === last) break;
    last = now;
    shot(`c${k}-p${page}`);
    // The list scrolls a row at a time; a page is sixteen rows.
    for (let r = 0; r < 16; r++) { await tap(ci, KEYS.down, 60); await sleep(45); }
    await sleep(500);
  }
  await tap(ci, KEYS.left, 130); await sleep(1200);
}
await ci.exit(); process.exit(0);
