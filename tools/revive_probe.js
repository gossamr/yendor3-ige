// Cast a restorative on a dead party member and watch the condition word.
//
//   bun tools/revive_probe.js --spell=13     # FEET OF FEATHERS
//   bun tools/revive_probe.js --spell=99     # RESURRECT, the control
//   bun tools/revive_probe.js --spell=1      # HEAL, the negative control
//
// docs/spells.md reads record 40 as a mask ANDed into the character's
// condition word at `0x03830`. FEET OF FEATHERS and ARMS OF GIANTS carry a
// mask of zero, so each of them clears the whole word, the dead bit included,
// and the target stops being dead. What four runs read back:
//
//   spell               MP spent   mask     condition word   rest
//   HEAL                       3   0xffff   0x0040 stands    0 health
//   FEET OF FEATHERS          19   0x0000   0x0040 -> 0      13 of 13
//   ARMS OF GIANTS            55   0x0000   0x0040 -> 0      13 of 13
//   RESURRECT                400   0xffbf   0x0040 -> 0      13 of 13
//
// Every MP figure is the spell's own record 24, so every row is a cast that
// happened. FEET OF FEATHERS also moved the target's dexterity 59 -> 64, its
// record 34 into the field its record 36 names.
//
// Four things about the interface that a run has to get right:
//
//   * the four party picks assemble on their own, so the `d` that follows
//     them opens the disk panel over the map and swallows everything after
//     it until the panel is closed;
//   * the first keypress after that is swallowed too, so C is pressed until
//     the list is actually standing;
//   * a click lands about 18 pixels below where it is asked for, so the one
//     row of the list is found by trying a band rather than by aiming;
//   * resting asks DO YOU WANT TO REST NOW, and a party with no food rests
//     for eight hours and recovers nothing, so the party is given food.
//
// Nothing is done to the spell records. What is set up, all of it before boot
// except the kill:
//
//   * DIANA's magic pool is zeroed, so the caster picker at image 0xd17c
//     walks past her to YENDOR, who is the Mage;
//   * YENDOR is put at level 6 with one spell bit set, so the cast list has
//     exactly one row and no menu has to be navigated;
//   * YENDOR gets 500 magic points and the party 9,999 nuore, so cost is
//     never what stops a cast;
//   * SQUIRE is killed after boot by poking health to 0 and condition bit
//     0x40, which is the state image 0x03745 leaves a character in.
//
// The spell's own record 32, 34, 36, 38 and 40 are untouched, and those five
// are what is under test.
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
const outDir = arg("out", "tmp/revive-probe");
const spellNo = Number(arg("spell", "13"));   // 1-based, as the bitmap counts
mkdirSync(outDir, { recursive: true });
const log = join(outDir, `log-${spellNo}.txt`);
writeFileSync(log, "");
const say = (s) => { console.log(s); appendFileSync(log, s + "\n"); };

// The roster template: ten 500-byte slots, the last four the shipped party.
// docs/saves.md has the displacements; the live block starts at 60 and the
// maximum block at 124, so health is 82 and 146 and magic is 84 and 148.
const ROSTER = 0x41D72F, SLOT = 500;
const LEVEL = 22, COND = 28, DEX = 62, HEALTH = 82, MAGIC = 84;
const MAX_HEALTH = 146, MAX_MAGIC = 148, SPELLBITS = 202, NUORE = 188;
const SQUIRE = 6, DIANA = 7, YENDOR = 8;

// Spell n lives in word (n-1)/16 of the bitmap, most significant bit first.
// Image 0x17b27 is the arithmetic: divide by 16, index by the quotient, and
// shift 0x8000 right by the remainder less one, with a remainder of zero
// meaning the last bit of the word before.
const spellWord = (n) => (n % 16 === 0 ? n / 16 - 1 : (n / 16) | 0);
const spellMask = (n) => 0x8000 >>> ((n % 16 === 0 ? 16 : n % 16) - 1);

buildTracedEmulator("/workspace/tmp/revive-fsops.json", true, true, "wdosbox-x.js");
const emulators = await loadEmulators();
emulators.wdosboxxJs = TRACED_X_JS;
const files = await initFs({ extra: HEADLESS_ARGS });
const world = files.find((f) => f.path && f.path.toUpperCase() === "WORLD.DAT");
const at = (slot, off) => ROSTER + slot * SLOT + off;
const put = (a, v) => {
  world.contents[a] = v & 0xff;
  world.contents[a + 1] = (v >> 8) & 0xff;
};
const got = (a) => world.contents[a] | (world.contents[a + 1] << 8);

put(at(DIANA, MAGIC), 0); put(at(DIANA, MAX_MAGIC), 0);
put(at(YENDOR, LEVEL), 6);
put(at(YENDOR, MAGIC), 500); put(at(YENDOR, MAX_MAGIC), 500);
for (let w = 0; w < 7; w++) put(at(YENDOR, SPELLBITS + 2 * w), 0);
put(at(YENDOR, SPELLBITS + 2 * spellWord(spellNo)), spellMask(spellNo));
say(`YENDOR: level 6, magic 500, one spell bit -- number ${spellNo},`
  + ` word ${spellWord(spellNo)} mask 0x${spellMask(spellNo).toString(16)}`);
// Nuore and food are party-wide and packed BCD, most significant byte first.
// A rest with no food passes the hours and restores nothing, so the food
// matters as much as the nuore does.
const FOOD = 184;
for (const [i, b] of [0x00, 0x00, 0x99, 0x99].entries()) {
  world.contents[ROSTER + NUORE + i] = b;
  world.contents[ROSTER + FOOD + i] = b;
}
say("party nuore -> 9,999, food -> 9,999");

const ci = await emulators.dosboxXNode(files);
let frame = null;
ci.events().onFrame((rgb) => {
  if (rgb) frame = { rgb: rgb.slice(), w: ci.width(), h: ci.height() };
});
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const shot = (n) => frame && writeFileSync(join(outDir, `${spellNo}-${n}.png`),
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
const atMenu = () => {
  const c = sig();
  return Math.abs(c[0] - 88) <= 6 && Math.abs(c[1] - 78) <= 6 && c[3] < 70;
};
const A = (c) => c.toUpperCase().charCodeAt(0);

for (let i = 0; i < 200 && !atMenu(); i++) {
  await tap(ci, KEYS.esc, 100);
  if (atMenu()) break;
  await tap(ci, KEYS.space, 100);
  await sleep(150);
}
await tap(ci, A("a"), 120); await sleep(4000);
for (const k of "6789") { await tap(ci, A(k), 120); await sleep(700); }
shot("00a-after-picks");
await tap(ci, A("d"), 120); await sleep(3000);
shot("00b-after-d");
await tap(ci, A("e"), 120); await sleep(13000);
shot("00c-after-e");
// The four picks assemble the party on their own, so `d` lands on the map
// dispatcher rather than on a DONE button and opens the disk panel over the
// map (image 0x566). Everything pressed after that goes into the panel. RETURN
// closes it; ESC is pressed as well because a panel that is already closed
// ignores both.
for (let i = 0; i < 4; i++) {
  await click(ci, 0.578, 0.603); await sleep(400);
  await tap(ci, KEYS.esc, 120); await sleep(400);
}
shot("00-on-the-map");

// The data segment, told apart from the executable's own image on the heap by
// a pointer rather than by a string: DS:0x537C is the character whose turn it
// is, zero in the copy on disk (tools/fight_probe.js has the trap).
const PICTURES = 0x969E, WORLD_STR = 0x96D0, CURRENT = 0x537C;
const ROSTER_DS = 0xCEDD;
const peek16 = (a) => { const b = globalThis.__peek(a, 2); return b[0] | (b[1] << 8); };
const poke16 = (a, v) => globalThis.__poke(a, [v & 0xff, (v >> 8) & 0xff]);
const str = (a, n) => String.fromCharCode.apply(null, globalThis.__peek(a, n));
const ds = globalThis.__find("PICTURES.VGA", 32)
  .map((n) => n - PICTURES)
  .find((base) => str(base + WORLD_STR, 9) === "WORLD.DAT" && peek16(base + CURRENT) !== 0);
if (ds === undefined) { say("could not find the data segment"); await ci.exit(); process.exit(1); }
say(`data segment at heap 0x${ds.toString(16)}`);

const slotAt = (slot) => ds + ROSTER_DS + slot * SLOT;
const read = (slot) => {
  const b = slotAt(slot);
  return {
    name: str(b, 14).split("\0")[0],
    level: peek16(b + LEVEL),
    cond: peek16(b + COND),
    dex: peek16(b + DEX),
    health: peek16(b + HEALTH),
    maxHealth: peek16(b + MAX_HEALTH),
    magic: peek16(b + MAGIC),
  };
};
const show = (tag) => {
  for (const slot of [SQUIRE, DIANA, YENDOR, 9]) {
    const c = read(slot);
    say(`  ${tag} ${c.name.padEnd(11)} lvl ${String(c.level).padStart(2)}`
      + ` cond 0x${c.cond.toString(16).padStart(4, "0")}`
      + ` hp ${String(c.health).padStart(4)}/${c.maxHealth}`
      + ` mp ${String(c.magic).padStart(4)} dex ${c.dex}`);
  }
};
say("as the party enters:"); show("   ");

// Kill SQUIRE the way image 0x03745 does: health to zero, condition bit 0x40.
poke16(slotAt(SQUIRE) + HEALTH, 0);
poke16(slotAt(SQUIRE) + COND, 0x40);
say("SQUIRE killed: health 0, condition 0x0040");
const before = read(SQUIRE);
say("before the cast:"); show("   ");
shot("01-squire-dead");

// C opens the cast flow. Out of hand-to-hand the caster is picked for you, by
// image 0xd17c, which takes the first party member with a magic pool. DIANA's
// is zeroed above, so it is YENDOR. One spell bit means one row in the list.
const HANDLES = 0xd0c9;
for (let i = 0; i < 4; i++) {
  const h = peek16(ds + HANDLES + 2 * i);
  say(`  handle ${i}: slot ${h}`
    + `  max magic ${h ? peek16(ds + ROSTER_DS + h * SLOT + MAX_MAGIC) : -1}`);
}
const rows = () => peek16(ds + 0x5dfc);
const state = (tag) => say(`  ${tag}: [0x53d4]=0x${peek16(ds + 0x53d4).toString(16)}`
  + ` [0x537c]=0x${peek16(ds + CURRENT).toString(16)} rows=${rows()}`);

// F3 makes YENDOR the character the panel belongs to. Image 0x59fd maps F1 to
// F4 onto the four handles at DS:0xd0c9, in the order the party was assembled.
await tap(ci, KEYS.f3, 160); await sleep(800); state("after F3");

// The first keypress after the disk panel closes is swallowed, so press C
// until the list is actually standing. One spell bit means one row.
for (let i = 0; i < 5 && rows() === 0; i++) {
  await tap(ci, A("c"), 90); await sleep(1200);
}
state("cast panel");
shot("02-cast-panel");
if (rows() !== 1) { say("the spell list did not open"); await ci.exit(); process.exit(1); }

// Take the one row. The cursor drawn after a click sits a little below where
// the click was asked for, so the row's hit band is found rather than assumed:
// each attempt is cheap, and a miss inside the list does nothing.
const magic = () => read(YENDOR).magic;
let took = null;
await tap(ci, KEYS.enter, 160); await sleep(1200);
if (magic() !== 500 || rows() !== 1) took = "enter";
shot("03a-enter");
say(`  after enter: magic=${magic()} rows=${rows()}`);
for (const y of [0.135, 0.15, 0.165, 0.18, 0.195]) {
  if (took) break;
  await click(ci, 0.219, y); await sleep(1200);
  say(`  click y=${y}: magic=${magic()} rows=${rows()}`
    + ` [0x5e0a]=${peek16(ds + 0x5e0a)}`);
  shot(`03b-click-${y}`);
  if (magic() !== 500 || peek16(ds + 0x5e0a) !== 0) { took = `click y=${y}`; }
}
say(`row taken by: ${took || "nothing"}`);
// Then the target: SQUIRE is the first of the four, so F1.
await tap(ci, KEYS.f1, 160); await sleep(2000);
shot("04-after-cast");
const after = read(SQUIRE);
say(`YENDOR magic after the cast: ${read(YENDOR).magic} (was 500)`);
say("after the cast:"); show("   ");

// Close whatever is standing, then rest. Image 0xd6a6 passes over any
// character carrying 0x1c40, so a rest only reaches SQUIRE if the cast
// cleared the dead bit.
for (let i = 0; i < 3; i++) { await tap(ci, KEYS.esc, 120); await sleep(400); }
await tap(ci, A("r"), 160); await sleep(1500);
await tap(ci, A("r"), 160); await sleep(1500);
shot("05a-rest-prompt");
// "DO YOU WANT TO REST NOW?" with YES and NO in the right-hand panel.
await tap(ci, A("y"), 160); await sleep(1200);
await click(ci, 0.828, 0.535); await sleep(6000);
shot("05-after-rest");
const rested = read(SQUIRE);
say("after resting:"); show("   ");

say(`RESULT spell=${spellNo}`
  + ` cond ${before.cond} -> ${after.cond} -> ${rested.cond}`
  + ` health ${before.health} -> ${after.health} -> ${rested.health}`
  + ` dex ${before.dex} -> ${after.dex}`
  + ` revived=${(after.cond & 0x40) === 0}`
  + ` restored=${rested.health > 0}`);
await ci.exit();
process.exit(0);
