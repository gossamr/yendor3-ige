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

// A container -- BAG, BOX or BACKPACK -- holds nothing itself. Its slot's
// second word is a record number into section 2 of the save, and that record
// holds the eight things inside it. Nothing marks a record as taken: the whole
// of the bookkeeping is two words in roster slot 0, which the allocator at
// image 0x1600e reads and writes.
//
// Those two words are part of the roster, so grafting characters into the
// template without them puts the counter behind the world: the grafted
// characters keep the records they were given, the counter goes back to the
// template's 3, and the next container equipped is handed a record another bag
// is already using. See docs/saves.md and tools/containers.py.
export const NEXT_RECORD = 430;   // slot 0: the next record to hand out
export const FREE_HEAD = 432;     // slot 0: the free list's head, 0 when empty
export const FIRST_RECORD = 1;    // 0 is what an unallocated container holds

// The three item ids whose category word carries the container bit 0x2000,
// which is what image 0x044bf tests before it allocates. tools/containers.py
// reads them out of the item table, and roster.test.js holds this list to it.
export const CONTAINER_ITEMS = [28, 29, 30];   // BAG, BOX, BACKPACK

// The eleven (id, state) pairs DELETE CHARACTER frees at image 0x13aab: the
// eight panel slots, then missile, container and hand.
export const SLOT_AT = 282;
export const SLOT_COUNT = 11;

// Slot 0 is the party header, not a character. Its 500 bytes hold the position,
// the clock, the purse, the party list and the sky ramp, and the ramp runs from
// +310, straight through the offsets a character keeps items at. A ramp byte of
// 28 beside a zero reads as a BAG, so the header is skipped rather than walked.
const CHARACTERS = [1, 2, 3, 4, 5, 6, 7, 8, 9];

// Slots 6-9 are the characters the game ships. They hold the records they
// have, and a created character is the one that yields, so a graft never
// renumbers SQUIRE's bag out from under him.
const STOCK = [6, 7, 8, 9];

const decoder = new TextDecoder("latin1");

const u16 = (blob, at) => blob[at] | (blob[at + 1] << 8);

function put16(blob, at, value) {
  blob[at] = value & 0xff;
  blob[at + 1] = (value >> 8) & 0xff;
}

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
 *
 * The one thing taken out of slot 0 is the container allocator's counter,
 * which `renumberContainers` moves past every record the grafted characters
 * hold. Without that a bag kept in one session and a bag equipped in the next
 * are handed the same record.
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
  const renumbered = renumberContainers(out);
  return { world: out, kept, renumbered };
}

/** Every container record number the template's characters write down. */
function containerRefs(world) {
  const out = [];
  for (const slot of CHARACTERS) {
    const base = ROSTER + slot * SLOT;
    if (!printable(nameOf(world.subarray(base, base + SLOT)))) continue;
    for (let i = 0; i < SLOT_COUNT; i++) {
      const at = base + SLOT_AT + 4 * i;
      const record = u16(world, at + 2);
      if (record && CONTAINER_ITEMS.includes(u16(world, at))) {
        out.push({ slot, at: at + 2, record });
      }
    }
  }
  return out.sort((a, b) =>
    (STOCK.includes(a.slot) ? 0 : 1) - (STOCK.includes(b.slot) ? 0 : 1)
    || a.slot - b.slot || a.at - b.at);
}

/**
 * Give every container in the template a record of its own, and move the
 * allocator's counter past all of them.
 *
 * The first container on a record keeps it and the rest are renumbered. There
 * is nothing to move with them: NEW GAME rebuilds section 2 from zeros, so
 * every container in the template starts empty. The free list is dropped,
 * since a list built while the counter was behind can name a record a bag is
 * still holding.
 */
export function renumberContainers(world) {
  const refs = containerRefs(world);
  const header = ROSTER;
  let next = Math.max(u16(world, header + NEXT_RECORD), FIRST_RECORD,
                      ...refs.map((r) => r.record + 1));
  const taken = new Set();
  const moved = [];
  for (const r of refs) {
    if (!taken.has(r.record)) {
      taken.add(r.record);
      continue;
    }
    put16(world, r.at, next);
    moved.push({ slot: r.slot, from: r.record, to: next });
    taken.add(next);
    next++;
  }
  put16(world, header + NEXT_RECORD, next);
  put16(world, header + FREE_HEAD, 0);
  return moved;
}

/** Does this blob look like the roster template, at the offset we expect? */
export function looksLikeWorld(world) {
  return decoder.decode(world.subarray(ROSTER, ROSTER + 17)) === "PRE-CREATED PARTY";
}
