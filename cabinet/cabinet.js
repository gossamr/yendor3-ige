// The cabinet: js-dos running the game beside the Restoration panel.
//
// Built on the `emulators` package directly rather than the js-dos player,
// because the player does not hand back the CommandInterface, and the
// CommandInterface is the whole point here. It is what exposes fsTree() and
// fsReadFile(), which is how the overlay reads the game's state: js-dos has no
// guest-memory API, so the emulated filesystem is the only channel.
import { KEY_CODES } from "./keymap.js";
import { BUTTONS, DOM_BUTTONS, MOUSE_SCALE, HOME } from "./keys.js";
import { startAudio } from "./audio.js";
import { calibrate, fallbackTransform, retryDelay, locateCursor } from "./mouse.js";
import { Taps, mountTouchKeys, mountTyper } from "./touch.js";
import {
  loadFiles, startAutosave, fingerprint, notKeptReason, putFile, diskPaths,
  loadRoster, saveRoster, requestPersistence, storageEstimate,
  exportBundle, importBundle, loadGame, saveGame, clearGame,
} from "./persist.js";
import { graft, rosterOf, slotsOf, looksLikeWorld, CREATED, SAVE_SIZE } from "./roster.js";
import { gameFromZip } from "./zip.js";
import { TRAINER_JS, TRAINER_X_JS } from "./trainer.js";
import { decodedTables, asPanelPayload, patchedExecutable } from "./decode.js";

// The emulator runtime, at one URL that resolves the same way everywhere.
//
// Relative to this module rather than to the site root: served from a project
// page the whole site sits under a path prefix, and an absolute "/emulators/"
// would walk off the top of it. This module is at <base>/cabinet/cabinet.js, so
// "../emulators/" is <base>/emulators/ wherever <base> happens to be.
//
// Locally serve.js maps that path onto cabinet/node_modules; a static build
// copies the files there. Neither side has to rewrite anything.
const EMU = new URL("../emulators/", import.meta.url).href;

// Off unless asked for by name. `?cheats` opens the panel's Cheats tab, which
// holds the trainer and the save editor.
//
// The two are not available in the same places. The save editor reads the save
// files this page is holding and needs nothing of the emulator, so it works
// wherever the cabinet does. The trainer reads and writes the running game's
// memory, which needs a second copy of js-dos's shim that `make trainer`
// writes beside the stock one, and the container installs js-dos from the
// lockfile without it. Asking for it where it does not exist used to set the
// emulator to a filename that 404s and put a tab in the panel with nothing
// behind it. So availability is checked once, and everything downstream reads
// the answer rather than the flag. The frame is told both through showPanel(),
// because at this point it has no src to rewrite: it is given one only when
// there is something to put in it.
const CHEATS = new URLSearchParams(location.search).has("cheats");
let trainerReady = false;

// Whether the pointer is a finger. Decided once from the media query rather
// than from the first event, because the keys have to be on the screen before
// anything is touched. `?touch` forces it, which is how tools/mobile_check.js
// drives the layout in a desktop browser.
const TOUCH = new URLSearchParams(location.search).has("touch")
  || (window.matchMedia && matchMedia("(pointer: coarse)").matches);
document.body.classList.toggle("touch", TOUCH);
// An iPhone, by name: it has no full screen for a page, and its browser
// scrolls a page that runs taller than the window however the page asks it
// not to, so the clue book starts put away there.
const IPHONE = /iPhone|iPod/.test(navigator.userAgent) || navigator.standalone === true;
document.body.classList.toggle("iphone", IPHONE);

async function trainerAvailable() {
  if (!CHEATS) return false;
  try {
    if ((await fetch(EMU + TRAINER_X_JS, { method: "HEAD" })).ok) return true;
  } catch { /* fall through */ }
  say("no trainer build here \u2014 running the stock emulator");
  return false;
}

const $ = (s) => document.querySelector(s);
const canvas = $("#screen");
const status = $("#status");

// Deliberately lazy: a canvas that has ever had a rendering context cannot be
// transferred to a worker, and transferring is the path we want.
let ctx = null;

const say = (m) => { status.textContent = m; };

let ci = null;
let image = null;
let audio = null;
let autosave = null;
// Whether pauseWhenAway has stopped the emulator. Read by
// tools/away_check.js. A stalled frame counter cannot tell a page that stopped
// the game from a browser that stopped painting it.
let paused = false;
let bootFingerprints = new Map();

async function loadEmulators() {
  await new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = EMU + "emulators.js";
    s.onload = resolve;
    s.onerror = () => reject(new Error(`could not load ${s.src}`));
    document.head.append(s);
  });
  window.emulators.pathPrefix = EMU;
  return window.emulators;
}

async function gameFiles() {
  const manifest = await (await fetch("game-files.json")).json();
  return Promise.all(manifest.map(async (name) => ({
    path: name,
    contents: new Uint8Array(await (await fetch(`/game/${name}`)).arrayBuffer()),
  })));
}

/**
 * Where this page's copy of the game comes from.
 *
 * Two deployments, and the page works out which it is in rather than being
 * told: the server lists the game files it holds, and an empty list means it
 * holds none. Served publicly there is no game on the server at all and each
 * player brings their own; run locally the files are right there and asking
 * for them again would be a pointless ceremony.
 *
 * So the drop zone appears only when there is nothing to drop it beside.
 */
const BRING_YOUR_OWN = { zip: null, name: null };
let hosted = false;

/**
 * The panel's tables, once there are any, as the text the frame asked for.
 *
 * Held as text rather than parsed: this page has no use for them, and parsing
 * 745 kB here only to serialize it again into the frame is two costs for
 * nothing. Null until a copy has been decoded, which is the state a local run
 * stays in: there the panel fetches /data/ and never asks.
 */
const PANEL = { text: null, worldMap: null };

// Installed before the frame is ever given a source, so every ask has an
// answer and the panel settles on a reply rather than on its timeout.
window.addEventListener("message", (e) => {
  const frame = $("#panel");
  if (!frame || e.source !== frame.contentWindow) return;
  if (!e.data) return;
  if (e.data.type === "restoration?") {
    e.source.postMessage(
      { type: "restoration", text: PANEL.text, worldMap: PANEL.worldMap }, "*");
    return;
  }
  if (SAVE_ASKS[e.data.type]) answerSaveAsk(e.source, e.data);
});

// --- the save files, for the panel's save editor ---------------------------
//
// The editor is in the panel and the save files are here, so it asks. It could
// open the same IndexedDB itself, since it is the same origin, but then two
// files would know the store's name and the shape of what is in it, and only
// this one owns the emulated disk. So the panel gets three asks and no
// knowledge of where a save lives.
//
// Which copy of a save is the real one depends on whether the game is running.
// The emulator's disk is what the game's LOAD reads, so while there is a game
// that is the copy to edit; with none, storage holds what the next boot will
// put on the disk. A write goes to both, so the edit survives either way.

const SAVE_SLOTS = [1, 2, 3, 4, 5, 6];        // docs/saves.md: SAVGAME1-6
const SAVE_PATH = /^SAVGAME[1-6]$/;

/** The caption the player typed at the save, from the roster's header slot. */
const saveCaption = (bytes) => {
  const end = bytes.indexOf(0);
  return new TextDecoder("latin1")
    .decode(bytes.slice(0, end < 0 || end > 25 ? 25 : end))
    .replace(/[^\x20-\x7e]/g, "").trim();
};

/** The save slots the emulated disk is holding, by name. */
async function onDisk() {
  if (!ci) return new Set();
  try {
    return new Set((await diskPaths(ci))
      .map((path) => path.split("/").pop().toUpperCase())
      .filter((name) => SAVE_PATH.test(name)));
  } catch (err) {
    console.warn("could not read the emulated disk:", err.message);
    return new Set();
  }
}

async function readSave(path) {
  if ((await onDisk()).has(path)) return ci.fsReadFile(path);
  const hit = (await loadFiles()).find((f) => f.path.toUpperCase() === path);
  if (!hit) throw new Error(`${path} is not here`);
  return hit.contents;
}

/** Every slot that exists, on the disk or in storage, with its caption. */
async function listSaves() {
  const stored = new Map((await loadFiles())
    .map((f) => [f.path.toUpperCase(), f.contents]));
  const disk = await onDisk();
  const out = [];
  for (const n of SAVE_SLOTS) {
    const path = `SAVGAME${n}`;
    const bytes = disk.has(path) ? await ci.fsReadFile(path) : stored.get(path);
    if (!bytes) continue;
    out.push({ path, size: bytes.length, caption: saveCaption(bytes),
               where: disk.has(path) ? "on the disk" : "stored" });
  }
  return out;
}

/**
 * Write a save back, to the disk the game reads and to the browser's storage.
 *
 * Both, because they answer different questions. The disk is what LOAD opens,
 * so an edit that only reached storage would do nothing until the next boot;
 * storage is what the next boot restores, so an edit that only reached the
 * disk would be lost with the tab. The autosave copies the disk into storage
 * anyway, and writing it here is what makes the editor work with the emulator
 * switched off.
 */
async function writeSave(path, bytes) {
  if (!SAVE_PATH.test(path)) throw new Error(`${path} is not a save slot`);
  if (bytes.length !== SAVE_SIZE) {
    throw new Error(`a save is ${SAVE_SIZE.toLocaleString()} bytes, not ${bytes.length}`);
  }
  const wrote = [];
  if (ci) {
    // A copy, because the emulator takes the buffer rather than borrowing it:
    // js-dos transfers it into the worker, which detaches it here, and the
    // write below would then be storing a buffer that is no longer there.
    await ci.fsWriteFile(path, bytes.slice());
    wrote.push("the disk");
  }
  await putFile(path, bytes);
  wrote.push("storage");
  return wrote.join(" and ");
}

const SAVE_ASKS = {
  "saves?": async () => ({ type: "saves", saves: await listSaves() }),
  "save-read": async (m) => ({ type: "save", bytes: await readSave(m.path) }),
  "save-write": async (m) => ({ type: "saved", wrote: await writeSave(m.path, m.bytes) }),
};

/** Answer one ask, and answer it even when it failed: the panel is waiting. */
async function answerSaveAsk(source, m) {
  let reply;
  try {
    reply = await SAVE_ASKS[m.type](m);
  } catch (err) {
    reply = { type: "save-error", error: err.message };
  }
  source.postMessage({ ...reply, id: m.id }, "*");
}

/** Point the panel frame at the shell, or reload it if it is already there.
 *
 * The frame carries `data-src` rather than `src`. Hosted, the panel's tables
 * are decoded from the player's own copy inside this page, so the frame is
 * given its source only once there is an answer for it to ask for. Locally
 * this function sets it immediately, and the panel fetches /data/ as before.
 */
function showPanel() {
  const frame = $("#panel");
  if (!frame) return;
  const url = new URL(frame.dataset.src, location.href);
  // The Cheats tab lives in this frame. It is told twice over, because its two
  // halves need different things: the save editor asks this page for the save
  // files, and the trainer talks to the emulator over a channel both open, so
  // the second flag goes only where there is a hooked emulator to answer it.
  if (CHEATS) url.searchParams.set("cheats", "1");
  if (trainerReady) url.searchParams.set("trainer", "1");
  url.searchParams.set("t", String(Date.now()));
  frame.src = url.pathname + url.search;
}

async function detectMode() {
  // Hosted unless the server affirmatively lists a game. A static host --
  // GitHub Pages or a bucket, has no endpoint to answer with, so the fetch
  // 404s or returns a page of HTML that will not parse; both mean there is no
  // game here and the player has to bring one. Reading a failure as "local"
  // instead sent boot() off to fetch files that do not exist.
  //
  // Being wrong this way is harmless: the worst case is offering a drop zone
  // beside a game that was there all along. Wrong the other way is a dead page.
  // ?byo forces it, which is the only way to reach the bring-your-own path on
  // a machine that has the game: tools/decode_check.js drives it against the
  // development server, where game-files.json answers with a full list.
  //
  // The drop zone in the markup is shown only where this returns true, which
  // is to say only where the server holds no game.
  if (new URLSearchParams(location.search).has("byo")) {
    hosted = true;
  } else {
    try {
      const manifest = await (await fetch("game-files.json")).json();
      hosted = !Array.isArray(manifest) || manifest.length === 0;
    } catch {
      hosted = true;
    }
  }
  document.body.classList.toggle("bring-your-own", hosted);
  if (hosted) {
    $("#boot").disabled = true;
    say("no game on this server \u00b7 choose your copy to begin");
  }
  return hosted;
}

/**
 * What the drop zone says, and what clicking it does.
 *
 * The zone is the only thing on the screen at this point, so it has to carry
 * the whole exchange: what to do, whether the last attempt worked, and where
 * the game starts. Once a copy is accepted it becomes the start button --
 * a player who has just dropped a file is looking at the zone, not at the
 * header.
 */
function offerZip(state, title, note) {
  const zone = $("#bring-your-own");
  if (!zone) return;
  zone.classList.toggle("chosen", state === "chosen");
  zone.classList.toggle("failed", state === "failed");
  zone.setAttribute("aria-label",
    state === "chosen" ? "Start the game" : "Choose your copy of the game");
  $("#byo-title").textContent = title;
  $("#byo-note").textContent = note;
}

/**
 * Decode the player's copy and give the panel its tables.
 *
 * Runs after the zone has already said the game can be started, because it
 * can: the emulator needs the zip, not the decode. Somebody who wants to play
 * clicks through while this is still going, and the clue book is populated by
 * the time they look at it.
 *
 * A failure here is reported and nothing else: the cabinet is a game with a
 * clue book beside it, and a clue book that could not be built is not a reason
 * to withhold the game.
 */
async function fillPanel(bytes, files, summary, caveat = "") {
  const zone = $("#bring-your-own");
  const note = $("#byo-note");
  const settled = note ? note.textContent : "";
  try {
    let fromStorage = false;
    const tables = await decodedTables(bytes, files, ({ label, fraction, cached }) => {
      if (cached) fromStorage = true;
      if (note) {
        note.textContent =
          `${summary}. Clue book: ${label} \u00b7 ${Math.round(fraction * 100)}%`;
      }
      if (zone) zone.style.setProperty("--decode", `${fraction * 100}%`);
      say(`clue book: ${label}`);
    });
    const payload = asPanelPayload(tables);
    PANEL.text = payload.text;
    PANEL.worldMap = payload.worldMap;
    showPanel();
    if (note) note.textContent = settled;
    if (zone) zone.style.removeProperty("--decode");
    say(`${summary} \u00b7 ready, clue book ${fromStorage ? "from storage" : "decoded"}${caveat}`);
  } catch (err) {
    // On the page for the player, and in the console for whoever is asked
    // about it: this runs three deployments deep (a worker, inside pyodide,
    // over files served three different ways) and the message is the only
    // thing that says which layer gave way.
    console.error("clue book: the decode failed.", err);
    if (note) note.textContent = `${settled} The clue book could not be built: ${err.message}`;
    if (zone) zone.style.removeProperty("--decode");
    say(`clue book: ${err.message}`);
  }
}

/**
 * Bring back the copy the browser is already holding.
 *
 * Hosted, the drop zone's job is to get a copy of the game into this page --
 * and once it has one, asking again on every reload is asking for something it
 * already has. So a stored copy is unpacked, checked and offered as the start
 * button, exactly as a fresh drop would be, and the zone says which copy and
 * how to replace it.
 *
 * Unpacked rather than trusted: a stored archive can be from an older release
 * of the cabinet, or half-written, and finding that out here is better than
 * booting to a DOS prompt.
 */
async function restoreGame() {
  const saved = await loadGame();
  if (!saved) return false;
  try {
    const files = await gameFromZip(saved.zip);
    BRING_YOUR_OWN.zip = saved.zip;
    BRING_YOUR_OWN.name = saved.name;
    $("#boot").disabled = false;
    const summary = `${saved.name} \u00b7 ${files.length} files \u00b7 `
      + `${(saved.zip.length / 1048576).toFixed(1)} MB`;
    offerZip("chosen", "Start the game",
      `${summary}, kept in this browser. Click here or the power button above. `
      + "Drop another zip to use a different copy.");
    say(`${summary} \u00b7 ready`);
    // The tables are keyed by a fingerprint of this same archive, so this is
    // a read rather than another decode.
    await fillPanel(saved.zip, files, summary);
    return true;
  } catch (err) {
    // A copy that no longer unpacks is worse than none: it would sit there as
    // a start button that cannot start. Drop it and ask again.
    console.warn("the stored copy could not be read:", err.message);
    await clearGame();
    return false;
  }
}

/**
 * Take a player's zip, without it ever leaving the page.
 *
 * The bytes are unpacked here rather than handed to js-dos as a bundle, so a
 * zip that does not hold the game is named as such now instead of booting to a
 * DOS prompt. The archive itself is kept and unpacked again at boot: the
 * unpacked buffers are transferred to the worker and read as empty afterwards,
 * so a second attempt needs its own copy.
 */
async function acceptZip(file) {
  if (!file) return;
  BRING_YOUR_OWN.zip = null;
  BRING_YOUR_OWN.name = null;
  $("#boot").disabled = true;
  offerZip("reading", "Reading\u2026", file.name);
  say(`reading ${file.name}\u2026`);
  try {
    const bytes = new Uint8Array(await file.arrayBuffer());
    const files = await gameFromZip(bytes);
    BRING_YOUR_OWN.zip = bytes;
    BRING_YOUR_OWN.name = file.name;
    $("#boot").disabled = false;
    const summary = `${file.name} \u00b7 ${files.length} files \u00b7 `
      + `${(file.size / 1048576).toFixed(1)} MB`;

    // The game can be started now; the clue book is filled in from the same
    // files, which takes a few seconds. Say so as it goes: the zone is the
    // only thing on the screen at this point, so it is where the progress has
    // to appear.
    offerZip("chosen", "Start the game",
      `${summary}. Click here or the power button above. Drop another zip to `
      + "use a different copy.");
    say(`${summary} \u00b7 ready`);
    // Keep it, so the next visit starts the game rather than asking for it
    // again. Hosted this is the only copy of the game there is: the server has
    // none, and a browser that already holds one should not send the player
    // back to the file picker.
    const kept = await saveGame(bytes, file.name);
    await fillPanel(bytes, files, summary,
                    kept ? "" : " (too large to keep in this browser)");
  } catch (err) {
    offerZip("failed", "That zip cannot be used",
      `${file.name}: ${err.message}. Drop another zip, or click to choose one.`);
    say(`${file.name}: ${err.message}`);
  }
}

function paint(rgb) {
  if (!ctx) ctx = canvas.getContext("2d", { alpha: false });
  const w = ci.width(), h = ci.height();
  if (!image || image.width !== w || image.height !== h) {
    canvas.width = w;
    canvas.height = h;
    image = ctx.createImageData(w, h);
  }
  const out = image.data;
  for (let i = 0, j = 0; i < rgb.length; i += 3, j += 4) {
    out[j] = rgb[i]; out[j + 1] = rgb[i + 1]; out[j + 2] = rgb[i + 2]; out[j + 3] = 255;
  }
  ctx.putImageData(image, 0, 0);
}



// How to turn a canvas pixel into a value for sendMouseMotion.
//
// Measured at runtime by mouse.js rather than assumed: the mapping is neither a
// 0..1 fraction of the screen nor constant across video modes. Null until the
// first successful calibration; recalculated whenever the mode changes.
let transform = null;
let calibrating = false;
let frames = 0;

/**
 * Frame differencing needs a still screen, so calibration can legitimately
 * fail: on an animated one it finds the game's redraws instead of the
 * cursor. The fallback mapping keeps the mouse usable meanwhile, and a few
 * spaced-out retries pick up a real measurement once the screen settles.
 *
 * One good reading holds for the session: the mapping is a pure function of
 * the value sent, so there is nothing to correct for afterwards. That makes a
 * failed attempt pure cost, which is why the retries back off and then stop --
 * see RETRY_BACKOFF in mouse.js.
 */
let failures = 0;
let nextAttempt = 0;

async function ensureCalibrated() {
  if (calibrating || !ci) return;
  // A finger has no pointer to align with, and a tap places the cursor by
  // homing it (see wireInput), so nothing is measured on a touch screen.
  if (TOUCH) return;
  const sized = transform && transform.width === canvas.width
    && transform.height === canvas.height;
  if (sized && !transform.approximate) return;
  // A video mode change invalidates the measurement rather than repeating a
  // failure, so it starts the schedule over rather than inheriting its state.
  if (!sized) { failures = 0; nextAttempt = 0; }
  if (retryDelay(failures) === null && failures) return;
  if (Date.now() < nextAttempt) return;
  calibrating = true;
  try {
    if (!ctx) ctx = canvas.getContext("2d", { alpha: false });
    const result = await calibrate(ci, canvas, ctx);
    if (result) {
      transform = result;
      failures = 0;
      say("running \u00b7 mouse aligned");
    } else {
      transform = fallbackTransform(canvas);
      failures += 1;
      const again = retryDelay(failures);
      say(again === null
        ? "running \u00b7 mouse approximate"
        : "running \u00b7 mouse approximate, realigning");
      // Measured from the end of the attempt, not the start: an attempt can
      // outlast a delay measured from when it began, which is what let this
      // run back-to-back on every pointer entry.
      nextAttempt = Date.now() + (again ?? 0);
    }
  } finally {
    calibrating = false;
  }
}

function wireInput() {
  canvas.tabIndex = 0;
  canvas.addEventListener("click", () => canvas.focus());
  const send = (e, pressed) => {
    const code = KEY_CODES[e.code];
    if (code === undefined) return;
    e.preventDefault();
    ci.sendKeyEvent(code, pressed);
  };
  canvas.addEventListener("keydown", (e) => send(e, true));
  canvas.addEventListener("keyup", (e) => send(e, false));

  // Mouse.
  //
  // The plain DOSBox backend never delivers coordinates to this game: the
  // cursor stays pinned at the origin whatever is sent, and js-dos's own v7 and
  // v8 players behave identically, so it is not this integration. DOSBox-X does
  // respond, but only with mouse_emulation=always, and on a scale and origin
  // that have to be measured. See mouse.js.

  /** Where the pointer is, in canvas pixels. */
  const target = (e) => {
    const r = canvas.getBoundingClientRect();
    const scale = Math.min(r.width / canvas.width, r.height / canvas.height);
    const w = canvas.width * scale;
    const h = canvas.height * scale;
    const x = (e.clientX - (r.left + (r.width - w) / 2)) / scale;
    const y = (e.clientY - (r.top + (r.height - h) / 2)) / scale;
    return {
      x: Math.max(0, Math.min(canvas.width - 1, x)),
      y: Math.max(0, Math.min(canvas.height - 1, y)),
    };
  };

  // Motion is coalesced to one send per frame, and a position equal to the one
  // already sent is not sent again.
  //
  // DOSBox drains a 32-slot mouse queue at about one event every 5ms and drops
  // what overflows, so a stream of motion can swallow a button press behind
  // it. A double click is two presses with a hand's worth of jitter between
  // them, which is exactly that case: every double click that works headlessly
  // here sends its second press bare, with no motion in front of it (session
  // `dclick`, tools/capture_legend.js). This is the same thing for a pointer.
  let pending = null;   // canvas pixels waiting to be sent
  let scheduled = 0;    // requestAnimationFrame handle, 0 when idle
  let sent = null;      // the last value handed to sendMouseMotion

  const sendMotion = () => {
    scheduled = 0;
    if (!pending || !transform) return;
    const [gx, gy] = transform.toSend(pending.x, pending.y);
    pending = null;
    if (sent && sent[0] === gx && sent[1] === gy) return;
    sent = [gx, gy];
    window.__cabinet.lastSent = sent;
    window.__cabinet.mouseEvents += 1;
    ci.sendMouseMotion(gx, gy);
  };

  /** Send the pending position now, rather than on the next frame. */
  const flush = () => {
    if (scheduled) cancelAnimationFrame(scheduled);
    sendMotion();
  };

  const move = (e) => {
    if (!transform) { ensureCalibrated(); return; }
    pending = target(e);
    if (!scheduled) scheduled = requestAnimationFrame(sendMotion);
  };

  // Browser button numbers are not DOSBox's: see BUTTONS in keys.js.
  const button = (e) => DOM_BUTTONS[e.button] ?? BUTTONS.left;

  canvas.addEventListener("mouseenter", ensureCalibrated);
  canvas.addEventListener("mousemove", move);
  canvas.addEventListener("mousedown", (e) => {
    e.preventDefault();
    canvas.focus();
    // Until the mapping is known a press lands wherever the guest cursor
    // happens to be sitting, which is not where it was aimed. Ask for the
    // measurement instead of clicking somewhere at random.
    if (!transform) { ensureCalibrated(); return; }
    move(e);
    flush();
    ci.sendMouseButton(button(e), true);
  });
  canvas.addEventListener("mouseup", (e) => {
    e.preventDefault();
    if (!transform) return;
    move(e);
    flush();
    ci.sendMouseButton(button(e), false);
  });
  canvas.addEventListener("contextmenu", (e) => e.preventDefault());

  // Touch.
  //
  // A finger is read by Taps into the mouse actions the game understands, and
  // each is sent here. The pointer events are taken before the browser makes
  // mouse events out of them, so the handlers above never see a touch.
  // A gesture that began on one of the keys laid over the game's own
  // controls: a tap is the key, and anything else, a hold, a second finger,
  // an armed Right, is the click it would have been on the game beneath.
  let keyUnderFinger = null;
  const taps = new Taps((a) => {
    const key = keyUnderFinger;
    if (a.type === "tap" || a.type === "press" || a.type === "release") keyUnderFinger = null;
    if (key && a.type === "tap" && a.button === BUTTONS.left) { pressKey(key); return; }
    touchAction(a);
  });
  const finger = (e) => e.pointerType === "touch" || e.pointerType === "pen";
  const at = (e) => ({ id: e.pointerId, x: e.clientX, y: e.clientY, t: e.timeStamp });
  const overGame = () => matchMedia("(orientation: landscape) and (max-height: 520px)").matches;
  const touchRoot = $("#touch");
  touchRoot.addEventListener("pointerdown", (e) => {
    const b = e.target.closest(".touch-actions button.touch-key");
    if (!b || !finger(e) || !overGame()) return;
    e.preventDefault();
    e.stopPropagation();   // not the key's own down: the gesture decides
    keyUnderFinger = b;
    b.classList.add("down");
    try { b.setPointerCapture(e.pointerId); } catch { /* the canvas finishes it */ }
    taps.down(at(e));
  }, true);
  for (const [type, go] of [["pointermove", "move"], ["pointerup", "up"], ["pointercancel", "cancel"]]) {
    touchRoot.addEventListener(type, (e) => {
      const b = e.target.closest?.(".touch-actions button.touch-key");
      if (!b || !finger(e) || !overGame() || !taps.active) return;
      e.stopPropagation();
      if (type !== "pointermove") b.classList.remove("down");
      taps[go](at(e));
    }, true);
  }
  canvas.addEventListener("pointerdown", (e) => {
    if (!finger(e)) return;
    e.preventDefault();
    canvas.focus({ preventScroll: true });
    taps.down(at(e));
  });
  // The touch itself is canceled as well as the pointer event: on an iPhone
  // a held touch starts a selection and its callout whatever the pointer
  // event said, and only a canceled touchstart stops it.
  canvas.addEventListener("touchstart", (e) => e.preventDefault(), { passive: false });
  canvas.addEventListener("pointermove", (e) => { if (finger(e)) taps.move(at(e)); });
  canvas.addEventListener("pointerup", (e) => { if (finger(e)) taps.up(at(e)); });
  canvas.addEventListener("pointercancel", (e) => { if (finger(e)) taps.cancel(at(e)); });
  touchTaps = taps;

  // Sent one after another: a double click is two presses in order.
  let queue = Promise.resolve();
  const later = (ms) => new Promise((r) => setTimeout(r, ms));
  // A tap is placed the way the headless drivers place a click, in
  // keys.js: the cursor is driven into the top-left corner with a delta
  // larger than the screen, then stepped out to the spot. The absolute
  // motion the mouse path sends is not a position to the guest: it reaches
  // the driver as the difference from the last one sent, so it is right
  // only while the cursor is where the last send left it, and a tap after
  // the game had moved the cursor itself landed a screen away. Homing
  // starts every tap from a known place, whatever happened in between.
  // The guest moves MOUSE_SCALE pixels per unit of delta, and the homed
  // cursor rests at HOME rather than at the corner.
  const place = async (a) => {
    const p = target({ clientX: a.x, clientY: a.y });
    if (!ctx) ctx = canvas.getContext("2d", { alpha: false });
    const read = () => ctx.getImageData(0, 0, canvas.width, canvas.height).data;
    const nearHome = (t) => Math.abs(t.x - HOME.x) <= 6 && Math.abs(t.y - HOME.y) <= 6;
    // Read frames until the arrow's tip is found where `want` says, or the
    // time is up. The guest draws at its own pace, and on a slow phone two
    // deltas sent a few tens of milliseconds apart reached the driver as
    // one: the homing plus the step summed to a move that still clamped at
    // the corner, and the tap landed there. So each move is sent only once
    // the frame shows the one before it drawn.
    const seen = async (before, want, ms = 900) => {
      const until = Date.now() + ms;
      while (Date.now() < until) {
        await later(40);
        const found = locateCursor(read(), before, canvas.width, canvas.height, 150, 400);
        if (found && want(found)) return found;
      }
      return null;
    };
    const before = read();
    ci.sendMouseRelativeMotion(-4000, -4000);
    const homed = await seen(before, nearHome, 1500);
    const corner = read();
    ci.sendMouseRelativeMotion(Math.round((p.x - HOME.x) / MOUSE_SCALE),
                               Math.round((p.y - HOME.y) / MOUSE_SCALE));
    window.__cabinet.mouseEvents += 1;
    window.__cabinet.lastSent = [p.x, p.y];
    // Where the arrow rests after homing moves with the video mode, by a
    // line or two, so once it is drawn at its new place the cursor is
    // nudged the rest of the way. A screen that hides the arrow gets the
    // press as aimed, and soon: the wait is long only where the arrow was
    // seen arrive at the corner, which says it will be seen leave it.
    const tip = await seen(homed ? corner : before, (t) => !nearHome(t), homed ? 2500 : 300);
    window.__cabinet.lastNudge = null;
    if (tip) {
      const dx = p.x - tip.x, dy = p.y - tip.y;
      window.__cabinet.lastNudge = [dx, dy];
      if (Math.abs(dx) > 1 || Math.abs(dy) > 1) {
        const nudged = read();
        ci.sendMouseRelativeMotion(Math.round(dx / MOUSE_SCALE), Math.round(dy / MOUSE_SCALE));
        await seen(nudged, () => true, 400);
      }
    }
    // The press never goes on the heels of a move: the driver takes the
    // queue one event at a time.
    await later(80);
    return p;
  };
  let fingerAt = null;   // canvas pixel the cursor was last put at by a finger
  // Between gestures the arrow rests in the far corner, where only its tip
  // shows: a cursor sitting where the last tap was is a pointer the phone
  // does not have, over whatever the player is looking at. A tap homes the
  // cursor anyway, so where it waited does not matter to the next one.
  let parkTimer = 0;
  const park = () => {
    parkTimer = 0;
    if (!ci || taps.active) return;
    ci.sendMouseRelativeMotion(4000, 4000);
    fingerAt = null;
  };
  const parkLater = () => {
    clearTimeout(parkTimer);
    parkTimer = setTimeout(park, PARK_AFTER);
  };
  parkLater();
  function touchAction(a) {
    clearTimeout(parkTimer);
    queue = queue.then(async () => {
      if (!ci) return;
      if (a.type === "move") {
        // A drag follows the finger by the distance it moved.
        const p = target({ clientX: a.x, clientY: a.y });
        if (fingerAt) {
          ci.sendMouseRelativeMotion(Math.round((p.x - fingerAt.x) / MOUSE_SCALE),
                                     Math.round((p.y - fingerAt.y) / MOUSE_SCALE));
        } else {
          await place(a);
        }
        fingerAt = p;
        return;
      }
      if (a.type === "release") { ci.sendMouseButton(a.button, false); return; }
      // The second click of a double click carries no motion: the guest
      // drops the pair if any arrives between the presses.
      if (!a.again) fingerAt = await place(a);
      ci.sendMouseButton(a.button, true);
      if (a.type === "press") return;
      // Held long enough for a slow guest to see it down. The game reads
      // the button's state as it goes round its loop, and on a phone one
      // turn of that loop can outlast a 60 ms click, which then never
      // happened as far as the game could tell.
      await later(TAP_HOLD);
      ci.sendMouseButton(a.button, false);
      await later(40);
      window.__cabinet.taps += 1;
    }).catch((err) => console.warn("touch:", err.message))
      .then(parkLater);
    armRight(false);
  }
}

/** How long a tap holds the button down. */
const TAP_HOLD = 160;
/** How long after the last gesture the cursor goes back to its corner. */
const PARK_AFTER = 4000;

// The finger's gesture reader, once wireInput has made one, so the on-screen
// right-button key can arm it.
let touchTaps = null;
const rightKey = () => document.querySelector('#touch button[data-action="right"]');
function armRight(on) {
  const b = rightKey();
  if (b) b.setAttribute("aria-pressed", String(on || !!touchTaps?.holdButton));
}

/**
 * The on-screen keys, and the device's keyboard behind one of them.
 *
 * Mounted at load rather than at boot so the strip is there to look at, and
 * a key does nothing until there is a game to send it to. Codes are the
 * KeyboardEvent.code names the keymap already translates.
 */
// The pad is on until put away and stays as it was left: the game draws its
// own arrows and its own A, S, C and D, but at a phone's size they are small
// for a thumb, and the party keys have no button in the game at all.
// Stored only when the key is pressed, so what is remembered is a choice.
const PAD_KEY = "cabinet.game-keys";
function showPad(on, remember = false) {
  $("#touch .touch-game").hidden = !on;
  syncPadKey();
  if (remember) {
    try { localStorage.setItem(PAD_KEY, on ? "on" : "off"); } catch { /* storage off */ }
  }
}
/** The Pad key lit only while the keys are on the screen. */
function syncPadKey() {
  const game = $("#touch .touch-game");
  const key = $('#touch button[data-action="pad"]');
  if (!game || !key) return;
  key.setAttribute("aria-pressed", String(!game.hidden && getComputedStyle(game).display !== "none"));
}

/**
 * Where the drawn game's left and right edges are within the stage, as the
 * two variables the landscape overlay is placed by. The canvas is the full
 * height there and the game keeps its own shape inside it, so the edges
 * move with the window and with the video mode.
 */
function fitTouchOverlay() {
  const touch = $("#touch");
  const stage = $("#stage");
  if (!touch || !stage) return;
  const r = canvas.getBoundingClientRect();
  const s = stage.getBoundingClientRect();
  const scale = Math.min(r.width / canvas.width, r.height / canvas.height);
  const w = canvas.width * scale, h = canvas.height * scale;
  const x = r.left - s.left + (r.width - w) / 2, y = r.top - s.top + (r.height - h) / 2;
  for (const [name, value] of [["x", x], ["y", y], ["w", w], ["h", h]]) {
    touch.style.setProperty(`--game-${name}`, `${Math.round(value)}px`);
  }
}

/** Press and release one of the drawn keys, held long enough to be seen. */
function pressKey(button) {
  const codes = (button.dataset.keys ?? "").split(" ").filter(Boolean);
  for (const c of codes) sendTouchKey(c, true);
  setTimeout(() => { for (const c of codes.slice().reverse()) sendTouchKey(c, false); }, 120);
}
let sendTouchKey = () => {};

function wireTouchKeys() {
  const root = $("#touch");
  fitTouchOverlay();
  window.addEventListener("resize", () => { fitTouchOverlay(); syncPadKey(); });
  // The canvas changes size without the window doing so: shown at boot, or
  // a phone's bars coming and going.
  if (window.ResizeObserver) new ResizeObserver(fitTouchOverlay).observe(canvas);
  matchMedia("(orientation: landscape)").addEventListener("change", () => setTimeout(fitTouchOverlay, 50));
  const sendKey = (code, down) => {
    const key = KEY_CODES[code];
    if (key === undefined || !ci) return;
    ci.sendKeyEvent(key, down);
    window.__cabinet.keys += 1;
  };
  sendTouchKey = sendKey;
  const typer = mountTyper($("#typer"), {
    sendKey,
    onClose: () => { $("#touch").classList.remove("typing"); },
  });
  mountTouchKeys(root, {
    sendKey,
    onAction: (action, button, e) => {
      if (action === "keyboard") {
        // focus() from inside the gesture is what brings the keyboard up.
        $("#touch").classList.add("typing");
        typer.open();
      } else if (action === "pad") {
        showPad(root.querySelector(".touch-game").hidden, true);
      } else if (action === "drawer") {
        const drawer = root.querySelector(".touch-drawer");
        drawer.hidden = !drawer.hidden;
        button.setAttribute("aria-pressed", String(!drawer.hidden));
      } else if (action === "right") {
        if (!touchTaps) return;
        // Armed for the next tap on the press; held down, every tap is a
        // right click until the key is let go.
        touchTaps.button = BUTTONS.right;
        touchTaps.holdButton = true;
        armRight(true);
        const up = () => {
          touchTaps.holdButton = false;
          armRight(touchTaps.button === BUTTONS.right);
          button.removeEventListener("pointerup", up);
          button.removeEventListener("pointercancel", up);
        };
        button.addEventListener("pointerup", up);
        button.addEventListener("pointercancel", up);
        try { button.setPointerCapture(e.pointerId); } catch { /* releases on pointerup anyway */ }
      }
    },
  });
  let padWanted = true;
  try { padWanted = localStorage.getItem(PAD_KEY) !== "off"; } catch { /* storage off */ }
  showPad(padWanted);
}


/**
 * Show what the game has written, and which of it is being kept.
 *
 * Rendered from the list a save already produced rather than fetched on its
 * own: working it out means reading the emulated disk, and doing that twice to
 * show the same answer twice is the sort of thing that makes a readout cost
 * more than it tells you. Saying why a file is not kept matters as much as
 * listing it, since the game rewrites CURGAME at every launch, so a player who
 * sees it in a list of saved files has been told the opposite of the truth.
 */
function renderSaves(changed) {
  $("#saves").textContent = changed?.length
    ? "written by the game:\n" + changed
        .map((f) => `${f.path}  ${f.contents.length} bytes`
          + `  \u2014 ${notKeptReason(f.path) ?? "kept"}`)
        .join("\n")
    : "nothing written yet";
}

/**
 * Splice any kept characters into the WORLD.DAT about to be handed to DOSBox.
 *
 * Modifies `files` in place and returns what it added, so the caller can say
 * so. A stored roster that does not fit the file it is being written into is
 * ignored rather than applied blindly, which would corrupt the game data.
 */
async function applyKeptCharacters(files) {
  const roster = await loadRoster();
  if (!roster) return [];
  const world = files.find((f) => f.path.toUpperCase() === "WORLD.DAT");
  if (!world || !looksLikeWorld(world.contents)) {
    console.warn("kept characters not applied: WORLD.DAT is not the expected build");
    return [];
  }
  const { world: patched, kept, renumbered } = graft(world.contents, roster);
  world.contents = patched;
  for (const m of renumbered) {
    console.warn(`slot ${m.slot}: container record ${m.from} was already taken, `
      + `moved to ${m.to}`);
  }
  return kept;
}

/**
 * Take the roster out of the running game and store it.
 *
 * CURGAME holds it from the moment KEEP CHARACTER is pressed, which is why
 * this can read it while the game is running; what it cannot do is take effect
 * now, because WORLD.DAT was handed to the emulator at boot. It applies at the
 * next start.
 */
async function keepCharacters() {
  if (!ci) { say("start the game first"); return; }
  let save;
  try {
    save = await ci.fsReadFile("CURGAME");
  } catch (err) {
    say(`could not read CURGAME: ${err.message}`);
    return;
  }
  // The game truncates CURGAME at launch and rebuilds it a moment later, so
  // early in the boot it is legitimately empty, which is not an error: it is
  // "not yet".
  if (save.length < SAVE_SIZE) {
    say("the game has not written its roster yet \u2014 wait for the main menu");
    return;
  }
  let roster;
  try {
    roster = rosterOf(save);
  } catch (err) {
    say(`could not read the roster: ${err.message}`);
    return;
  }
  const created = slotsOf(roster).filter((s) => CREATED.includes(s.slot));
  if (!created.length) {
    say("no created characters to keep \u2014 make one in Character Creation first");
    return;
  }
  await saveRoster(roster);
  const names = created.map((c) => c.name).join(", ");
  say(`kept ${names} \u2014 in the roster from the next start`);
}

// Whether to apply the cabinet's three patches to a copy the player brought.
//
// On by default, because they are what makes the cabinet pleasant to drive:
// the intro is skipped and the main menu stops falling into its attract loop
// while you are reading the clue book. But they are changes to somebody else's
// copy of a game they own, and a player who wants the thing as it shipped --
// intro and all, should be able to have it. Nothing is written to their
// files either way; the patch is applied to the bytes on their way into the
// emulator.
const PATCH_KEY = "yendor3.patch";
const patchWanted = () => localStorage.getItem(PATCH_KEY) !== "off";

/**
 * Patch the dropped copy's executable, in place in the file list.
 *
 * Runs before anything else reads the files, so the fingerprints taken below
 * are of what DOSBox is actually given. Quiet when there is nothing to patch:
 * a zip without REGISTER.EXE never gets this far, and a copy the patcher
 * refuses is started unpatched rather than not at all.
 */
async function applyGamePatches(files, key) {
  if (!patchWanted()) {
    say("starting your copy unpatched, as it shipped");
    return;
  }
  const exe = files.find((f) => f.path.toUpperCase() === "REGISTER.EXE");
  if (!exe) return;
  say("patching the executable\u2026");
  const { exe: out, patched, fromStorage, why } =
    await patchedExecutable(exe.contents, key);
  exe.contents = out;
  say(patched ? `patched${fromStorage ? " (from storage)" : ""} \u00b7 starting DOSBox\u2026`
              : `starting unpatched: ${why}`);
}

/**
 * What the browser will actually promise about the storage we just used.
 *
 * Short enough for the header; the caveat goes in the tooltip, because
 * "evictable" is the word that matters and the sentence explaining it is not.
 */
async function reportDurability() {
  const { supported, persisted } = await requestPersistence();
  const estimate = await storageEstimate();
  const used = estimate?.usage
    ? ` \u00b7 ${(estimate.usage / 1024).toFixed(0)} kB`
    : "";
  if (!supported) {
    status.title = "This browser does not report whether storage is durable.";
    return `saves stored${used}`;
  }
  status.title = persisted
    ? "Storage is persistent: the browser will not clear it to reclaim space."
    : "Storage is on disk and survives a restart, but the browser may clear it "
      + "to reclaim space. Export to keep a copy of your own.";
  return `${persisted ? "saves persistent" : "saves evictable"}${used}`;
}

/** What a save wrote, as the status line puts it. */
const savedLine = ({ count, bytes }) =>
  `running \u00b7 saved ${count} file${count === 1 ? "" : "s"}, ${(bytes / 1024).toFixed(1)} kB`;

async function boot() {
  $("#boot").disabled = true;
  try {
    say("loading emulator…");
    const emulators = await loadEmulators();
    say("loading game files…");
    // Hosted: the zip the player chose, unpacked here in the page. Nothing is
    // uploaded: the bytes go from the file picker into the emulator in this
    // tab. Unpacking rather than handing js-dos the archive gives the same
    // {path, contents} entries the local server serves, so everything below
    // this line (kept characters, fingerprints, layered saves) works the
    // same way in both deployments.
    const files = hosted
      ? (BRING_YOUR_OWN.zip ? await gameFromZip(BRING_YOUR_OWN.zip) : [])
      : await gameFiles();
    // Locally the executable was patched before the server ever saw it, by
    // `make patched`; in the container the entrypoint patches the mounted
    // copy. Hosted there is nothing mounted, so the player's own copy is
    // patched here: otherwise a hosted cabinet sits through the intro and
    // falls into the attract loop while the driver is thinking, which the
    // local one has not done since the patches landed.
    // Keyed by the archive, so the patched copy is kept with the tables and a
    // second boot starts the game without waking pyodide at all.
    if (hosted) {
      await applyGamePatches(
        files, BRING_YOUR_OWN.zip ? fingerprint(BRING_YOUR_OWN.zip) : null);
    }
    const conf = await (await fetch("dosbox.conf")).text();
    // Kept characters go in before anything else looks at the files. They live
    // in WORLD.DAT rather than in a save file (see roster.js), and grafting
    // them here, ahead of the fingerprints below, keeps the 4MB WORLD.DAT
    // out of the changed set, so autosave never stores a copy of it.
    const kept = await applyKeptCharacters(files);
    // Anything the game saved in an earlier session is layered over the
    // original files, so it boots with its characters and saved games intact.
    // Fingerprint the originals now: handing the files to the worker transfers
    // their buffers, and afterwards they read as empty.
    const originals = new Map(
      files.map((f) => [f.path.toUpperCase(), fingerprint(f.contents)]));
    bootFingerprints = originals;
    const saved = await loadFiles();
    say(saved.length ? `starting DOSBox (restoring ${saved.length} saved files)…`
                     : "starting DOSBox…");
    // Frames are pulled through onFrame and painted here rather than handing
    // the worker an OffscreenCanvas. Keeping the canvas on this side costs a
    // copy per frame but lets the page read pixels back, which is what makes
    // the mouse calibration below possible.
    const offscreen = undefined;
    // DOSBox-X, not DOSBox. The plain DOSBox backend never delivers mouse
    // coordinates to this game: the cursor stays pinned at the origin no
    // matter what is sent, and js-dos's own v7 and v8 players behave the same
    // way, so it is not this integration. DOSBox-X honors the coordinates,
    // provided mouse_emulation=always is set (see dosbox.conf.js). The game is
    // mouse-driven, so this matters: character creation cannot be completed
    // without it.
    const backend = new URLSearchParams(location.search).get("backend") || "dosboxX";
    // The trainer needs to read and write the guest's memory, which the stock
    // emulator offers no way to do. `?cheats` asks for the hooked build
    // instead, a second file beside the stock one, written by
    // `tools/build_trainer.js` and served from the same directory. It is never
    // the default: without the flag the cabinet runs js-dos as it ships.
    if (trainerReady) {
      // The blob is the whole URL, so the prefix and suffix js-dos would
      // otherwise wrap around a filename have to be cleared. Everything the
      // shim loads beside itself is pinned to EMU inside it, so nothing else
      // depends on the prefix once the worker is running.
      emulators.wdosboxJs = TRAINER_JS;
      emulators.wdosboxxJs = TRAINER_X_JS;
      say("trainer build");
    }
    const start = backend === "dosboxX"
      ? emulators.dosboxXWorker.bind(emulators)
      : emulators.dosboxWorker.bind(emulators);
    // Replace rather than overlay. Passing both the original and the saved
    // copy of a file leaves the original in place, later entries not winning,
    // so anything we have a saved version of is dropped from the base set.
    const restored = new Set(saved.map((f) => f.path.toUpperCase()));
    const base = files.filter((f) => !restored.has(f.path.toUpperCase()));
    ci = await start([
      ...base,
      ...saved,
      { dosboxConf: conf, jsdosConf: { version: emulators.version.split(" ")[0] } },
    ], offscreen ? { canvas: offscreen } : undefined);
    // The game is up: the drop zone has done its job and the screen takes its
    // place. Without this the canvas stays hidden behind the zone that asked
    // for it, and a running game paints where nobody can see it.
    document.body.classList.add("running");
    if (!offscreen) ci.events().onFrame((rgb) => { if (rgb) { frames += 1; paint(rgb); } });
    wireInput();
    // The canvas is shown now, and the overlay is placed by its edges.
    fitTouchOverlay();
    // A finger places the cursor by homing it, see wireInput, so the mapping
    // a mouse measures when it first arrives over the canvas is not needed.
    if (TOUCH) say("running \u00b7 touch");
    // Browsers only allow audio to start from a user gesture: the click that
    // got us here counts.
    audio = startAudio(ci);
    // resume() is not awaited. A browser may leave it pending instead of
    // rejecting it. Firefox does, where it will not start the context. That
    // left the rest of boot unreachable: no autosave, so nothing wrote the
    // player's game, and no pauseWhenAway. The context comes up again on the
    // way back from a pause. Volume applies to a suspended one.
    if (audio) { applyVolume(); audio.resume().catch(() => {}); unlockAudio(); }
    pauseWhenAway();
    autosave = startAutosave(ci, originals, {
      onSave: (result) => {
        renderSaves(result.changed);
        say(savedLine(result));
      },
    });
    canvas.focus();
    const durability = await reportDurability();
    const who = kept.length ? ` \u00b7 ${kept.map((k) => k.name).join(", ")} in the roster` : "";
    say(`${audio ? "running" : "running (no audio device)"}${who} \u00b7 ${durability}`);
  } catch (err) {
    say(`failed: ${err.message}`);
    $("#boot").disabled = false;
    throw err;
  }
}

/**
 * Start the sound on the first touch if the boot did not.
 *
 * A browser starts an audio context only inside a user gesture, and the boot
 * takes several seconds past the click that began it: Chrome remembers the
 * click and honors the late resume, Safari on a phone does not. So the next
 * press or tap resumes it, and the status line says which happened.
 */
function unlockAudio() {
  const state = () => audio?.context.state;
  // The volume icon shows it too, since the status line moves on.
  const show = () => volumeControl.classList.toggle("suspended", state() !== "running");
  const stop = () => {
    show();
    for (const type of ["pointerdown", "keydown", "touchend"]) {
      document.removeEventListener(type, tryResume, true);
    }
  };
  const tryResume = () => {
    if (!audio || state() === "running") return stop();
    audio.resume().then(() => { if (state() === "running") { stop(); say("running \u00b7 sound on"); } })
      .catch(() => {});
  };
  for (const type of ["pointerdown", "keydown", "touchend"]) {
    document.addEventListener(type, tryResume, true);
  }
  // Read after the resume the boot asked for has had its say.
  setTimeout(() => {
    if (state() === "running") { stop(); return; }
    show();
    status.textContent += " \u00b7 sound starts on the next tap";
  }, 1500);
}

/**
 * Stop the emulator while the player is away.
 *
 * The worker emulates whatever the page is doing. The main thread takes its
 * frames and samples, and a background page throttles that thread. The queue
 * grows for as long as the page is away, and the game runs that far behind the
 * input. Safari throttles after about ten seconds. Paused, nothing
 * accumulates. Samples buffered at that moment are dropped on the way back
 * rather than played late.
 *
 * Away is two conditions. `visibilitychange` covers a tab the browser is no
 * longer showing, and it is all that fires on a tab switch. It does not fire
 * when the browser stops being the active application. The tab is still the
 * visible one there, so only focus moves. `document.hasFocus()` reports that.
 * It stays true while focus is inside the panel iframe. A window `blur` alone
 * cannot tell that apart from leaving the browser.
 *
 * Both are read a task later. Focus has not settled during the event that
 * announces it.
 */
function pauseWhenAway() {
  const apply = () => {
    if (!ci) return;
    const away = document.hidden || !document.hasFocus();
    if (away === paused) return;
    paused = away;
    if (away) { ci.pause(); return; }
    if (audio) { audio.reset(); audio.resume(); }
    ci.resume();
  };
  const later = () => setTimeout(apply, 0);
  document.addEventListener("visibilitychange", later);
  window.addEventListener("blur", later);
  window.addEventListener("focus", later);
}

/**
 * Reload the panel when its files are rebuilt.
 *
 * Only the iframe is reloaded, never the page: the emulator runs in this
 * document, so reloading here would throw away the running game. Scroll
 * position inside the panel is not preserved, but the game is.
 */
function watchForRebuilds() {
  if (!("EventSource" in window)) return;
  // Live reload is the development server's, and a static host has no such
  // endpoint. Asking for one there produces a failed request in the console at
  // every page load, which is noise a player should not have to see.
  if (hosted) return;
  const events = new EventSource("events");
  events.onmessage = (e) => {
    if (e.data === "reload") {
      // Rebuild the src from the one the frame already has, so the flags the
      // markup set survive. Writing a fresh path here dropped `embed`, and the
      // reloaded panel came back wearing its own header inside the cabinet.
      const frame = $("#panel");
      const url = new URL(frame.src, location.href);
      url.searchParams.set("t", String(Date.now()));
      frame.src = url.pathname + url.search;
      say(ci ? "running — panel reloaded" : "panel reloaded");
    } else if (e.data === "shell") {
      // Reloading the page would end the game, so only do it when there is no
      // game to lose.
      if (!ci) location.reload();
      else say("shell updated — reload the page to pick it up");
    }
  };
  events.onerror = () => { /* the browser retries on its own */ };
  // Release the server's connection promptly when the page goes away. It does
  // not stop the browser reporting the aborted response, which happens
  // whatever we do and tools/cabinet_check.js knows to expect, but leaving
  // a streaming request open on a page that is gone is untidy.
  window.addEventListener("pagehide", () => events.close());
}

/**
 * A header button that opens a panel under itself.
 *
 * Two of these now, and they have to behave identically or the header stops
 * feeling like one thing: click to toggle, Escape or a click anywhere else to
 * dismiss, and focus that follows: into the panel on open, back to the
 * button on close, so dismissing never strands focus on a hidden control.
 */
function dropdown(button, panel, { onOpen } = {}) {
  // Centered under the button, but never off the window. The saves panel is far
  // wider than its icon and sits near the end of the header, so centering alone
  // hangs it over the edge; this keeps the centering wherever there is room and
  // slides it in only as far as it must.
  const MARGIN = 6;
  const place = () => {
    panel.style.transform = "";                 // back to the CSS default
    const box = panel.getBoundingClientRect();
    const room = document.documentElement.clientWidth;
    let shift = 0;
    if (box.right > room - MARGIN) shift = room - MARGIN - box.right;
    if (box.left + shift < MARGIN) shift = MARGIN - box.left;
    if (shift) panel.style.transform = `translateX(calc(-50% + ${Math.round(shift)}px))`;
  };
  const show = (open) => {
    panel.hidden = !open;
    button.setAttribute("aria-expanded", String(open));
    if (open) { place(); onOpen?.(); }
  };
  window.addEventListener("resize", () => { if (!panel.hidden) place(); });
  button.addEventListener("click", () => show(panel.hidden));
  document.addEventListener("pointerdown", (e) => {
    if (!panel.hidden && !panel.contains(e.target) && e.target !== button
        && !button.contains(e.target)) show(false);
  });
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape" || panel.hidden) return;
    show(false);
    button.focus();
  });
  return { show, get open() { return !panel.hidden; } };
}

// Saving, kept characters and export all answer the same question, what of
// this survives, so they are one menu rather than four header buttons, with
// the listing of what was kept right under the buttons that produce it.
const savesMenu = dropdown($("#saves-toggle"), $("#saves-menu"), {
  onOpen: () => $("#save-now").focus(),
});

// Volume. The slider works before the game starts and is applied when audio
// comes up, so it never has to be touched twice, and it is remembered, so
// somebody who turned the sound off does not turn it off again every visit.
const VOLUME_KEY = "cabinet.volume";
const volume = $("#volume");
const volumeControl = $("#volume-control");
try {
  const kept = localStorage.getItem(VOLUME_KEY);
  if (kept !== null && kept !== "") volume.value = kept;
} catch (e) { /* private window, or storage disabled */ }
const applyVolume = () => {
  const v = Number(volume.value) / 100;
  volumeControl.classList.toggle("muted", v === 0);
  $("#volume-value").textContent = volume.value;
  if (audio) audio.setVolume(v);
  try {
    localStorage.setItem(VOLUME_KEY, volume.value);
  } catch (e) { /* private window, or storage disabled */ }
};
volume.addEventListener("input", applyVolume);
applyVolume();
dropdown($("#volume-toggle"), $("#volume-menu"), { onOpen: () => volume.focus() });

const app = $("#app");
// Only offered where there is one to forget: locally the game is the server's
// and this button would promise something it cannot do. Saved games are a
// separate key and are deliberately left alone: a player replacing their
// copy of the game is not asking to lose their party.
const forget = $("#forget-game");
if (forget) {
  forget.addEventListener("click", async () => {
    await clearGame();
    BRING_YOUR_OWN.zip = null;
    BRING_YOUR_OWN.name = null;
    PANEL.text = null;
    PANEL.worldMap = null;
    $("#boot").disabled = true;
    offerZip("", "Bring your own copy",
      "Drop a zip of your Yendorian Tales III directory here, or click to "
      + "choose one. It is read in this tab and never uploaded.");
    say("forgotten \u2014 your saved games are untouched");
  });
}

// The patch toggle. Read at boot rather than watched, so changing it after the
// game has started is a decision about the next one: restarting is a page
// reload, and saying so is better than implying a running game will change.
// Reachable from tools/decode_check.js, which asserts the toggle decides
// something: a preference that quietly does nothing is the failure worth
// catching, and it cannot be seen from outside the page.
window.__applyPatches = applyGamePatches;

// The checkbox sits outside the drop zone rather than inside it. The zone is
// one large button, so a control placed within it would make a single click
// mean two things.
const patchBox = $("#patch-game");
if (patchBox) {
  patchBox.checked = patchWanted();
  patchBox.addEventListener("change", () => {
    localStorage.setItem(PATCH_KEY, patchBox.checked ? "on" : "off");
    say(patchBox.checked
      ? "patches on \u2014 applied when the game starts"
      : "patches off \u2014 your copy will run as it shipped");
  });
}

// The width of the clue book, dragged by the edge between the two panes.
//
// The game keeps whatever is left, so the limits are about it rather than about
// the panel: never less than a readable column of text, never so much that the
// screen has nowhere to draw. The default is the CSS clamp, which is what the
// variable falls back to while nothing has been dragged.
const PANEL_KEY = "cabinet.panel-width";
const PANEL_MIN = 280;
const GAME_MIN = 320;
const grip = $("#grip");
// The grip sits between them, so it comes out of the window before either
// pane's share of it.
const panelMax = () =>
  Math.max(PANEL_MIN, window.innerWidth - GAME_MIN - grip.offsetWidth);
const setPanelWidth = (px) => {
  const width = Math.round(Math.min(Math.max(px, PANEL_MIN), panelMax()));
  app.style.setProperty("--panel", `${width}px`);
  grip.setAttribute("aria-valuenow", String(width));
  return width;
};
const clearPanelWidth = () => {
  app.style.removeProperty("--panel");
  grip.removeAttribute("aria-valuenow");
  localStorage.removeItem(PANEL_KEY);
};
{
  const kept = Number(localStorage.getItem(PANEL_KEY));
  if (kept > 0) setPanelWidth(kept);
}
// A window that has been made narrower can leave a kept width with no room for
// the game; the clamp is re-applied rather than the width being forgotten, so
// widening the window brings it back.
window.addEventListener("resize", () => {
  const kept = Number(localStorage.getItem(PANEL_KEY));
  if (kept > 0) setPanelWidth(kept);
});

// The drag is held in a flag rather than read back off the pointer capture.
// Capture is released by the browser as well as by us -- implicitly after a
// pointerup, and whenever the window stops being the one receiving events --
// and a drag whose end was only ever noticed on the grip's own pointerup left
// `dragging` set when the release happened somewhere else. That class puts
// `pointer-events: none` on the panel, so the whole clue book went dead until
// something else pressed the grip. Every way a drag can end ends it.
let dragging = false;
const endDrag = () => {
  if (!dragging) return;
  dragging = false;
  app.classList.remove("dragging");
  const width = app.style.getPropertyValue("--panel");
  if (width) localStorage.setItem(PANEL_KEY, parseInt(width, 10));
  canvas.focus();
};
grip.addEventListener("pointerdown", (e) => {
  if (getComputedStyle(grip).display === "none") return;
  e.preventDefault();
  dragging = true;
  app.classList.add("dragging");
  try {
    grip.setPointerCapture(e.pointerId);
  } catch (err) {
    // A pointer the browser will not let us capture still drags: the moves
    // arrive while the button is down, and the release ends it below.
  }
});
grip.addEventListener("pointermove", (e) => {
  if (!dragging) return;
  // From the right edge of the window, so the pointer stays on the grip.
  setPanelWidth(window.innerWidth - e.clientX - grip.offsetWidth / 2);
});
grip.addEventListener("pointerup", endDrag);
grip.addEventListener("pointercancel", endDrag);
grip.addEventListener("lostpointercapture", endDrag);
// Released outside the window, or the window taken away mid-drag.
document.addEventListener("pointerup", endDrag);
window.addEventListener("blur", endDrag);
// Back to the width the stylesheet chooses, for a drag that went somewhere
// unhelpful.
grip.addEventListener("dblclick", clearPanelWidth);
// A separator is operable from the keyboard, and dragging a six-pixel strip is
// not something every pointer can do well.
grip.addEventListener("keydown", (e) => {
  const step = e.key === "ArrowLeft" ? 16 : e.key === "ArrowRight" ? -16 : 0;
  if (!step) return;
  e.preventDefault();
  const now = parseInt(app.style.getPropertyValue("--panel"), 10)
    || document.querySelector("#panel").getBoundingClientRect().width;
  localStorage.setItem(PANEL_KEY, setPanelWidth(now + step));
});

// Full screen, on the document rather than on the game alone: the bar goes
// with it, which is what keeps this button reachable to press again, and the
// player who wants nothing but the game hides the panel beside it. What the
// game gains is the browser's own chrome.
//
// Hidden where the browser has no such thing rather than shown and dead: on an
// iPhone no element can be made full screen, and a control that does nothing is
// worse than one that is not there.
const full = $("#toggle-full");
const fullscreenElement = () =>
  document.fullscreenElement || document.webkitFullscreenElement || null;
const enterFullscreen = document.documentElement.requestFullscreen
  || document.documentElement.webkitRequestFullscreen;
const exitFullscreen = document.exitFullscreen || document.webkitExitFullscreen;
// An iPhone has the functions and lets only a video use them, and Chrome
// there does not say so through fullscreenEnabled either, so the phone is
// asked for by name. The home screen is its full screen; the manifest offers
// that. A request the browser refuses anywhere else hides the button too.
const fullscreenAllowed = !IPHONE
  && (document.fullscreenEnabled ?? document.webkitFullscreenEnabled ?? true);
if (enterFullscreen && exitFullscreen && fullscreenAllowed) {
  full.hidden = false;
  full.addEventListener("click", async () => {
    try {
      if (fullscreenElement()) await exitFullscreen.call(document);
      else await enterFullscreen.call(document.documentElement);
    } catch (err) {
      // A refusal is the browser's to make: a window that is already the
      // system's full screen, or a policy that wants a fresh gesture. A
      // browser that will not do it at all gets its button taken away.
      status.textContent = `full screen refused: ${err.message}`;
      if (/not supported|not allowed|denied/i.test(err.message)) full.hidden = true;
    }
    canvas.focus();
  });
  // The state is the document's, not the button's: Escape and the browser's own
  // controls leave full screen without this button being pressed.
  for (const event of ["fullscreenchange", "webkitfullscreenchange"]) {
    document.addEventListener(event, () => {
      full.setAttribute("aria-pressed", String(!!fullscreenElement()));
      canvas.focus();
    });
  }
}

const toggle = $("#toggle-panel");
const showPane = (shown) => {
  app.classList.toggle("panel-hidden", !shown);
  toggle.setAttribute("aria-pressed", String(shown));
  syncPadKey();
};
// A toggle names what it controls; whether it is on is carried by its pressed
// state, not by rewriting the label to a verb.
toggle.addEventListener("click", () => {
  showPane(app.classList.contains("panel-hidden"));
  canvas.focus();
});
// A phone has the room for one thing. The game is that thing, and the clue
// book lies over it when asked for, in either orientation: see the
// stylesheet's phone blocks. So it starts put away there, and the book
// button is the only thing that moves it. The full screen button is its own
// switch and touches neither.
{
  const phone = matchMedia("(max-width: 900px)").matches
    || matchMedia("(orientation: landscape) and (max-height: 520px)").matches;
  if (phone || IPHONE) showPane(false);
}

// Handles for the browser checks in tools/cabinet_check.js.
window.__cabinet = {
  mouseEvents: 0,
  // Touch: taps delivered to the game, and on-screen key presses sent.
  taps: 0,
  keys: 0,
  // Frames delivered by the emulator. The guest drives its own vsync, so this
  // rate is how much of the emulated machine the host is actually managing to
  // run, which is what says whether a cycle count is being sustained or just
  // asked for. See tools/cycles_check.js.
  get frames() { return frames; },
  get paused() { return paused; },
  keys: KEY_CODES,
  lastMouse: null,
  get ci() { return ci; },
  get audio() { return audio; },
  get canvas() { return canvas; },
  get transform() { return transform; },
  // Asking by hand clears the backoff as well as the measurement: the caller
  // has picked the moment, which is exactly what the schedule cannot do.
  calibrate: () => {
    transform = null;
    failures = 0;
    nextAttempt = 0;
    return ensureCalibrated();
  },
  keepCharacters,
};

$("#save-now").addEventListener("click", async () => {
  if (!autosave) { say("start the game first"); return; }
  say("saving\u2026");
  const result = await autosave.save();
  renderSaves(result?.changed);
  // Every outcome ends the sentence this started. The autosave reports through
  // onSave. onSave stays quiet when a save wrote what the one before it wrote,
  // which keeps the fifteen-second timer from repeating itself. That rule is
  // wrong for a button. Two presses in a row, or a press just after the timer
  // saved the same files, left "saving..." on screen with nothing after it.
  if (!result) say("running \u00b7 the save did not run, see the console");
  else if (!result.count) say("running \u00b7 nothing new to save");
  else say(savedLine(result));
});

$("#keep-characters").addEventListener("click", keepCharacters);

$("#export-saves").addEventListener("click", async () => {
  const bundle = await exportBundle();
  if (!Object.keys(bundle.files).length && !bundle.roster) {
    say("nothing stored yet to export");
    return;
  }
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(bundle)], { type: "application/json" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = `tyrants-of-thaine-${bundle.saved.slice(0, 10)}.json`;
  a.click();
  URL.revokeObjectURL(url);
  say(`exported ${Object.keys(bundle.files).length} file(s)`);
});

$("#import-saves").addEventListener("click", () => $("#import-file").click());

$("#import-file").addEventListener("change", async (e) => {
  const file = e.target.files?.[0];
  if (!file) return;
  e.target.value = "";
  try {
    const result = await importBundle(JSON.parse(await file.text()));
    say(`imported ${result.files} file(s)${result.roster ? " and a roster" : ""}`
        + " \u2014 reload to play them");
  } catch (err) {
    say(`import failed: ${err.message}`);
  }
});

$("#boot").addEventListener("click", boot);
wireTouchKeys();
// The page has nothing to scroll, and a phone that scrolls it anyway, to
// bring a focused control into view, leaves the header off the top with no
// way back. Whatever scrolled it is undone.
for (const target of [window, document]) {
  target.addEventListener("scroll", () => {
    if (scrollY || scrollX) scrollTo(0, 0);
    const root = document.scrollingElement;
    if (root && (root.scrollTop || root.scrollLeft)) { root.scrollTop = 0; root.scrollLeft = 0; }
  }, { passive: true });
}

// Installable, and openable with no network once it has been opened with
// one: the shell, the emulator and the decoder are kept by the worker as
// they are fetched, and a copy of the game is already in storage. At the
// site root, because a worker reaches only what is under it, so both servers
// put it there. A browser that has none, or a page served in a way it will
// not take a worker from, is left as it was.
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register(new URL("../sw.js", import.meta.url))
    .catch((err) => console.warn("no service worker:", err.message));
}

// The drop zone, wired only where it is offered.
const drop = $("#bring-your-own");
if (drop) {
  const picker = $("#game-zip");
  // One control with two jobs: ask for a copy, then start it. The picker is
  // reopened for a zone that has nothing yet or whose last zip was refused.
  const act = () => {
    // The header's power button is already disabled while a boot is under way,
    // so it answers "can the game be started right now?" for both controls.
    if (!drop.classList.contains("chosen")) picker.click();
    else if (!$("#boot").disabled) boot();
  };
  drop.addEventListener("click", act);
  // role="button" promises the keyboard works like a button's does.
  drop.addEventListener("keydown", (e) => {
    if (e.key !== "Enter" && e.key !== " ") return;
    e.preventDefault();
    act();
  });
  // Selecting the same file twice fires no change event unless the value is
  // cleared, which is what a player does after a zip is refused.
  picker.addEventListener("change", () => {
    const file = picker.files[0];
    picker.value = "";
    acceptZip(file);
  });
  for (const type of ["dragenter", "dragover"]) {
    drop.addEventListener(type, (e) => {
      e.preventDefault();
      drop.classList.add("over");
    });
  }
  for (const type of ["dragleave", "drop"]) {
    drop.addEventListener(type, () => drop.classList.remove("over"));
  }
  drop.addEventListener("drop", (e) => {
    e.preventDefault();
    acceptZip(e.dataTransfer.files[0]);
  });
  // A zip dropped next to the zone rather than on it would otherwise replace
  // the page with the file, losing whatever the player had going. Only where
  // the zone is offered: a local run has no reason to swallow a drop.
  for (const type of ["dragover", "drop"]) {
    window.addEventListener(type, (e) => {
      if (hosted && !drop.contains(e.target)) e.preventDefault();
    });
  }
}
say("ready — press the power button");
// Live reload asks the development server for an endpoint a static host does
// not have, so which mode this is has to be settled first.
detectMode().then(async (byo) => {
  trainerReady = await trainerAvailable();
  // Locally the tables are on the server and the panel fetches them itself.
  // Hosted there are none until a copy has been decoded, so the frame waits:
  // pointing it at the shell now would only paint "no decoded data yet" over
  // the drop zone the player is being asked to use.
  if (!byo) showPanel();
  else {
    // Only where there is a copy to forget. Locally the game is the server's
    // and the button would promise something it cannot do.
    const forgetButton = $("#forget-game");
    if (forgetButton) forgetButton.hidden = false;
    await restoreGame();
  }
  watchForRebuilds();
});
