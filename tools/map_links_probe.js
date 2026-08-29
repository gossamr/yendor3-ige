// Read the map's per-cell event table out of the running game.
//
//   bun tools/map_links_probe.js
//
// The party's world position is DS:0xcf75 (x) and DS:0xcf77 (y), and a door
// sets both. Following what writes them reaches two tables:
//
//   * DS:0xba95, 18-byte destination records, 1-based: x, y, facing, sound,
//     two words, a picture, a gate mask and a flag word. In the executable.
//   * a buffer whose segment is DS:0xff7, the per-cell event table, built at
//     run time and therefore invisible to any search of the files. A column
//     index by world x, then per-column lists of 6-byte records sorted by y.
//
// This reads that buffer, and walks a door with --walk to check the decode
// against the game. Addressing a segment other than DS needs the load segment,
// which is not fixed: it is recovered from the image itself. At image 0x54fc
// the executable holds `mov ax, 0x1ddb`, a relocated word, so the live copy
// of it is DS's own segment, and the load segment is that minus 0x1ddb.
//
// What it read. The buffer is section 28 byte for byte, so the table decodes
// out of the file with nothing fixed up. And:
//
//   bun tools/map_links_probe.js --walk='<<_'
//   party at (460, 46)      the Athaneum, facing north
//   < -> (460, 46)          turn
//   < -> (460, 46)          turn, now facing the exit
//     -> (63, 59)           SPACE, and the party is on Yendor facing south
//
// which is destination record 1 exactly, facing included. A door cell is a
// wall (the Athaneum's exit is terrain 2, object 207) so it is never
// stepped on: SPACE "uses what's in front of you" (README.DOC line 299) and
// that is what fires the door.
import { mkdirSync, writeFileSync, appendFileSync } from "fs";
import { join } from "path";
import { loadEmulators, initFs, HEADLESS_ARGS } from "../cabinet/boot.js";
import { KEYS, tap } from "../cabinet/keys.js";
import { encodePng } from "../cabinet/png.js";
import { buildTracedEmulator, TRACED_JS } from "./trace_fs.js";

const arg = (n, d) => {
  const hit = process.argv.find((a) => a.startsWith(`--${n}=`));
  return hit === undefined ? d : hit.split("=").slice(1).join("=");
};
const outDir = arg("out", "tmp/map-links");
mkdirSync(outDir, { recursive: true });
const log = join(outDir, "log.txt");
writeFileSync(log, "");
const say = (s) => { console.log(s); appendFileSync(log, s + "\n"); };

buildTracedEmulator(join(outDir, "fsops.json"), true, true, "wdosbox.js");
const emulators = await loadEmulators();
emulators.wdosboxJs = TRACED_JS;
const files = await initFs({ extra: HEADLESS_ARGS });
const ci = await emulators.dosboxNode(files);

let frame = null;
ci.events().onFrame((rgb) => {
  if (rgb) frame = { rgb: rgb.slice(), w: ci.width(), h: ci.height() };
});
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const shot = (n) => frame && writeFileSync(join(outDir, `${n}.png`),
  encodePng(frame.w, frame.h, frame.rgb));
const sig = () => {
  if (!frame) return [0, 0, 0, 0];
  const px = frame.rgb; let r = 0, g = 0, b = 0; const seen = new Set();
  for (let i = 0; i < px.length; i += 3) {
    r += px[i]; g += px[i + 1]; b += px[i + 2];
    seen.add((px[i] >> 4 << 8) | (px[i + 1] >> 4 << 4) | (px[i + 2] >> 4));
  }
  const n = px.length / 3; return [r / n | 0, g / n | 0, b / n | 0, seen.size];
};
const atMenu = () => { const c = sig(); return Math.abs(c[0] - 88) <= 6 && Math.abs(c[1] - 78) <= 6 && c[3] < 70; };
const A = (c) => c.toUpperCase().charCodeAt(0);

for (let i = 0; i < 200 && !atMenu(); i++) {
  await tap(ci, KEYS.esc, 100);
  if (atMenu()) break;
  await tap(ci, KEYS.space, 100);
  await sleep(150);
}
say(`menu, sig=${sig()}`);
await tap(ci, A("a"), 120); await sleep(4000);
for (const k of "6789") { await tap(ci, A(k), 120); await sleep(700); }
await tap(ci, A("d"), 120); await sleep(3000);
await tap(ci, A("e"), 120); await sleep(13000);
await tap(ci, A("r"), 120); await sleep(2500);
shot("00-in-world");

const peek = (a, n) => globalThis.__peek(a, n);
const peek16 = (a) => { const b = peek(a, 2); return b[0] | (b[1] << 8); };
const str = (a, n) => String.fromCharCode.apply(null, peek(a, n));

const PICTURES = 0x969E, WORLD = 0x96D0, CURRENT = 0x537C;
const DGROUP_IMAGE = 0x1DDB0, DS_LITERAL_AT = 0x54FC, DS_LITERAL = 0x1DDB;
const PARTY_X = 0xCF75, PARTY_Y = 0xCF77, EVENT_SEG = 0xFF7;
const BOUNDS = { xMax: 0x5498, xMin: 0x549A, yMax: 0x54A0, yMin: 0x54A2 };

const ds = globalThis.__find("PICTURES.VGA", 32)
  .map((n) => n - PICTURES)
  .find((base) => str(base + WORLD, 9) === "WORLD.DAT" && peek16(base + CURRENT) !== 0);
if (ds === undefined) { say("could not find the data segment"); await ci.exit(); process.exit(1); }
const image0 = ds - DGROUP_IMAGE;
const dsSeg = peek16(image0 + DS_LITERAL_AT);
const loadSeg = dsSeg - DS_LITERAL;
const heapOf = (seg) => image0 + (seg - loadSeg) * 16;
say(`data segment heap 0x${ds.toString(16)}, image0 0x${image0.toString(16)},`
  + ` ds segment 0x${dsSeg.toString(16)}, load segment 0x${loadSeg.toString(16)}`);
say(`party at (${peek16(ds + PARTY_X)}, ${peek16(ds + PARTY_Y)})`);
for (const [k, at] of Object.entries(BOUNDS)) say(`  ${k} = ${peek16(ds + at)}`);

// Walk, and read the party's position after every key. A door is decoded from
// two tables that never mention each other, so the check that matters is
// stepping onto one and seeing where the game puts you.
// Cursor keys move and turn; SPACE "uses what's in front of you", which is
// what a door wants: a door cell is a wall, so it can never be stepped on.
const KEY = { "^": KEYS.up, v: KEYS.down, "<": KEYS.left, ">": KEYS.right,
              " ": KEYS.space };
for (const move of arg("walk", "").replace(/_/g, " ")) {
  await tap(ci, KEY[move], 120);
  await sleep(900);
  say(`  ${move} -> (${peek16(ds + PARTY_X)}, ${peek16(ds + PARTY_Y)})`);
}
if (arg("walk", "")) shot("01-walked");

const eventSeg = peek16(ds + EVENT_SEG);
say(`event buffer segment 0x${eventSeg.toString(16)} -> heap 0x${heapOf(eventSeg).toString(16)}`);
const SIZE = Number(arg("size", "26480"));
const buf = peek(heapOf(eventSeg), SIZE);
writeFileSync(join(outDir, "events.bin"), Buffer.from(buf));
say(`wrote ${SIZE} bytes of the event buffer`);

// The destination table, read out of the live image rather than the file, so
// the two can be compared.
writeFileSync(join(outDir, "dgroup.bin"), Buffer.from(peek(ds, 0xD000)));
say("wrote the live data segment");
await ci.exit();
process.exit(0);
