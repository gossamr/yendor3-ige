// Decode a player's own copy of the game, in their browser.
//
// Hosted there is no game on the server and so no `data/` either: the panel's
// tables have to be produced from the zip the player dropped, on their
// machine, and never sent anywhere. What produces them is the same Python the
// Makefile runs (`tools/pack_maps.py`, `tools/extract.py`,
// `tools/world_map.py`) loaded into pyodide and run unchanged.
//
// Unchanged is the point. A second implementation in JavaScript would be a
// second thing to keep correct, and the two would drift the first time a field
// was decoded. The decoders import nothing but the standard library, so there
// is nothing to port and nothing to install: they run here as they run under
// `make data`, and produce the same bytes.
//
// This runs in a worker because the decode is about three seconds of straight
// computation. On the main thread that is three seconds of frozen cabinet.

const PYODIDE = "../pyodide/pyodide.mjs";

// Where the decoders expect to be. They read `game/WORLD.DAT` and write
// `data/*.json` relative to the working directory, so the worker builds that
// shape in the guest filesystem rather than teaching them another one.
const ROOT = "/yendor";

// What the panel needs out of it. `extract.build` also writes one file per
// payload key (enemies.json, spells.json and the rest) which are for
// reading on a developer's machine; nothing fetches them here.
const WANTED = ["data/restoration.json", "data/world.png"];

// The three game files the decoders read. Everything else in the zip is the
// executable's overlays, the saves and the batch files, which the emulator
// needs and the decoders do not, and PICTURES.VGA alone is 17 MB, so the
// less that crosses into the guest heap the better.
const NEEDED = ["WORLD.DAT", "PICTURES.VGA", "REGISTER.EXE"];

// Each stage, and what it is doing, for the progress the drop zone shows. The
// weights are measured (0.65s, 0.50s, 1.68s on a development machine) rather
// than assumed equal, so the bar does not stall on the last third.
const STAGES = [
  { key: "maps", label: "drawing the maps", weight: 0.65,
    code: "import pack_maps; pack_maps.main()" },
  { key: "tables", label: "reading the tables", weight: 0.50,
    code: "import extract; extract.build('game', 'data')" },
  { key: "world", label: "drawing the world map", weight: 1.68,
    code: "import world_map; world_map.main()" },
];
const TOTAL_WEIGHT = STAGES.reduce((n, s) => n + s.weight, 0);

// The promise, not the runtime it resolves to. The decode and the patch both
// ask for this, and their calls overlap. Holding the resolved value let both
// past the guard while the first was still starting. Both loaded pyodide, and
// the second tripped over the directories the first had made. FS.mkdir threw
// ErrnoError 20. The patch was abandoned and the game booted unpatched, with
// the failure only in a console warning.
let starting = null;

const post = (msg) => self.postMessage(msg);

/**
 * Fetch, or say which URL failed and how.
 *
 * A bare `fetch(...).json()` on a 404 throws a parse error naming neither, and
 * the deployments differ in where these files come from, computed by
 * cabinet/serve.js, static on a Pages build, node_modules inside the image.
 * When one of them is missing, which one it was is the whole diagnosis.
 */
async function get(url) {
  let res;
  try {
    res = await fetch(url);
  } catch (err) {
    throw new Error(`${url} could not be reached: ${err.message}`);
  }
  if (!res.ok) throw new Error(`${url} returned ${res.status}`);
  return res;
}

/**
 * Start the runtime and put the decoders in it.
 *
 * Kept across calls: starting pyodide is about as expensive as the whole
 * decode, so a player who drops a second zip does not pay for it twice.
 * Two overlapping callers wait on the one start rather than racing it.
 */
function runtime() {
  if (!starting) starting = startRuntime();
  return starting;
}

async function startRuntime() {
  post({ type: "progress", stage: "runtime", label: "starting the decoder",
         fraction: 0 });
  const { loadPyodide } = await import(PYODIDE);
  const pyodide = await loadPyodide({ indexURL: new URL("../pyodide/", import.meta.url).href });

  const names = await get(new URL("../decoder-files.json", import.meta.url)).then((r) => r.json());
  pyodide.FS.mkdir(ROOT);
  pyodide.FS.mkdir(`${ROOT}/tools`);
  const sources = await Promise.all(names.map(async (name) => [
    name, await get(new URL(`../tools/${name}`, import.meta.url))
            .then((r) => r.arrayBuffer()),
  ]));
  for (const [name, body] of sources) {
    pyodide.FS.writeFile(`${ROOT}/tools/${name}`, new Uint8Array(body));
  }
  pyodide.runPython(`
import sys, os
sys.path.insert(0, ${JSON.stringify(`${ROOT}/tools`)})
os.chdir(${JSON.stringify(ROOT)})
`);
  return pyodide;
}

// The three the Makefile applies, and the container's entrypoint with them:
// the intro is skipped, the main menu stops falling into its attract loop, and
// changing a character's class no longer throws the roll away. See
// tools/patch.py for what each one rewrites and why.
const PATCHES = ["force-skip-intro", "no-attract", "keep-roll-on-class-change"];

// Somewhere of its own, not `game/`. This shares a runtime with the decode,
// and the decode reads game/REGISTER.EXE in its first stage. Patching used to
// write its input there and delete it on the way out. Whichever ran second
// failed. The decode reported a FileNotFoundError from pack_maps.py.
const PATCH_DIR = `${ROOT}/patch`;

/**
 * The player's own executable, with those three applied.
 *
 * patch.py checks the md5 before it writes anything, so a copy that is not the
 * release the offsets were read from is refused rather than corrupted, which
 * is the whole reason to run the project's own patcher here rather than
 * reimplementing three byte writes in JavaScript.
 */
async function patch(exe) {
  const py = await runtime();
  ensure(py, PATCH_DIR);
  py.FS.writeFile(`${PATCH_DIR}/REGISTER.EXE`, exe);
  py.runPython(`
import patch as _patch
from pathlib import Path
_out, _done = _patch.patched_bytes(${JSON.stringify(PATCHES)},
                                   Path(${JSON.stringify(`${PATCH_DIR}/REGISTER.EXE`)}))
Path(${JSON.stringify(`${PATCH_DIR}/PATCHED.EXE`)}).write_bytes(_out)
`);
  const out = py.FS.readFile(`${PATCH_DIR}/PATCHED.EXE`);
  py.FS.unlink(`${PATCH_DIR}/PATCHED.EXE`);
  py.FS.unlink(`${PATCH_DIR}/REGISTER.EXE`);
  return out;
}

/**
 * A thrown thing as something a person can read.
 *
 * Not every rejection out of pyodide is an Error. One whose `message` was
 * itself an object reached the page as "[object Object]". That named neither
 * the failure nor where it came from.
 */
function describe(err) {
  if (typeof err === "string") return err;
  if (typeof err?.message === "string" && err.message) return err.message;
  for (const value of [err?.message, err]) {
    if (value === undefined) continue;
    try {
      const json = JSON.stringify(value);
      if (json && json !== "{}") return json;
    } catch { /* circular, or not representable */ }
  }
  return String(err);
}

/** Make a directory, tolerating one that is already there. */
function ensure(py, path) {
  try { py.FS.mkdir(path); } catch { /* exists */ }
}

/**
 * Run the pipeline over one copy of the game.
 *
 * `files` is what cabinet/zip.js hands back: the game's own directory, flat,
 * with the paths made relative to wherever SW.BAT sat in the archive.
 */
async function decode(files) {
  const py = await runtime();
  const by = new Map(files.map((f) => [f.path.toUpperCase(), f.contents]));
  const missing = NEEDED.filter((n) => !by.has(n));
  if (missing.length) throw new Error(`this copy is missing ${missing.join(", ")}`);

  ensure(py, `${ROOT}/game`);
  ensure(py, `${ROOT}/data`);
  for (const name of NEEDED) py.FS.writeFile(`${ROOT}/game/${name}`, by.get(name));

  let done = 0;
  for (const stage of STAGES) {
    post({ type: "progress", stage: stage.key, label: stage.label,
           fraction: done / TOTAL_WEIGHT });
    // Yield first, so the message above is delivered before the stage blocks
    // this thread for the whole of its run.
    await new Promise((r) => setTimeout(r, 0));
    py.runPython(stage.code);
    done += stage.weight;
  }
  post({ type: "progress", stage: "done", label: "ready", fraction: 1 });

  const out = {};
  for (const path of WANTED) out[path] = py.FS.readFile(`${ROOT}/${path}`);
  // The game's files are the largest thing in the guest heap and the decode is
  // over; a second drop writes its own.
  for (const name of NEEDED) py.FS.unlink(`${ROOT}/game/${name}`);
  return out;
}

self.onmessage = async (e) => {
  const { id, op, files, exe } = e.data;
  try {
    if (op === "patch") {
      const out = await patch(exe);
      return post({ type: "done", id, out }, [out.buffer]);
    }
    const out = await decode(files);
    post({ type: "done", id, out }, Object.values(out).map((v) => v.buffer));
  } catch (err) {
    post({ type: "failed", id, message: describe(err) });
  }
};
