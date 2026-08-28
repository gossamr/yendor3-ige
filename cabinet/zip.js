// Read a player's zip in the page.
//
// Hosted there is no game on the server, so the player supplies one. js-dos
// will take a zip as a bundle and unpack it itself, but unpacking here buys
// three things it cannot:
//
//  * The game can live anywhere in the zip. Compressing a folder, which is
//    what a file manager's "Compress" does, puts every file one level down,
//    and a bundle is unpacked at the root, so SW.BAT is not where the autoexec
//    looks for it. DOSBox then says "Bad command or filename" to a player who
//    is told the game is running.
//  * A zip missing the game can be named as such when it is chosen, rather
//    than booting to a DOS prompt.
//  * The files arrive as the same {path, contents} entries the local server
//    hands over, so kept characters and saved games are grafted and layered
//    the same way in both deployments.
//
// The reader handles the two compression methods a zip of a DOS game uses:
// stored, and deflate through DecompressionStream.

const SIG_EOCD = 0x06054b50;
const SIG_CENTRAL = 0x02014b50;
const SIG_LOCAL = 0x04034b50;
// A zip's end record can be followed by up to 64kB of comment, so the
// signature has to be searched for rather than read from a fixed offset.
const MAX_COMMENT = 0xffff;
const U32_MAX = 0xffffffff;

const text = new TextDecoder();

/** Files of the game itself, without the archive's own bookkeeping. */
const IGNORED = /^__MACOSX\/|(^|\/)\.DS_Store$|(^|\/)Thumbs\.db$/i;

async function inflate(bytes, size) {
  const stream = new Blob([bytes]).stream()
    .pipeThrough(new DecompressionStream("deflate-raw"));
  const out = new Uint8Array(size);
  let at = 0;
  // A reader, not `for await (const chunk of stream)`. Safari puts no async
  // iterator on ReadableStream. Iterating one there throws "undefined is not a
  // function", and every zip is refused.
  const reader = stream.getReader();
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    out.set(value, at);
    at += value.length;
  }
  if (at !== size) throw new Error("a file in the zip is truncated");
  return out;
}

/**
 * Every file in a zip, as {path, contents}.
 *
 * Paths keep the archive's own separators and case; the caller decides what
 * the game's directory is called and what to strip.
 */
export async function readZip(bytes) {
  if (!("DecompressionStream" in globalThis)) {
    throw new Error("this browser cannot unzip in the page");
  }
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const u16 = (at) => view.getUint16(at, true);
  const u32 = (at) => view.getUint32(at, true);

  let eocd = -1;
  for (let at = bytes.length - 22; at >= 0 && at >= bytes.length - 22 - MAX_COMMENT; at--) {
    if (u32(at) === SIG_EOCD) { eocd = at; break; }
  }
  if (eocd < 0) throw new Error("this is not a zip file");
  const count = u16(eocd + 10);
  let at = u32(eocd + 16);
  // Zip64 moves the directory's location into a second end record. Nothing
  // that fits a 1990s CD-ROM game reaches the sizes that require it.
  if (at === U32_MAX || count === 0xffff) throw new Error("zip64 archives are not supported");

  const files = [];
  for (let i = 0; i < count; i++) {
    if (u32(at) !== SIG_CENTRAL) throw new Error("this zip's directory is damaged");
    const method = u16(at + 10);
    const compressed = u32(at + 20);
    const size = u32(at + 24);
    const nameLen = u16(at + 28);
    const extraLen = u16(at + 30);
    const commentLen = u16(at + 32);
    const local = u32(at + 42);
    const path = text.decode(bytes.subarray(at + 46, at + 46 + nameLen));
    at += 46 + nameLen + extraLen + commentLen;

    if (path.endsWith("/") || IGNORED.test(path)) continue;
    if (u32(local) !== SIG_LOCAL) throw new Error(`${path}: this zip is damaged`);
    // The local header repeats the name and carries its own extra field,
    // which is not the same length as the one in the directory.
    const start = local + 30 + u16(local + 26) + u16(local + 28);
    const raw = bytes.subarray(start, start + compressed);
    if (method === 0) files.push({ path, contents: raw.slice() });
    else if (method === 8) files.push({ path, contents: await inflate(raw, size) });
    else throw new Error(`${path}: compression method ${method} is not supported`);
  }
  return files;
}

// What has to be in the zip for the game to run. SW.BAT is the launcher the
// autoexec calls and REGISTER.EXE is what it runs; WORLD.DAT holds the maps
// and the character roster, PICTURES.VGA the artwork.
const REQUIRED = ["SW.BAT", "REGISTER.EXE", "WORLD.DAT", "PICTURES.VGA"];

const base = (path) => path.slice(path.lastIndexOf("/") + 1).toUpperCase();

/**
 * The game's files, rooted where DOSBox expects them.
 *
 * The directory holding SW.BAT is the game's, wherever the zip puts it, and
 * everything under it comes along with its path made relative to that
 * directory. Files outside it are left behind.
 */
export async function gameFromZip(bytes) {
  const entries = await readZip(bytes);
  const launcher = entries.find((f) => base(f.path) === "SW.BAT");
  if (!launcher) {
    throw new Error("no SW.BAT in this zip — zip your Yendorian Tales III directory");
  }
  const root = launcher.path.slice(0, launcher.path.length - "SW.BAT".length);
  const files = entries
    .filter((f) => f.path.startsWith(root))
    .map((f) => ({ path: f.path.slice(root.length), contents: f.contents }));
  const have = new Set(
    files.filter((f) => !f.path.includes("/")).map((f) => f.path.toUpperCase()));
  const missing = REQUIRED.filter((name) => !have.has(name));
  if (missing.length) throw new Error(`this zip is missing ${missing.join(", ")}`);
  return files;
}
