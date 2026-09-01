// Record what this build decodes the panel's source data to.
//
// The player's browser decodes their own copy of the game and fills the panel
// from the result. This writes down what that result is here, so the browser
// can hold what it produced to what the build intends: same game files, same
// decoders, same bytes, checked in the page against a number that traveled
// with the code rather than with the data.
//
// Written by hand rather than at deploy time because a static host has no game
// to decode. Regenerate after any change to a decoder, which is what
// cabinet/expected.test.js fails on:
//
//   make data && bun tools/write_expected.js
import { createHash } from "crypto";
import { readFile, writeFile } from "fs/promises";
import { dirname, join, resolve } from "path";
import { fileURLToPath } from "url";

import { decoderFingerprint } from "../cabinet/boot.js";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");

export const PANEL_SOURCES = {
  restoration: "data/restoration.json",
  worldMap: "data/world.png",
};

export const sha256 = (bytes) =>
  createHash("sha256").update(bytes).digest("hex");

/** The build that would decode this tree, and what it decodes the two to. */
export async function expected(root = ROOT) {
  const hashes = {};
  for (const [key, path] of Object.entries(PANEL_SOURCES)) {
    hashes[key] = sha256(await readFile(join(root, path)));
  }
  return { decoder: await decoderFingerprint(join(root, "tools")), hashes };
}

if (import.meta.main) {
  const { EXPECTED } = await import("../cabinet/expected.js");
  const { decoder, hashes } = await expected();
  // Every build that has been recorded, oldest first, the newest replacing an
  // entry of its own name. A page fetched from one deployment can be running
  // decoders from another, and an entry only leaves when nothing can still be
  // serving that build.
  const all = { ...EXPECTED, [decoder]: hashes };
  const body = Object.entries(all).map(([id, h]) =>
    `  ${JSON.stringify(id)}: {\n`
    + `    restoration: ${JSON.stringify(h.restoration)},\n`
    + `    worldMap: ${JSON.stringify(h.worldMap)},\n  },`).join("\n");
  await writeFile(join(ROOT, "cabinet/expected.js"), `\
// What each build decodes the panel's source data to. Written by
// tools/write_expected.js; see there for when to run it again.
//
// Keyed by the fingerprint of the modules that produced the hashes, the same
// one decoder-version.json carries. A page can be running decoders from an
// older deployment than the one it fetched this from, so the builds accumulate
// here and each is held to its own numbers.
export const EXPECTED = {
${body}
};
`);
  console.log(`expected: ${decoder} ${hashes.restoration.slice(0, 16)} `
              + `${hashes.worldMap.slice(0, 16)} (${Object.keys(all).length} builds)`);
}
