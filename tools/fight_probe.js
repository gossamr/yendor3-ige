// Change a creature's record, fight it, and watch what a blow takes off it.
//
//   bun tools/fight_probe.js --resist=0x2000 --blows=4 --how='aaac_'
//
// Reading the code says what a field *should* do. This says what it does. The
// party walks out of the Athaneum to the centipede that waits beyond the gate,
// swings and casts at it, and the creature's health is read straight out of
// the emulator between blows, so a blow's damage is a number, not an
// impression of one.
//
// What makes the reading clean, all of it done to WORLD.DAT before boot:
//
//   * the creature gets 30,000 health, no damage and no accuracy, so the run
//     is as long as it likes and the party is never interrupted;
//   * bits 13-15 of its word 96 are cleared, so no second or third creature
//     joins and fills another buffer;
//   * the party's four stock characters are armed and their combat words
//     forced to 250 accuracy and 100 damage, which puts the resolver at its
//     maximum margin: every swing then lands for the same number, and a
//     halving is visible in one blow rather than in a distribution;
//   * MAGIC ATTACK is made free and heavy, because the party starts with no
//     nuore and could otherwise cast nothing.
//
// `--how` is the keys pressed per round: `a` attack, `c` cast, `_` enter,
// `*` click the first row of a list, `s` shoot. `aaac_` is three swings and a
// spell, which measures both paths at once.
//
// Two traps this fell into, both worth knowing before the next probe:
//
//   * The executable's own image sits in the emulator's memory beside the live
//     data segment and carries the same strings, so an anchor string finds
//     both. The live one is told apart by a *pointer*, DS:0x537C, the
//     character whose turn it is, which is zero in the image on disk.
//   * The game is tactical about time as well as actions: the creature closes
//     while the party stands, so a 64 MB search for that anchor has to happen
//     before the party steps out, not after.
//
// What it measured, per round, against a centipede whose resistance word was
// set to each value in turn:
//
//   resistance   melee    spell   round
//   0x0000        244      124     856
//   0x4000        244      124     856      bit 14 changes nothing
//   0x8000        244      124     856      neither blow is a shot
//   0x2000        244       62     794      bit 13 halves the spell
//   0xFFFF        244       62     794      no bit reaches a melee swing
//
// Not measured: a volley. The centipede is in hand-to-hand by the end of the
// round the party gets on stepping out, and `S` is refused there.
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
const outDir = arg("out", "tmp/fight-probe");
const resist = Number(arg("resist", "0"));
const blows = Number(arg("blows", "12"));
const how = arg("how", "a");            // a attack, s shoot, c cast
const hand = Number(arg("hand", "560"));    // 2-HANDED SWORD +10 by default
const missile = Number(arg("missile", "525"));  // plain CROSSBOW
mkdirSync(outDir, { recursive: true });
const log = join(outDir, "log.txt");
writeFileSync(log, "");
const say = (s) => { console.log(s); appendFileSync(log, s + "\n"); };

// The enemy table: 73 records of 106 bytes; the centipede is record 2.
const ENEMIES = 0x417075, RECORD = 106, CENTIPEDE = 2;
const HEALTH = 30, DAMAGE = 40, ACCURACY = 34, RESISTANCE = 102;
const WORD96 = 96, WORD98 = 98, GROUP = 0xE000;

buildTracedEmulator("/workspace/tmp/fight-fsops.json", true, true, "wdosbox-x.js");
const emulators = await loadEmulators();
emulators.wdosboxxJs = TRACED_X_JS;

const files = await initFs({ extra: HEADLESS_ARGS });
const world = files.find((f) => f.path && f.path.toUpperCase() === "WORLD.DAT");
const rec = ENEMIES + CENTIPEDE * RECORD;
const put = (off, v) => {
  world.contents[rec + off] = v & 0xff;
  world.contents[rec + off + 1] = (v >> 8) & 0xff;
};
const get = (off) => world.contents[rec + off] | (world.contents[rec + off + 1] << 8);
say(`centipede resistance 0x${get(RESISTANCE).toString(16).padStart(4, "0")}`
  + ` -> 0x${resist.toString(16).padStart(4, "0")}`);
put(RESISTANCE, resist);
// A creature with eight health dies in four blows, which is too few readings
// to see a halving in. Give it more health than the run can spend, and take
// its own attack away so the party is never interrupted.
const w98 = arg("w98", "");
if (w98 !== "") {
  say(`centipede word 98 0x${get(WORD98).toString(16)} -> 0x${Number(w98).toString(16)}`);
  put(WORD98, Number(w98));
}
// Bits 13-15 of word 96 let two more of the creature join, which fills the
// other buffers and makes a health reading ambiguous. Clear them: one
// centipede, one buffer, one number to watch.
put(WORD96, get(WORD96) & ~GROUP & 0xffff);
put(HEALTH, 30000);
put(DAMAGE, 0);
put(ACCURACY, 0);

// Arm the four stock characters out of the roster template, all with the same
// weapon so a run measures one kind of blow. A base weapon does 1-2 damage,
// which halves to 0 or 1 and says nothing; forty says it plainly.
const ROSTER = 0x41D72F, SLOT = 500, MISSILE = 0x13A, HAND = 0x142;
// The five combat words the equip dispatch derives; setting them as well as
// the weapon ids keeps the blow big whether or not the dispatch reruns.
const SHOT_ACC = 0x48, SHOT_DMG = 0x4A, HIT_ACC = 0x4C, HIT_DMG = 0x4E;
for (const slot of [6, 7, 8, 9]) {
  const base = ROSTER + slot * SLOT;
  const set = (off, v) => {
    world.contents[base + off] = v & 0xff;
    world.contents[base + off + 1] = (v >> 8) & 0xff;
  };
  set(HAND, hand); set(MISSILE, missile);
  set(HIT_ACC, 250); set(HIT_DMG, 100);
  set(SHOT_ACC, 250); set(SHOT_DMG, 100);
}
say(`party armed: hand=${hand} missile=${missile}, damage forced to 100`);

// MAGIC ATTACK costs two nuore and the party starts with none, so the spell
// list opens and nothing can be cast from it. Make it free and make it hurt.
const SPELLS = 0x41B5BF, SPELL_RECORD = 80;
const MAGIC_ATTACK = 1, SPELL_MP = 24, SPELL_NUORE = 26, SPELL_DAMAGE = 46;
const spell = SPELLS + MAGIC_ATTACK * SPELL_RECORD;
for (const [off, v] of [[SPELL_MP, 0], [SPELL_NUORE, 0], [SPELL_DAMAGE, 200]]) {
  world.contents[spell + off] = v & 0xff;
  world.contents[spell + off + 1] = (v >> 8) & 0xff;
}
say("MAGIC ATTACK: free, 200 damage");

const ci = await emulators.dosboxXNode(files);
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
await tap(ci, A("a"), 120); await sleep(4000);
for (const k of "6789") { await tap(ci, A(k), 120); await sleep(700); }
await tap(ci, A("d"), 120); await sleep(3000);
await tap(ci, A("e"), 120); await sleep(13000);
await tap(ci, A("r"), 120); await sleep(2500);
// Up to the gate and through it, and no further: the creature is a step or
// two beyond, and it gets a move for every one the party spends.
const KEY = { "^": KEYS.up, v: KEYS.down, "<": KEYS.left, ">": KEYS.right, " ": KEYS.space };
for (const m of arg("walk", "<<^^^^^^^^^^^^ ")) {
  await tap(ci, KEY[m], 120); await sleep(1300);
}
shot("00-gate");

const peek16 = (a) => { const b = globalThis.__peek(a, 2); return b[0] | (b[1] << 8); };
const str = (a, n) => String.fromCharCode.apply(null, globalThis.__peek(a, n));
// The data segment, anchored on two strings the game keeps at known offsets in
// it. The engaged-creature buffers and the resolved-damage word are all
// DS-relative, so one anchor addresses the lot.
//
// This reads the whole 64 MB heap and takes seconds, and seconds are a
// resource: the creature closes while the party stands. So it happens *before*
// the party steps out, and the step that meets the creature is the last thing
// before the first blow.
const PICTURES = 0x969E, WORLD = 0x96D0, RESOLVED = 0xF36;
// A creature lives in one of the 80 spawn slots at DS:0x122C while it is out
// on the map, and is copied into one of three engaged buffers when it closes
// to hand-to-hand. A shot is resolved against the slot and a swing against the
// buffer, so a probe that only watched the buffers would see a volley land and
// read no damage anywhere.
const ENGAGED = [0x54B8, 0x5554, 0x55F0];
const SPAWN = 0x122C, SPAWN_SLOTS = 80, CREATURE = 156, RECORD_AT = 0x32;
// The executable's own image is in memory too, and its copy of the data
// segment carries the same strings, so a string is not enough to tell the live
// segment from the file it was loaded out of. What tells them apart is a
// pointer: DS:0x537C holds the character whose turn it is, which is zero in
// the image on disk and never zero once a party is playing.
const CURRENT = 0x537C;
const ds = globalThis.__find("PICTURES.VGA", 32)
  .map((n) => n - PICTURES)
  .find((base) => str(base + WORLD, 9) === "WORLD.DAT" && peek16(base + CURRENT) !== 0);
if (ds === undefined) { say("could not find the data segment"); await ci.exit(); process.exit(1); }
say(`data segment at heap 0x${ds.toString(16)}`);
// Reading eighty-three slots one at a time is that many calls across the
// emulator boundary, and it costs enough time for the creature to close before
// the first shot. Two bulk reads cost nothing: the engaged buffers are
// contiguous, and so is the spawn table.
const REGIONS = [[ENGAGED[0], ENGAGED.length * CREATURE],
                 [SPAWN, SPAWN_SLOTS * CREATURE]];
function creatures() {
  const out = [];
  for (const [start, len] of REGIONS) {
    const buf = globalThis.__peek(ds + start, len);
    for (let at = 0; at + CREATURE <= len; at += CREATURE) {
      const word = (o) => buf[at + o] | (buf[at + o + 1] << 8);
      // A slot or a buffer is occupied when its first word, the object's
      // number, is set. That is the test every walker over either of them
      // makes: image 0x0c56f, 0x10055, 0x125e9 and 0x128cd over the spawn
      // table, 0x01293 over the buffers.
      if (!word(0)) continue;
      const name = String.fromCharCode.apply(
        null, buf.slice(at + RECORD_AT, at + RECORD_AT + 9));
      if (name !== "CENTIPEDE") continue;
      out.push({
        where: start === SPAWN ? "slot" + at / CREATURE : "engaged",
        health: word(0x10),
        resist: word(RECORD_AT + RESISTANCE),
      });
    }
  }
  return out;
}

// Out of the gate and straight at it: one round is all the party gets.
for (const m of arg("engage", "^")) { await tap(ci, KEY[m], 120); await sleep(Number(arg("settle", "400"))); }

let hits = 0, total = 0;
for (let i = 0; i < blows; i++) {
  // Reading before the first blow costs the round the party has: the creature
  // closes while the read happens, and a volley is refused in hand-to-hand.
  // Its health at that point is the one this run set, so take it and shoot.
  const before = i === 0 ? [{ where: "as set", health: 30000, resist }] : creatures();
  for (const k of how) {
    if (k === "*") { await click(ci, 0.18, 0.195); }   // the first row of a list
    else if (k === "_") await tap(ci, KEYS.enter, 120);
    else if (k === "+") await tap(ci, KEYS.down, 120);
    else await tap(ci, A(k), 120);
    await sleep(700);
  }
  // The resolved damage is a scratch word the next blow overwrites, so it has
  // to be caught while it stands rather than read once the round is over.
  let resolved = 0;
  for (let t = 0; t < 40; t++) {
    const v = peek16(ds + RESOLVED);
    if (v > 0 && v < 5000) resolved = v;
    await sleep(55);
  }
  const after = creatures();
  // The same creature shows in two places while it is closing, still in its
  // map slot and already copied into a buffer, so what a blow took is what the
  // lowest reading anywhere went down by.
  const low = (rs) => (rs.length ? Math.min(...rs.map((r) => r.health)) : 0);
  const applied = low(before) - low(after);
  if (applied > 0 && applied < 5000) { hits += 1; total += applied; }
  say(`blow ${String(i).padStart(2, "0")}: resolved=${resolved} applied=${applied}`
    + `  ${after.map((r) => `${r.where}=${r.health}`).join(" ")}`
    + (i === 0 ? `  resist=0x${(after[0] || {}).resist?.toString(16)}` : ""));
  if (i < 3) shot(`blow-${String(i).padStart(2, "0")}`);
}
say(`RESULT resist=0x${resist.toString(16)} how=${how} hits=${hits}/${blows} total=${total}`
  + ` mean=${hits ? (total / hits).toFixed(2) : "-"}`);
await ci.exit();
process.exit(0);
