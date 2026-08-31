// Build a copy of js-dos's emulator that answers questions about the guest's
// memory, for the cabinet's trainer.
//
//   bun tools/build_trainer.js          # writes wdosbox*-trainer.js
//
// The same seam tools/trace_fs.js uses: the emulator's JavaScript is
// rewritten with a hook injected where `Module` is in scope, and `Module.HEAPU8`
// is the guest's RAM. What differs is where it runs and what it needs:
//
//   * That hook runs in this process and writes files. This one runs in a web
//     worker, where there is no `fs` and no way for the page to reach the
//     worker's globals, since js-dos owns the Worker object, not us.
//   * So it talks over a BroadcastChannel instead, which is same-origin and
//     needs no reference: the page opens the same channel by name and asks.
//     That also reaches the clue-book iframe, which is where the trainer's
//     panel lives.
//
// Structured clone moves about a gigabyte a second, and the largest thing the
// trainer reads at once is the 12 KB monster table, so the channel is not the
// constraint and a SharedArrayBuffer would buy nothing, which matters,
// because a SharedArrayBuffer needs cross-origin isolation and the cabinet
// deliberately runs without it.
//
// The transform itself is cabinet/trainer.js, because cabinet/serve.js
// synthesizes the same thing on demand: `?cheats` needs no build step
// against a running server. This writes the files, which is what a driver
// booting js-dos outside a browser needs (see tools/trainer_check.js).
import { copyFileSync, readFileSync, writeFileSync, existsSync } from "fs";
import { join } from "path";

import { EMU_DIST } from "../cabinet/boot.js";
import { CHANNEL, HOOK, TRAINER_JS, TRAINER_X_JS, trainerShim } from "../cabinet/trainer.js";

export { CHANNEL, HOOK, TRAINER_JS, TRAINER_X_JS };

/** Write the hooked copy of one emulator shim. Returns its filename. */
export function buildTrainerEmulator(from = "wdosbox-x.js") {
  const hooked = trainerShim(readFileSync(join(EMU_DIST, from), "utf8"), from);
  const name = from === "wdosbox.js" ? TRAINER_JS : TRAINER_X_JS;
  writeFileSync(join(EMU_DIST, name), hooked);
  // js-dos derives the wasm's URL from the shim's, by name, so a renamed shim
  // needs a renamed wasm. That derivation is in emulators.js and happens
  // before the shim runs, so there is no rewriting our way out of it: the copy
  // is the price of the hook.
  const wasm = from.replace(/\.js$/, ".wasm");
  if (!existsSync(join(EMU_DIST, wasm))) {
    throw new Error(`${wasm} missing beside the trainer copy`);
  }
  copyFileSync(join(EMU_DIST, wasm), join(EMU_DIST, name.replace(/\.js$/, ".wasm")));
  return name;
}

if (import.meta.main) {
  for (const from of ["wdosbox.js", "wdosbox-x.js"]) {
    console.log(`wrote ${buildTrainerEmulator(from)}`);
  }
}
