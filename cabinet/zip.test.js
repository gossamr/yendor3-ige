// The zip reader, against zips built from the real game directory.
import { expect, test } from "bun:test";
import { existsSync, readdirSync, readFileSync, statSync } from "fs";
import { join } from "path";

import { readZip, gameFromZip } from "./zip.js";

const GAME = join(import.meta.dir, "..", "game");
// The tests that zip the real game stand down where there is no copy.
const HAVE_GAME = existsSync(join(GAME, "WORLD.DAT"));
const NAMES = HAVE_GAME
  ? readdirSync(GAME).filter((n) => !n.startsWith("~$"))
  : [];

/**
 * A zip, built here rather than fetched.
 *
 * Both compression methods the reader supports appear in one archive: bun's
 * deflate for most files, stored for the ones asked for by name, which is the
 * mix a file manager produces when a file does not compress.
 */
function zip(entries, { stored = [] } = {}) {
  const enc = new TextEncoder();
  const parts = [];
  const central = [];
  let at = 0;
  const u16 = (v) => [v & 0xff, (v >> 8) & 0xff];
  const u32 = (v) => [v & 0xff, (v >> 8) & 0xff, (v >> 16) & 0xff, (v >>> 24) & 0xff];

  for (const [path, contents] of entries) {
    const name = enc.encode(path);
    const raw = stored.includes(path);
    const body = raw ? contents : Bun.deflateSync(contents);
    const head = Uint8Array.from([
      ...u32(0x04034b50), ...u16(20), ...u16(0), ...u16(raw ? 0 : 8),
      ...u16(0), ...u16(0), ...u32(0), ...u32(body.length), ...u32(contents.length),
      ...u16(name.length), ...u16(0),
    ]);
    central.push(Uint8Array.from([
      ...u32(0x02014b50), ...u16(20), ...u16(20), ...u16(0), ...u16(raw ? 0 : 8),
      ...u16(0), ...u16(0), ...u32(0), ...u32(body.length), ...u32(contents.length),
      ...u16(name.length), ...u16(0), ...u16(0), ...u16(0), ...u16(0), ...u32(0),
      ...u32(at), ...name,
    ]));
    parts.push(head, name, body);
    at += head.length + name.length + body.length;
  }
  const dir = at;
  const size = central.reduce((n, c) => n + c.length, 0);
  parts.push(...central, Uint8Array.from([
    ...u32(0x06054b50), ...u16(0), ...u16(0),
    ...u16(central.length), ...u16(central.length), ...u32(size), ...u32(dir), ...u16(0),
  ]));
  return new Uint8Array(Buffer.concat(parts.map((p) => Buffer.from(p))));
}

const gameEntries = (prefix = "") =>
  NAMES.map((n) => [prefix + n, new Uint8Array(readFileSync(join(GAME, n)))]);

test.skipIf(!HAVE_GAME)("a file round-trips through both compression methods", async () => {
  const stored = ["PICTURES.VGA"];
  const files = await readZip(zip(gameEntries(), { stored }));
  expect(files.map((f) => f.path).sort()).toEqual([...NAMES].sort());
  const world = files.find((f) => f.path === "WORLD.DAT");
  const pictures = files.find((f) => f.path === "PICTURES.VGA");
  expect(world.contents).toEqual(new Uint8Array(readFileSync(join(GAME, "WORLD.DAT"))));
  expect(pictures.contents.length).toBe(statSync(join(GAME, "PICTURES.VGA")).size);
});

test.skipIf(!HAVE_GAME)("a zipped folder is rooted where the autoexec looks", async () => {
  const files = await gameFromZip(zip(gameEntries("YENDOR3/")));
  expect(files.map((f) => f.path).sort()).toEqual([...NAMES].sort());
});

test.skipIf(!HAVE_GAME)("archive bookkeeping is left out", async () => {
  const junk = new Uint8Array([1, 2, 3]);
  const files = await readZip(zip([
    ["__MACOSX/._SW.BAT", junk], [".DS_Store", junk], ["SW.BAT", junk],
  ]));
  expect(files.map((f) => f.path)).toEqual(["SW.BAT"]);
});

test.skipIf(!HAVE_GAME)("a zip without the game says which file is missing", async () => {
  const holiday = zip([["photos/beach.jpg", new Uint8Array([1, 2, 3])]]);
  expect(gameFromZip(holiday)).rejects.toThrow(/no SW.BAT/);

  const partial = zip(gameEntries().filter(([n]) => n !== "WORLD.DAT"));
  expect(gameFromZip(partial)).rejects.toThrow(/missing WORLD.DAT/);
});

test("something that is not a zip is refused", async () => {
  expect(readZip(new Uint8Array(2000))).rejects.toThrow(/not a zip/);
});

// Safari puts no async iterator on ReadableStream. A `for await` over one
// throws "undefined is not a function", and every zip is refused. bun has the
// iterator, so the tests above pass either way. This one takes it away for the
// length of the call.
test.skipIf(!HAVE_GAME)("a zip inflates without an async iterator on streams", async () => {
  const proto = Object.getPrototypeOf(new Blob([]).stream());
  const iterator = proto[Symbol.asyncIterator];
  delete proto[Symbol.asyncIterator];
  try {
    const files = await readZip(zip(gameEntries()));
    expect(files.map((f) => f.path).sort()).toEqual([...NAMES].sort());
  } finally {
    if (iterator) proto[Symbol.asyncIterator] = iterator;
  }
});
