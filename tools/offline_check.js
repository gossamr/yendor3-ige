// Prove the installed cabinet runs with no network once it has run with one.
//
//   bun tools/offline_check.js [--out=tmp/offline]
//
// The static site is built and served as a host with no game would serve it.
// A copy of the game is dropped in, decoded, and booted, which fetches every
// file the page needs and lets the service worker keep each one. Then the
// browser is cut off and the page reloaded: it must come back from the
// worker's copy, the game from storage, and boot to a picture.
import * as playwright from "playwright";
import { readdir, readFile, mkdir } from "fs/promises";
import { join, extname, resolve } from "path";
import { deflateRawSync, crc32 } from "zlib";

import { STOCK_DIR } from "../cabinet/boot.js";

const arg = (n, d) => {
  const hit = process.argv.find((a) => a.startsWith(`--${n}=`));
  return hit === undefined ? d : hit.split("=").slice(1).join("=");
};
const outDir = arg("out", "tmp/offline");
await mkdir(outDir, { recursive: true });
const SITE = resolve("tmp/offline/site");
const PORT = Number(arg("port", "8091"));

// The site, as tools/build_pages.js writes it.
const build = Bun.spawn(["bun", "tools/build_pages.js", `--out=${SITE}`], { stdout: "inherit", stderr: "inherit" });
if (await build.exited !== 0) { console.error("the pages build failed"); process.exit(1); }

// A static host: files and nothing else, so a request for a game file or a
// live-reload stream is a 404 the way it is on Pages.
const TYPES = { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8", ".json": "application/json", ".wasm": "application/wasm",
  ".py": "text/x-python", ".png": "image/png", ".svg": "image/svg+xml", ".ico": "image/x-icon",
  ".webmanifest": "application/manifest+json", ".conf": "text/plain", ".woff": "font/woff" };
let served = 0;
const servedPaths = new Set();
const server = Bun.serve({
  port: PORT, hostname: "127.0.0.1",
  async fetch(req) {
    let path = decodeURIComponent(new URL(req.url).pathname);
    if (path === "/") path = "/index.html";
    const file = Bun.file(join(SITE, path));
    if (!(await file.exists())) return new Response("not found", { status: 404 });
    served += 1;
    servedPaths.add(path);
    return new Response(file, { headers: { "content-type": TYPES[extname(path)] ?? "application/octet-stream" } });
  },
});
const url = `http://127.0.0.1:${PORT}/`;

// The player's copy, zipped the way a file manager zips a folder.
async function zipGame(dir) {
  const names = (await readdir(dir)).filter((n) => !/^~\$|\.pif$|\.ico$/i.test(n));
  const locals = [], central = [];
  let at = 0;
  for (const name of names) {
    const raw = await readFile(join(dir, name));
    const body = deflateRawSync(raw);
    const path = Buffer.from(`YENDOR3/${name}`, "latin1");
    const crc = crc32(raw);
    const head = Buffer.alloc(30);
    head.writeUInt32LE(0x04034b50, 0); head.writeUInt16LE(20, 4); head.writeUInt16LE(8, 8);
    head.writeUInt32LE(crc, 14); head.writeUInt32LE(body.length, 18); head.writeUInt32LE(raw.length, 22);
    head.writeUInt16LE(path.length, 26);
    locals.push(head, path, body);
    const d = Buffer.alloc(46);
    d.writeUInt32LE(0x02014b50, 0); d.writeUInt16LE(20, 4); d.writeUInt16LE(20, 6); d.writeUInt16LE(8, 10);
    d.writeUInt32LE(crc, 16); d.writeUInt32LE(body.length, 20); d.writeUInt32LE(raw.length, 24);
    d.writeUInt16LE(path.length, 28); d.writeUInt32LE(at, 42);
    central.push(d, path);
    at += head.length + path.length + body.length;
  }
  const body = Buffer.concat(central);
  const end = Buffer.alloc(22);
  end.writeUInt32LE(0x06054b50, 0); end.writeUInt16LE(names.length, 8); end.writeUInt16LE(names.length, 10);
  end.writeUInt32LE(body.length, 12); end.writeUInt32LE(at, 16);
  return Buffer.concat([...locals, body, end]);
}
const zip = await zipGame(STOCK_DIR);
console.log(`built a ${(zip.length / 1048576).toFixed(1)} MB zip from ${STOCK_DIR}`);
await Bun.write(`${outDir}/game.zip`, zip);

const problems = [];
const fail = (m) => { problems.push(m); console.error("  -", m); };
const browser = await playwright.chromium.launch();
const context = await browser.newContext({ viewport: { width: 1280, height: 800 } });
const page = await context.newPage();
page.on("pageerror", (e) => fail(`pageerror: ${e.message}`));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const colors = () => page.evaluate(() => {
  const c = document.querySelector("#screen");
  const d = c.getContext("2d").getImageData(0, 0, c.width, c.height).data;
  const s = new Set(); for (let i = 0; i < d.length; i += 4 * 37) s.add((d[i]<<16)|(d[i+1]<<8)|d[i+2]); return s.size;
});
const painted = async (limit) => { const t0 = Date.now(); while (Date.now() - t0 < limit) { await sleep(2000); if (await colors().catch(() => 0) > 4) return true; } return false; };
const panelReady = async (limit) => {
  const t0 = Date.now();
  while (Date.now() - t0 < limit) {
    const ok = await page.evaluate(() => {
      const f = document.querySelector("#panel");
      // Rendered from tables, not the shell alone: the shell has six tabs and
      // no map names.
      return !!(f && f.contentDocument && f.contentDocument.querySelectorAll("nav button").length >= 5
        && /Dwarven Homeland|Acoknight/.test(f.contentDocument.body.textContent));
    }).catch(() => false);
    if (ok) return true;
    await sleep(500);
  }
  return false;
};

// --- online: everything fetched once ---------------------------------------
await page.goto(url, { waitUntil: "domcontentloaded" });
const sw = await page.evaluate(() => navigator.serviceWorker.ready.then((r) => !!r.active).catch(() => false));
if (!sw) fail("no service worker took the page");
await page.setInputFiles("#game-zip", { name: "yendor3.zip", mimeType: "application/zip", buffer: zip });
try { await page.waitForSelector("#bring-your-own.chosen", { timeout: 30000 }); } catch { fail("the zip was never accepted"); }
if (!await panelReady(240000)) fail("the clue book was never decoded from the dropped copy");
else console.log("decoded and the clue book populated, online");
await page.click("#boot");
if (!await painted(180000)) fail("the game never painted, online");
else console.log("the game painted, online");
await sleep(3000);
const kept = await page.evaluate(async () => {
  const names = await caches.keys();
  const out = {};
  for (const n of names) out[n] = (await (await caches.open(n)).keys()).map((r) => new URL(r.url).pathname);
  return out;
});
const cached = Object.values(kept).flat();
console.log(`the worker keeps ${cached.length} files`);
// Everything the visit fetched has to be in the cache, since any of it
// could be what the next visit needs.
for (const p of servedPaths) {
  if (p === "/sw.js") continue;   // the registration holds the worker itself
  const key = p === "/index.html" ? "/" : p;
  if (!cached.includes(key) && !cached.includes(p)) fail(`served online but not kept by the worker: ${p}`);
}
if (!cached.some((p) => /^\/emulators\/.*\.wasm$/.test(p))) fail("no emulator wasm kept by the worker");
if (!cached.some((p) => /^\/pyodide\//.test(p))) fail("no pyodide kept by the worker");
console.log(`served ${served} files online`);

// --- offline: the same page, from the worker and storage --------------------
//
// The server is stopped as well as the browser told it is offline: the
// worker's own fetches are not all covered by the browser's switch, and a
// server that is gone is what offline is.
await context.setOffline(true);
server.stop(true);
const before = served;
const asked = [];
page.on("request", (r) => { if (!r.url().startsWith("data:")) asked.push(new URL(r.url()).pathname); });
await page.reload({ waitUntil: "domcontentloaded" }).catch((e) => fail(`the page did not load offline: ${e.message}`));
await sleep(1500);
if (!(await page.evaluate(() => document.body.classList.contains("bring-your-own")).catch(() => false))) {
  fail("offline, the page did not come up as the hosted cabinet");
}
try { await page.waitForSelector("#bring-your-own.chosen", { timeout: 30000 }); console.log("offline: the stored copy is offered"); }
catch { fail("offline, the stored copy of the game was not offered"); }
if (!await panelReady(60000)) fail("offline, the clue book did not populate from storage");
else console.log("offline: the clue book populated from storage");
await page.click("#boot");
if (!await painted(180000)) fail("offline, the game never painted");
else console.log("offline: the game painted");
await page.screenshot({ path: `${outDir}/offline.png` });
if (served !== before) fail(`the server was asked for ${served - before} files while offline`);
console.log(`offline, the page asked for ${asked.length} files, all answered locally`);

await browser.close();
if (problems.length) { console.error(`OFFLINE CHECK FAILED: ${problems.length} problem(s)`); process.exit(1); }
console.log("offline check passed");
