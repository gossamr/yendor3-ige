// The hooked emulator's names: what `?cheats` loads instead of the stock
// shim, and the stock/hooked pairs a build writes. The hook itself, and the
// edit that injects it into js-dos's shim, are tools/trainer_hook.js: the
// page only needs to know what to ask for.
//
// js-dos derives the wasm's URL from the shim's own, by name, so a renamed
// shim needs a renamed wasm beside it, and there is no rewriting our way out
// of that: the derivation happens in emulators.js, before the shim runs. It is
// 7.5 MB published a second time, identical to the first. The alternative is
// rewriting a second js-dos file, which is worse.

export const CHANNEL = "yendor-trainer";
export const TRAINER_JS = "wdosbox-trainer.js";
export const TRAINER_X_JS = "wdosbox-x-trainer.js";

/** The stock shim a hooked name is made from. */
export const stockShim = (name) =>
  name === TRAINER_JS ? "wdosbox.js" : "wdosbox-x.js";

/** The stock/hooked pairs a build writes or publishes. */
export const TRAINER_BUILDS = [
  ["wdosbox.js", TRAINER_JS],
  ["wdosbox-x.js", TRAINER_X_JS],
];
