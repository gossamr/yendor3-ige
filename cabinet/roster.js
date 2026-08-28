// The character roster, and grafting kept characters into the game's template.
//
// Why this is not simply a matter of saving CURGAME: the game truncates and
// rewrites the whole of that file at every launch, and again on NEW GAME, and
// it never reads the roster back out of it. Persisting CURGAME therefore keeps
// nothing: the copy on disk is overwritten before anything reads it.
//
// The roster the game *restores from* is in WORLD.DAT at 0x41D72F, the
// "PRE-CREATED PARTY" section: ten 500-byte slots, slot 0 a header, slots 1-5
// free, slots 6-9 the four characters the game ships. Writing a kept character
// into a free slot there makes it part of the roster the game rebuilds from,
// so it survives both a launch and a NEW GAME.
//
// This mirrors tools/keep_characters.py; the constants are checked against the
// real WORLD.DAT by tests on both sides.

export const ROSTER = 0x41d72f;   // "PRE-CREATED PARTY" in WORLD.DAT
export const SLOT = 500;          // bytes per character record
export const SLOTS = 10;
export const CREATED = [1, 2, 3, 4, 5];   // the slots Character Creation fills
export const ROSTER_BYTES = SLOTS * SLOT;
export const SAVE_SIZE = 81037;   // CURGAME and every SAVGAMEn are this long

const decoder = new TextDecoder("latin1");

/** A record's name: a NUL-terminated string at the top of it. */
export function nameOf(record) {
  const end = record.indexOf(0);
  return decoder.decode(record.subarray(0, end < 0 ? record.length : end)).trim();
}

const printable = (s) => s.length > 0 && [...s].every((c) => c >= " " && c <= "~");

/** Every occupied slot of a roster, as [{ slot, name }]. */
export function slotsOf(blob, base = 0) {
  const out = [];
  for (let i = 0; i < SLOTS; i++) {
    const at = base + i * SLOT;
    if (at + SLOT > blob.length) break;
    const name = nameOf(blob.subarray(at, at + SLOT));
    if (printable(name)) out.push({ slot: i, name });
  }
  return out;
}

/** The 5,000-byte roster out of a CURGAME or SAVGAMEn image. */
export function rosterOf(save) {
  if (save.length !== SAVE_SIZE) {
    throw new Error(`expected a ${SAVE_SIZE}-byte game file, got ${save.length}`);
  }
  return save.slice(0, ROSTER_BYTES);
}

/**
 * Copy the created slots of `roster` into a copy of `world`.
 *
 * Only slots 1-5 are touched: slot 0 is the header and 6-9 are the four the
 * game ships, and overwriting either would lose something the player did not
 * create. An empty source slot clears nothing, so characters kept in one
 * session and the next accumulate rather than replacing each other.
 */
export function graft(world, roster) {
  const out = new Uint8Array(world);
  const kept = [];
  for (const i of CREATED) {
    const rec = roster.subarray(i * SLOT, (i + 1) * SLOT);
    const name = nameOf(rec);
    if (!printable(name)) continue;
    out.set(rec, ROSTER + i * SLOT);
    kept.push({ slot: i, name });
  }
  return { world: out, kept };
}

/** Does this blob look like the roster template, at the offset we expect? */
export function looksLikeWorld(world) {
  return decoder.decode(world.subarray(ROSTER, ROSTER + 17)) === "PRE-CREATED PARTY";
}
