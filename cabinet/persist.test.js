// What a save reads off the emulated disk.
//
// fsTree() reports no sizes in this build, so the only way to tell a changed
// file from an unchanged one is to read and hash it, which makes *what gets
// read* the whole cost of a save. The game data is 21MB and the game never
// writes to it, so reading it is 21MB of work for an answer known in advance.
import { expect, test } from "bun:test";

import { changedFiles, fingerprint, isPersistable, notKeptReason } from "./persist.js";

/** An emulator whose disk holds the game plus whatever the game has written. */
function fakeCi(extra = {}) {
  const disk = {
    "PICTURES.VGA": new Uint8Array(1024),
    "WORLD.DAT": new Uint8Array(512),
    "REGISTER.EXE": new Uint8Array(256),
    "SBFMDRV.COM": new Uint8Array(64),
    "SW.BAT": new Uint8Array(16),
    "CURGAME": new Uint8Array(0),
    ...extra,
  };
  const read = [];
  return {
    read,
    disk,
    fsTree: async () => ({
      name: ".",
      nodes: Object.keys(disk).map((name) => ({ name, size: null })),
    }),
    fsReadFile: async (path) => {
      read.push(path);
      const hit = disk[path.replace(/^\.?\/+/, "")];
      if (!hit) throw new Error(`no such file ${path}`);
      return hit;
    },
  };
}

const originalsOf = (ci) => new Map(
  Object.entries(ci.disk).map(([name, bytes]) => [name.toUpperCase(), fingerprint(bytes)]));

test("the game's data and executables are never read", async () => {
  const ci = fakeCi();
  await changedFiles(ci, originalsOf(ci));

  for (const name of ["PICTURES.VGA", "WORLD.DAT", "REGISTER.EXE", "SBFMDRV.COM"]) {
    expect(ci.read).not.toContain(name);
  }
});

test("files the game writes are still read, and reported when they change", async () => {
  const ci = fakeCi();
  const originals = originalsOf(ci);
  ci.disk["CURGAME"] = new Uint8Array(81037);
  ci.disk["SAVGAME1"] = new Uint8Array(81037);

  const changed = await changedFiles(ci, originals);
  const names = changed.map((f) => f.path);

  expect(names).toContain("CURGAME");
  expect(names).toContain("SAVGAME1");
  expect(ci.read).toContain("CURGAME");
});

test("an unchanged file the game could write is not reported", async () => {
  const ci = fakeCi();
  const changed = await changedFiles(ci, originalsOf(ci));

  expect(changed.map((f) => f.path)).not.toContain("CURGAME");
});

// LOGO.PCX is unpacked from the game data at load, so it is written on every
// run and holds nothing the player would miss. It is listed like anything else
// the game writes, and dropped before storage.
test("a file the game invents is listed but not kept", async () => {
  const ci = fakeCi();
  const originals = originalsOf(ci);
  ci.disk["LOGO.PCX"] = new Uint8Array(29214);

  const changed = await changedFiles(ci, originals);
  expect(changed.map((f) => f.path)).toContain("LOGO.PCX");
  expect(isPersistable("LOGO.PCX")).toBe(false);
  expect(notKeptReason("LOGO.PCX")).toBe("unpacked at load, not kept");
  expect(notKeptReason("SAVGAME1")).toBe(null);
});

// CURGAME is rebuilt from scratch at every launch, so a stored copy is read by
// nothing. It still has to be *listed*, which is why the filter is separate
// from the walk.
test("CURGAME is reported as changed but not kept", async () => {
  const ci = fakeCi();
  const originals = originalsOf(ci);
  ci.disk["CURGAME"] = new Uint8Array(81037);

  const changed = await changedFiles(ci, originals);
  expect(changed.map((f) => f.path)).toContain("CURGAME");
  expect(isPersistable("CURGAME")).toBe(false);
  expect(isPersistable("SAVGAME1")).toBe(true);
  expect(isPersistable("./CURGAME")).toBe(false);
});
