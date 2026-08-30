// Shared boot path: assemble the InitFs for the game and start a backend.
//
// js-dos accepts a plain array mixing {path, contents} file entries with a
// {dosboxConf, jsdosConf} config object, so the game boots straight from the
// files on disk: there is no .jsdos bundle to build.
import { createRequire } from "module";
import { existsSync } from "fs";
import { readFile, readdir } from "fs/promises";
import { join, dirname, resolve } from "path";
import { fileURLToPath } from "url";

import { dosboxConf } from "./dosbox.conf.js";

const require = createRequire(import.meta.url);
const HERE = dirname(fileURLToPath(import.meta.url));
export const EMU_DIST = join(HERE, "node_modules/js-dos/dist/emulators/");
// Pyodide, for decoding a player's own copy in their browser. Only these five
// files are ever served: the loader, the runtime, and the standard library.
// The rest of the package is types, source maps and a REPL page.
export const PYODIDE_DIST = join(HERE, "node_modules/pyodide/");
export const PYODIDE_FILES = [
  "pyodide.mjs", "pyodide.asm.mjs", "pyodide.asm.wasm",
  "python_stdlib.zip", "pyodide-lock.json",
];
// The patched build is the default. `make patched` writes it, applying
// force-skip-intro, no-attract and keep-roll-on-class-change; see
// tools/patch.py for what each one does and why. game/ itself is never
// written to, and is used when the patched build has not been made.
//
// YENDOR_GAME_DIR overrides both, for booting some other copy.
export const STOCK_DIR = join(HERE, "..", "game");
export const PATCHED_DIR = join(HERE, "..", "tmp", "game-patched");
export const GAME_DIR = process.env.YENDOR_GAME_DIR
  ? resolve(process.env.YENDOR_GAME_DIR)
  : existsSync(join(PATCHED_DIR, "REGISTER.EXE"))
    ? PATCHED_DIR
    : STOCK_DIR;

// Files DOSBox does not need; PICTURES.VGA is 17MB and is loaded by the game
// itself, so it must be included, but editor leftovers must not be.
const SKIP = /^~\$|\.pif$|\.ico$/i;

/**
 * The game's files, or none.
 *
 * An absent directory is a supported state, not an error: served publicly
 * there is no game on the server at all, and each player supplies their own
 * copy from the browser. Letting readdir throw here turned that into a 500
 * from /game-files.json, which the page could not tell apart from a broken
 * server. Empty means "bring your own"; the caller decides what to do about
 * it.
 */
export async function gameFiles(dir = GAME_DIR) {
  if (!existsSync(dir)) return [];
  const names = (await readdir(dir)).filter((n) => !SKIP.test(n));
  return Promise.all(
    names.map(async (name) => ({
      path: name,
      contents: new Uint8Array(await readFile(join(dir, name))),
    })),
  );
}

// --- the decoder, for a browser that has to decode a player's own copy -----

const TOOLS = join(HERE, "..", "tools");

// What the browser runs, and therefore what has to be served to it.
//
// The first three are where `make data` starts. `patch` is the fourth because
// hosted there is no executable on the server to patch: the container's
// entrypoint runs tools/patch.py over a mounted copy and there is none, so the
// player's own copy is patched in their browser instead, the same three
// patches, before DOSBox is given the files. Everything these four reach is
// published; everything they do not is a solver, a capture driver or a
// disassembler, and stays on the developer's machine.
const DECODER_ENTRY = ["pack_maps", "extract", "world_map", "patch"];

// `import x` / `from x import y` in the first column. Local modules only -- a
// name is a module of ours when tools/ holds a file called that, so the
// standard library is ignored.
//
// The column matters. An indented import is inside a function and runs only if
// that function is called, which the decode may never do: combat_model imports
// spell_curve inside `spell_options`, and nothing in the pipeline calls it. The
// closure this walk produces is compared against the modules Python really
// loads (tests/test_decoder.py), so publishing one that is never imported
// fails as surely as missing one that is.
const IMPORT = /^(?:import|from)[ \t]+([A-Za-z_]\w*)/gm;

/**
 * The modules the browser is given, and nothing else in tools/.
 *
 * Walked rather than listed, because a list goes stale silently: a module that
 * grows an import would simply be missing in the browser, and the failure
 * would arrive as a ModuleNotFoundError in a worker. `tests/test_decoder.py`
 * holds this against the closure Python itself produces when it imports the
 * three entry points, so the two cannot drift.
 */
export async function decoderFiles(dir = TOOLS) {
  const local = new Set(
    (await readdir(dir))
      .filter((n) => n.endsWith(".py"))
      .map((n) => n.slice(0, -".py".length)),
  );
  const seen = new Set(DECODER_ENTRY);
  const queue = [...DECODER_ENTRY];
  while (queue.length) {
    const stem = queue.pop();
    const src = await readFile(join(dir, `${stem}.py`), "utf8");
    for (const [, name] of src.matchAll(IMPORT)) {
      if (name !== stem && local.has(name) && !seen.has(name)) {
        seen.add(name);
        queue.push(name);
      }
    }
  }
  return [...seen].sort().map((stem) => `${stem}.py`);
}


/**
 * Switches worth passing whenever a human is not watching.
 *
 * `/NOM` and `/NOS` are the game's own no-music and no-sound-effects switches
 * (see the parser at image 0x1e56). Audio is pointless for headless capture and
 * costs host CPU, and turning it off *this* way is safe: it is a supported code
 * path, unlike setting `sbtype=none` in the DOSBox config, which hangs the game
 * on its second splash screen.
 *
 * `/P` is deliberately not included. It is the original developers' switch,
 * and what it turns on is a debug mode, not an intro skip: among its twelve
 * readers is one that bypasses the level check on training. Walls stop
 * clipping under it, so a build running with it is not one to play, and the
 * intro is skipped by the force-skip-intro patch instead.
 *
 * A driver that wants the debug mode asks for it: `make patched-debug`, then
 * YENDOR_GAME_DIR=tmp/game-debug and YENDOR_ARGS=/P, which skips the intro
 * on its own, so that build carries no force-skip-intro. No-clip is a short
 * way to walk a capture across a map, and the training bypass reaches a screen
 * a fresh party cannot.
 */
/** The page without its HTML comments.
 *
 * The comments explain markup decisions to whoever edits the file, and they
 * are of no use to a reader of the page. Anything served to a player is passed
 * through this, so the notes stay in the source and stop at the door.
 */
export function withoutComments(html) {
  return html.replace(/^[ \t]*<!--[\s\S]*?-->\n?/gm, "")
             .replace(/<!--[\s\S]*?-->/g, "");
}

export const HEADLESS_ARGS = "/NOM /NOS";

export async function loadEmulators() {
  require(join(EMU_DIST, "emulators.js"));
  const emulators = globalThis.emulators;
  emulators.pathPrefix = EMU_DIST;
  return emulators;
}

export async function initFs(opts = {}) {
  return [
    ...(await gameFiles()),
    { dosboxConf: dosboxConf(opts), jsdosConf: { version: "8.4.1" } },
  ];
}
