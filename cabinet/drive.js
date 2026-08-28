// Drive the game through a scripted sequence of inputs, screenshotting as it
// goes. Used to reach in-game screens (the party view, the Restoration clue
// book) so they can be inspected and their colors sampled.
//
//   bun drive.js --out=../tmp/shots --do="wait 14; shot menu; click .5 .45; wait 6; shot game"
//
// Actions: wait <sec> | shot <name> | click <x> <y> | rclick <x> <y> | key <name>
import { mkdirSync, writeFileSync } from "fs";
import { join } from "path";

import { loadEmulators, initFs, HEADLESS_ARGS } from "./boot.js";
import { KEYS, BUTTONS, tap, click } from "./keys.js";
import { encodePng } from "./png.js";

const arg = (n, d) => {
  const hit = process.argv.find((a) => a.startsWith(`--${n}=`));
  return hit === undefined ? d : hit.split("=").slice(1).join("=");
};

const outDir = arg("out", "../tmp/shots");
const script = arg("do", "wait 16; shot menu");
mkdirSync(outDir, { recursive: true });

const emulators = await loadEmulators();
const ci = await emulators.dosboxNode(await initFs({ extra: arg("args", HEADLESS_ARGS) }));

// Track the frame together with the size it was produced at: the game changes
// video mode during startup, so ci.width() at write time can disagree with the
// buffer we are holding.
let frame = null;
ci.events().onFrame((rgb) => {
  if (rgb) frame = { rgb: rgb.slice(), w: ci.width(), h: ci.height() };
});

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let n = 0;

for (const raw of script.split(";").map((s) => s.trim()).filter(Boolean)) {
  const [op, ...rest] = raw.split(/\s+/);
  switch (op) {
    case "wait":
      await sleep(Number(rest[0]) * 1000);
      break;
    case "shot": {
      if (!frame) { console.log("  (no frame yet)"); break; }
      const file = join(outDir, `${String(n++).padStart(2, "0")}-${rest[0] || "shot"}.png`);
      writeFileSync(file, encodePng(frame.w, frame.h, frame.rgb));
      console.log(`  shot ${file} ${frame.w}x${frame.h}`);
      break;
    }
    case "click":
      await click(ci, Number(rest[0]), Number(rest[1]));
      break;
    case "rclick":
      await click(ci, Number(rest[0]), Number(rest[1]), BUTTONS.right);
      break;
    case "key": {
      const k = rest[0];
      if (!(k in KEYS)) throw new Error(`unknown key '${k}'`);
      await tap(ci, KEYS[k]);
      break;
    }
    default:
      throw new Error(`unknown action '${op}' in: ${raw}`);
  }
}

await ci.exit();
process.exit(0);
