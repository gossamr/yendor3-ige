// Cut tools/ down to the decoder the browser runs.
//
// Hosted, the panel is filled in by running the project's own Python in the
// player's browser against the copy they brought. That needs the closure of
// `make data`'s three entry points, sixteen of the forty-seven modules in
// tools/, and nothing else. The rest are the instruments the decode was
// found with: the disassembler, the OCR, the solvers, the verifiers and the
// capture drivers. They read screenshots and memory dumps, they are no use on
// a server, and an image is not where they belong.
//
// Run in a build stage of its own, so what is left out is absent from the
// image rather than deleted in a later layer of it. An image's history is as
// public as its contents.
//
//   bun docker/prune-decoders.js [--tools=tools]
import { readdir, rm } from "fs/promises";
import { join, resolve, dirname } from "path";
import { fileURLToPath } from "url";

import { decoderFiles } from "../cabinet/boot.js";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const arg = (n, d) =>
  (process.argv.find((a) => a.startsWith(`--${n}=`)) || "").split("=")[1] ?? d;
const TOOLS = resolve(ROOT, arg("tools", "tools"));

const keep = new Set(await decoderFiles(TOOLS));
if (keep.size === 0) {
  console.error("prune: the decoder walk found nothing, refusing to empty tools/");
  process.exit(1);
}

let dropped = 0;
for (const name of await readdir(TOOLS)) {
  if (keep.has(name)) continue;
  await rm(join(TOOLS, name), { recursive: true, force: true });
  dropped += 1;
}

// A module the walk reached but the directory does not have would leave the
// browser stopping at a ModuleNotFoundError inside a worker, a long way from
// the import that caused it. Better to fail the build.
const left = new Set(await readdir(TOOLS));
const missing = [...keep].filter((n) => !left.has(n));
if (missing.length) {
  console.error(`prune: ${missing.join(", ")} is in the closure but not in ${TOOLS}`);
  process.exit(1);
}

console.log(`decoder: kept ${keep.size} modules, dropped ${dropped}`);
