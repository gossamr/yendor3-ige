// Build a copy of js-dos's emulator that logs what it does to the filesystem.
//
// The clue book's map layout could not be found anywhere in the game files by
// searching, so stop searching and watch instead: dosboxNode runs the emulator
// in this process, and js-dos loads its wasm shim from a path we choose. This
// writes a copy of that shim with hooks in it, so every byte range the game
// actually touches is recorded, with a timestamp to line up against what was
// on screen.
//
// Two modes, because two different questions get asked of it:
//
//   reads (default), every FS.read, which is how the map data was found.
//   ops               every mutation as well: open, write, truncate, unlink,
//                      rename, close. This is the one that answers "what did
//                      the game do to its save files when I pressed that key".
import { readFileSync, writeFileSync, existsSync } from "fs";
import { join } from "path";

import { EMU_DIST } from "../cabinet/boot.js";

export const TRACED_JS = "wdosbox-traced.js";
// The mouse only works under the DOSBox-X backend (docs/running.md), and that
// backend loads a different shim, so anything that needs to click while it
// traces needs this one instead.
export const TRACED_X_JS = "wdosbox-x-traced.js";

/** The hook, injected into the emulator's module scope. Exported for tests. */
export const HOOK = `
// The emulator's whole linear memory, on demand.
//
// DOSBox keeps the guest's RAM inside the wasm heap, so everything the game has
// in memory, including the tables it loaded at startup and never reads
// again, is somewhere in here. js-dos exposes no way to read it; this hook
// runs inside the module scope, where Module.HEAPU8 is in reach, and hands the
// whole thing to the driver.
//
// The guest's memory is a window into this, not the whole of it: the heap also
// holds the emulator's own state. Finding the window is the caller's problem,
// and \`tools/find_guest.py\` does it by looking for bytes the game is known to
// hold.
var __module = null;          // captured when the FS hook is installed
globalThis.__dumpMemory = function (path) {
  try {
    var fs = require("fs");
    var heap = __module.HEAPU8;
    fs.writeFileSync(path, Buffer.from(heap.buffer, heap.byteOffset, heap.length));
    return heap.length;
  } catch (e) {
    try { console.error("memory dump failed: " + e.message); } catch (e2) {}
    return -1;
  }
};

// Read a window of the heap without writing 64 MB to disk. Watching a value
// change, a monster's health as the party swings at it, needs a cheap
// read taken often, which a dump is not.
//
//   globalThis.__find("CENTIPEDE")   -> heap offsets of a byte string
//   globalThis.__peek(at, 16)        -> that many bytes, as an array
//   globalThis.__poke(at, [1, 2])    -> write them back
globalThis.__peek = function (at, len) {
  var heap = __module.HEAPU8;
  return Array.prototype.slice.call(heap.subarray(at, at + len));
};
globalThis.__poke = function (at, bytes) {
  var heap = __module.HEAPU8;
  for (var i = 0; i < bytes.length; i++) heap[at + i] = bytes[i] & 0xff;
  return bytes.length;
};
globalThis.__find = function (needle, limit) {
  var heap = __module.HEAPU8;
  var want = [];
  for (var i = 0; i < needle.length; i++) want.push(needle.charCodeAt(i));
  var out = [];
  for (var at = 0; at + want.length <= heap.length; at++) {
    if (heap[at] !== want[0]) continue;
    var ok = true;
    for (var k = 1; k < want.length; k++) {
      if (heap[at + k] !== want[k]) { ok = false; break; }
    }
    if (ok) { out.push(at); if (out.length >= (limit || 32)) break; }
  }
  return out;
};

// Dump the moment a particular file is read, rather than afterwards. The
// guest's CPU state is only interesting while it is doing the thing being
// investigated: after the page is drawn it is idle in the BIOS.
//
//   globalThis.__dumpOnRead = { match: "PICTURES", nth: 1, path: "/tmp/x.bin" }
globalThis.__dumpOnRead = null;
var __dumpCount = 0;

var __fsEvents = [];
var __fsPaths = [];
var __fsT0 = Date.now();
function __fsFlush() {
  try {
    var fs = require("fs");
    fs.writeFileSync(__fsLogPath, JSON.stringify(
      { t0: __fsT0, paths: __fsPaths, events: __fsEvents, ops: __fsOps }));
  } catch (e) {
    // A silent flush failure looks exactly like "the game touched nothing",
    // which is the most misleading result this tool can produce, so say so.
    if (!__fsFlushWarned) {
      __fsFlushWarned = true;
      try { console.error("fs trace: cannot write log: " + e.message); } catch (e2) {}
    }
  }
}
var __fsFlushWarned = false;
var __fsLogPath = "__LOG__";
var __fsRaw = __RAW__;
var __fsWantOps = __OPS__;
var __fsOps = [];
function __hookFS(FS, mod) {
  __module = mod;
  var __maybeDump = function (path) {
    var want = globalThis.__dumpOnRead;
    if (!want || !path || path.toUpperCase().indexOf(want.match) < 0) return;
    __dumpCount += 1;
    if (__dumpCount !== want.nth) return;
    globalThis.__dumpMemory(want.path);
    globalThis.__dumpTaken = { nth: want.nth, path: path };
  };
  var inner = FS.read.bind(FS);
  FS.read = function (stream, buffer, offset, length, position) {
    try {
      var path = stream && stream.path;
      __maybeDump(path);
      if (path) {
        var i = __fsPaths.indexOf(path);
        if (i < 0) { i = __fsPaths.length; __fsPaths.push(path); }
        var at = position === undefined || position === null
          ? (stream.position || 0) : position;
        if (__fsRaw) {
          __fsEvents.push([Date.now() - __fsT0, i, at, length]);
        } else {
          var last = __fsEvents.length && __fsEvents[__fsEvents.length - 1];
          // Sequential reads of one file are one access; the game reads in
          // small chunks and the uncoalesced log is mostly noise. Raw mode
          // keeps them, which is what shows the real request size.
          if (last && last[1] === i && last[2] + last[3] === at) {
            last[3] += length;
          } else {
            __fsEvents.push([Date.now() - __fsT0, i, at, length]);
          }
        }
        if (__fsEvents.length % 2000 === 0) __fsFlush();
      }
    } catch (e) { /* never break the emulator for the sake of the log */ }
    return inner(stream, buffer, offset, length, position);
  };
  if (__fsWantOps) __hookOps(FS);
  setInterval(__fsFlush, 2000);
}

// Emscripten's FS takes either a path or a node object for most of these, and
// a node has a parent pointer, so anything that reaches the log must be
// reduced to a string first or JSON.stringify throws on the cycle and the whole
// log silently never gets written.
function __fsName(x) {
  if (typeof x === "string") return x;
  if (x && typeof x === "object") return x.path || x.name || "?";
  return String(x);
}

// Mutations, by name. FS.write is wrapped separately because its interesting
// argument is a byte range rather than a path, and it is hot enough that
// consecutive writes to one file are coalesced the way reads are.
function __hookOps(FS) {
  var byPath = {
    open: function (a) { return [__fsName(a[0]), "flags=" + a[1]]; },
    truncate: function (a) { return [__fsName(a[0]), "len=" + a[1]]; },
    unlink: function (a) { return [__fsName(a[0]), ""]; },
    rmdir: function (a) { return [__fsName(a[0]), ""]; },
    mkdir: function (a) { return [__fsName(a[0]), ""]; },
    mknod: function (a) { return [__fsName(a[0]), ""]; },
    rename: function (a) { return [__fsName(a[0]), "-> " + __fsName(a[1])]; },
  };
  Object.keys(byPath).forEach(function (name) {
    if (typeof FS[name] !== "function") return;
    var inner = FS[name].bind(FS);
    FS[name] = function () {
      var args = Array.prototype.slice.call(arguments);
      var ok = true, out;
      try { out = inner.apply(null, args); } catch (e) { ok = false; throw e; }
      finally {
        try {
          var d = byPath[name](args);
          __fsOps.push([Date.now() - __fsT0, name, d[0], d[1] + (ok ? "" : " FAILED")]);
        } catch (e) { /* never break the emulator for the sake of the log */ }
      }
      return out;
    };
  });
  var innerClose = FS.close.bind(FS);
  FS.close = function (stream) {
    try {
      __fsOps.push([Date.now() - __fsT0, "close",
        __fsName(stream && stream.path),
        "size=" + ((stream && stream.node && stream.node.usedBytes) || 0)]);
    } catch (e) { /* ignore */ }
    return innerClose(stream);
  };
  var innerTrunc = FS.ftruncate.bind(FS);
  FS.ftruncate = function (fd, len) {
    try {
      var st = FS.getStream ? FS.getStream(fd) : null;
      __fsOps.push([Date.now() - __fsT0, "ftruncate",
        (st && st.path) ? __fsName(st.path) : ("fd" + fd), "len=" + len]);
    } catch (e) { /* ignore */ }
    return innerTrunc(fd, len);
  };
  var innerWrite = FS.write.bind(FS);
  FS.write = function (stream, buffer, offset, length, position, canOwn) {
    try {
      var path = __fsName(stream && stream.path);
      var at = position === undefined || position === null
        ? (stream.position || 0) : position;
      var last = __fsOps.length && __fsOps[__fsOps.length - 1];
      if (last && last[1] === "write" && last[2] === path && last[4] + last[5] === at) {
        last[5] += length;
      } else {
        __fsOps.push([Date.now() - __fsT0, "write", path, "", at, length]);
      }
    } catch (e) { /* ignore */ }
    return innerWrite(stream, buffer, offset, length, position, canOwn);
  };
}
`;

export function buildTracedEmulator(logPath, raw = false, ops = false,
                                    from = "wdosbox.js") {
  const src = readFileSync(join(EMU_DIST, from), "utf8");
  const marker = 'Module["FS"]=FS;';
  if (!src.includes(marker)) throw new Error("FS export not found in wdosbox.js");
  const hooked = HOOK
      .replace("__LOG__", logPath)
      .replace("__RAW__", String(raw))
      .replace("__OPS__", String(ops)) + "\n"
    + src.replace(marker, marker + "__hookFS(FS,Module);");
  const name = from === "wdosbox.js" ? TRACED_JS : TRACED_X_JS;
  writeFileSync(join(EMU_DIST, name), hooked);
  // The wasm is loaded by its own name, so the renamed js finds it unchanged.
  const wasm = from.replace(/\.js$/, ".wasm");
  if (!existsSync(join(EMU_DIST, wasm))) {
    throw new Error(`${wasm} missing beside the traced copy`);
  }
  return name;
}
