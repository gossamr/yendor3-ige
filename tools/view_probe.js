// The first-person view's cell table, read out of the running game.
//
//   bun tools/view_probe.js                       where the save left the party
//   bun tools/view_probe.js --x=460 --y=46 --facing=0x8000
//   bun tools/view_probe.js --save=tmp/perf-save.json --json=tmp/view.json
//
// `docs/combat.md:263-269` records that image 0x10153 walks a 51-entry table
// at DS:0x708e in seven runs of 17, 17, 5, 3, 3, 3 and 3, taking one parameter
// word per run from DS:0x538e, and draws each entry at 0x101fb. The table is
// 408 zero bytes in the executable's image, so the game builds it as it draws
// and it can be read rather than derived.
//
// What it prints, per entry: the eight bytes, the word at +0 that 0x0bc98
// turns into something to draw, and the bit at +6 that skips the cell. Put the
// party somewhere known, read the table, move one cell, read it again, and the
// entries that follow the party are the frustum.
//
// The party's position is poked rather than walked, so a reading costs one
// boot rather than a journey. Facings are 0x8000 north, 0x4000 south, 0x2000
// west and 0x1000 east (docs/saves.md, docs/view.md).
import { readFileSync, writeFileSync, mkdirSync } from "fs";

import { loadEmulators, initFs, HEADLESS_ARGS } from "../cabinet/boot.js";
import { KEYS, tap } from "../cabinet/keys.js";
import { encodePng } from "../cabinet/png.js";
import { buildTracedEmulator, TRACED_X_JS } from "./trace_fs.js";

const arg = (n, d) => {
  const hit = process.argv.find((a) => a.startsWith(`--${n}=`));
  return hit === undefined ? d : hit.split("=").slice(1).join("=");
};
const num = (n, d) => (arg(n) === undefined ? d : Number(arg(n)));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const say = (...a) => console.log(...a);

// DS-relative addresses. The view table and its run parameters are from
// docs/combat.md; the party's cell and facing from docs/saves.md.
const VIEW = 0x708e, ENTRY = 8, CELLS = 51;
const RUNS = [17, 17, 5, 3, 3, 3, 3];
const PARAMS = 0x538e;
const FACING = 0xcf73, PARTY_X = 0xcf75, PARTY_Y = 0xcf77;
// Anchors for finding the live data segment, as tools/fight_probe.js does:
// two strings the game keeps at fixed offsets, and a word that is zero in the
// executable's own image and never zero once a party is playing.
const PICTURES = 0x969e, WORLD = 0x96d0, CURRENT = 0x537c;

const files = await initFs({ extra: HEADLESS_ARGS });
// A save in the boot file set puts the party in the world for the price of
// three keys. Written after the emulator starts it is a file the game has
// already decided is not there, so it goes in here or not at all.
const savePath = arg("save", "tmp/perf-save.json");
let hasSave = false;
try {
  const kept = JSON.parse(readFileSync(savePath, "utf8"));
  files.unshift({ path: "SAVGAME1", contents: new Uint8Array(kept) });
  hasSave = true;
  say(`booting with ${savePath}`);
} catch {
  say(`no save at ${savePath}: assembling a party instead `
    + "(bun tools/perf_check.js writes one)");
}

// The hooked build, which is where __peek, __poke and __find come from:
// js-dos offers no way into the guest's memory, and this probe is nothing
// without one. tools/fight_probe.js takes the same route.
buildTracedEmulator("/workspace/tmp/view-fsops.json", true, true, "wdosbox-x.js");
const emulators = await loadEmulators();
emulators.wdosboxxJs = TRACED_X_JS;
const ci = await emulators.dosboxXNode(files);
// Kept so a run reports the screen it ended on.
let frame = null;
ci.events().onFrame((rgb) => {
  if (rgb) frame = { rgb: rgb.slice(), w: ci.width(), h: ci.height() };
});
const shot = (name) => {
  if (!frame) return;
  mkdirSync("tmp/view-probe", { recursive: true });
  writeFileSync(`tmp/view-probe/${name}.png`, encodePng(frame.w, frame.h, frame.rgb));
  say(`shot tmp/view-probe/${name}.png`);
};
const press = async (k, after) => { await tap(ci, KEYS[k], 120); await sleep(after); };

// To the menu, the way tmp/write_probe.js and tools/fight_probe.js both get
// there: the splash screens advance on a key, and how many there are depends
// on the build, so they are pressed through rather than waited out.
for (let i = 0; i < 10; i++) {
  await tap(ci, KEYS.esc, 100);
  await tap(ci, KEYS.space, 100);
  await sleep(400);
}
if (hasSave) {
  // Load, off the menu. The party comes with the save, so ENTER THE GAME
  // plays no part; the waits are tmp/write_probe.js's.
  await press("l", 900); await press("1", 3000); await press("y", 16000);
} else {
  await press("a", 4000);
  for (const k of ["6", "7", "8", "9"]) await press(k, 700);
  await press("d", 3000);
  await press("e", 25000);   // 25, not 13: the guest is slower here than under node
  await press("r", 2500);
}

shot("00-after-entering");
const peek16 = (a) => { const b = globalThis.__peek(a, 2); return b[0] | (b[1] << 8); };
const str = (a, n) => String.fromCharCode.apply(null, globalThis.__peek(a, n));
// The executable's image is in memory beside the live segment and carries the
// same strings, so a string alone does not tell them apart. What does is a
// word the game writes and the file does not. tools/fight_probe.js uses
// DS:0x537C, the character whose turn it is, which suits a probe that fights;
// standing in the world that can be zero, so the party's own position is the
// discriminator here: a loaded game has one and the image does not.
const candidates = globalThis.__find("PICTURES.VGA", 32).map((n) => n - PICTURES);
say(`${candidates.length} candidate segment(s)`);
for (const base of candidates) {
  say(`  0x${base.toString(16)}: WORLD.DAT=${str(base + WORLD, 9) === "WORLD.DAT"}`
    + ` turn=0x${peek16(base + CURRENT).toString(16)}`
    + ` x=${peek16(base + PARTY_X)} y=${peek16(base + PARTY_Y)}`
    + ` facing=0x${peek16(base + FACING).toString(16)}`);
}
const override = arg("ds");
const ds = override !== undefined
  ? Number(override)
  : candidates.find((base) => str(base + WORLD, 9) === "WORLD.DAT"
      && [0x8000, 0x4000, 0x2000, 0x1000].includes(peek16(base + FACING))
      && peek16(base + PARTY_X) > 0);
if (ds === undefined) {
  say("no candidate holds a party: is the party in the world? --ds=0x... forces one");
  await ci.exit();
  process.exit(1);
}
say(`data segment at heap 0x${ds.toString(16)}`);

const poke16 = (a, v) => globalThis.__poke(a, [v & 0xff, (v >> 8) & 0xff]);
const where = () => ({
  x: peek16(ds + PARTY_X), y: peek16(ds + PARTY_Y), facing: peek16(ds + FACING),
});

if (arg("x") !== undefined) poke16(ds + PARTY_X, num("x"));
if (arg("y") !== undefined) poke16(ds + PARTY_Y, num("y"));
if (arg("facing") !== undefined) poke16(ds + FACING, Number(arg("facing")));
if (arg("x") !== undefined || arg("y") !== undefined || arg("facing") !== undefined) {
  // The view is rebuilt on a step, not on a poke, so the party is turned full
  // circle to make the game redraw from where it now stands.
  for (const k of ["left", "left", "left", "left"]) await press(k, 700);
}

const at = where();
say(`party at x=${at.x} y=${at.y} facing=0x${at.facing.toString(16)}`);
say(`run parameters at DS:0x${PARAMS.toString(16)}: `
  + RUNS.map((_, i) => `0x${peek16(ds + PARAMS + i * 2).toString(16)}`).join(" "));

const table = globalThis.__peek(ds + VIEW, CELLS * ENTRY);
const rows = [];
let cell = 0;
for (let run = 0; run < RUNS.length; run++) {
  for (let i = 0; i < RUNS[run]; i++, cell++) {
    const at8 = cell * ENTRY;
    const word = (o) => table[at8 + o] | (table[at8 + o + 1] << 8);
    rows.push({
      cell, run,
      bytes: [...table.slice(at8, at8 + ENTRY)],
      draws: word(0), plus2: word(2), plus4: word(4), plus6: word(6),
      skipped: (word(6) & 1) === 1,
    });
  }
}

say("");
say("cell run  +0     +2     +4     +6     skip");
for (const r of rows) {
  say(`${String(r.cell).padStart(4)} ${String(r.run).padStart(3)}  `
    + [r.draws, r.plus2, r.plus4, r.plus6]
      .map((v) => `0x${v.toString(16).padStart(4, "0")}`).join(" ")
    + `  ${r.skipped ? "yes" : ""}`);
}

const json = arg("json");
if (json) {
  mkdirSync(json.replace(/\/[^/]*$/, "") || ".", { recursive: true });
  writeFileSync(json, JSON.stringify({ party: at, runs: RUNS, rows }, null, 1));
  say(`\nwrote ${json}`);
}
await ci.exit();
