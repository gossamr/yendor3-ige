// Is the cabinet's storage actually on disk, and does it survive a browser restart?
//
// "It uses IndexedDB" is not an answer to that: IndexedDB is disk-backed but
// evictable, and a claim about durability is worth nothing unless the browser
// has actually been closed and reopened. So this drives a real Chromium with a
// real profile directory: write, quit the browser, start it again against the
// same profile, and read back. It also looks in the profile on the host
// filesystem for the files the browser wrote, which is the part no in-page API
// can tell you.
//
//   bun cabinet/serve.js &
//   bun tools/persist_check.js [--url=http://localhost:8080/] [--profile=tmp/profile]
import { chromium } from "playwright";
import { mkdirSync, rmSync, existsSync, readdirSync, statSync } from "fs";
import { join } from "path";

const arg = (n, d) => {
  const hit = process.argv.find((a) => a.startsWith(`--${n}=`));
  return hit === undefined ? d : hit.split("=").slice(1).join("=");
};
const url = arg("url", "http://localhost:8080/");
const profile = arg("profile", "tmp/profile");
const problems = [];

rmSync(profile, { recursive: true, force: true });
mkdirSync(profile, { recursive: true });

const launch = () => chromium.launchPersistentContext(profile, {});

/** Bytes on the host filesystem under the profile's IndexedDB directory. */
function storedOnDisk() {
  const root = join(profile, "Default", "IndexedDB");
  if (!existsSync(root)) return { dirs: [], bytes: 0 };
  const dirs = readdirSync(root).filter((d) => d.includes("localhost"));
  let bytes = 0;
  for (const d of dirs) {
    const at = join(root, d);
    for (const f of readdirSync(at)) {
      const s = statSync(join(at, f));
      if (s.isFile()) bytes += s.size;
    }
  }
  return { dirs, bytes };
}

const PAYLOAD = "ZORBAX";
// The imported file has to be one the cabinet keeps. CURGAME is not: the game
// truncates and rewrites all 81,037 bytes of it at every launch, so
// persist.js filters it out on the way in and on the way out, and a check that
// imported one would be asserting that storage drops what it is told to drop.
const IMPORTED = "SAVGAME1";

// --- first run: write something we can recognize ---------------------------
{
  const ctx = await launch();
  const page = await ctx.newPage();
  await page.goto(url, { waitUntil: "domcontentloaded" });

  const result = await page.evaluate(async ({ name, file }) => {
    const p = await import("/cabinet/persist.js");
    const r = await import("/cabinet/roster.js");
    // A roster with one character in slot 1, and a save file beside it, so
    // both of the things the cabinet stores are covered.
    const roster = new Uint8Array(r.SLOTS * r.SLOT);
    roster.set(new TextEncoder().encode(name), r.SLOT);
    await p.saveRoster(roster);
    await p.importBundle({
      format: "yendorian-tales-3-cabinet",
      version: 1,
      files: { [file]: btoa("an imported save") },
      roster: null,
    });
    // Export, wipe, re-import: the export is the only copy that survives the
    // user clearing site data, so it has to actually round-trip.
    const bundle = await p.exportBundle();
    await p.clearFiles();
    await p.clearRoster();
    const emptied = (await p.loadRoster()) === null && (await p.loadFiles()).length === 0;
    const restored = await p.importBundle(JSON.parse(JSON.stringify(bundle)));

    // A save while the game is running must not throw away what is stored but
    // not yet on the emulated disk. An import is exactly that: it lands in
    // storage and reaches the disk at the next boot, so a save that replaced
    // the record erased it before the player got there.
    const ci = {
      fsTree: async () => ({ name: ".", nodes: [{ name: "SAVGAME2", size: null }] }),
      fsReadFile: async () => new Uint8Array(1234).fill(7),
    };
    await p.saveNow(ci, new Map());
    const afterSave = (await p.loadFiles()).map((f) => f.path).sort();

    const persistence = await p.requestPersistence();
    const estimate = await p.storageEstimate();
    return {
      persistence,
      usage: estimate?.usage ?? null,
      emptied,
      restored,
      afterSave,
      roundTripped: r.slotsOf(await p.loadRoster()).map((s) => s.name),
    };
  }, { name: PAYLOAD, file: IMPORTED });

  if (!result.emptied) problems.push("clearing storage left something behind");
  if (!result.roundTripped.includes(PAYLOAD)) {
    problems.push(`export/import lost the roster (got ${JSON.stringify(result.roundTripped)})`);
  }
  if (!result.restored.files) problems.push("export/import lost the save files");
  if (!result.afterSave.includes(IMPORTED)) {
    problems.push(`a save dropped an imported file (stored: ${JSON.stringify(result.afterSave)})`);
  }
  if (!result.afterSave.includes("SAVGAME2")) {
    problems.push(`a save did not store what the game wrote (stored: ${JSON.stringify(result.afterSave)})`);
  }
  console.log(`stored after a save: ${JSON.stringify(result.afterSave)}`);
  console.log(`export round trip: ${result.restored.files} file(s), `
    + `roster ${JSON.stringify(result.roundTripped)}`);

  console.log(`persistent storage: supported=${result.persistence.supported} `
    + `granted=${result.persistence.persisted}`);
  if (result.usage !== null) console.log(`reported usage: ${result.usage} bytes`);
  await ctx.close();
}

// --- the browser is now gone; what is left on the host? --------------------
const onDisk = storedOnDisk();
console.log(`profile IndexedDB: ${onDisk.dirs.length} origin dir(s), ${onDisk.bytes} bytes`);
if (!onDisk.dirs.length) {
  problems.push("nothing under the profile's IndexedDB directory: this is not on disk");
}
if (onDisk.bytes === 0) problems.push("the origin's IndexedDB directory is empty");

// --- second run: a different browser process, same profile -----------------
{
  const ctx = await launch();
  const page = await ctx.newPage();
  await page.goto(url, { waitUntil: "domcontentloaded" });

  const back = await page.evaluate(async () => {
    const p = await import("/cabinet/persist.js");
    const r = await import("/cabinet/roster.js");
    const roster = await p.loadRoster();
    const files = await p.loadFiles();
    return {
      roster: roster ? r.slotsOf(roster).map((s) => s.name) : null,
      files: files.map((f) => `${f.path}:${f.contents.length}`),
      persisted: await navigator.storage.persisted(),
    };
  });

  console.log(`after restart: roster=${JSON.stringify(back.roster)} `
    + `files=${JSON.stringify(back.files)} persisted=${back.persisted}`);

  if (!back.roster?.includes(PAYLOAD)) {
    problems.push(`the kept roster did not survive the restart (got ${JSON.stringify(back.roster)})`);
  }
  if (!back.files.length) problems.push("saved files did not survive the restart");
  await ctx.close();
}

if (problems.length) {
  console.error("\npersistence check failed:");
  for (const p of problems) console.error(`  - ${p}`);
  process.exit(1);
}
console.log("\npersistence ok - written to disk and read back by a new browser process");
