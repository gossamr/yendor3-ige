// Keeping the game's disk between sessions.
//
// The emulator starts from the files it is handed and writes changes only to
// its own in-memory filesystem, so without this everything the game saves --
// characters, saved games, the keep you built, is gone when the tab closes.
//
// ci.persist(true) is meant to return only the changed files, but when the
// filesystem is seeded from individual file entries rather than a bundle it
// returns the whole disk: 21MB, most of it WORLD.DAT and PICTURES.VGA, which
// the game never writes to. Storing that on a timer would be absurd, so the
// changed files are worked out here instead, by walking the emulated
// filesystem and comparing against the sizes we booted with. A save is then a
// few kilobytes.

const DB = "yendor3-cabinet";
const STORE = "state";
const KEY = "files";
// The roster is kept apart from the save files because it is not one: it is
// spliced into WORLD.DAT before the emulator ever sees it, so it must not be
// restored as a file. See roster.js for why WORLD.DAT is the only place a
// created character can live.
const ROSTER_KEY = "roster";
// The panel's tables, decoded from the player's own copy. Hosted there is no
// data/ on the server, so this is the only place they exist, and producing
// them is about five seconds of Python, which is worth not repeating on every
// reload. Keyed by a fingerprint of the zip and by one of the decoders that
// read it, so a different copy decodes again rather than being served another
// one's tables, and so does the same copy after the decoders change.
const DECODED_KEY = "decoded";
// The player's own copy of the game, hosted. Locally the server has it and
// this is never written; hosted it is the only copy there is, and without it
// every reload is another trip to the file picker for a game the browser
// already had. The archive rather than the unpacked files: 4 MB against 21,
// and cabinet/zip.js unpacks it at boot anyway.
const GAME_KEY = "game";
// The same copy with the cabinet's three patches applied. Kept for the same
// reason the tables are: producing it means starting pyodide, which costs more
// than the patching does, and the answer is the same every time for a given
// copy. 200 kB, against the archive it belongs to.
const PATCHED_KEY = "patched";

function open() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB, 1);
    req.onupgradeneeded = () => req.result.createObjectStore(STORE);
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function tx(mode, fn) {
  const db = await open();
  try {
    return await new Promise((resolve, reject) => {
      const t = db.transaction(STORE, mode);
      const req = fn(t.objectStore(STORE));
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  } finally {
    db.close();
  }
}

/** Saved files as [{ path, contents }], ready to append to an InitFs. */
export async function loadFiles() {
  try {
    const saved = await tx("readonly", (s) => s.get(KEY));
    if (!saved) return [];
    // Filtered on the way out as well as in: a record written before a file
    // joined NOT_WORTH_KEEPING still holds it, and this is what both the boot
    // restore and the export bundle read.
    return Object.entries(saved)
      .filter(([path]) => isPersistable(path))
      .map(([path, contents]) => ({ path, contents: new Uint8Array(contents) }));
  } catch (err) {
    console.warn("could not read saved state:", err.message);
    return [];
  }
}

export async function clearFiles() {
  await tx("readwrite", (s) => s.delete(KEY));
}

/**
 * The copy of the game the player brought, if the browser still has it.
 *
 * Returns the archive and the name it was dropped under, so the drop zone can
 * say which copy it is about to start rather than only that it has one.
 */
export async function loadGame() {
  try {
    const saved = await tx("readonly", (s) => s.get(GAME_KEY));
    if (!saved) return null;
    return { zip: new Uint8Array(saved.zip), name: saved.name };
  } catch (err) {
    console.warn("could not read the stored copy of the game:", err.message);
    return null;
  }
}

/**
 * Keep it, if there is room.
 *
 * A quota failure is a normal outcome rather than an error: a 20 MB archive on
 * a browser with little to spare is exactly the case, and the cabinet works
 * without this: the player drops the zip again. So it reports rather than
 * throws, and the caller says so once.
 */
export async function saveGame(zip, name) {
  try {
    await tx("readwrite", (s) => s.put({ zip, name }, GAME_KEY));
    return true;
  } catch (err) {
    console.warn("could not keep the copy of the game:", err.message);
    return false;
  }
}

/** The patched executable for a copy, or null for anything else. */
export async function loadPatched(key) {
  try {
    const saved = await tx("readonly", (s) => s.get(PATCHED_KEY));
    if (!saved || saved.key !== key) return null;
    return new Uint8Array(saved.exe);
  } catch (err) {
    console.warn("could not read the patched executable:", err.message);
    return null;
  }
}

export async function savePatched(key, exe) {
  try {
    await tx("readwrite", (s) => s.put({ key, exe }, PATCHED_KEY));
    return true;
  } catch (err) {
    console.warn("could not keep the patched executable:", err.message);
    return false;
  }
}

/** Forget a copy of the game and everything derived from it. */
export async function clearGame() {
  for (const key of [GAME_KEY, DECODED_KEY, PATCHED_KEY]) {
    await tx("readwrite", (s) => s.delete(key));
  }
}

/**
 * The decoded tables for one copy of the game, or null for anything else.
 *
 * `key` is a fingerprint of the zip the player dropped and `decoder` a
 * fingerprint of the modules that decoded it; tables kept under either a
 * different copy or a different build are not this build's tables and are a
 * miss, so the decode runs again. A record from before the build was recorded
 * has no `decoder` and misses for the same reason.
 *
 * A null `decoder` is "cannot tell", which is what a deployment that does not
 * publish one gives: then the copy alone decides, as it used to.
 *
 * A miss is the normal case on a first visit and is not worth a warning; so is
 * a browser that refuses storage, which is why this returns null rather than
 * throwing.
 */
export async function loadDecoded(key, decoder = null) {
  try {
    const saved = await tx("readonly", (s) => s.get(DECODED_KEY));
    if (!saved || saved.key !== key) return null;
    if (decoder && saved.decoder !== decoder) return null;
    return {
      restoration: new Uint8Array(saved.restoration),
      worldMap: new Uint8Array(saved.worldMap),
    };
  } catch (err) {
    console.warn("could not read the decoded tables:", err.message);
    return null;
  }
}

/** Keep one copy's tables, under the copy and the build that produced them.
 *  Only the most recent is kept; they are rebuildable. */
export async function saveDecoded(key, { restoration, worldMap }, decoder = null) {
  try {
    await tx("readwrite",
             (s) => s.put({ key, decoder, restoration, worldMap }, DECODED_KEY));
    return true;
  } catch (err) {
    console.warn("could not keep the decoded tables:", err.message);
    return false;
  }
}

export async function clearDecoded() {
  await tx("readwrite", (s) => s.delete(DECODED_KEY));
}

/** The kept-character roster, as 5,000 bytes, or null if none was ever kept. */
export async function loadRoster() {
  try {
    const saved = await tx("readonly", (s) => s.get(ROSTER_KEY));
    return saved ? new Uint8Array(saved) : null;
  } catch (err) {
    console.warn("could not read the kept roster:", err.message);
    return null;
  }
}

export async function saveRoster(bytes) {
  await tx("readwrite", (s) => s.put(bytes, ROSTER_KEY));
}

export async function clearRoster() {
  await tx("readwrite", (s) => s.delete(ROSTER_KEY));
}

/**
 * Ask the browser to stop treating this origin's storage as disposable.
 *
 * IndexedDB is on disk, but by default it is "best-effort": it can be evicted
 * when the device is short of space, and Safari deletes script-written storage
 * after seven days without a visit. navigator.storage.persist() moves the
 * origin to the persistent bucket, which is exempt from both. Chromium grants
 * it silently on a site the user has engaged with; Firefox prompts; Safari
 * grants it on sites added to the home screen and refuses otherwise.
 *
 * A refusal is not an error, since the storage still works and is merely evictable,
 * so this reports rather than throws, and the caller says so in the UI.
 */
export async function requestPersistence() {
  if (!navigator.storage?.persist) return { supported: false, persisted: false };
  try {
    const already = await navigator.storage.persisted();
    const persisted = already || await navigator.storage.persist();
    return { supported: true, persisted, already };
  } catch (err) {
    return { supported: true, persisted: false, error: err.message };
  }
}

/** Bytes used and available, for the UI to show what is actually stored. */
export async function storageEstimate() {
  if (!navigator.storage?.estimate) return null;
  try {
    return await navigator.storage.estimate();
  } catch {
    return null;
  }
}

/**
 * Flatten the emulator's fsTree into [{ path, size }].
 *
 * fsTree reports paths as "./CURGAME" while the files handed to InitFs are
 * plain names like "CURGAME". Feeding the dotted form back in writes to a
 * different place and the restore silently does nothing, so the leading "./"
 * is stripped here and paths stay in one form throughout.
 */
function flatten(node, prefix = "") {
  const here = node.name ? `${prefix}${node.name}` : prefix;
  if (!node.nodes) return [{ path: normalize(here), size: node.size ?? 0 }];
  return node.nodes.flatMap((child) => flatten(child, here ? `${here}/` : ""));
}

const normalize = (path) => path.replace(/^\.?\/+/, "");

/**
 * What is on the emulated disk, as paths.
 *
 * Asking for a file that is not there is not a safe way to find out whether it
 * is: `fsReadFile` rejects from inside the worker's own message handling, and
 * the caller's promise is left unsettled, so a probe for six save slots hangs
 * on the first one that does not exist. Read the tree and ask for what it
 * lists.
 */
export async function diskPaths(ci) {
  return flatten(await ci.fsTree())
    .map((f) => f.path)
    .filter((path) => !path.includes(".jsdos/"));
}

/**
 * Content fingerprint: FNV-1a over the bytes, with the length mixed in.
 *
 * Comparing lengths is not enough. The game rewrites CURGAME in place at a
 * fixed 81,037 bytes, so a length check says "unchanged" for the one file that
 * holds the party, which is why kept characters used to vanish on reload.
 * Reading and hashing the whole disk costs about 65ms (16MB of it is
 * PICTURES.VGA), so there is no reason to cut corners.
 */
export function fingerprint(bytes) {
  let h = 2166136261;
  for (let i = 0; i < bytes.length; i++) {
    h ^= bytes[i];
    h = Math.imul(h, 16777619);
  }
  return `${bytes.length}:${(h >>> 0).toString(16)}`;
}

/**
 * The game's own data and executables, which it only ever reads.
 *
 * fsTree() reports a null size for every file in this build, so there is no
 * cheap way to tell a changed file from an unchanged one except by reading and
 * hashing it, and doing that to everything means 21 MB a time, almost all of
 * it PICTURES.VGA and WORLD.DAT. Over a full traced session the guest writes
 * exactly CURGAME, SAVGAMEn and LOGO.PCX. It never writes any of these, so
 * they are not worth reading.
 *
 * WORLD.DAT is on the list even though the cabinet does modify it: the kept
 * roster is spliced in before the fingerprints are taken, so it is identical
 * to what was handed over and would only ever hash as unchanged.
 */
const NEVER_WRITTEN = new Set([
  "PICTURES.VGA", "WORLD.DAT", "REGISTER.EXE", "SBFMDRV.COM",
  "SW.BAT", "README.DOC", "MAKEBOOT.BAT", "AUTOEXEC.WTI", "CONFIG.WTI",
]);

/**
 * Files on the emulated disk that are new, or whose contents differ from what
 * we booted with.
 */
export async function changedFiles(ci, originals) {
  const out = [];
  for (const { path } of flatten(await ci.fsTree())) {
    if (path.includes(".jsdos/")) continue;          // emulator metadata
    const base = path.split("/").pop().toUpperCase();
    if (NEVER_WRITTEN.has(base)) continue;
    try {
      const contents = await ci.fsReadFile(path);
      if (originals.get(base) === fingerprint(contents)) continue;
      out.push({ path, contents });
    } catch {
      // Directories and unreadable entries surface here; skip them.
    }
  }
  return out;
}

/**
 * Files that change but are not worth keeping, and what to say about each.
 *
 * CURGAME holds the party and the roster while the game is running, so it
 * looks like the file to preserve, but the game does `truncate CURGAME 0`
 * and rewrites all 81,037 bytes at every single launch, before anything reads
 * it (observed in every trace, on both backends). Whatever is restored into it
 * is destroyed unread, so storing it only costs 81 kB a time and makes the
 * saved-file list imply a durability it does not have. Characters are kept
 * through WORLD.DAT instead; see roster.js.
 *
 * LOGO.PCX is unpacked from the game data at load and rewritten the same way
 * at the next one, at a fixed 29,214 bytes. It carried no player state and
 * added 29 kB to every export.
 *
 * SAVGAMEn is the opposite case: it is what LOAD reads, so it is the only
 * thing here that actually carries a game forward.
 */
const NOT_WORTH_KEEPING = new Map([
  ["CURGAME", "rebuilt at launch, not kept"],
  ["LOGO.PCX", "unpacked at load, not kept"],
]);

/** Why a file is not being kept, or null if it is. For the saves listing. */
export const notKeptReason = (path) =>
  NOT_WORTH_KEEPING.get(path.split("/").pop().toUpperCase()) ?? null;

/**
 * Will this file survive being stored?
 *
 * Exposed as a predicate rather than only as a filtered list because callers
 * that already have the changed files must not have to ask for them twice --
 * working them out means reading and hashing the whole emulated disk, and
 * 21 MB of that is game data the game never writes to.
 */
export const isPersistable = (path) => !notKeptReason(path);

/**
 * Put one file into the stored record, as if the game had written it.
 *
 * The save editor's way onto the browser's disk: it hands back a save file
 * the cabinet was holding. Merged into the record rather than written over it,
 * for the reason saveNow() merges, and refused for a file the record does not
 * keep, so an edited CURGAME cannot be stored under the impression that it
 * will come back.
 */
export async function putFile(path, contents) {
  if (!isPersistable(path)) throw new Error(`${notKeptReason(path)}: ${path}`);
  const record = (await tx("readonly", (s) => s.get(KEY))) ?? {};
  record[path] = contents;
  await tx("readwrite", (s) => s.put(record, KEY));
}

/** The changed files that are worth writing to storage. */
export async function persistableFiles(ci, originals) {
  return (await changedFiles(ci, originals)).filter((f) => isPersistable(f.path));
}

/**
 * Store what is worth storing, and report everything that changed.
 *
 * The full changed list comes back, not just the stored part, because the UI
 * shows both, since a file the game rewrites at every launch is worth telling the
 * player about precisely so they know it is *not* being kept. Working that
 * list out means walking the emulated disk, so handing it back is what lets
 * the readout be free rather than a second walk.
 */
export async function saveNow(ci, originals) {
  const changed = await changedFiles(ci, originals);
  const files = changed.filter((f) => isPersistable(f.path));
  if (!files.length) return { count: 0, bytes: 0, changed };
  // Merged into what is already stored, not written over it. The emulated disk
  // is not the whole of what is kept: an imported bundle sits in storage until
  // the next boot puts it on the disk, and a save that replaced the record
  // erased it one autosave interval after the import, which is every import
  // made without reloading immediately. The game overwrites its save slots
  // rather than deleting them, so a merged record does not collect files the
  // player has thrown away.
  const record = (await tx("readonly", (s) => s.get(KEY))) ?? {};
  for (const path of Object.keys(record)) {
    if (!isPersistable(path)) delete record[path];
  }
  let bytes = 0;
  for (const f of files) { record[f.path] = f.contents; bytes += f.contents.length; }
  await tx("readwrite", (s) => s.put(record, KEY));
  return { count: files.length, bytes, changed };
}

/**
 * Save periodically, and whenever the page is hidden, since closing a tab does not
 * reliably allow async work, but hiding it does, and every tab close is
 * preceded by a hide.
 */
export function startAutosave(ci, originals, { intervalMs = 15000, onSave = () => {} } = {}) {
  let busy = false;
  let lastSignature = "";
  const save = async (reason) => {
    if (busy) { console.warn(`a save is already running; ${reason} save skipped`); return null; }
    busy = true;
    try {
      const result = await saveNow(ci, originals);
      const signature = `${result.count}:${result.bytes}`;
      if (result.count && signature !== lastSignature) {
        lastSignature = signature;
        onSave(result, reason);
      }
      return result;
    } catch (err) {
      console.warn("autosave failed:", err.message);
      return null;
    } finally {
      busy = false;
    }
  };
  const timer = setInterval(() => save("timer"), intervalMs);
  const onHide = () => { if (document.visibilityState === "hidden") save("hidden"); };
  document.addEventListener("visibilitychange", onHide);
  return {
    save: () => save("manual"),
    stop: () => { clearInterval(timer); document.removeEventListener("visibilitychange", onHide); },
  };
}

// --- Exporting off the browser's disk -------------------------------------
//
// Persistent storage survives a restart and an eviction sweep, but nothing in
// the browser survives the user clearing site data, a fresh profile, or another
// machine. An export is a file the player owns, so that is the honest answer to
// "is my game actually saved anywhere I control".

const b64 = (bytes) => {
  let s = "";
  for (let i = 0; i < bytes.length; i += 0x8000) {
    s += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
  }
  return btoa(s);
};

const unb64 = (text) => {
  const raw = atob(text);
  const out = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
  return out;
};

export const EXPORT_VERSION = 1;

// What an exported bundle calls itself. The old name is still accepted:
// renaming this directory must not orphan a file somebody already saved to
// disk, and the format did not change with the name.
const FORMAT = "yendorian-tales-3-cabinet";
const FORMATS = [FORMAT, "yendorian-tales-3-shim"];

/** Everything this origin is holding, as a plain JSON-serializable object. */
export async function exportBundle() {
  const files = await loadFiles();
  const roster = await loadRoster();
  return {
    format: FORMAT,
    version: EXPORT_VERSION,
    saved: new Date().toISOString(),
    files: Object.fromEntries(files.map((f) => [f.path, b64(f.contents)])),
    roster: roster ? b64(roster) : null,
  };
}

/** Put an exported bundle back. Returns what it restored. */
export async function importBundle(bundle) {
  if (!FORMATS.includes(bundle?.format)) {
    throw new Error("not a Tyrants of Thaine save export");
  }
  if (bundle.version > EXPORT_VERSION) {
    throw new Error(`export is version ${bundle.version}; this build reads ${EXPORT_VERSION}`);
  }
  const record = {};
  for (const [path, text] of Object.entries(bundle.files ?? {})) {
    record[path] = unb64(text);
  }
  if (Object.keys(record).length) await tx("readwrite", (s) => s.put(record, KEY));
  if (bundle.roster) await saveRoster(unb64(bundle.roster));
  return { files: Object.keys(record).length, roster: Boolean(bundle.roster) };
}
