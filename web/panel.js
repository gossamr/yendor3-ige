/* Restoration panel: a modern rendering of Yendorian Tales III's in-game clue
   book, driven entirely by tables decoded out of WORLD.DAT at build time.

   window.RESTORATION holds those tables and window.GUIDES the written guides;
   tools/build_panel.py injects both. The guides are markdown, parsed here, and
   they are ours rather than the game's, which is why they ship inlined where
   the tables are fetched from the user's own copy. */
(function () {
  "use strict";

  const D = window.RESTORATION;
  const $ = (sel, el = document) => el.querySelector(sel);
  const el = (tag, props = {}, kids = []) => {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(props)) {
      // `dataset` is a read-only accessor, so it has to be filled key by key.
      if (k === "dataset") Object.assign(n.dataset, v);
      else n[k] = v;
    }
    for (const k of [].concat(kids)) n.append(k);
    return n;
  };

  /* --- capitalization --------------------------------------------------- */
  //
  // Every string in the game is stored upper case because its font had no
  // lower case. Rendering it that way is shouting, so it gets re-cased here at
  // display time while the JSON stays byte-faithful to the original.

  const PROPERS = new Set(D.propers);
  const MINOR = new Set(["of", "the", "a", "an", "and", "or", "to", "in",
                         "for", "on", "at", "by", "with"]);
  const ROMAN = /^(?:i{1,3}|iv|vi{0,3}|ix|xi{0,2})$/;

  const capitalize = (w) => w.charAt(0).toUpperCase() + w.slice(1);

  /** A word as it should appear: name, roman numeral, or plain lower case. */
  function word(w) {
    const bare = w.replace(/[^A-Za-z']/g, "");
    if (PROPERS.has(bare.toUpperCase())) return capitalize(w.toLowerCase());
    if (ROMAN.test(w.toLowerCase())) return w.toUpperCase();
    return w.toLowerCase();
  }

  /** For names and headings: "WASP QUEEN" -> "Wasp Queen". */
  function titleCase(s) {
    const parts = s.toLowerCase().split(/(\s+)/);
    let seen = 0;
    return parts.map((p) => {
      if (!p.trim()) return p;
      const isFirst = seen++ === 0;
      const w = word(p);
      if (!isFirst && MINOR.has(p.replace(/[^a-z]/g, ""))) return p;
      return w === p ? capitalize(p) : (w[0] === w[0].toUpperCase() ? w : capitalize(w));
    }).join("");
  }

  /** For prose: sentence case, with names kept capitalized. */
  function sentenceCase(s) {
    // The game draws horizontal rules by repeating a glyph that lands on 'e'
    // in ASCII, so long runs of it are a separator, not a word.
    const cleaned = s.replace(/\be{4,}\b/g, "—");
    const out = cleaned.toLowerCase().replace(/[A-Za-z'][A-Za-z']*/g, (w) => {
      if (PROPERS.has(w.toUpperCase().replace(/'S$/, ""))) return capitalize(w);
      if (w === "i") return "I";
      return w;
    });
    // A title immediately before a name is part of it: "king Yendor" reads
    // wrong where "King Yendor" does not.
    const titled = out.replace(
      /\b(king|queen|prince|princess|lord|lady|wizard|captain|governor|sir)\b(?=\s+[A-Z])/g,
      capitalize);
    // Capitalize the opening of the text and of every following sentence.
    // Only after a sentence end, never after an opening bracket: "(water,
    // hazard, etc.)" is a parenthetical, not a new sentence.
    return titled.replace(/(^|[.!?]\s+|["]\s*)([a-z])/g, (m, lead, c) => lead + c.toUpperCase());
  }

  /* --- remembered selections -------------------------------------------- */
  //
  // Which tab, which creature, which map. The panel is rebuilt and reloaded
  // while it sits open beside the game, and losing your place on every rebuild
  // costs more than the storage does. One object behind a Proxy, so an
  // ordinary assignment anywhere in the file persists and no tab has to
  // remember to save. Storage can throw outright in a private window, so every
  // touch of it is guarded and the panel runs unchanged without it.

  const STORE = "restoration.ui";
  const DEFAULTS = {
    active: "f1", monsterPick: null, spellClass: null, curveOpen: false,
    rawPages: false, mapPick: null, legendOpen: false, itemCategory: null,
    docPick: null,
  };

  function restored() {
    try {
      return Object.assign({}, DEFAULTS,
                           JSON.parse(localStorage.getItem(STORE)) || {});
    } catch (e) {
      return Object.assign({}, DEFAULTS);
    }
  }

  const ui = new Proxy(restored(), {
    set(target, key, value) {
      target[key] = value;
      try {
        localStorage.setItem(STORE, JSON.stringify(target));
      } catch (e) { /* private window, or storage disabled */ }
      return true;
    },
  });

  /* --- search ---------------------------------------------------------- */

  let query = "";
  const matches = (s) => !query || String(s).toLowerCase().includes(query);

  function highlight(text) {
    if (!query) return document.createTextNode(text);
    const frag = document.createDocumentFragment();
    const lower = text.toLowerCase();
    let i = 0;
    for (;;) {
      const at = lower.indexOf(query, i);
      if (at < 0) break;
      frag.append(text.slice(i, at), el("mark", { textContent: text.slice(at, at + query.length) }));
      i = at + query.length;
    }
    frag.append(text.slice(i));
    return frag;
  }

  /* --- trainer ---------------------------------------------------------- */

  // Off unless the page was asked for by name. The cabinet passes ?trainer
  // down to this frame only when it booted the hooked emulator, so the tab is
  // absent rather than broken when there is nothing behind it.
  const TRAINER = new URLSearchParams(location.search).has("trainer");

  // The channel the hooked emulator answers on. It is a BroadcastChannel
  // rather than a port because the emulator runs in a worker js-dos owns and
  // this code runs in an iframe, and neither holds a reference to the other, and
  // both are the same origin.
  const CHANNEL = "yendor-trainer";

  // Where things are in the game's data segment. Everything else is reached
  // from these.
  const DS = {
    pictures: 0x969E,     // "PICTURES.VGA", the anchor
    world: 0x96D0,        // "WORLD.DAT", beside it
    current: 0x537C,      // the character whose turn it is: never zero in play
    handles: 0xD0C9,      // four words, one a party slot
    roster: 0xCEDD,       // the ten 500-byte slots, header first
    characters: 0xD0D1,   // slot 1, the first character record
    character: 0x1F4,     // 500 bytes each
    // The fight. One word names whichever engaged creature is selected and the
    // three buffers follow it; the eighty spawn slots hold every creature out
    // on the map. Both are the 156-byte creature struct.
    selected: 0x54B6,
    engaged: 0x54B8,
    engagedSlots: 3,
    spawn: 0x122C,
    spawnSlots: 80,
    creature: 0x9C,
  };

  // The creature struct: a 50-byte header holding what the creature is doing
  // now, then the 106-byte record copied out of WORLD.DAT, so a record offset
  // is read at +0x32. Health now is the header's own word: the record's is
  // what the creature started with, and never moves. See docs/combat.md.
  const MOB = {
    id: 0,               // the object's number; zero means the slot is free
    impaired: 0x0C,      // & 0x3010 keeps it out of the turn list (image 0x115b)
    health: 0x10,        // at or below zero is dead (image 0x1298)
    record: 0x32,        // where the creature's own 106 bytes begin
    name: 0x32, nameField: 13,
    full: 0x32 + 30, level: 0x32 + 32,
  };

  // The roster's header slot holds where and when the party is. Same
  // displacements the save file uses, because it is the same 500 bytes --
  // see docs/saves.md.
  const HEADER = {
    facing: 150, x: 152, y: 154, day: 156, clock: 162,
    // The party's three currencies, four bytes of packed BCD each, in the
    // roster's header slot. Confirmed against saves either side of picking up
    // 30 gold, and nuore is the word the spell cost subtracts from at image
    // 0x0D336. See docs/saves.md.
    gold: 180, food: 184, nuore: 188,
  };
  const PURSE = ["gold", "food", "nuore"];
  const FACING = [[0x8000, "North"], [0x4000, "South"],
                  [0x2000, "West"], [0x1000, "East"]];
  // The world is one grid: seven areas of 24 bands down, twenty levels of 40
  // cells across, and a map is one (area, level) block of it.
  const BANDS = 24, CELLS = 40;
  const MOB_RECORD = 106;   // the enemy record, docs/monsters.md
  // The nine conditions a creature can inflict, plus the bit set when health
  // reaches zero. `docs/combat.md` has what each costs the character.
  const CONDITIONS = [
    [0x8000, "sick"], [0x4000, "poisoned"], [0x2000, "diseased"],
    [0x1000, "paralyzed"], [0x0800, "frozen"], [0x0400, "stoned"],
    [0x0200, "jinxed"], [0x0100, "hexed"], [0x0080, "cursed"], [0x0040, "dead"],
  ];
  const AFFLICTED = CONDITIONS.reduce((m, [bit]) => m | bit, 0);

  // In the order the sheet prints them. The first fourteen are what the
  // character is; the last twelve are what it can do.
  const SHEET = [
    "Strength", "Dexterity", "Stamina", "Intelligence", "Wisdom", "Charisma",
    "Shot accuracy", "Shot damage", "Accuracy", "Damage", "Absorption",
    "Health", "Magic", "Capacity",
    "Survival", "Projectile", "Slashing", "Bashing", "Polearm", "Casting",
    "Mapping", "Navigate", "Bartering", "Repair", "Thievery", "Linguistic",
  ];
  const SKILL_FROM = 14;   // where the skills start, and the table's second half

  // The class word holds 1 to 9, and a promoted tier adds 10 or 20. The first
  // three classes have no tiers; the other six are the triads the clue book's
  // F4 page names, in the same order.
  const PLAIN_CLASSES = ["fighter", "merchant", "rogue"];
  function className(code) {
    const tier = Math.floor(code / 10), base = code % 10;
    if (base >= 1 && base <= PLAIN_CLASSES.length) return PLAIN_CLASSES[base - 1];
    const triad = (D.labels.class_tiers || [])[base - 1 - PLAIN_CLASSES.length];
    return triad ? (triad[tier] || triad[0]).toLowerCase() : `class ${code}`;
  }

  const CHAR = {
    name: 0, nameLen: 14, klass: 0x0E, level: 0x16, experience: 0x18,
    condition: 0x1C, health: 0x52, magic: 0x54,
    // The twenty-six numbers the game's F1 sheet prints, held twice: what the
    // character has now at 0x3C and the maximum at 0x7C. Health and magic are
    // the pair that differ; an attribute or a skill reads the same in both
    // until a level raises it. docs/saves.md has the order.
    live: 0x3C, max: 0x7C, statStride: 2,
    // The character panel's eight carried slots, an item id and a second word
    // each. The equip dispatch fills the first empty one and refuses the item
    // when all eight are taken (image 0x437E onward), and the missile-weapon
    // slot at 0x13A is what ends the run.
    carried: 0x11A, carriedSlots: 8, carriedStride: 4,
  };
  const CHAR_BYTES = CHAR.carried + CHAR.carriedSlots * CHAR.carriedStride;

  // A value written here takes a moment to reach the game, and the tick that
  // lands in between would otherwise put the old number back in the box that
  // was just typed into. So a write quiets the refresh for a couple of ticks.
  let quietUntil = 0;
  const wrote = () => { quietUntil = Date.now() + 1500; };

  // And a box that has been typed in but not yet sent is left alone until it
  // is: several of these are filled in one at a time and sent together, and a
  // tick landing between two of them would put the game's number back in the
  // first. Focus is not enough: moving to the next field gives it up.
  const editable = (input) => {
    input.addEventListener("input", () => { input.dataset.typed = "1"; });
    return input;
  };
  const sent = (input) => { if (input) delete input.dataset.typed; };
  const refresh = (input, value) => {
    if (!input || input === document.activeElement || input.dataset.typed) return;
    if (Date.now() < quietUntil) return;
    input.value = String(value);
  };

  const emulator = (() => {
    if (!TRAINER || typeof BroadcastChannel === "undefined") return null;
    const ch = new BroadcastChannel(CHANNEL);
    const waiting = new Map();
    let next = 1;
    ch.onmessage = (e) => {
      const m = e.data;
      if (!m || m.to !== "page") return;
      const w = waiting.get(m.id);
      if (!w) return;
      waiting.delete(m.id);
      m.error ? w.reject(new Error(m.error)) : w.resolve(m);
    };
    const call = (op, extra = {}) => new Promise((resolve, reject) => {
      const id = next++;
      waiting.set(id, { resolve, reject });
      ch.postMessage({ to: "emulator", id, op, ...extra });
      // A search reads the whole heap, so the timeout has to allow for it.
      setTimeout(() => {
        if (waiting.delete(id)) reject(new Error(`${op} went unanswered`));
      }, 30000);
    });
    return {
      ping: () => call("ping"),
      peek: (at, len) => call("peek", { at, len }).then((m) => m.bytes),
      poke: (at, bytes) => call("poke", { at, bytes }),
      find: (needle, limit) => call("find", { needle, limit }).then((m) => m.found),
      // The same op with a byte needle, and optionally only at the addresses
      // an earlier search returned.
      search: (opts) => call("find", opts).then((m) => ({ found: m.found, total: m.total })),
    };
  })();

  let dsBase = null;          // where the data segment sits in the wasm heap

  const u16 = (b, at) => b[at] | (b[at + 1] << 8);
  // Four bytes, most significant pair first, two decimal digits a byte, so the
  // same packing the creature rewards use.
  const bcd = (b, at) => [0, 1, 2, 3].reduce(
    (v, i) => v * 100 + (b[at + i] >> 4) * 10 + (b[at + i] & 0xF), 0);
  const bcdBytes = (v) => {
    const s = String(Math.max(0, Math.min(99999999, v | 0))).padStart(8, "0");
    return [0, 2, 4, 6].map((i) => (+s[i] << 4) | +s[i + 1]);
  };
  const bytes16 = (v) => [v & 0xff, (v >> 8) & 0xff];
  const asText = (b) => String.fromCharCode(...b).split("\0")[0].trim();

  // Item ids as the game holds them, enchanted forms included: those are
  // separate items with their own ids, folded into the base's `variants`.
  // What an unlit torch's page prints, which is what a lit one should start
  // with. The two are separate items and only the unlit one carries the figure.
  const LIT = 240;

  let itemsById = null;
  function itemIndex() {
    if (!itemsById) {
      itemsById = new Map();
      for (const item of D.items || []) {
        // What a slot's second word should hold. For most items it is nothing.
        // For one that burns down it is how much is left, and a torch handed
        // over with zero there is a torch that has already burned out. The
        // figure is the one the item's own page prints, except for LIT
        // TORCH, whose page says zero *because* the burning one carries its
        // remaining time here rather than in its properties. It is given the
        // unlit torch's.
        const duration = Number(String((item.fields || {}).duration || "")
          .match(/^\d+/)?.[0] || 0) || (item.name === "LIT TORCH" ? LIT : 0);
        itemsById.set(item.id, { name: item.name, charge: duration });
        for (const v of item.variants || []) {
          itemsById.set(v.id, { name: `${item.name} +${v.plus}`, charge: duration });
        }
      }
    }
    return itemsById;
  }
  const itemName = (id) => itemIndex().get(id)?.name || `item ${id}`;
  const itemCharge = (id) => itemIndex().get(id)?.charge || 0;

  // A character's name is the test for "is this really the party": four
  // uppercase letters or more, and nothing that is not a name character.
  const looksLikeName = (s) => /^[A-Z][A-Z' .-]{2,}$/.test(s);

  /** The party as one candidate data segment has it, or an empty list. */
  async function partyAt(base) {
    const handles = await emulator.peek(base + DS.handles, 8);
    const out = [];
    for (let slot = 0; slot < 4; slot += 1) {
      const handle = u16(handles, slot * 2);
      // A handle is a small one-based index into the character records.
      if (!handle || handle > 32) continue;
      const at = base + DS.characters + (handle - 1) * DS.character;
      const rec = await emulator.peek(at, CHAR_BYTES);
      const name = asText(rec.slice(CHAR.name, CHAR.name + CHAR.nameLen));
      if (!looksLikeName(name)) continue;
      const carried = [];
      for (let k = 0; k < CHAR.carriedSlots; k += 1) {
        const off = CHAR.carried + k * CHAR.carriedStride;
        const id = u16(rec, off);
        carried.push({ at: at + off, id, charge: u16(rec, off + 2),
                       name: id ? itemName(id) : null });
      }
      out.push({
        // The record itself comes along: the stats panel reads twenty-six
        // words out of it twice over, and they are all inside what was
        // already read to get here.
        slot, at, name, carried, rec,
        health: u16(rec, CHAR.health),
        magic: u16(rec, CHAR.magic),
        condition: u16(rec, CHAR.condition),
        klass: u16(rec, CHAR.klass),
        level: u16(rec, CHAR.level),
        experience: bcd(rec, CHAR.experience),
      });
    }
    return out;
  }

  /** Find the game's data segment. It moves every boot, so a stale one is
   *  thrown away rather than read: the address that was the party last time is
   *  something else after the cabinet is switched off and on. */
  async function anchor() {
    if (dsBase !== null) {
      const party = await partyAt(dsBase);
      if (party.length) return { base: dsBase, party };
      dsBase = null;
    }
    // The executable's own image is in memory beside the live data segment and
    // carries the same strings, so a string cannot tell them apart. What can
    // is the party: the image on disk has no characters in it. Reading them is
    // also the thing the caller wanted, so nothing is checked twice.
    const hits = await emulator.find("PICTURES.VGA", 64);
    const near = [];
    for (const hit of hits) {
      const base = hit - DS.pictures;
      if (base < 0) continue;
      if (asText(await emulator.peek(base + DS.world, 9)) !== "WORLD.DAT") continue;
      near.push(base);
      const party = await partyAt(base);
      if (party.length) { dsBase = base; return { base, party }; }
    }
    const failed = new Error(
      `${hits.length} anchor${hits.length === 1 ? "" : "s"}, `
      + `${near.length} data segment${near.length === 1 ? "" : "s"}, no party. `
      + (hits.length === 0
        ? "The emulator answered, so the hook is in; the game has not loaded yet."
        : near.length === 0
          ? "Nothing that looked like the data segment \u2014 report this."
          : "Assemble a party and enter the game, then read again."));
    // Not loaded yet, and no party yet, are both just "wait". A data segment
    // that cannot be found at all is a fault worth printing.
    failed.waiting = hits.length === 0 || near.length > 0;
    throw failed;
  }

  // The tab is live: it re-reads the game every tick rather than waiting to be
  // asked, because the interesting moment is usually mid-fight and clicking a
  // button is one of the things that changes what you wanted to look at.
  const TRAINER_TICK = 700;
  let trainerTimer = null;
  let trainerReading = false;
  let trainerRows = null;      // name -> the row's live nodes
  let trainerNote = null;      // where a failure is reported

  function renderTrainer(root) {
    root.textContent = "";
    trainerRows = null;
    // One line across the top: what the tab is showing on the left, the button
    // that says what the tab is on the right. What it is showing is either the
    // party or the reason there is no party yet, and both start at the same
    // place. Everything else lives in a container that is not shown at all
    // until there is a game to show: a tab full of empty tables says less
    // than one line saying what it is waiting for.
    trainerHeading = el("h4", { className: "curve-sub", textContent: "Party" });
    trainerNote = el("p", { className: "empty trainer-note" });
    root.append(el("div", { className: "trainer-head" }, [
      el("div", { className: "trainer-headline" }, [trainerHeading, trainerNote]),
      ...about()]));

    trainerBody = el("div", { className: "trainer-body" });
    const body = trainerBody;
    root.append(body);
    setLive(false, "Waiting for the game\u2026");

    const table = el("table", { className: "effects trainer-table" });
    const head = el("thead");
    head.append(el("tr", {}, ["", "Health", "Magic", "Condition", ""]
      .map((t) => el("th", { scope: "col", textContent: t }))));
    table.append(head);
    table.append(el("tbody"));
    body.append(table);

    // The sheet for whichever character was asked for, under the table it is
    // asked for from. Empty until then.
    statsBox = el("div", { className: "trainer-stats" });
    statsBox.hidden = true;
    body.append(statsBox);

    // The fight. Three buffers hold what is in hand-to-hand; everything else
    // the party can shoot at is out in the spawn table, which is eighty slots
    // and is only read when it is asked for. A slot or a buffer is occupied
    // when its first word, the object's number, is set, which is the test
    // every one of the game's own walkers over them makes.
    body.append(el("h4", { className: "curve-sub", textContent: "In the fight" }));
    mobNote = el("p", { className: "empty trainer-mobnote" });
    body.append(mobNote);
    const mobTable = el("table", { className: "effects trainer-mobs" });
    mobTable.append(el("thead", {}, el("tr", {},
      ["", "Health", "Full", "Level"].map((t) => el("th", { scope: "col", textContent: t })))));
    mobTable.append(el("tbody"));
    body.append(mobTable);
    const onMap = el("input", { type: "checkbox", className: "trainer-onmap",
                                id: "trainer-onmap" });
    body.append(el("p", { className: "note" }, [
      onMap, el("label", { htmlFor: "trainer-onmap",
                           textContent: " Creatures out on the map as well" })]));
    trainerMobs = { table: mobTable, onMap };

    // Handing over an item needs somewhere to put it: the character panel's
    // eight carried slots. An enchanted form is its own item with its own id,
    // so the list offers those too.
    // Where and when. Both are words in the roster's header slot, so both are
    // one write.
    const place = el("div", { className: "picker-row", style: "margin-top:1rem" });
    const where = el("select", { className: "picker trainer-where" });
    where.setAttribute("aria-label", "Where to go");
    const pages = [...(D.map_pages || [])]
      .filter((p) => p.arrive)
      .sort((a, b) => a.title < b.title ? -1 : 1);
    for (const page of pages) {
      where.append(el("option", { value: `${page.area},${page.level}`,
                                  textContent: titleCase(page.title) }));
    }
    const go = el("button", { type: "button", className: "toggle trainer-go", textContent: "Go" });
    go.onclick = () => teleport(pages.find(
      (p) => `${p.area},${p.level}` === where.value), go);
    trainerWhere = el("span", { className: "note trainer-at" });
    place.append(where, go, trainerWhere);
    body.append(place);

    // The party's purse: three four-byte BCD counters in the same header slot.
    const purse = el("div", { className: "picker-row" });
    trainerPurse = {};
    for (const key of PURSE) {
      const input = editable(el("input", { type: "number", min: "0", max: "99999999",
                                  className: "trainer-num trainer-purse" }));
      input.setAttribute("aria-label", key);
      input.onkeydown = (e) => { if (e.key === "Enter") setPurse(key, input); };
      trainerPurse[key] = input;
      purse.append(el("span", { className: "note", textContent: titleCase(key) }), input);
    }
    const pay = el("button", { type: "button", className: "toggle trainer-pay",
                               textContent: "Set" });
    pay.onclick = () => { for (const key of PURSE) setPurse(key, trainerPurse[key]); };
    purse.append(pay);
    body.append(purse);

    const when = el("div", { className: "picker-row" });
    const clock = editable(el("input", { type: "time", className: "trainer-clock" }));
    clock.setAttribute("aria-label", "Time of day");
    clock.onchange = () => { setClock(clock.value); sent(clock); };
    trainerClock = clock;
    when.append(el("span", { className: "note", textContent: "Time" }), clock);
    trainerDay = el("span", { className: "note" });
    when.append(trainerDay);
    body.append(when);

    const give = el("div", { className: "picker-row", style: "margin-top:1rem" });
    const who = el("select", { className: "picker trainer-who" });
    who.setAttribute("aria-label", "Who gets it");
    // Every item in the game and every enchanted form of one is 631 options,
    // which is not a list anyone scrolls. The filter narrows it as you type and
    // keeps whatever was selected if it still matches.
    const all = [];
    for (const item of [...(D.items || [])].sort((a, b) => a.name < b.name ? -1 : 1)) {
      all.push({ id: item.id, label: titleCase(item.name) });
      for (const v of item.variants || []) {
        all.push({ id: v.id, label: `${titleCase(item.name)} +${v.plus}` });
      }
    }
    const what = el("select", { className: "picker trainer-what" });
    what.setAttribute("aria-label", "What to give");
    const filter = el("input", { type: "search", className: "trainer-filter",
                                 placeholder: `Filter ${all.length} items` });
    filter.setAttribute("aria-label", "Filter items");
    const fill = () => {
      const q = filter.value.trim().toLowerCase();
      const hits = q ? all.filter((i) => i.label.toLowerCase().includes(q)) : all;
      const keep = what.value;
      what.textContent = "";
      for (const i of hits) {
        what.append(el("option", { value: String(i.id), textContent: i.label }));
      }
      if (hits.some((i) => String(i.id) === keep)) what.value = keep;
      what.disabled = !hits.length;
      filter.classList.toggle("empty", !hits.length);
    };
    filter.oninput = fill;
    fill();
    const hand = el("button", { type: "button", className: "toggle trainer-give", textContent: "Give" });
    hand.onclick = () => giveItem(who.value, Number(what.value), hand);
    give.append(who, filter, what, hand);
    body.append(give);
    trainerRows = { table, who };

    renderDebug(body);

    startTrainerPoll(root);
  }

  /** What the tab is, behind a button: it is the same three paragraphs every
   *  time, and the space above the party is worth more than they are. The
   *  button rides the first heading rather than taking a line of its own. */
  function about() {
    const dialog = el("dialog", { className: "trainer-about" });
    dialog.append(el("h3", { textContent: "The trainer" }));
    for (const text of [
      "Reads and writes the running game's memory. A write lands at once, but "
      + "the game redraws its own panels on the party's next action, so take a "
      + "step to see it.",
      "A name opens that character's sheet: the twenty-six numbers the game's "
      + "own F1 page prints, held twice, as what the character has now and as "
      + "the maximum.",
      "It works only in the cabinet, only when the page was asked for with the "
      + "trainer flag in its URL, and only once a party is in play \u2014 the "
      + "game's data segment moves every boot and is found by searching for "
      + "it.",
    ]) {
      dialog.append(el("p", { className: "note", textContent: text }));
    }
    const close = el("button", { type: "button", className: "toggle", textContent: "Close" });
    close.onclick = () => dialog.close();
    dialog.append(close);
    const open = el("button", { type: "button", className: "toggle trainer-about-open",
                                textContent: "?" });
    open.setAttribute("aria-label", "About the trainer");
    open.title = "About the trainer";
    open.onclick = () => dialog.showModal();
    return [open, dialog];
  }

  /** Show the tab, or show one line saying what it is waiting for. */
  function setLive(live, message) {
    if (trainerBody) trainerBody.hidden = !live;
    if (trainerHeading) trainerHeading.hidden = !live;
    if (!live) { trainerNote.textContent = message; return; }
    // A complaint has to outlast the tick that follows it, or it is on screen
    // for less time than it takes to look down at it.
    if (Date.now() > noteUntil) trainerNote.textContent = "";
  }

  let noteUntil = 0;
  const say = (text) => {
    trainerNote.textContent = text;
    noteUntil = Date.now() + 5000;
  };

  function startTrainerPoll(root) {
    clearInterval(trainerTimer);
    if (!emulator) { setLive(false, "No emulator on the channel."); return; }
    const tick = async () => {
      if (!root.isConnected || root.hidden) { clearInterval(trainerTimer); return; }
      if (trainerReading) return;
      trainerReading = true;
      try {
        const { base, party } = await anchor();
        await applyFrozen(base);
        updateTrainer(party);
        updateHeader(await readHeader(base));
        updateCreatures(await readCreatures(base, trainerMobs.onMap.checked));
        await tickWatch(base);
        setLive(true);
      } catch (e) {
        // The ordinary case is that the game has not got there yet, and that
        // is one line rather than a paragraph. Anything else is a fault and
        // says what it is.
        setLive(false, e.waiting ? "Waiting for the game\u2026" : e.message);
      } finally {
        trainerReading = false;
      }
    };
    trainerTimer = setInterval(tick, TRAINER_TICK);
    tick();
  }

  /** Put the party's numbers on screen without disturbing what is being typed. */
  function updateTrainer(party) {
    const { table, who } = trainerRows;
    const body = table.querySelector("tbody");
    const names = party.map((p) => p.name).join("|");
    if (body.dataset.names !== names) {
      body.textContent = "";
      body.dataset.names = names;
      who.textContent = "";
      for (const person of party) {
        who.append(el("option", { value: person.name,
                                  textContent: titleCase(person.name) }));
        const row = el("tr", { dataset: { name: person.name } });
        // The name opens the sheet. A button of its own would be a fourth
        // control on a row that is already wider than the panel it sits in.
        const sheet = el("button", { type: "button", className: "trainer-sheet",
                                     textContent: titleCase(person.name) });
        sheet.onclick = () => {
          statsFor = statsFor === person.name ? null : person.name;
          updateStats();
        };
        row.append(el("th", { scope: "row" }, [sheet]));
        for (const key of ["health", "magic"]) {
          const input = editable(el("input", { type: "number", min: "0", max: "9999",
                                      className: "trainer-num", dataset: { key } }));
          // Enter writes it; anything else and the next tick puts the game's
          // own value back, which is what makes the field safe to leave alone.
          input.onkeydown = (e) => { if (e.key === "Enter") setField(person.name, key, input); };
          row.append(el("td", {}, [input]));
        }
        row.append(el("td", { className: "trainer-state" }));
        const buttons = el("td", { className: "trainer-buttons" });
        const set = el("button", { type: "button", className: "toggle", textContent: "Set" });
        set.onclick = () => {
          for (const key of ["health", "magic"]) {
            setField(person.name, key, row.querySelector(`input[data-key="${key}"]`));
          }
        };
        // Hidden rather than absent when there is nothing wrong: a button that
        // comes and goes would move everything under it every time a character
        // is poisoned.
        const cure = el("button", { type: "button", className: "toggle trainer-cure",
                                    textContent: "Cure" });
        cure.onclick = () => cureCharacter(person.name);
        buttons.append(set, cure);
        row.append(buttons);
        body.append(row);
      }
    }
    trainerParty = party;
    for (const person of party) {
      const row = body.querySelector(`tr[data-name="${CSS.escape(person.name)}"]`);
      if (!row) continue;
      for (const key of ["health", "magic"]) {
        refresh(row.querySelector(`input[data-key="${key}"]`), person[key]);
      }
      // What is wrong with them, which is the thing a button here can fix. What
      // they are carrying is on the game's own panel already.
      const ills = CONDITIONS.filter(([bit]) => person.condition & bit)
        .map(([, name]) => name);
      const state = row.querySelector(".trainer-state");
      state.textContent = ills.length ? ills.join(", ") : "\u2014";
      state.classList.toggle("ill", ills.length > 0);
      const cure = row.querySelector(".trainer-cure");
      cure.hidden = !ills.length;
      cure.textContent = person.condition & 0x0040 ? "Revive" : "Cure";
      row.querySelector(".trainer-sheet").classList
        .toggle("on", statsFor === person.name);
    }
    updateStats();
  }

  function updateHeader(at) {
    trainerAt = at;
    if (posBand) { refresh(posBand, at.band); refresh(posCell, at.cell); }
    if (posFacing && posFacing !== document.activeElement) {
      const bit = (FACING.find(([, name]) => name === at.facing) || [0])[0];
      if (bit) posFacing.value = String(bit);
    }
    trainerWhere.textContent =
      `${at.page ? titleCase(at.page.title) : `area ${at.area} level ${at.level}`}`
      + ` \u00b7 band ${at.band} cell ${at.cell} \u00b7 facing ${at.facing}`;
    refresh(trainerClock, hhmm(at.clock));
    trainerDay.textContent = `day ${at.day}`;
    for (const key of PURSE) {
      if (trainerPurse[key]) refresh(trainerPurse[key], at.purse[key]);
    }
  }

  let trainerParty = [];
  let trainerHeading = null;
  let trainerBody = null;
  let trainerMobList = [];
  let trainerAt = null;
  let statsBox = null;
  let statsFor = null;         // whose sheet is open, by name
  let trainerMobs = null;
  let mobNote = null;
  let trainerWhere = null;
  let trainerClock = null;
  let trainerDay = null;
  let trainerPurse = {};

  const hhmm = (m) => `${String(Math.floor(m / 60)).padStart(2, "0")}`
    + `:${String(m % 60).padStart(2, "0")}`;

  /** Where and when the party is, from the roster's header slot. */
  async function readHeader(base) {
    const b = await emulator.peek(base + DS.roster, HEADER.nuore + 4);
    const x = u16(b, HEADER.x), y = u16(b, HEADER.y);
    const facing = u16(b, HEADER.facing);
    const area = Math.floor(y / BANDS), level = Math.floor(x / CELLS);
    const page = (D.map_pages || []).find((p) => p.area === area && p.level === level);
    return {
      x, y, area, level, page,
      band: y % BANDS, cell: x % CELLS,
      facing: (FACING.find(([bit]) => facing & bit) || [0, "?"])[1],
      day: u16(b, HEADER.day), clock: u16(b, HEADER.clock),
      purse: Object.fromEntries(PURSE.map((k) => [k, bcd(b, HEADER[k])])),
    };
  }

  async function teleport(page, button) {
    if (!page || dsBase === null) return;
    const [band, cell] = page.arrive;
    button.textContent = "\u2026";
    // x and y are one grid across the whole world, and the area and level fall
    // out of them: `area = y / 24`, `level = x / 40`. Nothing else is written,
    // because nothing else in the header is known to hold either.
    const at = dsBase + DS.roster;
    await emulator.poke(at + HEADER.x, bytes16(page.level * CELLS + cell));
    await emulator.poke(at + HEADER.y, bytes16(page.area * BANDS + band));
    button.textContent = "Go";
  }

  async function setPurse(key, input) {
    if (dsBase === null) return;
    await emulator.poke(dsBase + DS.roster + HEADER[key], bcdBytes(Number(input.value)));
    wrote();
    sent(input);
    input.blur();
  }

  async function setClock(value) {
    if (dsBase === null || !/^\d\d:\d\d$/.test(value)) return;
    const [h, m] = value.split(":").map(Number);
    await emulator.poke(dsBase + DS.roster + HEADER.clock, bytes16(h * 60 + m));
  }


  async function setField(name, key, input) {
    const person = trainerParty.find((p) => p.name === name);
    if (!person) return;
    await emulator.poke(person.at + CHAR[key], bytes16(Number(input.value) | 0));
    wrote();
    sent(input);
    input.blur();
  }

  /** Lift every condition, the dead bit included. */
  async function cureCharacter(name) {
    const person = trainerParty.find((p) => p.name === name);
    if (!person) return;
    await emulator.poke(person.at + CHAR.condition,
                        bytes16(person.condition & ~AFFLICTED & 0xFFFF));
  }

  async function giveItem(name, id, button) {
    const person = trainerParty.find((p) => p.name === name);
    if (!person || !id) return;
    const free = person.carried.find((c) => !c.id);
    if (!free) { say(`${titleCase(name)} is carrying eight already.`); return; }
    button.textContent = "\u2026";
    try {
      // The id, and beside it whatever the item needs there. A torch's second
      // word is how much of it is left to burn (image 0x0EB8F decrements it
      // and puts the light out at zero), so handing one over with a zero
      // hands over a torch that has already burned down.
      await emulator.poke(free.at, [...bytes16(id), ...bytes16(itemCharge(id))]);
      trainerNote.textContent = "";
    } catch (e) {
      say(e.message);
    }
    button.textContent = "Give";
  }


  /* --- the sheet -------------------------------------------------------- */

  /** The twenty-six numbers, both columns, for whoever asked. */
  function updateStats() {
    if (!statsBox) return;
    const person = trainerParty.find((p) => p.name === statsFor);
    statsBox.hidden = !person;
    if (!person) { statsBox.dataset.name = ""; return; }
    if (statsBox.dataset.name !== person.name) buildStats(person);
    for (const input of statsBox.querySelectorAll("input.trainer-stat")) {
      const at = CHAR[input.dataset.col] + Number(input.dataset.index) * CHAR.statStride;
      refresh(input, u16(person.rec, at));
    }
    refresh(statsBox.querySelector(".trainer-level"), person.level);
    refresh(statsBox.querySelector(".trainer-xp"), person.experience);
  }

  function buildStats(person) {
    statsBox.textContent = "";
    statsBox.dataset.name = person.name;
    const head = el("div", { className: "picker-row" });
    head.append(el("strong", { textContent: titleCase(person.name) }),
                el("span", { className: "note",
                             textContent: titleCase(className(person.klass)) }),
                el("span", { className: "note", textContent: "Level" }));
    const level = editable(el("input", { type: "number", min: "1", max: "99",
                                className: "trainer-num trainer-level" }));
    level.setAttribute("aria-label", "level");
    level.onchange = () => {
      write(person.at + CHAR.level, bytes16(Number(level.value) | 0));
      sent(level);
    };
    const xp = editable(el("input", { type: "number", min: "0", max: "99999999",
                             className: "trainer-num trainer-xp" }));
    xp.setAttribute("aria-label", "experience");
    xp.onchange = () => {
      write(person.at + CHAR.experience, bcdBytes(Number(xp.value)));
      sent(xp);
    };
    head.append(level, el("span", { className: "note", textContent: "Exp." }), xp);
    statsBox.append(head);

    // Two stats to a row: the fourteen the character is on the left, the
    // twelve it can do on the right. Each is held twice, and both are
    // writable: raising an attribute without its maximum leaves the next
    // level-up to put it back.
    const table = el("table", { className: "effects trainer-sheet-table" });
    table.append(el("thead", {}, el("tr", {},
      ["Attribute", "Now", "Max", "Skill", "Now", "Max"]
        .map((t) => el("th", { scope: "col", textContent: t })))));
    const body = el("tbody");
    const cell = (index, col) => {
      const input = editable(el("input", { type: "number", min: "0", max: "9999",
                                  className: "trainer-num trainer-stat",
                                  dataset: { index: String(index), col } }));
      // "live" is what the code calls it; "now" is what the column says.
      input.setAttribute("aria-label",
                         `${SHEET[index]} ${col === "live" ? "now" : "max"}`);
      input.onchange = () => {
        write(person.at + CHAR[col] + index * CHAR.statStride,
              bytes16(Number(input.value) | 0));
        sent(input);
      };
      return el("td", {}, [input]);
    };
    for (let i = 0; i < SKILL_FROM; i += 1) {
      const row = el("tr");
      row.append(el("th", { scope: "row", textContent: SHEET[i] }),
                 cell(i, "live"), cell(i, "max"));
      const j = SKILL_FROM + i;
      if (j < SHEET.length) {
        row.append(el("th", { scope: "row", textContent: SHEET[j] }),
                   cell(j, "live"), cell(j, "max"));
      } else {
        for (let k = 0; k < 3; k += 1) row.append(el("td", {}));
      }
      body.append(row);
    }
    table.append(body);
    statsBox.append(table);
    statsBox.append(el("p", { className: "note", textContent:
      "Capacity is what the character can carry, in tenths of a unit." }));
  }

  /** Every write goes through here, so every write quiets the refresh. */
  async function write(at, bytes) {
    if (!emulator) return;
    try {
      await emulator.poke(at, bytes);
      wrote();
      trainerNote.textContent = "";
    } catch (e) {
      say(e.message);
    }
  }

  /* --- the fight -------------------------------------------------------- */

  /** What is engaged, and what else is out on the map if that was asked for. */
  async function readCreatures(base, includeMap) {
    // The selected-creature pointer and the three buffers behind it are
    // contiguous, so they are one read.
    const buf = await emulator.peek(base + DS.selected,
                                    2 + DS.engagedSlots * DS.creature);
    const selected = u16(buf, 0);
    const out = [];
    for (let i = 0; i < DS.engagedSlots; i += 1) {
      const off = 2 + i * DS.creature;
      if (!u16(buf, off + MOB.id)) continue;
      const where = DS.engaged + i * DS.creature;
      out.push(creature(buf, off, base + where, `Engaged ${i + 1}`, where === selected));
    }
    if (includeMap) {
      const slots = await emulator.peek(base + DS.spawn, DS.spawnSlots * DS.creature);
      for (let i = 0; i < DS.spawnSlots; i += 1) {
        const off = i * DS.creature;
        if (!u16(slots, off + MOB.id)) continue;
        out.push(creature(slots, off, base + DS.spawn + off, `Slot ${i}`, false));
      }
    }
    return out;
  }

  function creature(b, off, at, where, selected) {
    const field = (k) => asText(b.slice(off + MOB.name + k * MOB.nameField,
                                        off + MOB.name + (k + 1) * MOB.nameField));
    return {
      at, where, selected,
      name: [field(0), field(1)].filter(Boolean).join(" "),
      health: u16(b, off + MOB.health),
      full: u16(b, off + MOB.full),
      level: u16(b, off + MOB.level),
      impaired: u16(b, off + MOB.impaired),
      // The record itself, for the debug editor: it is inside what was read.
      rec: b.slice(off + MOB.record, off + MOB.record + MOB_RECORD),
    };
  }

  function updateCreatures(mobs) {
    const { table } = trainerMobs;
    const body = table.querySelector("tbody");
    mobNote.textContent = mobs.length ? "" : "Nothing in the fight.";
    const key = mobs.map((m) => `${m.where}:${m.name}`).join("|");
    if (body.dataset.key !== key) {
      body.textContent = "";
      body.dataset.key = key;
      for (const mob of mobs) {
        const row = el("tr", { dataset: { where: mob.where } });
        row.append(el("th", { scope: "row" }, [
          el("span", { textContent: titleCase(mob.name) }),
          el("span", { className: "note", textContent: ` ${mob.where}` })]));
        const health = editable(el("input", { type: "number", min: "0", max: "32767",
                                     className: "trainer-num trainer-hp" }));
        health.setAttribute("aria-label", `${mob.name} health`);
        // The end-of-turn pass marks anything at or below zero dead and pays
        // out for it, so a zero here is a kill rather than a corpse left
        // standing.
        health.onchange = () => {
          write(mob.at + MOB.health, bytes16(Number(health.value) | 0));
          sent(health);
        };
        row.append(el("td", {}, [health]),
                   el("td", { textContent: String(mob.full) }),
                   el("td", { textContent: String(mob.level) }));
        body.append(row);
      }
    }
    for (const mob of mobs) {
      const row = body.querySelector(`tr[data-where="${CSS.escape(mob.where)}"]`);
      if (!row) continue;
      refresh(row.querySelector(".trainer-hp"), mob.health);
      row.classList.toggle("on", mob.selected);
    }
    trainerMobList = mobs;
    if (debugBox && debugBox.open) updateMobEdit(mobs);
  }

  /* --- debug ------------------------------------------------------------ */
  //
  // Everything below is for taking the game apart rather than playing it: raw
  // fields, raw addresses, and no guard against a value the game cannot reach
  // on its own. It is one collapsed block at the foot of the tab so that the
  // controls above it, the ones that play the game, are what the tab is.

  // The creature record's combat fields, as record offsets; `docs/monsters.md`
  // has the rest. Split because the four flag words are read and written in
  // hex and the rest in decimal.
  const MOB_FIELDS = [
    [30, "Health full"], [32, "Level"], [34, "Accuracy"], [36, "Dexterity"],
    [38, "Absorption"], [40, "Damage"], [50, "Shot accuracy"], [52, "Shot damage"],
  ];
  const MOB_FLAGS = [
    [96, "Word 96"], [98, "Word 98"], [100, "Immunity"], [102, "Resistance"],
  ];
  // The turn-list builder leaves out a creature with any of these; setting them
  // holds a fight still while it is read (image 0x115b).
  const IMPAIRED = 0x3010;

  let debugBox = null;
  let posFacing = null, posBand = null, posCell = null;
  let mobPick = null, mobFields = null;

  function renderDebug(root) {
    debugBox = el("details", { className: "trainer-debug" });
    debugBox.append(el("summary", { textContent: "Debug" }));
    debugBox.append(el("p", { className: "note", textContent:
      "For taking the game apart rather than playing it. These write raw "
      + "fields at raw addresses, with nothing checking that the result is a "
      + "state the game can reach on its own." }));
    renderPosition(debugBox);
    renderMobEdit(debugBox);
    renderWatch(debugBox);
    root.append(debugBox);
  }

  /* Position: the same header words the map picker writes, one cell at a
     time, for standing somewhere the picker's arrival cell is not. */
  function renderPosition(root) {
    root.append(el("h4", { className: "curve-sub", textContent: "Position" }));
    const row = el("div", { className: "picker-row" });
    posFacing = el("select", { className: "picker debug-facing" });
    posFacing.setAttribute("aria-label", "Facing");
    for (const [bit, name] of FACING) {
      posFacing.append(el("option", { value: String(bit), textContent: name }));
    }
    posBand = editable(el("input", { type: "number", min: "0", max: String(BANDS - 1),
                            className: "trainer-num debug-band" }));
    posBand.setAttribute("aria-label", "Band");
    posCell = editable(el("input", { type: "number", min: "0", max: String(CELLS - 1),
                            className: "trainer-num debug-cell" }));
    posCell.setAttribute("aria-label", "Cell");
    const set = el("button", { type: "button", className: "toggle debug-place",
                               textContent: "Set" });
    set.onclick = () => setPosition();
    row.append(posFacing,
               el("span", { className: "note", textContent: "Band" }), posBand,
               el("span", { className: "note", textContent: "Cell" }), posCell,
               set);
    root.append(row);
    root.append(el("p", { className: "note", textContent:
      "Within the map the party is already on. A cell that is not part of the "
      + "drawn map is not somewhere the party can stand." }));
  }

  /** Band and cell within the current map, and which way the party looks. */
  async function setPosition() {
    if (dsBase === null || !trainerAt) return;
    const at = dsBase + DS.roster;
    const band = Math.min(BANDS - 1, Math.max(0, Number(posBand.value) | 0));
    const cell = Math.min(CELLS - 1, Math.max(0, Number(posCell.value) | 0));
    await write(at + HEADER.x, bytes16(trainerAt.level * CELLS + cell));
    await write(at + HEADER.y, bytes16(trainerAt.area * BANDS + band));
    await write(at + HEADER.facing, bytes16(Number(posFacing.value) | 0));
    sent(posBand);
    sent(posCell);
  }

  /* Creatures: the record itself, live. `tools/fight_probe.js` does the same
     thing by patching WORLD.DAT before boot and paying for a boot per reading;
     this changes a creature that is already standing there. A shot resolves
     against the map slot and a swing against the engaged buffer, so an
     experiment on a volley edits the slot; tick the map box above to reach
     one. */
  function renderMobEdit(root) {
    root.append(el("h4", { className: "curve-sub", textContent: "Creatures" }));
    const row = el("div", { className: "picker-row" });
    mobPick = el("select", { className: "picker debug-mob" });
    mobPick.setAttribute("aria-label", "Which creature");
    mobPick.onchange = () => updateMobEdit(trainerMobList);
    const pacify = el("button", { type: "button", className: "toggle debug-pacify",
                                  textContent: "Pacify" });
    pacify.onclick = () => withMob((mob) =>
      write(mob.at + MOB.impaired, bytes16(mob.impaired | IMPAIRED)));
    const kill = el("button", { type: "button", className: "toggle debug-kill",
                                textContent: "Kill" });
    kill.onclick = () => withMob((mob) => write(mob.at + MOB.health, bytes16(0)));
    const clear = el("button", { type: "button", className: "toggle debug-clear",
                                 textContent: "Clear the map" });
    clear.onclick = () => clearMap(clear);
    row.append(mobPick, pacify, kill, clear);
    root.append(row);
    mobFields = el("div", { className: "debug-fields" });
    root.append(mobFields);
  }

  const withMob = (fn) => {
    const mob = trainerMobList.find((m) => m.where === mobPick.value);
    return mob ? fn(mob) : undefined;
  };

  /** Free every spawn slot. Word 0 is what the game's own walkers test, so a
   *  zero there is a slot with nothing in it. */
  async function clearMap(button) {
    if (dsBase === null) return;
    button.textContent = "\u2026";
    for (let i = 0; i < DS.spawnSlots; i += 1) {
      await write(dsBase + DS.spawn + i * DS.creature + MOB.id, bytes16(0));
    }
    button.textContent = "Clear the map";
  }

  function updateMobEdit(mobs) {
    if (!mobPick) return;
    const key = mobs.map((m) => m.where).join("|");
    if (mobPick.dataset.key !== key) {
      const keep = mobPick.value;
      mobPick.dataset.key = key;
      mobPick.textContent = "";
      for (const mob of mobs) {
        mobPick.append(el("option", { value: mob.where,
          textContent: `${mob.where} \u00b7 ${titleCase(mob.name)}` }));
      }
      if (mobs.some((m) => m.where === keep)) mobPick.value = keep;
      mobPick.disabled = !mobs.length;
    }
    const mob = mobs.find((m) => m.where === mobPick.value);
    if (!mob) {
      mobFields.textContent = "";
      mobFields.append(el("p", { className: "note",
                                 textContent: "Nothing to edit." }));
      mobFields.dataset.where = "";
      return;
    }
    if (mobFields.dataset.where !== mob.where) buildMobFields(mob);
    for (const input of mobFields.querySelectorAll("input")) {
      const off = Number(input.dataset.off);
      const v = u16(mob.rec, off);
      refresh(input, input.dataset.hex ? `0x${hex(v, 4)}` : v);
    }
  }

  function buildMobFields(mob) {
    mobFields.textContent = "";
    mobFields.dataset.where = mob.where;
    const grid = el("div", { className: "debug-grid" });
    const field = (off, label, asHex) => {
      const input = asHex
        ? editable(el("input", { type: "text", className: "watch-at debug-field",
                                 dataset: { off: String(off), hex: "1" } }))
        : editable(el("input", { type: "number", min: "0", max: "65535",
                                 className: "trainer-num debug-field",
                                 dataset: { off: String(off) } }));
      input.setAttribute("aria-label", label);
      input.onchange = () => {
        write(mob.at + MOB.record + off, bytes16(readNumber(input)));
        sent(input);
      };
      grid.append(el("div", { className: "debug-pair" }, [
        el("span", { className: "note", textContent: label }), input]));
    };
    for (const [off, label] of MOB_FIELDS) field(off, label, false);
    for (const [off, label] of MOB_FLAGS) field(off, label, true);
    mobFields.append(grid);
  }

  /** A field's value, decimal or `0x` hex. */
  const readNumber = (input) => {
    const text = String(input.value).trim();
    const v = /^0x/i.test(text) ? parseInt(text.slice(2), 16) : Number(text);
    return Number.isFinite(v) ? (v & 0xffff) : 0;
  };

  /* --- memory ----------------------------------------------------------- */

  // Somewhere to start from. Every one is a data-segment offset, so they hold
  // across a reboot even though the segment itself moves.
  const WATCH_SPOTS = [
    ["Party header", DS.roster, 200],
    ["Character 1", DS.characters, 128],
    ["Combat flags", 0x5370, 32],
    ["Turn list", 0x5696, 112],
    ["Engaged 1", DS.engaged, DS.creature],
    ["Spawn slot 0", DS.spawn, DS.creature],
    ["Attack table", 0x96DA, 96],
    ["Attack readouts", 0x0F4A, 80],
  ];
  const WATCH_MAX = 1024;      // bytes, so the dump stays a page
  const WATCH_LOG = 200;       // lines kept
  const SCAN_KEEP = 20000;     // addresses a search hands back
  const SCAN_SHOWN = 16;
  const hex = (v, w) => v.toString(16).padStart(w, "0");

  let watch = null;            // { at, len, snapshot, last }
  let watchBox = null;
  let watchDump = null;
  let watchLog = null;
  let watchHits = null;
  let scanFound = null;        // heap addresses the last search left
  let frozenList = null;
  let frozen = [];             // [{ at, bytes }], rewritten every tick

  function renderWatch(root) {
    watchBox = el("div", { className: "trainer-watch" });
    watchBox.append(el("h4", { className: "curve-sub", textContent: "Memory" }));
    watchBox.append(el("p", { className: "note", textContent:
      "A window on the data segment, re-read every tick. Bytes that differ "
      + "from the snapshot are lit, and every word that changes is logged. "
      + "The search takes a value the game is showing and hands back where it "
      + "could be; change the value in the game and narrow to find which." }));

    const pick = el("div", { className: "picker-row" });
    const spot = el("select", { className: "picker watch-spot" });
    spot.setAttribute("aria-label", "Where to watch");
    WATCH_SPOTS.forEach(([label], i) => {
      spot.append(el("option", { value: String(i), textContent: label }));
    });
    const at = el("input", { type: "text", className: "watch-at" });
    at.setAttribute("aria-label", "Address, hex, from the data segment");
    const len = el("input", { type: "number", min: "2", max: String(WATCH_MAX),
                              className: "trainer-num watch-len" });
    len.setAttribute("aria-label", "Length");
    const load = ([, spotAt, spotLen]) => {
      at.value = `0x${hex(spotAt, 4)}`;
      len.value = String(spotLen);
    };
    load(WATCH_SPOTS[0]);
    spot.onchange = () => { load(WATCH_SPOTS[Number(spot.value)]); startWatch(at, len); };
    const go = el("button", { type: "button", className: "toggle watch-go",
                              textContent: "Watch" });
    go.onclick = () => startWatch(at, len);
    const stop = el("button", { type: "button", className: "toggle watch-stop",
                                textContent: "Stop" });
    stop.onclick = () => { watch = null; watchDump.textContent = ""; };
    pick.append(spot, el("span", { className: "note", textContent: "DS +" }),
                at, len, go, stop);
    watchBox.append(pick);

    watchDump = el("pre", { className: "watch-dump" });
    watchLog = el("pre", { className: "watch-log" });
    watchBox.append(watchDump, watchLog);

    const hunt = el("div", { className: "picker-row" });
    const value = el("input", { type: "number", className: "trainer-num watch-value" });
    value.setAttribute("aria-label", "Value to search for");
    const width = el("select", { className: "picker watch-width" });
    width.setAttribute("aria-label", "How it is stored");
    for (const [v, label] of [["word", "word"], ["byte", "byte"], ["bcd", "BCD"]]) {
      width.append(el("option", { value: v, textContent: label }));
    }
    const search = el("button", { type: "button", className: "toggle watch-search",
                                  textContent: "Search" });
    search.onclick = () => runScan(value, width, false, search);
    const narrow = el("button", { type: "button", className: "toggle watch-narrow",
                                  textContent: "Narrow" });
    narrow.onclick = () => runScan(value, width, true, narrow);
    hunt.append(value, width, search, narrow);
    watchBox.append(hunt);
    watchHits = el("div", { className: "watch-hits" });
    watchBox.append(watchHits);

    // The write side. A search that cannot be acted on is a viewer: this is
    // what makes the address it found worth having.
    const put = el("div", { className: "picker-row" });
    const putAt = el("input", { type: "text", className: "watch-at watch-put-at" });
    putAt.setAttribute("aria-label", "Address to write, hex, from the data segment");
    const putBytes = el("input", { type: "text", className: "watch-at watch-put-bytes" });
    putBytes.setAttribute("aria-label", "Bytes to write, hex");
    putBytes.placeholder = "39 30";
    const writeIt = el("button", { type: "button", className: "toggle watch-write",
                                   textContent: "Write" });
    writeIt.onclick = () => pokeFrom(putAt, putBytes);
    // Freezing is the same write, made again on every tick. It is how a value
    // stays put through a routine that keeps setting it back.
    const freeze = el("button", { type: "button", className: "toggle watch-freeze",
                                  textContent: "Freeze" });
    freeze.onclick = () => addFreeze(putAt, putBytes);
    put.append(el("span", { className: "note", textContent: "DS +" }),
               putAt, putBytes, writeIt, freeze);
    watchBox.append(put);
    frozenList = el("div", { className: "watch-frozen" });
    watchBox.append(frozenList);
    root.append(watchBox);
  }

  /** Bytes from `12 34` or `1234` or `0x1234`; anything that is not a hex
   *  digit separates. */
  function hexBytes(text) {
    const clean = String(text).replace(/0x/gi, " ").replace(/[^0-9a-f]+/gi, "");
    if (!clean || clean.length % 2) return null;
    return clean.match(/../g).map((h) => parseInt(h, 16));
  }

  const watchAddress = (input) => {
    const at = parseInt(String(input.value).replace(/^0x/i, ""), 16);
    return Number.isInteger(at) && at >= 0 ? at : null;
  };

  async function pokeFrom(atInput, bytesInput) {
    const at = watchAddress(atInput), bytes = hexBytes(bytesInput.value);
    if (dsBase === null || at === null || !bytes) {
      say("An address and an even number of hex digits.");
      return;
    }
    await write(dsBase + at, bytes);
  }

  function addFreeze(atInput, bytesInput) {
    const at = watchAddress(atInput), bytes = hexBytes(bytesInput.value);
    if (at === null || !bytes) {
      say("An address and an even number of hex digits.");
      return;
    }
    if (!frozen.some((f) => f.at === at)) frozen.push({ at, bytes });
    drawFrozen();
  }

  function drawFrozen() {
    frozenList.textContent = "";
    if (!frozen.length) return;
    frozenList.append(el("p", { className: "note", textContent: "Frozen" }));
    for (const f of frozen) {
      const label = `+0x${hex(f.at, 4)} = ${f.bytes.map((b) => hex(b, 2)).join(" ")}`;
      const drop = el("button", { type: "button", className: "toggle watch-thaw",
                                  textContent: `${label}  \u00d7` });
      drop.setAttribute("aria-label", `Stop freezing ${label}`);
      drop.onclick = () => {
        frozen = frozen.filter((x) => x !== f);
        drawFrozen();
      };
      frozenList.append(drop);
    }
  }

  /** Written before the tick reads, so what is shown is what was frozen. */
  async function applyFrozen(base) {
    for (const f of frozen) await emulator.poke(base + f.at, f.bytes);
  }

  function startWatch(at, len) {
    const where = parseInt(String(at.value).replace(/^0x/i, ""), 16);
    const size = Math.min(WATCH_MAX, Math.max(2, Number(len.value) | 0));
    if (!Number.isInteger(where) || where < 0) {
      say(`${at.value} is not an address.`);
      return;
    }
    watch = { at: where, len: size, snapshot: null, last: null };
    watchLog.textContent = "";
  }

  /** Read the window, light what has moved since the snapshot, log what moved
   *  since the last read. */
  async function tickWatch(base) {
    if (!watch || !debugBox.open) return;
    const now = await emulator.peek(base + watch.at, watch.len);
    if (!watch.snapshot) watch.snapshot = now;
    if (watch.last) {
      const lines = [];
      for (let i = 0; i + 1 < watch.len; i += 2) {
        const was = u16(watch.last, i), is = u16(now, i);
        if (was !== is) {
          lines.push(`+0x${hex(watch.at + i, 4)}  0x${hex(was, 4)} -> 0x${hex(is, 4)}`
                     + `   ${was} -> ${is}`);
        }
      }
      if (lines.length) {
        const kept = (watchLog.textContent ? watchLog.textContent.split("\n") : []);
        watchLog.textContent = lines.concat(kept).slice(0, WATCH_LOG).join("\n");
      }
    }
    watch.last = now;
    drawDump(now);
  }

  function drawDump(now) {
    const out = document.createDocumentFragment();
    for (let i = 0; i < watch.len; i += 16) {
      out.append(`${hex(watch.at + i, 4)}  `);
      for (let k = 0; k < 16 && i + k < watch.len; k += 1) {
        const text = `${hex(now[i + k], 2)} `;
        if (now[i + k] === watch.snapshot[i + k]) out.append(text);
        else out.append(el("span", { className: "watch-moved", textContent: text }));
      }
      out.append("\n");
    }
    watchDump.textContent = "";
    watchDump.append(out);
  }

  /** The value as the game would hold it. */
  function scanBytes(value, width) {
    const v = Number(value.value) | 0;
    if (width.value === "byte") return [v & 0xff];
    if (width.value === "bcd") return bcdBytes(v);
    return bytes16(v & 0xffff);
  }

  async function runScan(value, width, narrow, button) {
    if (!emulator) return;
    if (narrow && !scanFound) {
      say("Search once before narrowing.");
      return;
    }
    button.textContent = "\u2026";
    try {
      const res = await emulator.search({
        bytes: scanBytes(value, width), limit: SCAN_KEEP,
        candidates: narrow ? scanFound : undefined,
      });
      scanFound = res.found;
      showHits(res);
      trainerNote.textContent = "";
    } catch (e) {
      say(e.message);
    }
    button.textContent = narrow ? "Narrow" : "Search";
  }

  function showHits(res) {
    watchHits.textContent = "";
    const more = res.total > res.found.length ? `, ${res.found.length} kept` : "";
    watchHits.append(el("p", { className: "note",
      textContent: `${res.total} address${res.total === 1 ? "" : "es"}${more}` }));
    for (const found of res.found.slice(0, SCAN_SHOWN)) {
      const off = dsBase === null ? -1 : found - dsBase;
      const inside = off >= 0 && off < 0x10000;
      const label = inside ? `DS +0x${hex(off, 4)}` : `heap 0x${hex(found, 6)}`;
      const b = el("button", { type: "button", className: "toggle", textContent: label });
      // A hit inside the data segment is somewhere the window can go; one
      // outside it is not, and says so by not being offered.
      b.disabled = !inside;
      b.onclick = () => {
        const at = watchBox.querySelector(".watch-at");
        const len = watchBox.querySelector(".watch-len");
        at.value = `0x${hex(off & ~1, 4)}`;
        len.value = "32";
        startWatch(at, len);
      };
      watchHits.append(b);
    }
  }

  /** A globe, drawn rather than typed: the panel's font has no glyph that
   *  reads as one at 14 pixels. */
  function globeIcon() {
    const NS = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(NS, "svg");
    for (const [k, v] of Object.entries({
      viewBox: "0 0 16 16", width: "14", height: "14", fill: "none",
      stroke: "currentColor", "stroke-width": "1.2", "aria-hidden": "true",
    })) svg.setAttribute(k, v);
    for (const d of [
      "M14.6 8a6.6 6.6 0 1 1-13.2 0a6.6 6.6 0 0 1 13.2 0",   // the sphere
      "M8 1.4c-2 1.8-3 4-3 6.6s1 4.8 3 6.6",                 // the meridians
      "M8 1.4c2 1.8 3 4 3 6.6s-1 4.8-3 6.6",
      "M1.9 5.6h12.2", "M1.9 10.4h12.2",                     // the parallels
    ]) {
      const path = document.createElementNS(NS, "path");
      path.setAttribute("d", d);
      svg.append(path);
    }
    return svg;
  }

  /** The whole world, over the panel. It is 6,400 pixels wide, so it opens
   *  fitted to the dialog and scrolls at its own size on a click. */
  function worldDialog() {
    const dialog = el("dialog", { className: "world-map" });
    const head = el("div", { className: "world-map-head" });
    const shell = el("div", { className: "world-map-shell" });
    // The self-contained build carries the picture; the shell fetches its
    // tables from a server, and that server has the file.
    shell.append(el("img", { className: "world-map-img",
      src: D.world_map || "/data/world.png",
      alt: "Every map in the game, drawn where it sits on the world grid" }));
    const zoom = el("button", { type: "button", className: "toggle world-map-zoom",
                                textContent: "Actual size" });
    zoom.onclick = () => {
      const full = shell.classList.toggle("full");
      zoom.textContent = full ? "Fit" : "Actual size";
    };
    const close = el("button", { type: "button", className: "toggle world-map-close",
                                 textContent: "Close" });
    close.onclick = () => dialog.close();
    head.append(el("strong", { textContent: "The world" }),
                el("span", { className: "note", textContent:
                  "Twenty levels across, seven areas down, and every map drawn "
                  + "in its own block of the grid." }),
                zoom, close);
    dialog.append(head, shell);
    return dialog;
  }

  /* --- F3 spells -------------------------------------------------------- */

  const MAGIC_CLASSES = ["MONK", "ALCHEMIST", "PALADIN", "MAGE", "DRUID", "MARKSMAN"];

  /** What a spell does, in one word: the thing you scan the list for. */
  // Harm and heal are both a magnitude; the color says which, so the chip only
  // needs the number. PERFECT HEALTH stores 9999 to mean "all health points".
  function spellKind(s) {
    if (s.damage) {
      return {
        label: String(s.damage), cls: "harm", title: `${s.damage} damage`,
        magnitude: s.damage, noun: "damage",
      };
    }
    const text = (s.description || "").toLowerCase();
    // Lean on the decoded restorative flag rather than on the prose naming
    // "health": Great Heal and Restore Health both say "restore N points",
    // and matching on the word alone filed them as utility spells.
    if (s.restorative && /restore|heal/.test(text)) {
      const all = s.amount >= 9999;
      return {
        label: all ? "Full" : (s.amount ? String(s.amount) : "Heal"),
        cls: "heal",
        title: all ? "restores all health" : `restores ${s.amount} health`,
        // "All health" has no figure to divide, so it has no rate either.
        magnitude: all ? null : s.amount,
        noun: "healing",
      };
    }
    if (/remove|cure|relieve/.test(text)) return { label: "Cure", cls: "heal" };
    return { label: "Utility", cls: "util" };
  }

  // What a point of each resource buys you. MP regenerates and nuore does not,
  // so the two rates answer different questions and are both worth showing.
  const rate = (n) => (n >= 1 ? n.toFixed(1) : n.toFixed(2));

  function efficiency(s, kind) {
    if (!kind.magnitude) return [];
    return [["MP", s.mp], ["nuore", s.nuore]]
      .filter(([, cost]) => cost > 0)
      .map(([unit, cost]) => ({
        text: `${rate(kind.magnitude / cost)}/${unit}`,
        title: `${kind.magnitude} ${kind.noun} for ${cost} ${unit}`,
      }));
  }

  // How far the spell reaches, as distinct from when it may be cast. This is
  // where the ranged sense lives. A reach of "in hand to hand" is deliberately
  // absent: it never says anything the Melee condition has not already said.
  const REACH = {
    "at a distance": "Ranged",
    "in a 3x3 area": "3x3 area",
    "in a straight line": "In a line",
  };

  // The game's three casting conditions, shortened. "OUT OF HAND TO HAND" is a
  // restriction on when you may cast, that you must be out of combat, and not a
  // targeting mode. The two rows are nested, not independent: every spell
  // reaching "at a distance", "in a 3x3 area" or "in a straight line" is cast
  // out of melee, and every spell reaching "in hand to hand" is cast in it. So
  // this row is the coarse condition and REACH is the pattern within it.
  const WHEN = {
    "in hand to hand": "Melee",
    "out of hand to hand": "OOC",
    anytime: "Anytime",
  };

  // What survives of the target once side and scope have said their part: the
  // restrictions that genuinely narrow it.
  function targetQualifier(s) {
    if (!s.target) return null;
    const bits = [];
    if (s.target.includes("visible")) bits.push("Visible");
    // A spell restricted to one kind of creature is named by that kind: the
    // restriction is the whole point, so the word carries it on its own.
    if (s.target.includes("undead")) bits.push("Undead");
    if (s.target.includes("insect")) bits.push("Insect");
    return bits.join(", ") || null;
  }

  /** Single target or area, and what it lands on. */
  function spellReach(s) {
    if (!s.scope) return null;
    // Shape only. Coloring this by side duplicated the harm/heal color: every
    // damaging spell targets monsters and every healing one targets the party,
    // across all 98 without exception, so the side was never new information.
    return {
      shape: s.scope === "all" ? "all" : "single",
      title: [s.scope, s.target].filter(Boolean).join(" "),
    };
  }

  const SVG_NS = "http://www.w3.org/2000/svg";

  /** A small inline SVG on a 12x12 grid, sized in ems so it tracks the text. */
  function icon(cls, build) {
    const svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("viewBox", "0 0 12 12");
    svg.setAttribute("class", `icon ${cls}`);
    svg.setAttribute("aria-hidden", "true");
    build({
      dot: (cx, cy, r) => {
        const c = document.createElementNS(SVG_NS, "circle");
        c.setAttribute("cx", cx); c.setAttribute("cy", cy); c.setAttribute("r", r);
        c.setAttribute("fill", "currentColor");
        svg.append(c);
      },
      area: (x, y, w, h, opacity) => {
        const r = document.createElementNS(SVG_NS, "rect");
        r.setAttribute("x", x); r.setAttribute("y", y);
        r.setAttribute("width", w); r.setAttribute("height", h);
        r.setAttribute("fill", "currentColor");
        r.setAttribute("opacity", opacity);
        svg.append(r);
      },
      line: (d, width = 1.1) => {
        const path = document.createElementNS(SVG_NS, "path");
        path.setAttribute("d", d);
        path.setAttribute("fill", "none");
        path.setAttribute("stroke", "currentColor");
        path.setAttribute("stroke-width", width);
        path.setAttribute("stroke-linecap", "round");
        path.setAttribute("stroke-linejoin", "round");
        svg.append(path);
      },
    });
    return svg;
  }

  /** A scroll seen edge-on: a sheet between two rolled ends. */
  function scrollIcon() {
    return icon("scroll", ({ area, line }) => {
      // The sheet is filled rather than outlined: drawn as two side edges it
      // reads as an H-bar at this size.
      area(2.6, 3, 6.8, 6, .38);
      line("M2 3h8M2 9h8", 2.2);   // the rolls, top and bottom
    });
  }

  // How many the spell lands on. The dots are literal: one target, or many.
  const SCOPE_ICONS = {
    single: ({ dot }) => dot(6, 6, 2.4),
    all: ({ dot }) => { dot(3.4, 4.2, 1.7); dot(8.6, 4.2, 1.7); dot(6, 8.6, 1.7); },
  };

  const elementClass = (name) =>
    name.toLowerCase().replace(" damage", "").replace(/\s+/g, "-");

  const elementNote = (name) => {
    const plain = name.toLowerCase().replace(" damage", "");
    return `monsters immune to ${plain} take none`;
  };

  // What the damage is made of. Drawn as shapes, not colors: color in this
  // panel already means harm-or-heal and friend-or-foe, and a third color
  // scale on top of those would collide with both. These inherit the damage
  // color, so the element adds a channel without spending one.
  //
  // The vocabulary is the game's own: these are the very bits a monster's
  // immunity word is tested against, so "cold" here and "immune to cold" on the
  // monster page are the same flag.
  const ELEMENT_ICONS = {
    FIRE: ({ line }) => line("M6 1.5c2.2 2.2.8 3.4 2 4.7 1.2 1.3 1.6 2.2 1.6 3"
      + "a3.6 3.6 0 0 1-7.2 0c0-1.9 1.3-3.1 2.4-4.1 1.2-1 1.5-2.2 1.2-3.6z"),
    COLD: ({ line }) => line("M6 1.2v9.6M2 3.6l8 4.8M10 3.6l-8 4.8"),
    ELECTRIC: ({ line }) => line("M7.2 1.2 3.2 6.4h2.6l-1 4.4 4-5.4H6.2z"),
    POWER: ({ dot, line }) => {
      dot(6, 6, 1.5);
      line("M6 1.2v1.8M6 9v1.8M1.2 6h1.8M9 6h1.8"
        + "M2.6 2.6l1.3 1.3M8.1 8.1l1.3 1.3M9.4 2.6 8.1 3.9M3.9 8.1 2.6 9.4", .9);
    },
    POISON: ({ line }) => line("M6 1.3c2.5 3 3.8 4.5 3.8 6A3.8 3.8 0 0 1 2.2 7.3"
      + "c0-1.5 1.3-3 3.8-6z"),
    DISEASE: ({ dot, line }) => {
      line("M6 1.6a4.4 4.4 0 1 0 .01 0z", 1);
      dot(4.6, 5, 1); dot(7.4, 5.4, .9); dot(5.8, 7.8, .9);
    },
    "MAGIC DAMAGE": ({ line }) =>
      line("M6 1.2 7.1 4.9 10.8 6 7.1 7.1 6 10.8 4.9 7.1 1.2 6 4.9 4.9z"),
  };

  // The shape the spell covers, drawn as the shape itself.
  const REACH_ICONS = {
    "in a 3x3 area": ({ dot }) => {
      for (const y of [2.6, 6, 9.4]) for (const x of [2.6, 6, 9.4]) dot(x, y, 1.15);
    },
    "in a straight line": ({ dot }) => {
      for (const x of [2.4, 6, 9.6]) dot(x, 6, 1.3);
    },
    "at a distance": ({ dot, line }) => {
      dot(1.8, 6, 1.3);
      line("M4.2 6h5.4M7.6 3.9 9.9 6l-2.3 2.1");
    },
  };

  function castRow(s) {
    const wrap = el("div", { className: "cast" });
    for (const c of s.classes) {
      const on = !ui.spellClass || c.class === ui.spellClass;
      const tag = el("span", {
        className: "cast-class" + (on ? "" : " dim"),
        title: c.source === "SCROLL"
          ? `${titleCase(c.class)} level ${c.level}, learned from a scroll`
          : c.source === "TRAINING"
            ? `${titleCase(c.class)} level ${c.level}, learned by training`
            : `${titleCase(c.class)} knows this from the start`,
        textContent: `${titleCase(c.class)} ${c.level}`,
      });
      // A scroll-taught spell is not granted on leveling; the level is only
      // the gate. Mark it with the item you need rather than the word.
      if (c.source === "SCROLL") tag.append(scrollIcon());
      wrap.append(tag);
    }
    return wrap;
  }


  function renderSpells(root) {
    root.textContent = "";

    // Filter by caster: the question the clue book's class column exists to
    // answer is "what can this character cast, and at what level".
    //
    // Each chip carries its own count, under whatever is in the search box. So
    // the row says where the hits are before you press anything, so search for
    // "fire" and the classes that have none read (0).
    const found = D.spells.filter((s) => s.listed
      && (matches(s.name) || matches(s.description)));
    const countFor = (c) => (c
      ? found.filter((s) => s.classes.some((x) => x.class === c)).length
      : found.length);

    const filter = el("div", { className: "chipbar" });
    const addClass = (label, value) => {
      const b = el("button", { type: "button", className: "toggle" });
      b.append(document.createTextNode(label));
      b.append(el("span", { className: "count", textContent: ` (${countFor(value)})` }));
      b.setAttribute("aria-pressed", String(ui.spellClass === value));
      b.onclick = () => { ui.spellClass = value; renderSpells(root); };
      filter.append(b);
    };
    addClass("All classes", null);
    for (const c of MAGIC_CLASSES) addClass(titleCase(c), c);

    // What the costs are worth, folded into this tab rather than given one of
    // its own: it is the same six classes seen a second way, and it is scoped
    // by the chips below rather than by a second row of controls. It sits
    // above them because it is a view of the whole tab, not a filter within
    // it, and closed, which it is by default, it is one chip.
    const costs = el("details", { className: "curve-box" });
    costs.open = ui.curveOpen;
    costs.addEventListener("toggle", () => { ui.curveOpen = costs.open; });
    costs.append(el("summary", { textContent: "Efficiency" }));
    // The analysis gets its own ground so it reads as a panel the control
    // opened, rather than as more of the spell tab, while the control itself
    // stays the size of its label.
    const costBody = el("div", { className: "curve-body" });
    appendCurve(costBody, ui.spellClass);
    costs.append(costBody);
    root.append(costs);
    root.append(filter);

    let hits = found;
    if (ui.spellClass) {
      hits = hits.filter((s) => s.classes.some((c) => c.class === ui.spellClass));
      // Sorted by the level that class needs, which is the order you learn them.
      hits.sort((a, b) => level(a) - level(b) || a.name.localeCompare(b.name));
    }
    function level(s) {
      const c = s.classes.find((x) => x.class === ui.spellClass);
      return c ? c.level : 99;
    }

    if (!hits.length) {
      return root.append(el("p", { className: "empty", textContent: "No spell matches." }));
    }

    for (const s of hits) {
      const card = el("div", { className: "spell" });
      const head = el("div", { className: "spell-head" });
      const name = el("h4");
      name.append(highlight(titleCase(s.name)));
      if (ui.spellClass) {
        head.append(el("span", { className: "lvl", textContent: `L${level(s)}` }));
      }
      head.append(name);
      const kind = spellKind(s);
      const element = (s.element || [])[0];
      const chip = el("span", {
        className: `chip ${kind.cls}${element ? " " + elementClass(element) : ""}`,
        title: element ? `${kind.title}, ${elementNote(element)}` : (kind.title || ""),
        textContent: kind.label,
      });
      const glyph = element && ELEMENT_ICONS[element];
      if (glyph) chip.append(icon("element-glyph", glyph));
      head.append(chip);
      const reach = spellReach(s);
      if (reach) {
        const chip = el("span", { className: "chip scope", title: reach.title });
        chip.append(icon("scope", SCOPE_ICONS[reach.shape]));
        head.append(chip);
      }
      card.append(head);

      const meta = el("div", { className: "spell-meta" });
      const qualifier = targetQualifier(s);
      if (qualifier) meta.append(el("span", { textContent: qualifier }));
      // Reach and when are drawn from the same enumeration, so for most spells
      // they say the same thing; REACH only maps the ones that add something.
      const shape = REACH_ICONS[s.reach];
      if (shape) {
        const span = el("span", { className: "reach", title: REACH[s.reach] });
        span.append(icon("shape", shape));
        span.append(document.createTextNode(REACH[s.reach]));
        meta.append(span);
      }
      if (s.when) meta.append(el("span", { textContent: WHEN[s.when] || s.when }));
      meta.append(el("span", { className: "num", textContent: `${s.mp} MP` }));
      if (s.nuore) meta.append(el("span", { className: "num", textContent: `${s.nuore} nuore` }));
      for (const e of efficiency(s, kind)) {
        meta.append(el("span", { className: "eff", title: e.title, textContent: e.text }));
      }
      card.append(meta);

      if (s.classes.length) card.append(castRow(s));
      const desc = el("p", { className: "spell-desc" });
      desc.append(highlight(sentenceCase(s.description)));
      card.append(desc);
      root.append(card);
    }
  }

  /* --- F1 maps, F4 classes, F5 items ------------------------------------ */

  /** Draw a map page onto a canvas from its grid and tileset.

   * The canvas is sized in game pixels and stretched by CSS, so the browser
   * scales it as a whole with `image-rendering: pixelated`, crisp at any
   * panel width, and no bitmap to ship.
   */
  function drawMap(page, canvas) {
    const T = page.tile;
    const tiles = atob(page.tiles);
    const grid = atob(page.grid);
    const palette = page.palette.map((hex) => [
      parseInt(hex.slice(1, 3), 16),
      parseInt(hex.slice(3, 5), 16),
      parseInt(hex.slice(5, 7), 16),
    ]);
    canvas.width = page.cols * T;
    canvas.height = page.rows * T;
    const ctx = canvas.getContext("2d");
    const img = ctx.createImageData(canvas.width, canvas.height);
    const out = img.data;
    for (let r = 0; r < page.rows; r += 1) {
      for (let c = 0; c < page.cols; c += 1) {
        const tile = grid.charCodeAt(r * page.cols + c) * T * T;
        for (let y = 0; y < T; y += 1) {
          for (let x = 0; x < T; x += 1) {
            const [pr, pg, pb] = palette[tiles.charCodeAt(tile + y * T + x)];
            const at = ((r * T + y) * canvas.width + c * T + x) * 4;
            out[at] = pr; out[at + 1] = pg; out[at + 2] = pb; out[at + 3] = 255;
          }
        }
      }
    }
    // The markers (exits, people, items) are painted over the tiles rather
    // than being tiles, so they come as their own small layer.
    const sprites = atob(page.sprites || "");
    for (const [r, c, sprite] of page.overlay || []) {
      const at = sprite * T * T;
      for (let y = 0; y < T; y += 1) {
        for (let x = 0; x < T; x += 1) {
          const [pr, pg, pb] = palette[sprites.charCodeAt(at + y * T + x)];
          const i = ((r * T + y) * canvas.width + c * T + x) * 4;
          out[i] = pr; out[i + 1] = pg; out[i + 2] = pb; out[i + 3] = 255;
        }
      }
    }
    ctx.putImageData(img, 0, 0);
  }

  /** Re-focus the selected area after the list is rebuilt. */
  function focusCurrent(root) {
    const b = root.querySelector('.maps-list [aria-current="true"]');
    if (b) b.focus();
  }


  // A legend line that names another map is a door, and the registry names
  // every map, so the line can carry you there. "EXIT TO YENDOR" and a bare
  // "COPPER MINE" both resolve; "SAXON'S SHIP TO THAINE" does not, because
  // Thaine is ten maps and the label does not say which. Where the data cannot
  // say, nothing is offered rather than a guess.
  function destination(label, pages, from) {
    if (!label) return null;
    const walked = (D.map_links || {})[`${from}|${label}`];
    if (walked) return walked;
    const text = String(label).toUpperCase().trim();
    // "EXIT TO X", "PORTAL TO X", "SAXON'S SHIP TO X" all name X after " TO ".
    const at = text.lastIndexOf(" TO ");
    const name = at === -1 ? text : text.slice(at + 4).trim();
    // A bare "LEVEL 2" or "MAP 3" means this place's level 2: the stairs
    // inside one dungeon are labeled by the level alone.
    const bare = /^(LEVEL|MAP) \d+$/.test(name);
    if (bare && from) {
      const place = String(from).split(" LEVEL ")[0].split(" MAP ")[0];
      const here = pages.find((p) => p.title === `${place} ${name}`);
      if (here) return here.title;
    }
    const exact = pages.filter((p) => p.title === name);
    if (exact.length === 1) return exact[0].title;
    // A place with exactly one map can be named without its suffix.
    const place = pages.filter((p) => p.title === name
      || p.title.startsWith(`${name} MAP `) || p.title.startsWith(`${name} LEVEL `)
      // "SHIP TO HOMELAND MAP 3" names Dwarven Homeland Map 3 by its tail.
      || p.title.endsWith(` ${name}`));
    return place.length === 1 ? place[0].title : null;
  }

  function renderMaps(root) {
    root.textContent = "";

    const pages = D.map_pages.filter((p) => matches(p.title));
    if (!pages.length) {
      root.append(el("p", { className: "empty", textContent: "No area matches." }));
      return;
    }
    if (!pages.some((p) => p.title === ui.mapPick)) ui.mapPick = pages[0].title;
    const shown = pages.find((p) => p.title === ui.mapPick);

    // The map comes first. Thirty-seven area names above it meant scrolling
    // past the whole list to reach the thing the tab is for.
    const figure = el("figure", { className: "map" });
    const frame = el("div", { className: "map-frame" });
    frame.style.setProperty("--map-aspect", String(shown.cols / shown.rows));
    const canvas = el("canvas", { className: "map-canvas" });
    canvas.setAttribute("role", "img");
    canvas.setAttribute("aria-label", `Map of ${titleCase(shown.title)}`);
    frame.append(canvas);
    // The gold squares on the page are the legend markers, and nothing on the
    // page says which is which. The marker records do, so each one gets its
    // number, laid over the canvas as positioned elements rather than drawn
    // into it: the bitmap is 272px wide and scaled up, so a number painted
    // into it would scale up as a blur.
    const marks = (D.map_marks || {})[shown.title] || [];
    for (const m of marks) {
      if (!m.shown) continue;
      const goes = destination(m.label, D.map_pages, shown.title);
      const badge = el(goes ? "button" : "span", {
        className: goes ? "map-mark to" : "map-mark",
        textContent: String(m.n),
        title: goes ? `${titleCase(m.label)} \u2014 go to ${titleCase(goes)}`
                    : (m.label ? titleCase(m.label) : "no caption decoded"),
      });
      if (goes) {
        badge.type = "button";
        badge.onclick = () => { ui.mapPick = goes; renderMaps(root); };
      }
      // `cell` is the column in the stored row; `col` was relative to the
      // book's cropped window, which the page no longer uses.
      badge.style.left = `${(((m.cell ?? m.col + 3) + 0.5) / shown.cols) * 100}%`;
      badge.style.top = `${((m.row + 0.5) / shown.rows) * 100}%`;
      frame.append(badge);
    }
    figure.append(frame);
    const caption = el("figcaption");
    // The 140 map slots are one grid, 20 levels across by 7 areas down, and
    // a map is one block of it, so they can be drawn where they actually
    // sit. `tools/world_map.py` does that, and the globe opens what it wrote.
    // It keeps the far end of the caption line the map's name starts, so it is
    // in the same place whichever map is showing and however long its name is.
    const world = worldDialog();
    const globe = el("button", { type: "button", className: "map-globe" });
    globe.setAttribute("aria-label", "The world map");
    globe.title = "The world map";
    globe.append(globeIcon());
    globe.onclick = () => world.showModal();
    caption.append(el("strong", { textContent: titleCase(shown.title) }), globe);
    figure.append(caption);
    // The dialog is a sibling of the figure rather than a child of the
    // caption: inside it, its own heading is a second `figcaption strong`.
    root.append(world);
    drawMap(shown, canvas);

    // Then the picker, in a box of its own so it can never push the map away.
    const list = el("div", { className: "list maps-list" });
    for (const page of pages) {
      const b = el("button", { type: "button" });
      b.append(highlight(titleCase(page.title)));
      b.setAttribute("aria-current", String(page.title === ui.mapPick));
      b.onclick = () => { ui.mapPick = page.title; renderMaps(root); };
      // Arrow keys walk the areas without leaving the keyboard, and without
      // tabbing through thirty-seven buttons to reach the one below.
      b.onkeydown = (e) => {
        const step = e.key === "ArrowDown" ? 1 : e.key === "ArrowUp" ? -1 : 0;
        if (!step) return;
        e.preventDefault();
        const at = pages.findIndex((x) => x.title === ui.mapPick);
        const next = pages[Math.min(pages.length - 1, Math.max(0, at + step))];
        if (next) { ui.mapPick = next.title; renderMaps(root); focusCurrent(root); }
      };
      list.append(b);
    }
    // Map first in the source order, so a narrow panel shows it first; wide
    // enough and the two sit side by side instead of the list falling off the
    // bottom of a very large map.
    const layout = el("div", { className: "map-layout" });
    layout.append(figure, list);
    root.append(layout);

    // Keep the chosen area visible when the selection moves under a search.
    const current = list.querySelector('[aria-current="true"]');
    if (current) current.scrollIntoView({ block: "nearest" });

    // The legend, numbered to match the badges on the map. Both come from the
    // marker records, which carry each line's own square and page, so the
    // numbering is the game's data rather than a guess at pairing.
    if (marks.length) {
      root.append(el("h3", { className: "curve-head",
        textContent: `On this map (${marks.length})` }));
      const own = el("ol", { className: "map-own" });
      for (const m of marks) {
        const li = el("li");
        li.value = m.n;
        const goes = destination(m.label, D.map_pages, shown.title);
        if (goes) {
          const b = el("button", { className: "map-goto", type: "button",
            title: `Go to ${titleCase(goes)}` });
          b.append(highlight(titleCase(m.label)));
          b.onclick = () => { ui.mapPick = goes; renderMaps(root); };
          li.append(b);
        } else {
          li.append(highlight(titleCase(m.label || "\u2014")));
        }
        if (!m.shown) {
          li.append(el("span", { className: "map-offpage",
            title: "This line's square is outside the columns the page prints",
            textContent: " off the printed page" }));
        }
        own.append(li);
      }
      root.append(own);
    }

    // Every label has a page now, its own record saying which, but the book
    // prints only 37 of the 140 map slots, so a third of the legend belongs to
    // slots it leaves out. That is worth offering once, not on every page.
    const elsewhere = D.map_unplaced || [];
    if (elsewhere.length) {
      const bar = el("div", { className: "legend-bar" });
      const toggle = el("button", {
        type: "button", className: "toggle",
        // Named, because the registry names every map: these belong to maps
        // the panel cannot draw yet, not to maps the game leaves nameless.
        textContent: (() => {
          const maps = [...new Set(elsewhere.map((m) => m.map).filter(Boolean))];
          return maps.length
            ? `Legend lines for ${maps.map(titleCase).join(" and ")} (${elsewhere.length})`
            : `Legend lines for maps not shown here (${elsewhere.length})`;
        })(),
      });
      toggle.setAttribute("aria-expanded", String(ui.legendOpen || Boolean(query)));
      toggle.onclick = () => { ui.legendOpen = !ui.legendOpen; renderMaps(root); };
      bar.append(toggle);
      root.append(bar);
      if (ui.legendOpen || query) {
        const lg = el("div", { className: "grid2" });
        for (const u of elsewhere.filter((u) => matches(u.label))) {
          const d = el("div");
          d.append(highlight(titleCase(u.label)));
          d.append(el("span", { className: "map-offpage",
            textContent: ` block ${u.area}, slot ${u.level}` }));
          lg.append(d);
        }
        root.append(lg);
      }
    }

    // Searching should find a label wherever it lives, and say where that is.
    if (query) {
      const others = Object.entries(D.map_marks || {})
        .filter(([title]) => title !== shown.title)
        .flatMap(([title, ms]) => ms
          .filter((m) => m.label && matches(m.label))
          .map((m) => [m.label, title, m.n]));
      if (others.length) {
        root.append(el("h3", { className: "curve-head",
          textContent: `On other maps (${others.length})` }));
        const other = el("div", { className: "grid2 map-own-other" });
        for (const [label, title, n] of others) {
          const d = el("div");
          d.append(highlight(titleCase(label)));
          d.append(el("span", { className: "map-where",
                                textContent: ` ${titleCase(title)} #${n}` }));
          other.append(d);
        }
        root.append(other);
      }
    }
  }

  /* --- items ------------------------------------------------------------ */

  // The eight categories the clue book files items under, in its own order.
  // Six of them are lists of item ids in the executable; the other two are
  // pages of their own: rules for the enhancers, and three transports that
  // are not items at all.
  const ITEM_CATEGORIES = D.labels.item_categories;
  const PAGE_CATEGORIES = new Set(["ATTRIBUTE ENHANCERS", "TRANSPORTATIONS"]);

  // The ink the game prints each field in, so the panel reads like the screen
  // it came from: value and weight in yellow, damage and absorption in red,
  // where it fits in blue, the skill it uses in green.
  // Several fields are a figure followed by what it applies to, and the game
  // colors the two halves differently, "40" in red and "JINXING" in green. So
  // an ink is a pair: one for the number, one for the words after it.
  const ITEM_INK = {
    damage: { num: "harm", text: "harm" },
    absorption: { num: "harm", text: "harm" },
    "fits in": { num: "fits", text: "fits" },
    skill: { num: "skill", text: "skill" },
    protections: { num: "harm", text: "skill" },
    restores: { num: "harm", text: "skill" },
    cures: { num: "skill", text: "skill" },
    adds: { num: "harm", text: "skill" },
    duration: { num: "value", text: "plain" },
    uses: { num: "value", text: "plain" },
    when: { num: "value", text: "plain" },
    teaches: { num: "skill", text: "skill" },
    worn: { num: "fits", text: "fits" },
    magic: { num: "value", text: "plain" },
  };
  const DEFAULT_INK = { num: "value", text: "plain" };

  // What the words after the figure are: a named thing the game capitalizes
  // (a skill, a condition, a container) or ordinary prose that should not be.
  const PHRASE_FIELDS = new Set(["restores", "cures"]);

  const formatValue = (field, value) => {
    if (field === "fits in") return value.split(" ").map(titleCase).join(", ");
    if (PHRASE_FIELDS.has(field)) return value.toLowerCase();
    return titleCase(value);
  };

  function itemMatches(item) {
    if (!item.listed) return false;
    if (ui.itemCategory && item.category !== ui.itemCategory) return false;
    if (!query) return true;
    return matches(item.name)
      || matches(item.category || "")
      || Object.values(item.fields || {}).flat().some((v) => matches(String(v)));
  }

  function renderItems(root) {
    root.textContent = "";

    const counts = new Map();
    for (const item of D.items) {
      if (item.listed) counts.set(item.category, (counts.get(item.category) || 0) + 1);
    }

    const bar = el("div", { className: "chipbar" });
    const addCat = (label, value) => {
      // Same control as the spell class selector: one toggle style for every
      // filter in the panel.
      const b = el("button", { type: "button", className: "toggle", textContent: label });
      b.setAttribute("aria-pressed", String(ui.itemCategory === value));
      b.onclick = () => { ui.itemCategory = value; draw(); };
      bar.append(b);
    };
    addCat("All items", null);
    for (const c of ITEM_CATEGORIES) {
      if (counts.get(c) || PAGE_CATEGORIES.has(c)) addCat(titleCase(c), c);
    }
    root.append(bar);

    // ATTRIBUTE ENHANCERS has no items to list: the clue book gives it a page
    // of rules instead, so show those rather than leaving the category out.
    if (ui.itemCategory === "ATTRIBUTE ENHANCERS") {
      root.append(el("p", { className: "note", textContent:
        "The clue book gives this category a page of rules rather than a list "
        + "of items: what each kind of enhancer raises, and by how much." }));
      const rules = el("div", { className: "items" });
      for (const rule of D.enhancers) {
        const row = el("div", { className: "item" });
        const head = el("div", { className: "item-head" });
        head.append(el("h4", { textContent: titleCase(rule.kind) }));
        head.append(el("span", { className: "ink caption",
                                 textContent: "permanently add" }));
        head.append(el("span", { className: "ink harm",
                                 textContent: String(rule.amount) }));
        head.append(el("span", { className: "ink skill",
                                 textContent: `to ${/^[AEIOU]/.test(rule.raises) ? "an" : "a"} `
                                   + rule.raises.toLowerCase() }));
        row.append(head);
        rules.append(row);
      }
      root.append(rules);
      return;
    }

    // TRANSPORTATIONS is the other page that is not a list: three things that
    // appear nowhere in the item records, held in a table of their own.
    if (ui.itemCategory === "TRANSPORTATIONS") {
      root.append(el("p", { className: "note", textContent:
        "Not items: these three are a table of their own, and the game charges "
        + "for a fixed number of flights rather than selling you the animal." }));
      const rides = el("div", { className: "items" });
      for (const t of D.transports) {
        const row = el("div", { className: "item" });
        const head = el("div", { className: "item-head" });
        head.append(el("h4", { textContent: titleCase(t.name) }));
        head.append(el("span", { className: "ink value",
                                 textContent: t.value.toLocaleString() }));
        row.append(head);
        const meta = el("div", { className: "item-meta" });
        meta.append(fieldSpan("uses", t.uses));
        meta.append(fieldSpan("when", t.when));
        row.append(meta);
        rides.append(row);
      }
      root.append(rides);
      return;
    }

    const hits = D.items.filter(itemMatches);
    root.append(el("p", { className: "note", textContent: ui.itemCategory
      ? `${hits.length} ${titleCase(ui.itemCategory).toLowerCase()}.`
      : `${hits.length} items, as the clue book lists them. Every row is `
        + `decoded from the game's files: the record, the properties table `
        + `it points at, and the effects entry behind Adds and Protections, `
        + `and shown in the colors the game prints it in.` }));

    if (!hits.length) {
      root.append(el("p", { className: "empty", textContent: "No items match." }));
      return;
    }

    const list = el("div", { className: "items" });
    for (const item of hits) list.append(itemCard(item));
    root.append(list);
  }

  // One "Caption 40 Jinxing" run, colored the way the game colors it: the
  // figure in one ink and the words after it in another.
  function fieldSpan(field, value, caption = true) {
    const ink = ITEM_INK[field] || DEFAULT_INK;
    const span = el("span", { className: "field" });
    // The game prints the caption on the first row of a field and leaves the
    // continuation rows bare, so a three-line Protections reads as one field.
    span.append(el("span", { className: "ink caption",
                             textContent: caption ? `${titleCase(field)} ` : "" }));
    const lead = String(value).match(/^([\d.,]+)\s*(.*)$/);
    if (lead) {
      span.append(el("span", { className: `ink ${ink.num}`,
                               textContent: lead[1] + (lead[2] ? " " : "") }));
      if (lead[2]) {
        const rest = el("span", { className: `ink ${ink.text}` });
        rest.append(highlight(formatValue(field, lead[2])));
        span.append(rest);
      }
    } else {
      const only = el("span", { className: `ink ${ink.text}` });
      only.append(highlight(formatValue(field, String(value))));
      span.append(only);
    }
    return span;
  }

  function itemCard(item) {
    const card = el("div", { className: "item" });
    const head = el("div", { className: "item-head" });
    const name = el("h4");
    name.append(highlight(titleCase(item.name)));
    head.append(name);
    if (item.value) {
      head.append(el("span", { className: "ink value",
                               textContent: item.value.toLocaleString() }));
    }
    if (item.weight) {
      head.append(el("span", { className: "ink value",
                               title: `weighs ${item.weight}`,
                               textContent: `${item.weight.toFixed(1)} wt` }));
    }
    if (item.absorption) {
      head.append(el("span", { className: "ink harm",
                               title: "absorption",
                               textContent: `${item.absorption} abs` }));
    }
    card.append(head);

    const meta = el("div", { className: "item-meta" });
    // A scroll's own page never says which spell it teaches: the record does.
    if (item.spell) meta.append(fieldSpan("teaches", item.spell));
    if (item.slot) meta.append(fieldSpan("worn", item.slot));
    for (const [field, value] of Object.entries(item.fields || {})) {
      // A field the game prints on several rows, as Adds and Protections both
      // carry up to four, comes through as a list, one span each.
      let first = true;
      for (const one of [].concat(value)) {
        if (one === null || one === "") continue;
        meta.append(fieldSpan(field, one, first));
        first = false;
      }
    }
    if (meta.childNodes.length) card.append(meta);

    // The book puts an item's enchanted forms behind a +0..+8 selector rather
    // than listing them, and the record keeps them as separate entries; show
    // the ladder as one line instead of repeating the item nine times.
    if (item.variants.length) {
      const row = el("div", { className: "variants" });
      row.append(el("span", { className: "variants-label", textContent: "Enchanted" }));
      for (const v of item.variants) {
        row.append(el("span", {
          className: "variant",
          title: `+${v.plus}: ${v.value.toLocaleString()} value, ${v.weight} weight`
            + (v.absorption ? `, ${v.absorption} absorption` : ""),
          textContent: `+${v.plus}`,
        }));
      }
      card.append(row);
    }
    return card;
  }

  /* --- casting curve ---------------------------------------------------- */

  // Two things the clue book cannot tell you by listing spells in order.
  //
  // First: as a class levels, which newly available damage spell gives the most
  // damage per point of each resource. These are usually different spells. The
  // two rates rank the 70 damage spells almost independently (Spearman 0.24),
  // because nuore cost grows as roughly the two-thirds power of MP, so the
  // biggest spells are dear in MP and cheap in nuore.
  //
  // Second: the game never names a tier, but its level ladder has a shape --
  // every level to 20, then even levels only to 28, then a dense band at the
  // top. That, not the damage numbers, is where the tiers are.

  const damageSpells = () => D.spells.filter((s) => s.listed && s.damage);

  /** Every level at which this class's best rate actually improves. */
  function upgrades(klass, cost) {
    const mine = [];
    for (const s of damageSpells()) {
      for (const c of s.classes) if (c.class === klass) mine.push({ level: c.level, s });
    }
    mine.sort((a, b) => a.level - b.level);
    // Only the steps: repeating an unchanged best for twenty levels is noise.
    let best = 0;
    const out = [];
    for (const { level, s } of mine) {
      const r = s.damage / s[cost];
      if (r > best) { best = r; out.push({ level, s, rate: r }); }
    }
    return out;
  }

  const TIER_BANDS = [
    { from: 1, to: 20, ladder: "every level" },
    { from: 21, to: 29, ladder: "even levels only" },
    { from: 30, to: 40, ladder: "every level again" },
  ];

  const minLevel = (s) => Math.min(...s.classes.map((c) => c.level));

  /**
   * Appends the casting curve, for one class or for all six.
   *
   * Scoped by the same chips that filter the list above it, so the tab has one
   * class control rather than two that look alike and mean different things.
   */
  function appendCurve(root, only = null) {
    const shown = only ? [only] : MAGIC_CLASSES;
    root.append(el("p", { className: "note", textContent:
      "Derived from the decoded costs, not from anything the clue book prints. "
      + "The two rates disagree: the spell that gives the most damage per MP is "
      + "rarely the one that gives the most per nuore." }));

    for (const [cost, unit] of [["mp", "MP"], ["nuore", "nuore"]]) {
      root.append(el("h4", { className: "curve-sub",
                             textContent: `Best damage per ${unit}, as you level` }));
      // The shape of each list is itself the finding, so say what it is rather
      // than leaving the reader to notice that one of them stops early.
      const last = shown
        .map((k) => upgrades(k, cost).at(-1))
        .filter(Boolean)
        .map((st) => st.level);
      const peak = Math.max(...last);
      const who = only ? `A ${titleCase(only)}` : "Every class";
      root.append(el("p", { className: "note", textContent: cost === "mp"
        ? `${who} reaches its most MP-efficient damage spell by level `
          + `${peak}, and never improves on it. Nothing learned in the next `
          + `thirty levels delivers more damage per point of MP than the `
          + `cheap spell it started with: the big spells buy reach and `
          + `volume, not efficiency.`
        : `Nuore efficiency does keep improving, all the way to level ${peak}. `
          + `This is the opposite shape to MP, and it is why the two columns `
          + `name different spells: nuore cost grows far more slowly than MP `
          + `as spells get bigger.` }));
      const grid = el("div", { className: "curve" });
      for (const klass of shown) {
        const steps = upgrades(klass, cost);
        if (!steps.length) continue;
        const col = el("div", { className: "curve-class" });
        col.append(el("h4", { textContent: titleCase(klass) }));
        for (const st of steps) {
          const row = el("div", { className: "curve-step" });
          row.append(el("span", { className: "lvl", textContent: `L${st.level}` }));
          row.append(el("span", { className: "curve-name",
                                  textContent: titleCase(st.s.name) }));
          // Two decimals here, unlike the spell cards: consecutive steps can
          // differ by hundredths, and rounding them to a tie would make an
          // upgrade look like no change at all.
          row.append(el("span", { className: "eff",
            title: `${st.s.damage} damage for ${st.s[cost]} ${unit}`,
            dataset: { rate: st.rate.toFixed(4) },
            textContent: `${st.rate.toFixed(2)}/${unit}` }));
          col.append(row);
        }
        grid.append(col);
      }
      root.append(grid);
    }

    root.append(el("h4", { className: "curve-sub", textContent: "Implicit tiers" }));
    root.append(el("p", { className: "note", textContent:
      "Damage rises smoothly with level, so the tiers are not in the numbers. "
      + "They are in the ladder: which levels carry new spells at all." }));
    const table = el("table", { className: "tiers" });
    const head = el("tr");
    for (const h of ["Levels", "Ladder", "Spells", "Damage", "Damage per MP"]) {
      head.append(el("th", { textContent: h }));
    }
    const thead = el("thead");
    thead.append(head);
    table.append(thead);
    const body = el("tbody");
    for (const band of TIER_BANDS) {
      const group = damageSpells()
        .filter((s) => minLevel(s) >= band.from && minLevel(s) <= band.to);
      if (!group.length) continue;
      const rates = group.map((s) => s.damage / s.mp);
      const dmg = group.map((s) => s.damage);
      const levels = group.map(minLevel);
      const tr = el("tr");
      for (const cell of [
        `${Math.min(...levels)}\u2013${Math.max(...levels)}`,
        band.ladder,
        String(group.length),
        `${Math.min(...dmg)}\u2013${Math.max(...dmg)}`,
        `${rate(Math.min(...rates))}\u2013${rate(Math.max(...rates))}`,
      ]) tr.append(el("td", { textContent: cell }));
      body.append(tr);
    }
    table.append(body);
    root.append(table);
    root.append(el("p", { className: "note", textContent:
      "The spread in the last column is the point: early on, picking the "
      + "efficient spell matters by a factor of seven. By the top band every "
      + "option costs about what it deals, and the choice stops mattering." }));
  }

  /* --- markdown --------------------------------------------------------- */
  //
  // Enough of the format for the guides in the repository root and no more:
  // headings, paragraphs, pipe tables, block quotes, indented code, rules and
  // both kinds of list. Nodes are built rather than assembled as HTML, so a
  // guide cannot inject markup into the panel, and the search highlighter
  // reaches the prose the same way it reaches every other tab.

  // The four inline spans, captured so that String.split keeps the delimiters.
  const INLINE = /(`[^`]+`|\*\*[^*]+\*\*|\*[^*\s][^*]*\*|\[[^\]]+\]\([^)]+\))/;

  /** A control that opens another guide, for either way of naming one. */
  function crossReference(label, open) {
    const b = el("button", { type: "button", className: "guide-link" },
                 highlight(label));
    b.onclick = open;
    return b;
  }

  function inline(text, onLink) {
    const frag = document.createDocumentFragment();
    for (const part of String(text).split(INLINE)) {
      if (!part) continue;
      if (part.length > 2 && part.startsWith("`") && part.endsWith("`")) {
        // The guides name each other as filenames rather than as links, which
        // is how they should read in a repository. Here that is a reference to
        // another document, so it opens one and is named the way the picker
        // names it: "Strategy", not "STRATEGY.md".
        const name = part.slice(1, -1);
        const hit = onLink && onLink.get(name);
        if (hit) frag.append(crossReference(hit.label, hit.open));
        else frag.append(el("code", { textContent: name }));
      } else if (part.length > 4 && part.startsWith("**") && part.endsWith("**")) {
        frag.append(el("strong", {}, highlight(part.slice(2, -2))));
      } else if (part.length > 2 && part.startsWith("*") && part.endsWith("*")) {
        frag.append(el("em", {}, highlight(part.slice(1, -1))));
      } else if (part.startsWith("[")) {
        const cut = part.indexOf("](");
        const label = part.slice(1, cut);
        const href = part.slice(cut + 2, -1);
        // A link to a sibling guide switches documents. Anything else in these
        // files points at a path in the repository, which the panel cannot
        // open, so it is shown as the path it is rather than a dead link.
        const guide = /^https?:/.test(href) ? null : href.replace(/^\.\//, "");
        const hit = guide && onLink && onLink.get(guide);
        if (hit) {
          // A link written as its own filename is named by the document; one
          // given real link text keeps the text the author chose.
          frag.append(crossReference(
            /\.md$/i.test(label) ? hit.label : label, hit.open));
        } else if (/^https?:/.test(href)) {
          frag.append(el("a", { href, target: "_blank",
                                rel: "noreferrer" }, highlight(label)));
        } else {
          frag.append(el("code", { textContent: label }));
        }
      } else {
        frag.append(highlight(part));
      }
    }
    return frag;
  }

  /** A pipe-table row split into its cells, without the outer pipes. */
  const cells = (line) =>
    line.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());

  const isRule = (line) => /^\s*(\|?\s*:?-{3,}:?\s*)+\|?\s*$/.test(line)
                           && line.includes("-");

  /**
   * Whether a line may cut a paragraph short and start a list.
   *
   * CommonMark's rule, and it exists for exactly the case that hit this file:
   * an ordered item interrupts a paragraph only when it starts at 1. Prose
   * wraps wherever it wraps, so "...42 fights per rest instead of / 10.
   * Casting Earthquake..." puts a line break in front of "10." and without
   * this the rest of the paragraph becomes a numbered list. A list that opens
   * its own block may still start at any number; only interruption is
   * restricted.
   */
  const interrupts = (line) => /^\s*[-*+]\s+\S/.test(line)
                               || /^\s*1[.)]\s+\S/.test(line);

  /**
   * Markdown to a list of blocks: `{ tag, level, text, rows, items }`.
   *
   * Kept as data rather than nodes so that the outline and the search filter
   * can both read the structure before anything is drawn.
   */
  function parseMarkdown(src) {
    const lines = String(src).replace(/\r\n?/g, "\n").split("\n");
    const blocks = [];
    let i = 0;
    while (i < lines.length) {
      const line = lines[i];
      if (!line.trim()) { i++; continue; }

      const comment = /^<!--\s*(.*?)\s*-->\s*$/.exec(line);
      if (comment) {
        blocks.push({ tag: "comment", note: comment[1] });
        i++;
        continue;
      }

      const heading = /^(#{1,6})\s+(.*)$/.exec(line);
      if (heading) {
        blocks.push({ tag: "h", level: heading[1].length, text: heading[2] });
        i++;
        continue;
      }
      if (/^\s*(---+|\*\*\*+|___+)\s*$/.test(line)) {
        blocks.push({ tag: "hr" });
        i++;
        continue;
      }
      // A table is a header row followed by a dashed rule; without the rule
      // the pipes are just punctuation.
      if (line.includes("|") && isRule(lines[i + 1] || "")) {
        const rows = [cells(line)];
        i += 2;
        while (i < lines.length && lines[i].includes("|")
               && lines[i].trim()) rows.push(cells(lines[i++]));
        blocks.push({ tag: "table", rows });
        continue;
      }
      if (line.startsWith("```")) {
        const text = [];
        i++;
        while (i < lines.length && !lines[i].startsWith("```")) text.push(lines[i++]);
        i++;
        blocks.push({ tag: "pre", text: text.join("\n") });
        continue;
      }
      if (/^ {4}\S/.test(line)) {
        const text = [];
        while (i < lines.length && (/^ {4}/.test(lines[i]) || !lines[i].trim())) {
          if (!lines[i].trim() && !/^ {4}/.test(lines[i + 1] || "")) break;
          text.push(lines[i++].slice(4));
        }
        blocks.push({ tag: "pre", text: text.join("\n") });
        continue;
      }
      if (/^>\s?/.test(line)) {
        const text = [];
        while (i < lines.length && /^>/.test(lines[i])) {
          text.push(lines[i++].replace(/^>\s?/, ""));
        }
        blocks.push({ tag: "quote", text: text.join("\n").trim() });
        continue;
      }
      const bullet = /^\s*([-*+]|\d+\.)\s+/;
      if (bullet.test(line)) {
        const ordered = /^\s*\d+\./.test(line);
        const items = [];
        while (i < lines.length && lines[i].trim()) {
          if (bullet.test(lines[i])) items.push(lines[i++].replace(bullet, ""));
          // A wrapped continuation line belongs to the item above it.
          else items[items.length - 1] += " " + lines[i++].trim();
        }
        blocks.push({ tag: "list", ordered, items });
        continue;
      }
      const text = [];
      while (i < lines.length && lines[i].trim() && !/^#{1,6}\s/.test(lines[i])
             && !/^>/.test(lines[i]) && !interrupts(lines[i])
             && !(lines[i].includes("|") && isRule(lines[i + 1] || ""))) {
        text.push(lines[i++].trim());
      }
      blocks.push({ tag: "p", text: text.join(" ") });
    }
    return blocks;
  }

  /** One block as a node. `links` maps a guide filename to a switch callback. */
  function renderBlock(b, links) {
    if (b.tag === "hr") return el("hr");
    if (b.tag === "h") {
      const n = el(`h${Math.min(b.level + 1, 6)}`, { className: "md-h" },
                   inline(b.text, links));
      n.id = slug(b.text);
      return n;
    }
    if (b.tag === "pre") return el("pre", { textContent: b.text });
    if (b.tag === "quote") return el("blockquote", {}, inline(b.text, links));
    if (b.tag === "list") {
      const list = el(b.ordered ? "ol" : "ul");
      for (const item of b.items) list.append(el("li", {}, inline(item, links)));
      return list;
    }
    if (b.tag === "table") {
      // Wrapped, because a wide table has to scroll inside its own column
      // rather than push the page sideways.
      const table = el("table", { className: "tiers md-table" });
      const [head, ...body] = b.rows;
      table.append(el("thead", {}, el("tr", {},
        head.map((c) => el("th", {}, inline(c, links))))));
      const tb = el("tbody");
      for (const row of body) {
        tb.append(el("tr", {}, row.map((c) => el("td", {}, inline(c, links)))));
      }
      table.append(tb);
      return el("div", { className: "md-table-wrap" }, table);
    }
    return el("p", {}, inline(b.text, links));
  }

  const slug = (s) => "g-" + s.toLowerCase().replace(/[^a-z0-9]+/g, "-")
                                .replace(/^-|-$/g, "");

  /* --- tabs ------------------------------------------------------------- */

  const TABS = [
    { key: "f1", label: "Maps", render: renderMaps },
    { key: "f3", label: "Spells", render: renderSpells },
    { key: "f5", label: "Items", render: renderItems },
    // Last, and only when the cabinet booted the hooked emulator for it.
    ...(TRAINER ? [{ key: "tr", label: "Trainer", render: renderTrainer }] : []),
  ];

  // Number keys select a tab, the way a browser selects one of its own.
  //
  // The clue book's F1 to F6 are not mirrored. In a browser beside a DOS
  // window those keys belong to the game, which has all of them bound, so the
  // panel could only ever see one after the user had already clicked away from
  // the game. That is the same click that would have hit the tab.
  const typing = (node) => !!node && (node.isContentEditable
    || /^(INPUT|TEXTAREA|SELECT)$/.test(node.tagName));


  // A remembered tab from an older build may name a section that no longer
  // exists, which would leave the panel with nothing shown.
  if (!TABS.some((t) => t.key === ui.active)) ui.active = DEFAULTS.active;

  function draw() {
    for (const t of TABS) {
      const btn = $(`nav button[data-key="${t.key}"]`);
      btn.setAttribute("aria-selected", String(t.key === ui.active));
      const sec = $(`section[data-key="${t.key}"]`);
      sec.hidden = t.key !== ui.active;
      if (t.key === ui.active) t.render(sec);
    }
  }

  function init() {
    const nav = $("nav");
    const main = $("main");

    // Embedded beside the game, the page's own header would be a second header
    // under the application's. Drop it and keep only the search, which moves
    // onto the tab row.
    const embedded = new URLSearchParams(location.search).has("embed");
    if (embedded) document.body.classList.add("embedded");
    TABS.forEach((t, i) => {
      const b = el("button", { type: "button", dataset: { key: t.key } });
      // The number is the accelerator, shown so that it is discoverable.
      b.append(el("span", { className: "fk", textContent: String(i + 1) }),
               document.createTextNode(t.label));
      b.onclick = () => { ui.active = t.key; draw(); };
      nav.append(b);
      main.append(el("section", { hidden: true, dataset: { key: t.key } }));
    });
    const search = $("#search");
    if (embedded) {
      nav.append(el("span", { className: "nav-spacer" }), search);
    }
    search.oninput = () => { query = search.value.trim().toLowerCase(); draw(); };

    // Nothing here fires while a field has focus, so typing a creature's name
    // into the search box never navigates. Modified keys are the browser's.
    addEventListener("keydown", (e) => {
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      const busy = typing(document.activeElement);
      if (e.key === "/" && !busy) { e.preventDefault(); search.focus(); return; }
      if (e.key === "Escape" && document.activeElement === search) {
        search.value = "";
        query = "";
        search.blur();
        draw();
        return;
      }
      if (busy) return;
      const index = Number(e.key) - 1;
      if (Number.isInteger(index) && index >= 0 && index < TABS.length) {
        e.preventDefault();
        ui.active = TABS[index].key;
        draw();
      }
    });
    draw();
  }

  document.readyState === "loading"
    ? addEventListener("DOMContentLoaded", init)
    : init();
})();
