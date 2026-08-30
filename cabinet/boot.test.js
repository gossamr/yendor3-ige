// The DOSBox configuration carries two hard-won requirements. These tests
// exist so a later tidy-up cannot quietly drop either of them.
import { expect, test } from "bun:test";

import { existsSync } from "fs";
import { mkdtemp, rm, writeFile } from "fs/promises";
import { tmpdir } from "os";
import { join } from "path";

// The real game is not in this repository, so the tests that read it
// stand down where there is no copy, which is the case in CI.
const HAVE_GAME = existsSync(join(import.meta.dir, "..", "game",
                                  "WORLD.DAT"));

import { dosboxConf } from "./dosbox.conf.js";
import { gameFiles, initFs, GAME_DIR, PATCHED_DIR, STOCK_DIR, HEADLESS_ARGS }
  from "./boot.js";

test("expanded memory is enabled", () => {
  // Without it the game aborts: "Required Expanded Memory Manager (EMM Ver 4.0
  // or later) was not found", and README.DOC confirms it needs EMM386.
  expect(dosboxConf()).toContain("ems=true");
});

test("the game is launched through SW.BAT, never REGISTER.EXE", () => {
  const conf = dosboxConf();
  expect(conf).toContain("SW.BAT");
  expect(conf).not.toContain("REGISTER.EXE");
});

test("a fixed cycle count is used, not cycles=max", () => {
  // Fixed rather than max because cycles=max starves the host. 20000 rather
  // than the 3000 this used to be because 3000 was chosen to get through the
  // splash screens, which the force-skip-intro patch no longer shows, and at
  // 3000 a step in play takes about a second.
  expect(dosboxConf()).toContain("cycles=20000");
  expect(dosboxConf({ cycles: "max" })).toContain("cycles=max");
});

test("sound stays on by default", () => {
  // Turning the Sound Blaster off hangs the game on its second splash screen,
  // which suggests the splash chain advances off the audio path.
  expect(dosboxConf()).toContain("sbtype=sb16");
  expect(dosboxConf({ sound: false })).toContain("sbtype=none");
});

test.skipIf(!HAVE_GAME)("every file the game needs is shipped to the emulator", async () => {
  const names = (await gameFiles()).map((f) => f.path);
  for (const needed of ["REGISTER.EXE", "WORLD.DAT", "PICTURES.VGA",
                        "SW.BAT", "SBFMDRV.COM", "CURGAME"]) {
    expect(names).toContain(needed);
  }
});

test.skipIf(!HAVE_GAME)("editor leftovers and Windows shell metadata are excluded", async () => {
  const names = (await gameFiles()).map((f) => f.path);
  expect(names.some((n) => n.startsWith("~$"))).toBe(false);
  expect(names.some((n) => /\.(pif|ico)$/i.test(n))).toBe(false);
});

test.skipIf(!HAVE_GAME)("initFs pairs the files with a config object", async () => {
  const fs = await initFs();
  const configs = fs.filter((e) => e.dosboxConf);
  expect(configs).toHaveLength(1);
  expect(configs[0].jsdosConf.version).toBeTruthy();
  expect(fs.length).toBeGreaterThan(5);
  const byName = Object.fromEntries(
    fs.filter((e) => e.path).map((e) => [e.path, e.contents.byteLength]));
  // CURGAME is a zero-byte marker the game writes, so only the real payloads
  // are required to have content.
  expect(byName["REGISTER.EXE"]).toBe(202_676);
  expect(byName["WORLD.DAT"]).toBe(4_350_901);
  expect(byName["PICTURES.VGA"]).toBeGreaterThan(1_000_000);
  expect(byName["CURGAME"]).toBe(0);
});

test("headless runs mute the game with its own switches", () => {
  // /NOM and /NOS are parsed by the game itself. Muting this way is safe;
  // muting via sbtype=none hangs the game on its second splash screen.
  expect(HEADLESS_ARGS).toContain("/NOM");
  expect(HEADLESS_ARGS).toContain("/NOS");
  expect(dosboxConf({ extra: HEADLESS_ARGS })).toContain(`SW.BAT ${HEADLESS_ARGS}`);
  // Still a real Sound Blaster as far as DOSBox is concerned.
  expect(dosboxConf({ extra: HEADLESS_ARGS })).toContain("sbtype=sb16");
});

test("the developers' /P debug switch is not passed by default", () => {
  // /P turns on a debug mode (walls stop clipping, and the level check on
  // training is bypassed) so no default may carry it, and the intro is
  // skipped by patching the executable instead. A driver that wants no-clip
  // still asks for it explicitly, through YENDOR_ARGS.
  expect(HEADLESS_ARGS).not.toContain("/P");
  expect(dosboxConf()).not.toContain("/P");
  expect(dosboxConf({ extra: "/P" })).toContain("SW.BAT /P");
});

test("the patched build is booted in preference to the stock one", () => {
  // `make patched` writes it; without it the stock directory still boots, so a
  // fresh checkout works before anything has been built.
  const built = existsSync(join(PATCHED_DIR, "REGISTER.EXE"));
  expect(GAME_DIR).toBe(built ? PATCHED_DIR : STOCK_DIR);
});

test("an absent game directory yields no files rather than throwing", async () => {
  // Served publicly there is no game on the server: each player brings their
  // own copy from the browser. That has to read as "none", not as a failure --
  // letting this throw made /game-files.json answer 500, which the page cannot
  // tell apart from a broken server.
  expect(await gameFiles(join(PATCHED_DIR, "..", "no-such-game-dir"))).toEqual([]);
});


// --- the decoder fingerprint ---------------------------------------------
//
// The browser keeps the tables it decodes and hands them back on the next
// visit. What says they are still the right tables is this hash: if it does
// not move when a decoder does, a player carries an old decode for ever and
// the panel quietly lacks whatever the new one added.

test("the decoder fingerprint follows what the modules say", async () => {
  const { decoderFingerprint } = await import("./boot.js");
  const dir = await mkdtemp(join(tmpdir(), "decoder-"));
  try {
    for (const name of ["pack_maps", "extract", "world_map", "patch"]) {
      await writeFile(join(dir, `${name}.py`), `def main():\n    return "${name}"\n`);
    }
    const before = await decoderFingerprint(dir);
    expect(await decoderFingerprint(dir)).toBe(before);

    // A module that changes what it decodes.
    await writeFile(join(dir, "extract.py"), 'def main():\n    return "more"\n');
    const after = await decoderFingerprint(dir);
    expect(after).not.toBe(before);

    // And a module that arrives, which is how the planner tables appeared.
    await writeFile(join(dir, "planner.py"), "def build():\n    return {}\n");
    await writeFile(join(dir, "extract.py"),
                    'import planner\ndef main():\n    return "more"\n');
    expect(await decoderFingerprint(dir)).not.toBe(after);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});
