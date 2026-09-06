// Cast a spell in the running game and keep every frame of what it draws.
//
//   bun tools/cast_probe.js --keys=c_1                     # HEAL, on the first character
//   bun tools/cast_probe.js --as="BALL OF FIRE" --keys=c+_ # an area, out of the second row
//
// What a cast draws is read off the dispatcher in docs/spells.md and this is
// what holds those readings to the screen: a renderer driven from those tables
// redraws the animation step by step against a frame kept here and reports the
// best match.
//
// The party knows two spells at the start, HEAL and SLING SHOT, so `--as`
// copies another record over SLING SHOT's: the character still casts the
// second row of its own plate and what runs is the record named. Both are
// freed before boot, since the party starts with no nuore, and the four stock
// characters are hurt so a restorative has something to give back.
//
// The keys are given as a string, one screen kept after each, so the plate's
// own flow can be read off the shots rather than guessed at: `c` opens it,
// `+` and `-` walk it, `_` takes the row it is on, and `1` to `4` click a
// portrait. The frames after the last key are `fNN`, 60 ms apart, which is
// where the animation itself shows; `--settle` is how long each key before
// them is given, so a run watching a blow land can cut it to nothing.
//
// `--walk` takes the party somewhere first, one key per character of
// `^v<>` and a space, which is the way out of the Athaneum and up to the
// centipede beyond the gate that tools/fight_probe.js measures against:
//
//   bun tools/cast_probe.js --walk="<<^^^^^^^^^^^^ " --keys=a --settle=0
//
// `--at=x,y,facing` pokes the party there instead, which is how a fight with a
// particular monster is reached: the maps stand three thieves in a column at
// 486,57 to 486,59, so `--at=486,55,0x4000 --walk="^^"` walks into them.
//
// What it measured with HEAL: entry 18's `+2`, which is run 7's picture 2, on
// the first portrait, 39 of its 45 opaque pixels exact against the file's own
// palette. The six left are the mouse cursor, which the click that picks the
// target leaves sitting on that portrait, and the other three portraits take
// nothing. Four of the twenty frames hold the picture at all, 60 ms apart: f02
// and f03 at the file's own indices, and f00 and f01 with indices 208 and up
// rotated down one inside each four-color block, which is a palette cycle
// running on that ramp.
import { mkdirSync, writeFileSync, appendFileSync } from "fs";
import { join } from "path";
import { loadEmulators, initFs, HEADLESS_ARGS } from "../cabinet/boot.js";
import { KEYS, tap, click } from "../cabinet/keys.js";
import { encodePng } from "../cabinet/png.js";
import { buildTracedEmulator, TRACED_X_JS } from "./trace_fs.js";

const arg = (n, d) => {
  const hit = process.argv.find((a) => a.startsWith(`--${n}=`));
  return hit === undefined ? d : hit.split("=").slice(1).join("=");
};
const outDir = arg("out", "tmp/cast-probe");
mkdirSync(outDir, { recursive: true });
const log = join(outDir, "log.txt");
writeFileSync(log, "");
const say = (s) => { console.log(s); appendFileSync(log, s + "\n"); };

buildTracedEmulator("/workspace/tmp/heal-fsops.json", true, true, "wdosbox-x.js");
const emulators = await loadEmulators();
emulators.wdosboxxJs = TRACED_X_JS;
const files = await initFs({ extra: HEADLESS_ARGS });
const world = files.find((f) => f.path && f.path.toUpperCase() === "WORLD.DAT");

// What the stock party knows between them: HEAL on every plate's first row,
// and MAGIC ATTACK or SLING SHOT on the second, by the character. Free all
// three, and drop the four characters' health so a restorative has something
// to restore.
const SPELLS = 0x41B5BF, SPELL_RECORD = 80, HEAL = 0, SLING_SHOT = 2;
const KNOWN = [HEAL, 1, SLING_SHOT];
const SPELL_NAME = 21, SPELL_MP = 24, SPELL_NUORE = 26;
const put = (at, v) => {
  world.contents[at] = v & 0xff;
  world.contents[at + 1] = (v >> 8) & 0xff;
};
const record = (n) => SPELLS + n * SPELL_RECORD;
const nameOf = (n) => String.fromCharCode(
  ...world.contents.slice(record(n), record(n) + SPELL_NAME)).split("\0")[0].trim();
// A record copied over one of those, name and all, is cast by pressing that
// row: the character's own book holds spell numbers, not records. `--over`
// picks which, since the second row is MAGIC ATTACK on some plates and SLING
// SHOT on others.
const as = arg("as", "");
const over = Number(arg("over", String(SLING_SHOT)));
if (as !== "") {
  const from = [...Array(107).keys()].find((n) => nameOf(n) === as.toUpperCase());
  if (from === undefined) { say(`no spell named ${as}`); process.exit(1); }
  const was = nameOf(over);
  world.contents.copyWithin(record(over), record(from), record(from) + SPELL_RECORD);
  say(`${as.toUpperCase()} (record ${from}) copied over ${was}'s`);
}
for (const n of KNOWN) {
  for (const off of [SPELL_MP, SPELL_NUORE]) put(record(n) + off, 0);
}
const ROSTER = 0x41D72F, SLOT = 500, LIVE_HEALTH = 0x60;
for (const slot of [6, 7, 8, 9]) put(ROSTER + slot * SLOT + LIVE_HEALTH, 3);

// The centipede beyond the gate, softened the way tools/fight_probe.js
// softens it: health it cannot spend, nothing to turn a blow aside with and
// no blow of its own. What that buys is certainty -- every swing and every
// cast lands, so the frame a splat is drawn on is in every run rather than in
// the lucky ones.
const ENEMIES = 0x417075, ENEMY_RECORD = 106;
const ENEMY_HEALTH = 30, ENEMY_ACCURACY = 34, ENEMY_ABSORB = 38, ENEMY_DAMAGE = 40;
const ENEMY_WORD98 = 98, ENEMY_FREQUENCY = 0x1E00, ENEMY_ALWAYS = 0x1000;
// A name occupies two 13-byte fields so a two-word one fits (tools/extract.py).
const enemyName = (n) => {
  const at = ENEMIES + n * ENEMY_RECORD;
  const part = (from, len) => String.fromCharCode(
    ...world.contents.slice(at + from, at + from + len)).split("\0")[0].trim();
  return [part(0, 13), part(13, 13)].filter(Boolean).join(" ");
};
// Which monster stands outside the Athaneum, since the road there is the one
// this probe walks: `--monster="SCORPION over CENTIPEDE"` copies the first
// record over the second, name and all, so the spawn on that cell draws and
// fights as the first. What it buys is any monster's own splat pair without a
// road to wherever that monster stands.
const swap = arg("monster", "");
if (swap !== "") {
  const [want, over] = swap.toUpperCase().split(" OVER ");
  const named = (n) => [...Array(73).keys()].find((i) => enemyName(i) === n);
  const from = named(want), to = named(over ?? "CENTIPEDE");
  if (from === undefined || to === undefined) {
    say(`no monster named ${from === undefined ? want : over}`);
    process.exit(1);
  }
  world.contents.copyWithin(ENEMIES + to * ENEMY_RECORD,
    ENEMIES + from * ENEMY_RECORD, ENEMIES + (from + 1) * ENEMY_RECORD);
  say(`${want} (record ${from}) copied over record ${to}`);
}
const soften = arg("soften", "");
if (soften !== "") {
  const n = [...Array(73).keys()].find((i) => enemyName(i) === soften.toUpperCase());
  if (n === undefined) { say(`no monster named ${soften}`); process.exit(1); }
  const enemy = ENEMIES + n * ENEMY_RECORD;
  put(enemy + ENEMY_HEALTH, 30000);
  put(enemy + ENEMY_ABSORB, 0);
  put(enemy + ENEMY_ACCURACY, 0);
  put(enemy + ENEMY_DAMAGE, 0);
  // Word 98 bits 9 to 12 are how often the monster engages once it has closed,
  // 90 percent at bit 12 and 5 where none is set (image 0x129F8). Most records
  // set none, which is one roll in twenty per pass of the hourly walk, so a
  // run that wants a fight waits through rest after rest. Bit 12 takes that to
  // nine in ten.
  const was98 = world.contents[enemy + ENEMY_WORD98]
    | (world.contents[enemy + ENEMY_WORD98 + 1] << 8);
  put(enemy + ENEMY_WORD98, (was98 & ~ENEMY_FREQUENCY) | ENEMY_ALWAYS);
  say(`${soften.toUpperCase()}, record ${n}: 30,000 health, no absorption,`
    + " no blow of its own, engages nine times in ten");
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

// Where to stand, poked rather than walked. The three words are the ones
// tools/view_probe.js pokes, and the data segment is found the way
// tools/fight_probe.js finds it: on a string, with a pointer that is zero in
// the executable's own image to tell the live segment from the copy of it the
// loader left in the heap.
//
// The view is rebuilt on a step rather than on a poke, and the game seats the
// monsters of a page as it loads one, so a poke is followed by a step: that is
// what makes the monsters standing there stand up.
const FACING = 0xcf73, PARTY_X = 0xcf75, PARTY_Y = 0xcf77;
const PICTURES = 0x969e, WORLD_STR = 0x96d0, CURRENT = 0x537c;
const at_ = arg("at", "");
let ds;
{
  const peek16 = (a) => { const b = globalThis.__peek(a, 2); return b[0] | (b[1] << 8); };
  const str = (a, n) => String.fromCharCode.apply(null, globalThis.__peek(a, n));
  ds = globalThis.__find("PICTURES.VGA", 32)
    .map((n) => n - PICTURES)
    .find((base) => str(base + WORLD_STR, 9) === "WORLD.DAT" && peek16(base + CURRENT) !== 0);
  if (ds === undefined) say("could not find the data segment");
}
if (at_ !== "" && ds !== undefined) {
  const [x, y, facing] = at_.split(",").map(Number);
  const poke16 = (a, v) => globalThis.__poke(a, [v & 0xff, (v >> 8) & 0xff]);
  poke16(ds + PARTY_X, x);
  poke16(ds + PARTY_Y, y);
  poke16(ds + FACING, facing);
  // The view is rebuilt on a step rather than on a poke, so the party is
  // turned full circle to make the game redraw from where it now stands,
  // which is what tools/view_probe.js does with the same three words.
  for (let turn = 0; turn < 4; turn++) { await tap(ci, KEYS.left, 120); await sleep(250); }
  say(`party poked to ${x},${y} facing 0x${facing.toString(16)}`);
  shot("01-poked");
}

// Somewhere to stand, before anything is cast: one key per character, at the
// pace tools/fight_probe.js walks the same road at.
const WALK = { "^": KEYS.up, v: KEYS.down, "<": KEYS.left, ">": KEYS.right, " ": KEYS.space };
for (const m of arg("walk", "")) {
  await tap(ci, WALK[m], 120);
  await sleep(Number(arg("step", "1300")));
}
if (arg("walk", "")) shot("01-walked");

// Three monsters in hand to hand, seated by hand.
//
// A fight is hard to stage on purpose: a monster closes on the hourly pass and
// rolls its own frequency to engage, so a run that wants two or three in the
// three places waits on luck. The draw does not care how they got there. It
// walks the three buffers at DS:0x54B8, 0x5554 and 0x55F0, draws each through
// the table its buffer index names, and lays a splat where the monster's state
// word carries bit 3 (docs/pictures.md). So `--melee` copies a live monster
// out of its spawn slot into as many buffers as asked, sets DS:0x5370's
// hand-to-hand bit, and marks each one struck: bits 1 and 3 of `+0x0C`, and
// the rung bit of `+0x0E` the ladder would have set.
//
// What that buys is a frame with a splat in every place at once, which is what
// a renderer driven from that table holds the six corners to.
const MELEE_BIT = 0x1000, STATE = 0x5370;
const SPAWN = 0x122c, SPAWN_SLOTS = 80, MONSTER = 156;
const BUFFERS = [0x54b8, 0x5554, 0x55f0];
const STRUCK_BITS = 0x0a, RUNG_AT = 0x0e, RUNG_LIGHT = 0x8000, RECORD_IN = 0x32;
// The drawing mode is the monster's own, at `+0x0A`: image 0x126A8 writes 10
// where word 96 bit 0 is set and 13 where it is clear, which is the middle of
// each run's three places, and the two either side are one below and one
// above. The draw at image 0x107CE walks the three buffers and takes each
// monster's mode from its own struct, so a copy seated by hand carries the
// middle until this is set.
const MODE_AT = 0x0a;
const melee = Number(arg("melee", "0"));
if (melee > 0 && ds !== undefined) {
  const peek16 = (a) => { const b = globalThis.__peek(a, 2); return b[0] | (b[1] << 8); };
  const poke16 = (a, v) => globalThis.__poke(a, [v & 0xff, (v >> 8) & 0xff]);
  let from = -1;
  for (let slot = 0; slot < SPAWN_SLOTS; slot++) {
    if (peek16(ds + SPAWN + slot * MONSTER)) { from = slot; break; }
  }
  if (from < 0) say("no monster stands on this page");
  else {
    const live = globalThis.__peek(ds + SPAWN + from * MONSTER, MONSTER);
    const name = String.fromCharCode
      .apply(null, live.slice(RECORD_IN, RECORD_IN + 13)).split("\0")[0].trim();
    const middle = live[MODE_AT] | (live[MODE_AT + 1] << 8);
    for (let place = 0; place < melee && place < BUFFERS.length; place++) {
      globalThis.__poke(ds + BUFFERS[place], [...live]);
      poke16(ds + BUFFERS[place] + MODE_AT, middle - 1 + place);
      poke16(ds + BUFFERS[place] + 0x0c, (live[0x0c] | (live[0x0d] << 8)) | STRUCK_BITS);
      poke16(ds + BUFFERS[place] + RUNG_AT, RUNG_LIGHT);
    }
    poke16(ds + STATE, peek16(ds + STATE) | MELEE_BIT);
    say(`${melee} x ${name} seated from slot ${from}, modes `
      + `${middle - 1} to ${middle + melee - 2}, each struck`);
  }
}

// Every key of `--keys`, with the screen kept after each so the plate's own
// flow can be read off the shots rather than guessed at.
//   c cast   _ enter   + down   - up   < > turn   * click the first row
//   1..4 a portrait
const PORTRAIT = [[0.094, 0.82], [0.244, 0.82], [0.394, 0.82], [0.544, 0.82]];
const settle = Number(arg("settle", "600"));
const keys = arg("keys", "c");
let step = 1;
for (const [at, k] of [...keys].entries()) {
  step += 1;
  if (k === "*") await click(ci, 0.18, 0.195);
  else if (k === "_") await tap(ci, KEYS.enter, 120);
  else if (k === "+") await tap(ci, KEYS.down, 120);
  else if (k === "-") await tap(ci, KEYS.up, 120);
  else if (k === "<") await tap(ci, KEYS.left, 120);
  else if (k === ">") await tap(ci, KEYS.right, 120);
  else if ("1234".includes(k)) await click(ci, ...PORTRAIT[Number(k) - 1]);
  else await tap(ci, A(k), 120);
  say(`key ${k}`);
  // The last key is the one that spends the turn, and what it draws starts at
  // once, so the frames below begin on it rather than after a settle.
  if (at === keys.length - 1) break;
  await sleep(settle);
  shot(`${String(step).padStart(2, "0")}-after-${k === "_" ? "enter" : k}`);
}

// What is engaged, out of the three buffers at DS:0x54B8, 0x5554 and 0x55F0,
// which is what says whether a run reached a fight at all and which place each
// monster took. A buffer whose first word is zero is empty (image 0x01293).
if (ds !== undefined) {
  const ENGAGED = [0x54b8, 0x5554, 0x55f0], RECORD_AT = 0x32, MONSTER = 156;
  const peek16 = (a) => { const b = globalThis.__peek(a, 2); return b[0] | (b[1] << 8); };
  ENGAGED.forEach((at, place) => {
    if (!peek16(ds + at)) { say(`place ${place}: empty`); return; }
    const name = String.fromCharCode
      .apply(null, globalThis.__peek(ds + at + RECORD_AT, 13)).split("\0")[0].trim();
    say(`place ${place}: ${name}, health ${peek16(ds + at + 0x10)}`);
  });
}

// An animation holds for a few tenths of a second, so the frames right after
// the last key are where it shows. One every 60 ms, `--frames` of them.
//
// A seated monster's struck bit is cleared by the draw that lays its splat
// down, and the game redraws only on an event, so under `--melee` each frame
// is a fresh mark and a turn to draw it.
//
// One place per frame, in turn. The splat is laid inside the monster's own
// draw and the three are drawn in order, so a place marked alongside a later
// one has its splat painted over by that monster's body: only the last of
// them survives whole. Marked one at a time, each comes out untouched.
for (let i = 0; i < Number(arg("frames", "20")); i++) {
  if (melee > 0 && ds !== undefined) {
    const poke16 = (a, v) => globalThis.__poke(a, [v & 0xff, (v >> 8) & 0xff]);
    const peek16 = (a) => { const b = globalThis.__peek(a, 2); return b[0] | (b[1] << 8); };
    const place = i % Math.min(melee, BUFFERS.length);
    poke16(ds + BUFFERS[place] + 0x0c, peek16(ds + BUFFERS[place] + 0x0c) | STRUCK_BITS);
    poke16(ds + BUFFERS[place] + RUNG_AT, RUNG_LIGHT);
    await tap(ci, KEYS.left, 60);
  }
  await sleep(60);
  shot(`f${String(i).padStart(2, "0")}`);
}
say(`wrote ${outDir}`);
await ci.exit();
process.exit(0);
