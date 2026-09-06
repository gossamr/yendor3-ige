// Dress the four stock characters and keep a shot of each paper doll.
//
//   bun tools/doll_probe.js --wear=head=LEATHER HELMET,body=ROBES
//   bun tools/doll_probe.js --wear=body=CLOTHES --who=1,3
//
// The doll is the character's own body with a picture per worn slot over it,
// and a head piece and a body piece are both drawn straight onto the stone
// plate the figure stands in (docs/items.md). What this holds to the screen is
// the subtraction that takes that plate off. An exporter that cuts the stone
// and redraws the pieces on a plate of its own has to leave each piece whole,
// and a shot of the game's own sheet is what says whether it did.
//
// `--wear` names a slot and an item for all four characters, written into
// WORLD.DAT's roster before the game reads it rather than bought in a shop.
// The slots are the ten the record carries, `missile container hand shield
// ring ring2 head body feet hands`, and one left out keeps what the character
// ships with. `--two-handed` sets the flag the game's own equip sets, which
// moves the weapon onto the figure. `--who` picks which inventory panels are
// opened, 1 to 4, and each is kept as `NN-<name>.png`.
import { mkdirSync, writeFileSync, appendFileSync } from "fs";
import { join } from "path";
import { loadEmulators, initFs, HEADLESS_ARGS } from "../cabinet/boot.js";
import { KEYS, BUTTONS, tap, click } from "../cabinet/keys.js";
import { encodePng } from "../cabinet/png.js";
import { buildTracedEmulator, TRACED_X_JS } from "./trace_fs.js";

const arg = (n, d) => {
  const hit = process.argv.find((a) => a.startsWith(`--${n}=`));
  return hit === undefined ? d : hit.split("=").slice(1).join("=");
};
const outDir = arg("out", "tmp/doll-probe");
mkdirSync(outDir, { recursive: true });
const log = join(outDir, "log.txt");
writeFileSync(log, "");
const say = (s) => { console.log(s); appendFileSync(log, s + "\n"); };

buildTracedEmulator("/workspace/tmp/doll-fsops.json", true, true, "wdosbox-x.js");
const emulators = await loadEmulators();
emulators.wdosboxxJs = TRACED_X_JS;
const files = await initFs({ extra: HEADLESS_ARGS });
const world = files.find((f) => f.path && f.path.toUpperCase() === "WORLD.DAT");

// What the four stock characters carry. The ten slot words are the character
// record's own and the shipped party is roster slots 6 to 9 (docs/saves.md).
// Four of the ten wear a picture on the figure and the other six draw an icon
// in a box beside it (docs/items.md).
const ROSTER = 0x41D72F, SLOT = 500, RECORD_NAME = 0, RECORD_NAME_LEN = 13;
const WORN_AT = {
  missile: 314, container: 318, hand: 322, shield: 326, ring: 330, ring2: 334,
  head: 338, body: 340, feet: 344, hands: 346,
};
const PARTY = [6, 7, 8, 9];
// The character's own flag word, whose bit 0x20 image 0x06568 sets as a
// two-handed weapon is equipped. The doll reads it rather than the item, so a
// weapon poked straight into the hand slot needs it set by hand: image
// 0x16101 draws the weapon over the shield's box where it is set, and image
// 0x160ca skips the container's icon.
const FLAGS_AT = 348, TWO_HANDED = 0x20;
const ITEMS = 0x83EE8, ITEM_RECORD = 58, ITEM_COUNT = 631;
const put = (at, v) => {
  world.contents[at] = v & 0xff;
  world.contents[at + 1] = (v >> 8) & 0xff;
};
// The game has no apostrophe glyph and holds one as `~`, so KNIGHT'S POLE is
// stored "KNIGHT~S POLE" (tools/labels.py).
const textAt = (at, n) => String.fromCharCode(...world.contents.slice(at, at + n))
  .split("\0")[0].replace(/[~`]/g, "'").replace(/\\/g, "/").trim();
// An item's name runs across three 13-byte fields at the record's own +19, so
// LEATHER HELMET is held as "LEATHER" and "HELMET" (tools/items.py). Ids run
// from 1, so record n sits n - 1 records in.
const ITEM_FIELDS = 19, ITEM_NAME_LEN = 13, ITEM_NAME_FIELDS = 3;
const itemName = (n) => {
  const at = ITEMS + (n - 1) * ITEM_RECORD + ITEM_FIELDS;
  return [...Array(ITEM_NAME_FIELDS).keys()]
    .map((k) => textAt(at + k * ITEM_NAME_LEN, ITEM_NAME_LEN - 1))
    .filter(Boolean).join(" ");
};
const itemNamed = (want) => {
  for (let n = 1; n <= ITEM_COUNT; n++) if (itemName(n) === want) return n;
  return 0;
};
for (const pair of arg("wear", "").split(",").filter(Boolean)) {
  const [slot, want] = pair.split("=");
  if (!WORN_AT[slot]) { say(`no slot named ${slot}`); continue; }
  const id = itemNamed((want ?? "").toUpperCase());
  if (!id) { say(`no item named ${want}`); continue; }
  for (const who of PARTY) put(ROSTER + who * SLOT + WORN_AT[slot], id);
  say(`all four wear ${want.toUpperCase()}, item ${id}, in the ${slot} slot`);
}
if (arg("two-handed", null) !== null) {
  for (const who of PARTY) {
    const at = ROSTER + who * SLOT + FLAGS_AT;
    put(at, (world.contents[at] | (world.contents[at + 1] << 8)) | TWO_HANDED);
  }
  say("all four hold their hand weapon in both hands");
}

const ci = await emulators.dosboxXNode(files);
let frame = null;
ci.events().onFrame((rgb) => {
  if (rgb) frame = { rgb: rgb.slice(), w: ci.width(), h: ci.height() };
});
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const shot = (n) => frame && writeFileSync(join(outDir, `${n}.png`),
  encodePng(frame.w, frame.h, frame.rgb));
// The main menu, by its own color: the boot is a sequence of screens and this
// is what says the game has settled on one this run can drive.
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

// Past the attract loop and into the world with the four stock characters,
// which is tools/fight_probe.js's own way in.
for (let i = 0; i < 200 && !atMenu(); i++) {
  await tap(ci, KEYS.esc, 100);
  if (atMenu()) break;
  await tap(ci, KEYS.space, 100);
  await sleep(150);
}
await tap(ci, A("a"), 120); await sleep(4000);
for (const k of "6789") { await tap(ci, A(k), 120); await sleep(700); }
await tap(ci, A("d"), 120); await sleep(3000);
await tap(ci, A("e"), 120); await sleep(13000);
await tap(ci, A("r"), 120); await sleep(2500);
shot("00-world");

// The doll is on the inventory panel rather than on the stats sheet F1 opens,
// and a right click on a portrait is what raises it (docs/running.md). A
// second right click puts it away, so the next one opens on a clear screen.
const PORTRAIT = [[0.094, 0.82], [0.244, 0.82], [0.394, 0.82], [0.544, 0.82]];
const settle = Number(arg("settle", "1200"));
for (const digit of arg("who", "1,2,3,4").split(",").filter(Boolean)) {
  const who = Number(digit);
  if (!PORTRAIT[who - 1]) { say(`no character ${digit}`); continue; }
  const name = textAt(ROSTER + PARTY[who - 1] * SLOT + RECORD_NAME, RECORD_NAME_LEN);
  await click(ci, ...PORTRAIT[who - 1], BUTTONS.right);
  await sleep(settle);
  shot(`${String(who).padStart(2, "0")}-${name.toLowerCase() || who}`);
  say(`inventory ${who}: ${name}`);
  await click(ci, ...PORTRAIT[who - 1], BUTTONS.right);
  await sleep(400);
}
say(`wrote ${outDir}`);
await ci.exit();
process.exit(0);
