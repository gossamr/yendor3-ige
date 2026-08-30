// The filesystem tracer's hook, exercised against a stand-in FS.
//
// The hook logs into an array that gets JSON.stringify'd to disk on a timer,
// and a failure to serialize is caught and swallowed, so a bad entry does not
// crash anything, it just means no log is ever written, which reads exactly
// like "the game touched no files". That cost a run to diagnose once; these
// tests make sure it cannot happen quietly again.
import { expect, test } from "bun:test";

import { HOOK } from "../tools/trace_fs.js";

/** Evaluate the hook in a scope of its own and hand back its internals. */
function hooked(fs) {
  const src = HOOK
    .replace("__LOG__", "/dev/null")
    .replace("__RAW__", "true")
    .replace("__OPS__", "true");
  const make = new Function(
    "require",
    `${src}; __hookFS(FS_IN); return { ops: () => __fsOps, events: () => __fsEvents };`
      .replace("FS_IN", "this.FS"),
  );
  // The hook installs a flush timer; give it a require that yields no fs so
  // nothing is written during a test.
  return make.call({ FS: fs }, () => { throw new Error("no fs in tests"); });
}

/** The parts of Emscripten's FS the hook wraps. */
function fakeFS() {
  return {
    read: () => 0,
    write: () => 0,
    open: () => ({}),
    close: () => {},
    ftruncate: () => {},
    truncate: () => {},
    unlink: () => {},
    rename: () => {},
    mkdir: () => {},
    rmdir: () => {},
    mknod: () => {},
    getStream: () => ({ path: "/CURGAME" }),
  };
}

test("a write is recorded with its byte range", () => {
  const fs = fakeFS();
  const t = hooked(fs);
  fs.write({ path: "/CURGAME", position: 0 }, new Uint8Array(4), 0, 5000, 0);

  expect(t.ops()).toEqual([[expect.any(Number), "write", "/CURGAME", "", 0, 5000]]);
});

test("consecutive writes to one file coalesce", () => {
  const fs = fakeFS();
  const t = hooked(fs);
  fs.write({ path: "/CURGAME" }, null, 0, 100, 0);
  fs.write({ path: "/CURGAME" }, null, 0, 100, 100);

  expect(t.ops().length).toBe(1);
  expect(t.ops()[0][5]).toBe(200);
});

test("mutations are recorded by name", () => {
  const fs = fakeFS();
  const t = hooked(fs);
  fs.truncate("/CURGAME", 0);
  fs.unlink("/SAVGAME1");
  fs.rename("/a", "/b");

  expect(t.ops().map((o) => o[1])).toEqual(["truncate", "unlink", "rename"]);
  expect(t.ops()[0][2]).toBe("/CURGAME");
});

// Emscripten's FS.open takes either a path or a node, and a node points at its
// parent, which points back. Logging one whole made every flush throw inside
// the catch that hides flush errors, so the log stayed empty and the run looked
// like the game had touched nothing at all.
test("a node argument is reduced to its path, not logged whole", () => {
  const fs = fakeFS();
  const t = hooked(fs);
  const node = { path: "/CURGAME", name: "CURGAME" };
  node.parent = node;
  fs.open(node, 577);

  expect(t.ops()[0][2]).toBe("/CURGAME");
  expect(() => JSON.stringify(t.ops())).not.toThrow();
});

test("every logged field stays serializable whatever it is handed", () => {
  const fs = fakeFS();
  const t = hooked(fs);
  const cyclic = {};
  cyclic.self = cyclic;
  fs.open(cyclic, 0);
  fs.unlink(cyclic);
  fs.rename(cyclic, cyclic);
  fs.close({ path: cyclic, node: { usedBytes: 3 } });

  expect(() => JSON.stringify(t.ops())).not.toThrow();
});

test("reads are still recorded, since that is what the tracer was built for", () => {
  const fs = fakeFS();
  const t = hooked(fs);
  fs.read({ path: "/WORLD.DAT" }, null, 0, 3200, 0x25800);

  expect(t.events()).toEqual([[expect.any(Number), 0, 0x25800, 3200]]);
});
