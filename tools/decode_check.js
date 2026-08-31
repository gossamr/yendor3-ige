// Drive the bring-your-own path end to end, in a real browser.
//
// Hosted there is no game on the server: the player drops a zip, it is
// unpacked in the page, decoded in a worker by the project's own Python under
// pyodide, and the panel is filled in from the result. Nothing is uploaded.
// This asserts all of that happens, against a zip built here from game/.
//
// `?byo` forces the page into that mode, so this runs against the development
// server, which does have the game and would otherwise never offer the drop
// zone.
//
// With --trainer it also boots the dropped copy with ?cheats, walks the menus
// to a party
// and reads it out of the running game's memory. That is the combination the
// deployments keep breaking in isolation: the hooked emulator has to be built
// into whatever is serving, the panel has to be told the flag through a frame
// that is given its src late, and the game has to come from the zip.
//
// --browser picks the engine. The page has to work in all three. The three
// disagree about storage, about workers, and about iframes. This path relies
// on all three.
//
//   bun cabinet/serve.js --port=8080 &
//   bun tools/decode_check.js --url=http://localhost:8080/ [--trainer]
//                            [--browser=chromium|firefox|webkit]
import * as playwright from "playwright";
import { readdir, readFile, rm } from "fs/promises";
import { join } from "path";
import { deflateRawSync, crc32 } from "zlib";

import { STOCK_DIR } from "../cabinet/boot.js";

const arg = (n, d) => {
  const hit = process.argv.find((a) => a.startsWith(`--${n}=`));
  return hit === undefined ? d : hit.split("=").slice(1).join("=");
};
const url = new URL(arg("url", "http://localhost:8080/"));
url.searchParams.set("byo", "1");
const engineName = arg("browser", "chromium");
const engine = playwright[engineName];
if (!engine) throw new Error(`no such browser: ${engineName}`);
const WITH_TRAINER = process.argv.includes("--trainer");
if (WITH_TRAINER) url.searchParams.set("cheats", "1");

// A zip of the game directory, made here rather than kept in the tree: the
// game is not ours to commit, and this is what a player's own archive looks
// like. Deflate, one level down, the way a file manager's "Compress" writes it
// which is the case cabinet/zip.js exists to handle.
async function zipGame(dir) {
  const names = (await readdir(dir)).filter((n) => !/^~\$|\.pif$|\.ico$/i.test(n));
  const locals = [];
  const central = [];
  let at = 0;
  for (const name of names) {
    const raw = await readFile(join(dir, name));
    const body = deflateRawSync(raw);
    const path = Buffer.from(`YENDOR3/${name}`, "latin1");
    const crc = crc32(raw);
    const head = Buffer.alloc(30);
    head.writeUInt32LE(0x04034b50, 0);
    head.writeUInt16LE(20, 4);            // version needed
    head.writeUInt16LE(8, 8);             // deflate
    head.writeUInt32LE(crc, 14);
    head.writeUInt32LE(body.length, 18);
    head.writeUInt32LE(raw.length, 22);
    head.writeUInt16LE(path.length, 26);
    locals.push(head, path, body);

    const dir_ = Buffer.alloc(46);
    dir_.writeUInt32LE(0x02014b50, 0);
    dir_.writeUInt16LE(20, 4);
    dir_.writeUInt16LE(20, 6);
    dir_.writeUInt16LE(8, 10);
    dir_.writeUInt32LE(crc, 16);
    dir_.writeUInt32LE(body.length, 20);
    dir_.writeUInt32LE(raw.length, 24);
    dir_.writeUInt16LE(path.length, 28);
    dir_.writeUInt32LE(at, 42);
    central.push(dir_, path);
    at += head.length + path.length + body.length;
  }
  const body = Buffer.concat(central);
  const end = Buffer.alloc(22);
  end.writeUInt32LE(0x06054b50, 0);
  end.writeUInt16LE(names.length, 8);
  end.writeUInt16LE(names.length, 10);
  end.writeUInt32LE(body.length, 12);
  end.writeUInt32LE(at, 16);
  return Buffer.concat([...locals, body, end]);
}

// The stock game, not the patched build the local server runs: what a player
// drops is their own retail copy, and the patches are applied in the page.
// Zipping the patched one instead makes the patcher refuse it, correctly.
const zip = await zipGame(STOCK_DIR);
console.log(`built a ${(zip.length / 1048576).toFixed(1)} MB zip from ${STOCK_DIR}`);

// So the failure shot only exists when this run failed. It outlived a passing
// run otherwise, sitting next to the success shot as if both were from now.
const shot = (how) => `tmp/decode-${how}-${engineName}.png`;
await rm(shot("failed"), { force: true });

const browser = await engine.launch();
const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });

const problems = [];
page.on("pageerror", (e) => problems.push(`pageerror: ${e.message}`));
page.on("console", (m) => { if (m.type() === "error") problems.push(`console: ${m.text()}`); });

// Anything leaving this page with the game in it would be the one thing the
// hosted deployment must never do, so watch for it rather than trusting it.
const uploads = [];
// The other direction matters too. ?byo drives the bring-your-own path against
// a server that does have the game. A route reading the server's copy would
// pass every other assertion here: the panel fills in, the tables are right,
// and none of it came from the dropped zip. The panel shell falls back to
// fetching /data/ when the host page answers with no tables of its own.
// Locally that fetch finds them.
const localData = [];
const LOCAL = /\/(game-files\.json|game\/|data\/)/;
page.on("request", (r) => {
  if (["POST", "PUT", "PATCH"].includes(r.method())) {
    uploads.push(`${r.method()} ${r.url()}`);
  }
  if (LOCAL.test(new URL(r.url()).pathname)) localData.push(r.url());
});

// The panel is reached through the parent document, not through a frame
// locator. This page gives its iframe no src and navigates it later.
// Playwright's Firefox does not follow that, and reports the frame as
// about:blank long after it has loaded. The two are same-origin, so the parent
// can see into it.
const inPanel = (fn, arg) => page.evaluate(
  ({ src, a }) => {
    const d = document.querySelector("#panel").contentDocument;
    return (0, eval)("(" + src + ")")(d, a);
  }, { src: fn.toString(), a: arg ?? null });

// Text as textContent, not innerText. Only Chromium counts the text of an
// <option> as rendered, and the monster and item lists are <select> elements.
const panelText = () => inPanel((d) => d.querySelector("main").textContent);

// Polled, not page.waitForFunction. That defaults to polling on
// requestAnimationFrame. Headless Firefox does not reliably run a frame
// callback for a page nobody is looking at. The predicate went unevaluated and
// the wait ran to its timeout, while the decode had in fact finished. The same
// decode passes here well inside the 180 seconds it was being given.
const panelSourced = async (ms) => {
  const until = Date.now() + ms;
  while (Date.now() < until) {
    const src = await page.getAttribute("#panel", "src").catch(() => null);
    if (src) return src;
    await page.waitForTimeout(250);
  }
  return null;
};

const panelReady = async (ms) => {
  const until = Date.now() + ms;
  while (Date.now() < until) {
    const n = await inPanel((d) => d?.querySelectorAll("nav button").length ?? 0)
      .catch(() => 0);
    if (n > 0) return n;
    await page.waitForTimeout(250);
  }
  return 0;
};

const fail = async (why) => {
  console.error(`DECODE CHECK FAILED: ${why}`);
  for (const p of problems) console.error("  -", p);
  await page.screenshot({ path: shot("failed") }).catch(() => {});
  await browser.close();
  process.exit(1);
};

await page.goto(url.href, { waitUntil: "domcontentloaded" });

// The drop zone is the whole of the page's offer at this point.
try {
  await page.waitForSelector("body.bring-your-own #bring-your-own", { timeout: 8000 });
} catch { await fail("the page never offered the drop zone"); }

// The panel frame must not have loaded yet: there is nothing to put in it, and
// pointing it at the shell now would paint "no decoded data yet" over the
// zone the player is being asked to use.
if (await page.getAttribute("#panel", "src")) {
  await fail("the panel frame was given a source before anything was decoded");
}

await page.evaluate((bytes) => { window.__zip = new Uint8Array(bytes); },
                   [...zip]);
await page.setInputFiles("#game-zip", {
  name: "yendor3.zip", mimeType: "application/zip", buffer: zip,
});

// The zip is read first and the game becomes startable; the decode runs on
// after that. Both have to happen.
try {
  await page.waitForSelector("#bring-your-own.chosen", { timeout: 30000 });
} catch { await fail("the zip was never accepted"); }
console.log("zip accepted, the game can be started");

let sawProgress = false;
const watch = setInterval(async () => {
  const at = await page.getAttribute("#bring-your-own", "style").catch(() => null);
  if (at && at.includes("--decode")) sawProgress = true;
}, 100);

// The decode: pyodide starts, sixteen modules load, three stages run.
if (!await panelSourced(180000)) await fail("the panel frame was never given its tables");
clearInterval(watch);

if (!await panelReady(30000)) await fail("the panel never rendered its navigation");

// Decoded content, not copy: a section that lost its data is the regression.
const CHECKS = [
  ["f2", /Wasp/],
  ["f3", /Sling Shot/],
  ["f5", /Weapons/],
];
for (const [tab, want] of CHECKS) {
  await inPanel((d, k) => d.querySelector(`nav button[data-key="${k}"]`).click(), tab);
  await page.waitForTimeout(200);
  if (!want.test(await panelText())) await fail(`the ${tab} tab did not populate (${want})`);
}
console.log("panel populated from the dropped copy");

// The three patches. Hosted there is no executable on the server to patch, so
// they are applied in the page, and a cabinet that skips the intro locally
// and sits through it hosted would be two different games.
const patched = await page.evaluate(async () => {
  const { patchedExecutable } = await import("./cabinet/decode.js");
  const zip = await import("./cabinet/zip.js");
  const files = await zip.gameFromZip(window.__zip);
  const exe = files.find((f) => f.path.toUpperCase() === "REGISTER.EXE");
  const before = exe.contents.slice();
  const out = await patchedExecutable(exe.contents, "check");
  // Again: the second answer must come from storage, not from pyodide.
  const twice = await patchedExecutable(exe.contents, "check");
  let changed = 0;
  for (let i = 0; i < before.length; i++) if (before[i] !== out.exe[i]) changed += 1;
  return { patched: out.patched, why: out.why, changed,
           keptSecondTime: twice.fromStorage === true };
});
if (!patched.patched) await fail(`the patches were not applied: ${patched.why}`);
if (!patched.changed) await fail("the patcher reported success but changed nothing");
if (!patched.keptSecondTime) {
  await fail("the patched executable was not kept; every boot would re-patch");
}
console.log(`patched the executable in the page: ${patched.changed} bytes changed, `
            + "kept for the next boot");

if (!sawProgress) console.warn("  (no progress bar was observed; the decode may have been cached)");
if (uploads.length) await fail(`the page sent the game somewhere: ${uploads.join(", ")}`);
if (localData.length) {
  await fail(`the page read the server's copy instead of the dropped one: ${
    [...new Set(localData)].join(", ")}`);
}

// The patches are optional: they are changes to a copy the player owns, and
// the toggle has to actually decide. Both settings, against the same bytes.
const both = await page.evaluate(async () => {
  const { patchedExecutable } = await import("./cabinet/decode.js");
  const zip = await import("./cabinet/zip.js");
  const files = await zip.gameFromZip(window.__zip);
  const exe = files.find((f) => f.path.toUpperCase() === "REGISTER.EXE");
  const box = document.querySelector("#patch-game");
  const out = {};
  for (const on of [true, false]) {
    box.checked = on;
    box.dispatchEvent(new Event("change"));
    const copy = files.map((f) => ({ ...f, contents: f.contents.slice() }));
    const before = copy.find((f) => f.path.toUpperCase() === "REGISTER.EXE")
                       .contents.slice();
    await window.__applyPatches(copy, "toggle-check");
    const after = copy.find((f) => f.path.toUpperCase() === "REGISTER.EXE").contents;
    let changed = 0;
    for (let i = 0; i < before.length; i++) if (before[i] !== after[i]) changed += 1;
    out[on ? "on" : "off"] = changed;
  }
  box.checked = true;
  box.dispatchEvent(new Event("change"));
  return { ...out, exeLen: exe.contents.length };
});
if (!both.on) await fail("with patches on, nothing was changed");
if (both.off) await fail(`with patches off, ${both.off} bytes were still changed`);
console.log(`patch toggle: on changes ${both.on} bytes, off changes none`);

// A reload must not ask for the zip again, and must not decode again. Both
// are kept in the browser's own storage: the archive under its own key, the
// tables under a fingerprint of it. Note there is no setInputFiles here --
// needing one would mean the copy was not kept.
const started = Date.now();
await page.reload({ waitUntil: "domcontentloaded" });
// Directly: did a decode stage run at all? Timing it is circumstantial, since a
// fast machine and a warm runtime could beat a threshold while still decoding.
// The stage labels only appear when the pipeline runs, so their absence is
// the assertion.
const decodedAgain = [];
await page.exposeFunction("__stage", (label) => decodedAgain.push(label));
await page.addInitScript(() => {
  const stages = ["drawing the maps", "reading the tables",
                  "drawing the world map"];
  const watch = () => new MutationObserver(() => {
    const t = document.querySelector("#byo-note")?.textContent || "";
    for (const s of stages) if (t.includes(s)) window.__stage?.(s);
  }).observe(document.body, { subtree: true, childList: true,
                              characterData: true });
  // An init script runs before the document has a body.
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", watch);
  } else {
    watch();
  }
});
try {
  await page.waitForSelector("#bring-your-own.chosen", { timeout: 30000 });
} catch { await fail("the browser did not remember the copy of the game"); }
if (await page.isDisabled("#boot")) {
  await fail("the game was remembered but cannot be started");
}
if (!await panelSourced(60000)) await fail("the kept tables were not used on a second visit");
const again = Date.now() - started;
if (!await panelReady(30000)) await fail("the panel never came back after the reload");
await inPanel((d) => d.querySelector('nav button[data-key="f2"]').click());
await page.waitForTimeout(200);
if (!/Wasp/.test(await panelText())) {
  await fail("the panel did not repopulate from storage");
}
await page.waitForTimeout(300);
if (decodedAgain.length) {
  await fail(`the tables were decoded again on a reload: ${[...new Set(decodedAgain)].join(", ")}`);
}
const note = await page.textContent("#byo-note");
if (/too large to keep/.test(note)) {
  await fail("the browser would not keep the tables, so every visit re-decodes");
}
console.log(`second visit: no zip asked for, no decode ran, panel up in ${(again / 1000).toFixed(1)}s`);

// What was kept has to record which build decoded it, or a player carries an
// old decode for ever: the payload grows fields as the decode does, and a
// panel handed tables from before a field existed does without it and says
// nothing. The tab that reads the newest block is simply absent.
const stamped = await page.evaluate(async () => {
  const version = await fetch("decoder-version.json", { cache: "no-cache" })
    .then((r) => (r.ok ? r.json() : null)).catch(() => null);
  // cabinet/persist.js: database "yendor3-cabinet", store "state", the tables
  // under "decoded".
  const kept = await new Promise((resolve) => {
    const open = indexedDB.open("yendor3-cabinet");
    open.onerror = () => resolve(null);
    open.onsuccess = () => {
      const db = open.result;
      if (!db.objectStoreNames.contains("state")) return resolve(null);
      const get = db.transaction("state", "readonly").objectStore("state").get("decoded");
      get.onsuccess = () => resolve(get.result || null);
      get.onerror = () => resolve(null);
    };
  });
  return { served: version && version.decoder, kept: kept && kept.decoder };
});
if (!stamped.served) {
  await fail("the server published no decoder version, so a stale decode cannot be spotted");
}
if (stamped.kept !== stamped.served) {
  await fail(`the kept tables are stamped ${JSON.stringify(stamped.kept)}, `
    + `the decoder that produced them ${JSON.stringify(stamped.served)}`);
}
console.log(`kept tables stamped with the decoder that made them: ${stamped.served}`);

// And the stamp has to be acted on. A deployment whose decoders have changed
// serves a different one, and the kept tables are then not what this build
// would produce, so they are decoded again. Standing in for a new deployment
// by answering that one file differently is the whole of the difference the
// page can see.
decodedAgain.length = 0;
await page.route("**/decoder-version.json", (route) => route.fulfill({
  contentType: "application/json",
  body: JSON.stringify({ decoder: "0000000000000000" }),
}));
await page.reload({ waitUntil: "domcontentloaded" });
if (!await panelReady(90000)) {
  await fail("the panel never came back after a decoder change");
}
await page.waitForTimeout(300);
if (!decodedAgain.length) {
  await fail("a decode kept by another build was reused rather than run again");
}
console.log(`a changed decoder re-decodes: ${[...new Set(decodedAgain)].join(", ")}`);
await page.unroute("**/decoder-version.json");

// The trainer, against the copy that was dropped. Everything above is the
// panel; this is the emulator, and it needs the hooked build to have been
// published by whatever is serving, which is the part that has no other
// check on it.
if (WITH_TRAINER) {
  const shim = await page.evaluate(async () => {
    const res = await fetch("emulators/wdosbox-x-trainer.js", { method: "HEAD" });
    return res.status;
  });
  if (shim !== 200) await fail(`the hooked emulator is not published here (${shim})`);

  const frameSrc = await page.getAttribute("#panel", "src");
  for (const flag of ["cheats", "trainer"]) {
    if (!new RegExp(`[?&]${flag}=1`).test(frameSrc)) {
      await fail(`the panel was not told about ${flag}: ${frameSrc}`);
    }
  }

  await page.click("#boot");
  await page.waitForTimeout(6000);

  // What DOSBox is actually running, read back out of the guest.
  //
  // The toggle check above patches a copy of the files. That says the patcher
  // works and says nothing about what was booted. Patching is allowed to fail:
  // the page catches it, warns, and starts the game unpatched. A broken patch
  // step therefore looked exactly like a working one. It was broken. This is
  // the assertion that would have said so.
  const guestExe = await page.evaluate(async () => {
    const walk = (node, prefix = "") => {
      for (const child of node.nodes ?? []) {
        const path = `${prefix}/${child.name}`;
        if (child.name.toUpperCase() === "REGISTER.EXE") return path;
        const found = child.nodes ? walk(child, path) : null;
        if (found) return found;
      }
      return null;
    };
    const ci = window.__cabinet.ci;
    const path = walk(await ci.fsTree());
    if (!path) return null;
    return [...await ci.fsReadFile(path.replace(/^\//, ""))];
  });
  if (!guestExe) await fail("REGISTER.EXE is not in the running game's filesystem");
  const stockExe = new Uint8Array(await readFile(join(STOCK_DIR, "REGISTER.EXE")));
  const booted = new Uint8Array(guestExe);
  let differ = 0;
  for (let i = 0; i < Math.min(booted.length, stockExe.length); i++) {
    if (booted[i] !== stockExe[i]) differ += 1;
  }
  if (booted.length !== stockExe.length) {
    await fail(`the booted executable is ${booted.length} bytes, the stock one ${stockExe.length}`);
  }
  if (!differ) await fail("DOSBox is running the unpatched executable");
  console.log(`the running game is patched: ${differ} bytes differ from the stock copy`);
  // Reaching a party takes the menu walk; booting alone stops at the main
  // menu, where the tab has nothing to read and an empty table is not a
  // failure. Same sequence as tools/trainer_check.js.
  const nap = (ms) => new Promise((r) => setTimeout(r, ms));
  const type = async (keys, gap = 700) => {
    for (const k of keys) { await page.keyboard.press(k); await nap(gap); }
  };
  await page.click("#screen").catch(() => {});
  for (let i = 0; i < 40; i++) { await page.keyboard.press("Escape"); await nap(200); }
  await type(["a"], 4000);
  await type(["6", "7", "8", "9"]);
  await type(["d"], 3000);
  await type(["e"], 14000);
  await type(["r"], 3000);

  await inPanel((d) => {
    d.querySelector('nav button[data-key="ch"]')?.click();
    d.querySelector('section[data-key="ch"] .view-picker button[data-view="trainer"]')
      ?.click();
  });
  let rows = 0;
  for (let i = 0; i < 180 && !rows; i++) {
    rows = await inPanel((d) =>
      d.querySelectorAll('section[data-key="ch"] table tbody tr').length).catch(() => 0);
    if (!rows) await page.waitForTimeout(500);
  }
  if (!rows) await fail("the trainer never read the party out of the running game");
  console.log(`trainer: ${rows} rows read out of the running game's memory`);
}

// Everything the check is about is on the screen now: the panel populated from
// the player's own copy, beside the zone that took it. Taken here rather than
// at the end, because the end is after the teardown below, which resets the
// page, and made the success shot a picture of an empty drop zone.
await page.screenshot({ path: shot("ok") });

// And forgetting it puts the page back where it started.
await page.click("#saves-toggle");
await page.click("#forget-game");
await page.waitForTimeout(200);
await page.reload({ waitUntil: "domcontentloaded" });
await page.waitForSelector("body.bring-your-own #bring-your-own", { timeout: 8000 });
if (await page.evaluate(() => document.querySelector("#bring-your-own").classList.contains("chosen"))) {
  await fail("the copy was forgotten but the page still offers to start it");
}
console.log("forgetting the copy returns the page to the drop zone");

if (problems.length) {
  console.error("DECODE CHECK FAILED: the page reported errors.");
  for (const p of problems) console.error("  -", p);
  await browser.close();
  process.exit(1);
}
console.log(`decode ok in ${engineName} - screenshot in ${shot("ok")}`);
await browser.close();
