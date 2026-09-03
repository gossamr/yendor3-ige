// The first-person view's cell table, read out of the running game.
//
//   bun tools/view_probe.js                       where the save left the party
//   bun tools/view_probe.js --x=460 --y=46 --facing=0x8000
//   bun tools/view_probe.js --at=460,46,0x8000 --at=460,46,0x1000   one boot
//   bun tools/view_probe.js --serve=7777                        stays up
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
//
// `--serve=PORT` boots once and then takes actions over a socket, which is the
// way to use this: getting to the world costs 13 seconds and a reading costs
// 2.4, so a session of twenty readings is half a minute against five minutes
// of booting. Frames and the readings that place them are written together,
// beside `--json`, because a frame whose position is lost cannot be diffed.
//
//   GET /at?x=&y=&facing=&clock=   stand there, redraw, read the table, keep a
//                                  frame, and hand back the reading. Any of
//                                  the four left out keeps its current value.
//   GET /peek?at=&len=             bytes from the data segment, DS-relative
//   GET /poke?at=&v=               a word into the data segment
//   GET /stop                      end the run
//
// **What a poke reaches, and what it does not.** Anything the game reads while
// it draws answers a poke: writing the clock at DS:0xCF7F and redrawing moves
// the distance shading, because the shade table is looked up per draw. Anything
// that happens on a game event does not, because nothing here raises one. The
// sky is the example. Its palette window slides from images 0x0E93B and
// 0x0EC5C, on the path that advances time, so a poked clock leaves it where it
// was however far it is moved (docs/view.md). Watching that needs the party to
// walk until the game's own clock reaches six in the evening, and this only
// turns the party, never steps it.
//
// The process outlives its work: the readings are written and `ci.exit()`
// returns, and it goes on holding an emulator until something stops it. Under
// `--serve` that is the point. Otherwise capture the pid and kill it, since
// seven of these accumulated in one session before anyone noticed:
//
//   bun tools/view_probe.js --at=... & echo $! > tmp/probe.pid
//   kill $(cat tmp/probe.pid)
import { readFileSync, writeFileSync, mkdirSync } from "fs";

import { loadEmulators, initFs, HEADLESS_ARGS } from "../cabinet/boot.js";
import { KEYS, tap, click } from "../cabinet/keys.js";
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
// Minutes since midnight. The distance shading is keyed on it
// (docs/view.md), and so is the sky.
const CLOCK = 0xcf7f;
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
// Kept so a run reports the screen it ended on, and counted so a wait can end
// on the picture rather than on the clock.
let frame = null, delivered = 0, waiting = [];
ci.events().onFrame((rgb) => {
  if (!rgb) return;
  frame = { rgb: rgb.slice(), w: ci.width(), h: ci.height() };
  delivered += 1;
  for (const resolve of waiting.splice(0)) resolve();
});
const nextFrame = () => new Promise((r) => waiting.push(r));
// Frames go beside the readings that place them: a frame whose position is
// lost cannot be diffed against anything.
const shotDir = arg("json", "tmp/view-probe/readings.json")
  .replace(/\/[^/]*$/, "") || ".";
let shots = 0;
/** Keep the screen as it stands, and hand back where it went. */
const shot = (name) => {
  if (!frame) return null;
  const path = `${shotDir}/${String(++shots).padStart(2, "0")}-${name}.png`;
  mkdirSync(shotDir, { recursive: true });
  writeFileSync(path, encodePng(frame.w, frame.h, frame.rgb));
  say(`shot ${path}`);
  return path;
};
// A key is followed by the picture it draws, not by a guess at how long that
// takes. `cabinet/perf.js` waits the same way, and for the same reason: the
// pace differs by an order of magnitude between one machine and another. The
// wait ends when no frame has arrived for `quiet` ms, or at `cap`.
const settled = async (quiet = 350, cap = 30000) => {
  const until = Date.now() + cap;
  for (;;) {
    const seen = delivered;
    await Promise.race([nextFrame(), sleep(quiet)]);
    if (delivered === seen || Date.now() > until) return;
  }
};
const press = async (k, quiet) => { await tap(ci, KEYS[k], 120); await settled(quiet); };

// To the menu, the way tmp/write_probe.js and tools/fight_probe.js both get
// there: the splash screens advance on a key, and how many there are depends
// on the build, so they are pressed through rather than waited out.
for (let i = 0; i < 10; i++) {
  await tap(ci, KEYS.esc, 100);
  await tap(ci, KEYS.space, 100);
  await settled(250, 3000);
}
if (hasSave) {
  // Load, off the menu. The party comes with the save, so ENTER THE GAME
  // plays no part.
  await press("l"); await press("1"); await press("y");
} else {
  await press("a");
  for (const k of ["6", "7", "8", "9"]) await press(k);
  await press("d");
  await press("e");
  await press("r");
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
  clock: peek16(ds + CLOCK),
});

// Where to stand for each reading. Getting to the world costs 13 seconds and a
// reading costs 2.4, so the party is walked between readings rather than
// booted again: `--at=x,y,facing` once per stop, or the party's own place when
// none is given. `--serve` keeps the boot for as long as it is left running.
// Every stop writes a frame, which is what a redrawn view is diffed against.
const stops = process.argv.filter((a) => a.startsWith("--at="))
  .map((a) => a.slice(5).split(",").map(Number));
if (!stops.length) {
  stops.push(arg("x") === undefined && arg("y") === undefined
    && arg("facing") === undefined
    ? []
    : [num("x", -1), num("y", -1), arg("facing") === undefined
        ? -1 : Number(arg("facing"))]);
}

let taken = 0;
const readings = [];
// Where the readings go. A frame without the position it was taken from
// cannot be diffed against anything, so serve mode writes the file after
// every stop rather than at the end.
const ledger = arg("json", "tmp/view-probe/readings.json");
const keep = () => {
  mkdirSync(ledger.replace(/\/[^/]*$/, "") || ".", { recursive: true });
  writeFileSync(ledger, JSON.stringify(
    readings.length === 1 ? readings[0] : { readings }, null, 1));
};

/** Stand somewhere, turn to redraw, read the table, keep a frame. */
async function stand([x, y, facing, clock = -1]) {
  const i = taken++;
  if (x >= 0) poke16(ds + PARTY_X, x);
  if (y >= 0) poke16(ds + PARTY_Y, y);
  if (facing >= 0) poke16(ds + FACING, facing);
  if (clock >= 0) poke16(ds + CLOCK, clock);
  if (x >= 0 || y >= 0 || facing >= 0 || clock >= 0) {
    // The view is rebuilt on a step, not on a poke, so the party is turned
    // full circle to make the game redraw from where it now stands.
    for (const k of ["left", "left", "left", "left"]) await press(k);
  }

  const at = where();
  say("");
  say(`[${i + 1}] party at x=${at.x} y=${at.y} `
    + `facing=0x${at.facing.toString(16)} clock=${at.clock}`);
  say(`run parameters at DS:0x${PARAMS.toString(16)}: `
    + RUNS.map((_, n) => `0x${peek16(ds + PARAMS + n * 2).toString(16)}`).join(" "));

  const table = globalThis.__peek(ds + VIEW, CELLS * ENTRY);
  const rows = [];
  let cell = 0;
  for (let run = 0; run < RUNS.length; run++) {
    for (let n = 0; n < RUNS[run]; n++, cell++) {
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

  say("cell run  +0     +2     +4     +6     skip");
  for (const r of rows) {
    say(`${String(r.cell).padStart(4)} ${String(r.run).padStart(3)}  `
      + [r.draws, r.plus2, r.plus4, r.plus6]
        .map((v) => `0x${v.toString(16).padStart(4, "0")}`).join(" ")
      + `  ${r.skipped ? "yes" : ""}`);
  }

  const path = shot(`${at.x}-${at.y}-${at.facing.toString(16)}-${at.clock}`);
  const reading = { party: at, runs: RUNS, rows, shot: path };
  readings.push(reading);
  keep();
  return reading;
}

for (const stop of stops) await stand(stop);

// Getting to the world is what a run spends its time on, so `--serve=PORT`
// pays it once and then answers stops over a socket for as long as it is left
// running. `GET /at?x=&y=&facing=` stands there and hands back the reading it
// took; `GET /stop` ends the run.
const port = num("serve", 0);
if (port) {
  say(`\nserving on http://localhost:${port}/  `
    + `at?x=460&y=46&facing=0x8000 | stop`);
  let done;
  const ending = new Promise((r) => { done = r; });
  const server = Bun.serve({
    port,
    async fetch(request) {
      const url = new URL(request.url);
      if (url.pathname === "/stop") { done(); return Response.json({ stopped: true }); }
      // A click, for what only the mouse reaches. The cursor is homed from a
      // corner and the aim runs high and left of where it lands, so aim a few
      // pixels up and left of the target, as tools/capture_legend.js does.
      // `n=2` double clicks, which is what this game's lists select on.
      if (url.pathname === "/click") {
        const x = Number(url.searchParams.get("x"));
        const y = Number(url.searchParams.get("y"));
        for (let i = 0; i < Number(url.searchParams.get("n") || 1); i++) {
          await click(ci, x / 320, y / 200);
        }
        await settled();
        return Response.json({ clicked: [x, y], shot: shot(`click-${x}-${y}`) });
      }
      // A key, for anything the game only does on an event. `keys` is a comma
      // separated list of names from cabinet/keys.js.
      if (url.pathname === "/key") {
        const names = (url.searchParams.get("keys") || "").split(",").filter(Boolean);
        for (const k of names) {
          if (!(k in KEYS)) return Response.json({ error: `no key ${k}` }, { status: 400 });
          await press(k);
        }
        return Response.json({ pressed: names, party: where(),
                               shot: shot(`key-${names.join("-")}`) });
      }
      // Anything else the game holds, for a question the table above does not
      // answer: `peek?at=0x71c6&len=72` reads DS-relative, `poke?at=&v=` writes
      // a word there.
      if (url.pathname === "/peek") {
        const at = Number(url.searchParams.get("at"));
        const len = Number(url.searchParams.get("len") || 2);
        return Response.json({ at, bytes: globalThis.__peek(ds + at, len) });
      }
      if (url.pathname === "/poke") {
        const at = Number(url.searchParams.get("at"));
        poke16(ds + at, Number(url.searchParams.get("v")));
        return Response.json({ at, wrote: Number(url.searchParams.get("v")) });
      }
      if (url.pathname !== "/at") {
        return new Response("at | peek | poke | stop", { status: 404 });
      }
      const pick = (n) => (url.searchParams.has(n)
        ? Number(url.searchParams.get(n)) : -1);
      return Response.json(await stand(
        [pick("x"), pick("y"), pick("facing"), pick("clock")]));
    },
  });
  await ending;
  server.stop();
}

if (readings.length) say(`\nwrote ${ledger}`);
await ci.exit();
