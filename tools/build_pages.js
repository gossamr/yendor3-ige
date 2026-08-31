// Assemble the static site: everything the cabinet needs, and no game.
//
// The hosted deployment has no application server. Three of the five routes
// cabinet/serve.js answers are about a game the server does not have, one is
// live reload, and the last is static files, so a bucket or GitHub Pages
// serves this as well as a running process would, and cannot receive a copy
// of anyone's game because there is nothing there to receive it.
//
//   bun tools/build_pages.js [--out=build/pages]
//
// Deliberately absent: game/, data/, the observations folder,
// web/restoration.html. tests/test_distribution.py fails the build if any of
// it creeps in.
import { cp, mkdir, rm, writeFile, readFile, readdir, stat } from "fs/promises";
import { join, resolve, dirname } from "path";
import { fileURLToPath } from "url";

import { dosboxConf } from "../cabinet/dosbox.conf.js";
import { EMU_DIST, PYODIDE_DIST, PYODIDE_FILES, decoderFiles,
         decoderFingerprint, withoutComments } from "../cabinet/boot.js";
import { TRAINER_BUILDS, trainerShim } from "../cabinet/trainer.js";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const arg = (name, fallback) =>
  (process.argv.find((a) => a.startsWith(`--${name}=`)) || "").split("=")[1] ?? fallback;
const OUT = resolve(ROOT, arg("out", "build/pages"));

// cabinet/ holds the page's own code next to the things that run it here: the
// development server, and the drivers that boot it headlessly. Only the code
// the browser loads is published.
const SERVER_ONLY = /^(serve|session|capture|drive|probe|boot)\.js$|\.test\.js$/;

await rm(OUT, { recursive: true, force: true });
await mkdir(join(OUT, "cabinet"), { recursive: true });
await mkdir(join(OUT, "web"), { recursive: true });

// The page. index.html is the site root here, where serve.js maps / onto it.
//
// og:url has to be an absolute address, and only the deployment knows its own.
// SITE_URL carries it in, so the tag is written for the deployment that has a
// fixed address and left out everywhere else, rather than pointing every copy
// of the page at one of them. The Pages workflow reads the value from
// actions/configure-pages, which reports a custom domain correctly.
{
  let page = await readFile(join(ROOT, "cabinet/index.html"), "utf8");
  const site = (process.env.SITE_URL ?? "").trim();
  if (site) {
    const url = site.endsWith("/") ? site : site + "/";
    const anchor = '<meta property="og:title"';
    if (!page.includes(anchor)) throw new Error("index.html has no og:title to anchor og:url to");
    page = page.replace(anchor,
      `<meta property="og:url" content="${url}">\n` + anchor);
  }
  await writeFile(join(OUT, "index.html"), withoutComments(page));
}

for (const name of await readdir(join(ROOT, "cabinet"))) {
  if (SERVER_ONLY.test(name) || !/\.(js|css)$/.test(name)) continue;
  await cp(join(ROOT, "cabinet", name), join(OUT, "cabinet", name));
}

for (const name of ["panel.html", "panel.css", "panel.js"]) {
  await cp(join(ROOT, "web", name), join(OUT, "web", name));
}

// The emulator, at the path cabinet.js resolves to relative to itself.
//
// Any copy `make trainer` left in the source directory is filtered out and
// rebuilt below, so what is published is a function of this script rather than
// of what happened to be lying around.
await cp(EMU_DIST, join(OUT, "emulators"), {
  recursive: true,
  filter: (from) => !/-trainer\.(js|wasm)$/.test(from),
});

// The hooked emulator, which is what `?cheats` loads. Written here rather
// than copied, because a static host cannot generate it and the page cannot
// either: js-dos refuses an emulator whose filename does not start with "w"
// after the last slash, so it has to be a real file with a real name.
//
// The wasm goes with it: js-dos derives the wasm's URL from the shim's name,
// in emulators.js and before the shim runs, so a renamed shim needs a renamed
// wasm. That is 9 MB published a second time, identical to the first, and it
// is what `?cheats` costs on a host that cannot generate anything.
for (const [stock, hooked] of TRAINER_BUILDS) {
  const src = await readFile(join(EMU_DIST, stock), "utf8");
  await writeFile(join(OUT, "emulators", hooked), trainerShim(src, stock));
  await cp(join(EMU_DIST, stock.replace(/\.js$/, ".wasm")),
           join(OUT, "emulators", hooked.replace(/\.js$/, ".wasm")));
}

// Nothing generates this on a static host, and the page fetches it at boot.
await writeFile(join(OUT, "dosbox.conf"), dosboxConf());

// The decoder: pyodide, and the Python that runs in it. There is no data/ on
// a static host and no executable to patch either, so this is both halves of
// what a server would otherwise have done: the player's own copy is decoded
// and patched in their browser, by the same modules `make data` and
// `make patched` run.
//
// Only the closure of the three entry points is published. The rest of tools/
// is solvers, capture drivers, the disassembler and the verifiers: development
// instruments that read screenshots and memory dumps, and have no business on
// a public host. `cabinet/boot.js` walks the imports so the line between the
// two is computed rather than remembered.
await mkdir(join(OUT, "pyodide"), { recursive: true });
for (const name of PYODIDE_FILES) {
  await cp(join(PYODIDE_DIST, name), join(OUT, "pyodide", name));
}
await mkdir(join(OUT, "tools"), { recursive: true });
const decoders = await decoderFiles();
for (const name of decoders) {
  await cp(join(ROOT, "tools", name), join(OUT, "tools", name));
}
await writeFile(join(OUT, "decoder-files.json"), JSON.stringify(decoders));
// What produced a decode, for telling a kept one apart from what this build
// would produce now. A flat file on a flat host: the page fetches it beside
// the list above, and nothing here has to be served by a program.
await writeFile(join(OUT, "decoder-version.json"),
                JSON.stringify({ decoder: await decoderFingerprint() }));

// game-files.json is deliberately not written. Its absence is how the page
// works out that there is no game here and asks the player for theirs.

// GitHub Pages runs Jekyll by default, which drops files and directories whose
// names begin with an underscore. The emulator ships some.
await writeFile(join(OUT, ".nojekyll"), "");

let bytes = 0, count = 0;
const walk = async (dir) => {
  for (const name of await readdir(dir)) {
    const p = join(dir, name);
    const s = await stat(p);
    if (s.isDirectory()) await walk(p);
    else { bytes += s.size; count += 1; }
  }
};
await walk(OUT);
console.log(`${OUT}: ${count} files, ${(bytes / 1048576).toFixed(1)} MB, no game data`);
console.log(`  decoder: ${decoders.length} of ${
  (await readdir(join(ROOT, "tools"))).filter((n) => n.endsWith(".py")).length
} python modules: the decode, and the patcher the page applies`);
