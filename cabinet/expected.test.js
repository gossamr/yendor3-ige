// cabinet/expected.js is what the page holds a decode to, and it is written by
// hand. These fail when it has fallen behind the decoders or the data, which
// is the only way the page could hold a copy to numbers nobody meant.
//
//   make data && bun tools/write_expected.js
import { expect, test } from "bun:test";

import { existsSync } from "fs";
import { join } from "path";

import { EXPECTED } from "./expected.js";
import { expected, PANEL_SOURCES } from "../tools/write_expected.js";

const ROOT = join(import.meta.dir, "..");
// `make data` needs the game, which is not in this repository, so the test
// that hashes a decode stands down where there is none.
const HAVE_DATA = Object.values(PANEL_SOURCES)
  .every((p) => existsSync(join(ROOT, p)));

test("every build is a decoder id and two hashes", () => {
  expect(Object.keys(EXPECTED).length).toBeGreaterThan(0);
  for (const [id, h] of Object.entries(EXPECTED)) {
    expect(id).toMatch(/^[0-9a-f]{16}$/);
    expect(Object.keys(h).sort()).toEqual(["restoration", "worldMap"]);
    expect(h.restoration).toMatch(/^[0-9a-f]{64}$/);
    expect(h.worldMap).toMatch(/^[0-9a-f]{64}$/);
  }
});

test.if(HAVE_DATA)("this tree's build is recorded, with what it decodes", async () => {
  const { decoder, hashes } = await expected(ROOT);
  expect(Object.keys(EXPECTED)).toContain(decoder);
  expect(EXPECTED[decoder]).toEqual(hashes);
});
