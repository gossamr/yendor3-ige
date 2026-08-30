// The panel's tables, from the player's own copy, without leaving the page.
//
// Locally the server has the game and `make data` has already run, so the
// panel fetches /data/restoration.json and none of this happens. Hosted there
// is no game on the server and no data/ either, and this is what fills the
// panel in: the zip the player dropped goes to a worker running the project's
// own Python under pyodide, and comes back as the same two files the Makefile
// produces.
//
// Nothing is uploaded. The zip is read in the page, decoded in a worker in the
// page, and the result is kept in the browser's own storage.
import {
  fingerprint, loadDecoded, saveDecoded, loadPatched, savePatched,
} from "./persist.js";

let worker = null;
let next = 1;
// Everything waiting on a reply. A worker that fails to *load* never runs its
// message handler and so never answers, and a promise that is only settled by
// an answer waits for ever, which is a silent hang with nothing in the
// console, the worst way for this to fail. The pending set is what lets a
// load error reach every caller.
const pending = new Map();

function fail(err) {
  for (const [, reject] of pending) reject(err);
  pending.clear();
  // The worker is not reusable after a load error: it never started.
  worker = null;
}

function start() {
  if (worker) return worker;
  worker = new Worker(new URL("./decode.worker.js", import.meta.url),
                      { type: "module" });
  // `error` here is the worker script itself failing: a module it imports
  // that 404s, a syntax error. The event carries a message only when the
  // failure is same-origin, and everything this loads is, so say what it says.
  worker.addEventListener("error", (e) => {
    e.preventDefault();
    const where = e.filename ? ` (${e.filename}:${e.lineno})` : "";
    fail(new Error(`the decoder could not start: ${e.message || "load failed"}${where}`));
  });
  // A reply that cannot be cloned back. Not expected, since the reply is two
  // byte arrays, but it is the other way a message goes missing.
  worker.addEventListener("messageerror", () => {
    fail(new Error("the decoder's reply could not be read"));
  });
  return worker;
}

// One message at a time, in the order they were asked for.
//
// The decode starts when the player drops the zip. The patch starts when they
// press start. The decode takes about three seconds, so the press usually
// lands first. The two share this worker, its pyodide and its filesystem.
// Run together, each started the runtime and each wrote where the other was
// reading. Sequenced here, the worker does one thing at a time.
let queue = Promise.resolve();

/**
 * Decode one zip, reporting progress as it goes.
 *
 * The worker is kept between calls: starting pyodide costs about as much as
 * the decode, and a player comparing two copies should pay it once.
 */
function run(message, onProgress = () => {}) {
  const mine = queue.then(() => send(message, onProgress));
  // The queue never rejects. One failed message does not strand the messages
  // behind it. The caller still sees its own failure.
  queue = mine.then(() => {}, () => {});
  return mine;
}

function send(message, onProgress) {
  const w = start();
  const id = next++;
  return new Promise((resolve, reject) => {
    const settle = (fn) => (value) => {
      w.removeEventListener("message", listen);
      pending.delete(id);
      fn(value);
    };
    const ok = settle(resolve);
    const no = settle(reject);
    pending.set(id, no);
    const listen = (e) => {
      const msg = e.data;
      if (msg.type === "progress") return onProgress(msg);
      if (msg.id !== id) return;
      if (msg.type === "done") ok(msg.out);
      else no(new Error(msg.message));
    };
    w.addEventListener("message", listen);
    // The file contents are not transferred: cabinet.js unpacks the same zip
    // again at boot to hand DOSBox its own copy, and a transferred buffer is
    // read as empty afterwards. Structured clone copies 21 MB in a few
    // milliseconds, which is not worth the bug that transferring invites.
    w.postMessage({ id, ...message });
  });
}

/**
 * Which build a decode came from, or null when that cannot be told.
 *
 * Fetched relative to this module, so a cabinet served out of a subdirectory
 * needs no configuration, and it is a plain file at both ends: computed by
 * cabinet/serve.js locally, written by tools/build_pages.js for a host that
 * serves files and runs nothing.
 *
 * Revalidated rather than read from the browser's cache, since a stale copy of
 * this one file is the case it exists to catch. A deployment too old to carry
 * it answers 404, and then nothing can be told apart and what was kept is
 * kept: the same behavior as before there was a fingerprint at all.
 */
let decoderVersion;
async function decoderBuild() {
  if (decoderVersion !== undefined) return decoderVersion;
  decoderVersion = null;
  try {
    const res = await fetch(new URL("../decoder-version.json", import.meta.url),
                            { cache: "no-cache" });
    if (res.ok) decoderVersion = (await res.json()).decoder ?? null;
  } catch (err) {
    console.warn("could not read the decoder version:", err.message);
  }
  return decoderVersion;
}

/**
 * The decoded tables for a zip, from storage if they are there.
 *
 * `bytes` is the archive itself rather than the unpacked files, because it is
 * what identifies the copy: two zips of the same directory made a minute apart
 * are the same game, and fingerprinting the archive says so.
 *
 * The copy is half the key. The other half is the build that decoded it: the
 * payload grows fields as the decode does, and a panel handed tables from
 * before a field existed does without it and says nothing, which is how the
 * Planner tab came to be missing for anyone who had decoded their copy
 * already. A decode kept under a different fingerprint is run again.
 */
export async function decodedTables(bytes, files, onProgress = () => {}) {
  const key = fingerprint(bytes);
  const decoder = await decoderBuild();
  const kept = await loadDecoded(key, decoder);
  if (kept) {
    onProgress({ type: "progress", stage: "cached", label: "from storage",
                 fraction: 1, cached: true });
    return kept;
  }
  const out = await run({ files }, onProgress);
  const tables = {
    restoration: out["data/restoration.json"],
    worldMap: out["data/world.png"],
  };
  // A failure here is why a reload would decode again, so it is worth saying
  // out loud rather than only in a console warning: the tables are 1.2 MB on
  // top of the archive, and a browser short of room refuses the second write
  // while accepting the first.
  const kept2 = await saveDecoded(key, tables, decoder);
  if (!kept2) {
    onProgress({ type: "progress", stage: "unkept", fraction: 1,
                 label: "decoded, but too large to keep \u2014 this will run again" });
  }
  return tables;
}

/**
 * The player's executable with the cabinet's three patches applied.
 *
 * Locally the Makefile does this before the server ever serves the game, and
 * inside the container the entrypoint does it over the mounted copy. Hosted
 * there is nothing mounted to patch, so it happens here instead, on the same
 * files, with the same tools/patch.py, in the browser.
 *
 * A copy that is not the release the offsets were read from is refused by the
 * patcher rather than rewritten, so this returns the original in that case:
 * what the patches buy is the intro skipped and the attract loop stopped, and
 * neither is worth refusing to start a game over.
 */
export async function patchedExecutable(exe, key) {
  const kept = key ? await loadPatched(key) : null;
  if (kept) return { exe: kept, patched: true, fromStorage: true };
  try {
    const out = await run({ op: "patch", exe });
    if (key) await savePatched(key, out);
    return { exe: out, patched: true, fromStorage: false };
  } catch (err) {
    console.warn("the game's own patches were not applied:", err.message);
    return { exe, patched: false, why: err.message };
  }
}

/**
 * What the panel is given, and where the world map lives.
 *
 * The tables go across as text rather than a parsed object: the parent has no
 * use for them, and parsing 745 kB here only to structured-clone the result
 * into the frame would be two costs for nothing. The panel parses once.
 *
 * The world map is a blob URL because it is a 468 kB PNG behind a link in the
 * Maps tab. Inlining it as a data: URL would put 640 kB of base64 into a
 * payload that is otherwise all tables.
 */
export function asPanelPayload({ restoration, worldMap }) {
  return {
    text: new TextDecoder().decode(restoration),
    worldMap: URL.createObjectURL(new Blob([worldMap], { type: "image/png" })),
  };
}
