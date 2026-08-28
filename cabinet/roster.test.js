// The roster module, against the real WORLD.DAT.
//
// This mirrors tools/keep_characters.py, and the two are only useful if they
// agree: the Python builds a patched game directory offline, the JavaScript
// patches the same bytes in the browser before the emulator sees them. Both
// sides are tested against the same ground truth.
import { expect, test } from "bun:test";
import { existsSync, readFileSync } from "fs";
import { join } from "path";

import {
  ROSTER, SLOT, SLOTS, CREATED, SAVE_SIZE,
  graft, nameOf, rosterOf, slotsOf, looksLikeWorld,
} from "./roster.js";

const GAME_FILES = join(import.meta.dir, "..", "game");
// The real game is not in this repository, so the tests that read it
// stand down where there is no copy, which is the case in CI.
const HAVE_GAME = existsSync(join(GAME_FILES, "WORLD.DAT"));
const WORLD = HAVE_GAME
  ? new Uint8Array(readFileSync(join(GAME_FILES, "WORLD.DAT")))
  : new Uint8Array();

test.skipIf(!HAVE_GAME)("the roster template is where we think it is", () => {
  expect(looksLikeWorld(WORLD)).toBe(true);
});

test.skipIf(!HAVE_GAME)("the four stock characters sit on the 500-byte grid", () => {
  const found = Object.fromEntries(
    slotsOf(WORLD, ROSTER).map(({ slot, name }) => [slot, name]));
  expect(found[6]).toBe("SQUIRE");
  expect(found[7]).toBe("DIANA");
  expect(found[8]).toBe("YENDOR");
  expect(found[9]).toBe("JOSEPHINE");
});

test.skipIf(!HAVE_GAME)("the created slots ship empty", () => {
  const taken = slotsOf(WORLD, ROSTER).map((s) => s.slot);
  expect(CREATED.filter((i) => taken.includes(i))).toEqual([]);
});

/** A roster blob with one character in it, laid out like the game's. */
function rosterWith(name, slot = 1) {
  const roster = WORLD.slice(ROSTER, ROSTER + SLOTS * SLOT);
  roster.fill(0, slot * SLOT, (slot + 1) * SLOT);
  roster.set(new TextEncoder().encode(name), slot * SLOT);
  return roster;
}

test.skipIf(!HAVE_GAME)("a name is read up to its NUL", () => {
  expect(nameOf(rosterWith("ZORBAX").subarray(SLOT, SLOT * 2))).toBe("ZORBAX");
});

test.skipIf(!HAVE_GAME)("grafting writes the record into the template", () => {
  const { world, kept } = graft(WORLD, rosterWith("ZORBAX"));
  expect(kept).toEqual([{ slot: 1, name: "ZORBAX" }]);
  expect(slotsOf(world, ROSTER).find((s) => s.slot === 1).name).toBe("ZORBAX");
});

test.skipIf(!HAVE_GAME)("grafting changes only that slot, and not the length", () => {
  const { world } = graft(WORLD, rosterWith("ZORBAX"));
  expect(world.length).toBe(WORLD.length);
  const at = ROSTER + SLOT;
  let outside = 0;
  for (let i = 0; i < WORLD.length; i++) {
    if (WORLD[i] !== world[i] && (i < at || i >= at + SLOT)) outside++;
  }
  expect(outside).toBe(0);
});

test.skipIf(!HAVE_GAME)("grafting never touches the header or the stock four", () => {
  // A source with every slot filled must still only move slots 1-5.
  const roster = new Uint8Array(SLOTS * SLOT);
  for (let i = 0; i < SLOTS; i++) {
    roster.set(new TextEncoder().encode("INTRUDER"), i * SLOT);
  }
  const { world, kept } = graft(WORLD, roster);

  expect(kept.length).toBe(CREATED.length);
  const found = Object.fromEntries(
    slotsOf(world, ROSTER).map(({ slot, name }) => [slot, name]));
  expect(found[0]).toBe("PRE-CREATED PARTY");
  expect([6, 7, 8, 9].map((i) => found[i]))
    .toEqual(["SQUIRE", "DIANA", "YENDOR", "JOSEPHINE"]);
});

test.skipIf(!HAVE_GAME)("grafting twice accumulates rather than replacing", () => {
  const first = graft(WORLD, rosterWith("ZORBAX", 1)).world;
  const { world, kept } = graft(first, rosterWith("MIRABEL", 2));

  expect(kept).toEqual([{ slot: 2, name: "MIRABEL" }]);
  const found = Object.fromEntries(
    slotsOf(world, ROSTER).map(({ slot, name }) => [slot, name]));
  expect(found[1]).toBe("ZORBAX");
  expect(found[2]).toBe("MIRABEL");
});

test.skipIf(!HAVE_GAME)("an empty source slot clears nothing", () => {
  const grafted = graft(WORLD, rosterWith("ZORBAX")).world;
  const { world, kept } = graft(grafted, new Uint8Array(SLOTS * SLOT));

  expect(kept).toEqual([]);
  expect(world).toEqual(grafted);
});

test.skipIf(!HAVE_GAME)("rosterOf takes the first five thousand bytes of a save", () => {
  const save = new Uint8Array(SAVE_SIZE);
  save.set(rosterWith("ZORBAX"), 0);
  expect(slotsOf(rosterOf(save)).find((s) => s.slot === 1).name).toBe("ZORBAX");
});

test("rosterOf refuses a file that is not a saved game", () => {
  expect(() => rosterOf(new Uint8Array(100))).toThrow(/81037/);
});

test("looksLikeWorld rejects something that is not WORLD.DAT", () => {
  expect(looksLikeWorld(new Uint8Array(ROSTER + 100))).toBe(false);
});
