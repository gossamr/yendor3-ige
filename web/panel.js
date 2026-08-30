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
  // Which tab, which monster, which map. The panel is rebuilt and reloaded
  // while it sits open beside the game, and losing your place on every rebuild
  // costs more than the storage does. One object behind a Proxy, so an
  // ordinary assignment anywhere in the file persists and no tab has to
  // remember to save. Storage can throw outright in a private window, so every
  // touch of it is guarded and the panel runs unchanged without it.

  const STORE = "restoration.ui";
  const DEFAULTS = {
    active: "f2", monsterPick: null, spellClass: null, curveOpen: false,
    rawPages: false, mapPick: null, legendOpen: false, itemCategory: null,
    docPick: null, plan: null, planPool: false,
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

  /* --- the monster census ---------------------------------------------- */
  //
  // `data/spawns.json` is per map, holding which monsters stand on it and how
  // many. Both directions of that are wanted. A monster's card asks where it
  // is and a map asks what is on it, so the inverse is built once here rather
  // than shipped twice. See docs/encounters.md.

  const SPAWNS = D.spawns || {};
  const BY_NAME = new Map(D.enemies.map((m) => [m.name, m]));

  /** Monster name -> [{ map, count }], commonest first. */
  const WHERE = (() => {
    const out = {};
    for (const [map, page] of Object.entries(SPAWNS)) {
      for (const [name, count] of Object.entries(page.monsters)) {
        (out[name] = out[name] || []).push({ map, count });
      }
    }
    for (const list of Object.values(out)) {
      list.sort((a, b) => b.count - a.count || (a.map < b.map ? -1 : 1));
    }
    return out;
  })();

  /**
   * Move to another tab and land on a named thing.
   *
   * The search box filters every tab, so a query that hides the target would
   * send the jump somewhere else. The maps tab falls back to the first page
   * that still matches. Following a link is a request for one particular
   * thing, so the filter is cleared out of its way.
   */
  function goTo(tab, apply) {
    const search = $("#search");
    if (search) search.value = "";
    query = "";
    apply();
    ui.active = tab;
    draw();
  }

  /** A chip that carries you to a map or a monster, with how many there are. */
  function censusChip(label, count, onGo, hint) {
    const b = el("button", { type: "button", className: "chip census",
                             title: hint });
    b.append(highlight(titleCase(label)),
             el("span", { className: "census-n",
                          textContent: `×${count}` }));
    b.onclick = onGo;
    return b;
  }

  /* --- F2 monsters ------------------------------------------------------ */

  // The five the game's own Combat block prints. The two ranged rows it prints
  // beneath them go with the rest of the ranged attack instead, where the
  // reader can see what the monster actually throws.
  const STATS = ["health", "accuracy", "dexterity", "absorption", "damage"];

  // Monsters with the same code at offset 28 share a kind. The field takes
  // eleven values across the monsters the game lists, and the game names two
  // of them itself: INSECT and UNDEAD, from the enumeration its spells target.
  // What the other nine group by is not decoded, and a bare number is not
  // something a reader can do anything with, so those monsters say nothing
  // here. Any one of the nine goes in this slot the day it is named.
  const FAMILIES = { 9: "insect", 13: "undead" };

  const REWARDS = ["experience", "gold", "food", "nuore"];

  function statList(m, fields) {
    const dl = el("dl", { className: "stats" });
    for (const f of fields) {
      const v = m[f];
      // Ranged rows are blank on the game's own screen for melee monsters.
      if (v === null || v === undefined) continue;
      dl.append(el("dt", { textContent: titleCase(f.replace(/_/g, " ")) }),
                el("dd", { className: "num", textContent: (v || 0).toLocaleString() }));
    }
    return dl;
  }

  /**
   * The twelve effects, laid out the way the game lays them out: every effect
   * on its own row whether or not the monster has it, so the shape of a
   * monster's defenses reads at a glance and rows line up between monsters.
   */
  function effectTable(m) {
    const immune = new Set(m.immune);
    const table = el("table", { className: "effects" });
    const body = el("tbody");
    for (const effect of D.labels.effects) {
      let value = "", cls = "none";
      if (immune.has(effect)) { value = "Immune"; cls = "immune"; }
      else if (effect === "MAGIC DAMAGE" && m.resist_magic) { value = "Resistant"; cls = "resist"; }
      else if (effect === "PHYSICAL DAMAGE" && m.resist_physical) {
        value = "Resistant"; cls = "resist";
      }
      body.append(el("tr", { className: cls }, [
        el("th", { scope: "row", textContent: titleCase(effect) }),
        el("td", { textContent: value || "—" }),
      ]));
    }
    table.append(body);
    return table;
  }

  function monsterDetail(m) {
    const card = el("div", { className: "card" });

    // The monster's own picture, at the size the game stores it, beside its
    // name. It is the first thing that says which monster this is, so it goes
    // above everything the monster does.
    const title = el("div", {}, [
      el("h3", { textContent: titleCase(m.name) }),
      el("p", { className: "note",
                textContent: [`Level ${m.level}`, FAMILIES[m.family]]
                  .filter(Boolean).join(" \u00b7 ") }),
    ]);
    const art = (D.monster_art || {})[m.name];
    card.append(el("div", { className: "monster-head" }, art ? [
      el("img", {
        className: "monster-art", src: art.src, alt: "",
        width: art.width, height: art.height, loading: "lazy",
      }), title,
    ] : [title]));

    // Combat and rewards pair up across the top whenever there is room for two
    // columns, with the twelve effect rows below them at full width, since they are
    // the tallest block, so putting them beside a short list wastes the space.
    const top = el("div", { className: "detail-top" });
    top.append(el("div", {}, [el("h5", { textContent: "Combat" }), statList(m, STATS)]));
    top.append(el("div", {}, [el("h5", { textContent: "Rewards" }), statList(m, REWARDS)]));
    card.append(top);
    card.append(el("h5", { textContent: "Immunities and resistances",
                           style: "margin-top:1.1rem" }));
    card.append(effectTable(m));
    // What a resistance is worth, which the game's own page does not say. Each
    // one answers a damage type and halves damage of that type; a melee swing
    // carries no type and is never halved. Two types share the physical row,
    // and one of them is carried by nothing in the game.
    const worth = [];
    if (m.resist_shot) worth.push("Halves a shot.");
    if (m.resist_magic) worth.push("Halves a damage spell.");
    if (worth.length) worth.push("A melee swing is unaffected.");
    if (m.resist_unmatched) {
      worth.push("The physical row also stands for a damage type nothing in "
        + "the game carries, so that part of it never applies.");
    }
    if (worth.length) {
      card.append(el("p", { className: "note", style: "margin:.5rem 0 0",
                            textContent: worth.join(" ") }));
    }

    if (m.ranged) {
      card.append(el("h5", { textContent: "Ranged attack", style: "margin-top:1.1rem" }));
      const shot = el("div", { className: "ranged" });
      const art = (D.projectile_art || {})[m.ranged.picture];
      if (art) {
        shot.append(el("img", {
          className: "shot-art", src: art.src, alt: "",
          width: art.width, height: art.height, loading: "lazy",
        }));
      }
      // The chance is how often the monster shoots rather than closing to
      // melee, so it belongs beside the two numbers that say what the shot
      // does when it lands.
      const rows = [["Fires on", `${m.ranged.chance}% of turns`],
                    ["Accuracy", m.ranged_accuracy],
                    ["Damage", m.ranged_damage]];
      const dl = el("dl", { className: "stats" });
      for (const [label, value] of rows) {
        if (value === null || value === undefined) continue;
        dl.append(el("dt", { textContent: label }),
                  el("dd", { className: "num", textContent: String(value) }));
      }
      shot.append(dl);
      card.append(shot);
    }

    if (m.attacks && m.attacks.length) {
      card.append(el("h5", { textContent: "Special attacks", style: "margin-top:1.1rem" }));
      const chips = el("div", { className: "chips" });
      for (const atk of m.attacks) {
        chips.append(el("span", {
          className: "chip attack",
          title: "Decoded from the record",
          textContent: titleCase(atk),
        }));
      }
      card.append(chips);
      // What the steal takes is in the record, not on the game's own screen.
      if (m.steal) {
        card.append(el("p", { className: "note", style: "margin:.5rem 0 0",
          textContent: `Steals ${m.steal.toLocaleString()} gold.` }));
      }
    }

    // Where the monster stands. Each one is placed on a cell of the world
    // grid and killed once, so this is the whole of what the game holds: the
    // maps, the count on each, and the experience all of them together pay.
    const where = WHERE[m.name] || [];
    if (where.length) {
      const total = where.reduce((n, w) => n + w.count, 0);
      card.append(el("h5", { textContent: "Locations",
                             style: "margin-top:1.1rem" }));
      const chips = el("div", { className: "chips" });
      for (const w of where) {
        chips.append(censusChip(w.map, w.count,
          () => goTo("f1", () => { ui.mapPick = w.map; }),
          `${w.count} on ${titleCase(w.map)}. Open the map.`));
      }
      card.append(chips);
      // A monster placed once needs no line. The chip above already names its
      // one map, and multiplying its experience by one only repeats the
      // Rewards block. That a kill is permanent holds for every monster, so it
      // is said once, in the manual's own section on earning experience,
      // rather than on all 71 cards.
      if (total > 1) {
        const worth = total * (m.experience || 0);
        card.append(el("p", { className: "note", style: "margin:.5rem 0 0",
          textContent: `${total} in the game, on ${where.length} `
            + `${where.length === 1 ? "map" : "maps"}, worth `
            + `${worth.toLocaleString()} experience in all.` }));
      }
    }

    // The rest of the record (the flag words, the attack ids, the sound
    // numbers, where a hit graphic lands) is in data/enemies.json and
    // docs/combat.md. Everything a monster does with it is already on this
    // card, and the numbers themselves are not something a player can act on.
    return card;
  }

  // The 72nd record is the game's own placeholder, named NOT USED: every field
  // zero, no screen of its own to check against, and a sprite field of 0 that
  // points at the tree the monster artwork happens to start after. The decode
  // keeps it, because it is what the record says; the clue book does not list
  // it and neither does this.
  const MONSTERS = D.enemies.filter((m) => m.listed);

  // Level first, because that is the order the table itself is built in: every
  // other statistic is grown from it, so walking the list by level walks it
  // from the wasp outside the first town to the thing at the end of the game.
  const byLevel = (a, b) => a.level - b.level || (a.name < b.name ? -1 : 1);

  function renderMonsters(root) {
    root.textContent = "";
    const hits = MONSTERS.filter((m) => matches(m.name)).sort(byLevel);
    if (!hits.length) return root.append(el("p", { className: "empty", textContent: "No monster matches." }));
    if (!hits.some((m) => m.name === ui.monsterPick)) ui.monsterPick = hits[0].name;

    const pick = el("select", { className: "picker" });
    pick.setAttribute("aria-label", "Monster");
    for (const m of hits) {
      pick.append(el("option", {
        value: m.name, selected: m.name === ui.monsterPick,
        textContent: titleCase(m.name),
      }));
    }

    // Choosing redraws the card and nothing else, so the select keeps focus
    // and the arrow keys walk the list without the page moving underneath.
    const detail = el("div");
    const show = () => {
      detail.textContent = "";
      detail.append(monsterDetail(hits.find((m) => m.name === ui.monsterPick)));
    };
    pick.onchange = () => { ui.monsterPick = pick.value; show(); };
    show();

    root.append(el("div", { className: "picker-row" }, [
      pick,
      el("span", { className: "note",
                   textContent: `${hits.length} monster${hits.length === 1 ? "" : "s"}` }),
    ]));
    root.append(detail);
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
    // The fight. One word names whichever engaged monster is selected and the
    // three buffers follow it; the eighty spawn slots hold every monster out
    // on the map. Both are the 156-byte monster struct.
    selected: 0x54B6,
    engaged: 0x54B8,
    engagedSlots: 3,
    spawn: 0x122C,
    spawnSlots: 80,
    monster: 0x9C,
  };

  // The monster struct: a 50-byte header holding what the monster is doing
  // now, then the 106-byte record copied out of WORLD.DAT, so a record offset
  // is read at +0x32. Health now is the header's own word: the record's is
  // what the monster started with, and never moves. See docs/combat.md.
  const MOB = {
    id: 0,               // the object's number; zero means the slot is free
    impaired: 0x0C,      // & 0x3010 keeps it out of the turn list (image 0x115b)
    health: 0x10,        // at or below zero is dead (image 0x1298)
    record: 0x32,        // where the monster's own 106 bytes begin
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
  // The nine conditions a monster can inflict, plus the bit set when health
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
    name: 0, nameLen: 14, classCode: 0x0E, level: 0x16, experience: 0x18,
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
  // same packing the monster rewards use.
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
        classCode: u16(rec, CHAR.classCode),
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
                           textContent: " Monsters out on the map as well" })]));
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
        updateMonsters(await readMonsters(base, trainerMobs.onMap.checked));
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
                             textContent: titleCase(className(person.classCode)) }),
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
  async function readMonsters(base, includeMap) {
    // The selected-monster pointer and the three buffers behind it are
    // contiguous, so they are one read.
    const buf = await emulator.peek(base + DS.selected,
                                    2 + DS.engagedSlots * DS.monster);
    const selected = u16(buf, 0);
    const out = [];
    for (let i = 0; i < DS.engagedSlots; i += 1) {
      const off = 2 + i * DS.monster;
      if (!u16(buf, off + MOB.id)) continue;
      const where = DS.engaged + i * DS.monster;
      out.push(monster(buf, off, base + where, `Engaged ${i + 1}`, where === selected));
    }
    if (includeMap) {
      const slots = await emulator.peek(base + DS.spawn, DS.spawnSlots * DS.monster);
      for (let i = 0; i < DS.spawnSlots; i += 1) {
        const off = i * DS.monster;
        if (!u16(slots, off + MOB.id)) continue;
        out.push(monster(slots, off, base + DS.spawn + off, `Slot ${i}`, false));
      }
    }
    return out;
  }

  function monster(b, off, at, where, selected) {
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

  function updateMonsters(mobs) {
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

  // The monster record's combat fields, as record offsets; `docs/monsters.md`
  // has the rest. Split because the four flag words are read and written in
  // hex and the rest in decimal.
  const MOB_FIELDS = [
    [30, "Health full"], [32, "Level"], [34, "Accuracy"], [36, "Dexterity"],
    [38, "Absorption"], [40, "Damage"], [50, "Shot accuracy"], [52, "Shot damage"],
  ];
  const MOB_FLAGS = [
    [96, "Word 96"], [98, "Word 98"], [100, "Immunity"], [102, "Resistance"],
  ];
  // The turn-list builder leaves out a monster with any of these; setting them
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

  /* Monsters: the record itself, live. `tools/fight_probe.js` does the same
     thing by patching WORLD.DAT before boot and paying for a boot per reading;
     this changes a monster that is already standing there. A shot resolves
     against the map slot and a swing against the engaged buffer, so an
     experiment on a volley edits the slot; tick the map box above to reach
     one. */
  function renderMobEdit(root) {
    root.append(el("h4", { className: "curve-sub", textContent: "Monsters" }));
    const row = el("div", { className: "picker-row" });
    mobPick = el("select", { className: "picker debug-mob" });
    mobPick.setAttribute("aria-label", "Which monster");
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
      await write(dsBase + DS.spawn + i * DS.monster + MOB.id, bytes16(0));
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
    ["Engaged 1", DS.engaged, DS.monster],
    ["Spawn slot 0", DS.spawn, DS.monster],
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
    // A spell restricted to one kind of monster is named by that kind: the
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

  /* --- F6 walkthrough --------------------------------------------------- */


  const PAGE_FOOTER = /^\s*\d+ OF \d+\s*$/;

  /**
   * The walkthrough as sections, not pages.
   *
   * The 33 pages are how the text was *stored* (25 rows of 51 columns, with
   * a "n OF 33" footer on each) not how it reads. Its own structure is the
   * numbered locations, and those run across page breaks: section 3 begins on
   * page 1 and finishes on page 2. Reading it a page at a time therefore cuts
   * sections in half for no reason, so the reflowed view walks every row of
   * every page as one stream and groups it by heading instead.
   *
   * No paragraph is ever split by a page break, since every page ends with a
   * blank row before its footer, so joining the pages needs no repair, only the
   * footers dropped.
   */
  function walkthroughSections() {
    const sections = [];
    let cur = { n: null, title: null, paras: [] };
    let buf = [];
    const flush = () => {
      if (!buf.length) return;
      const text = buf.join(" ");
      buf = [];
      const head = text.match(/^(\d+)\.\s+(.*)$/);
      if (!head) { cur.paras.push(text); return; }
      if (cur.title || cur.paras.length) sections.push(cur);
      cur = { n: Number(head[1]), title: titleCase(head[2]), paras: [] };
    };
    for (const pg of D.walkthrough) {
      for (const row of pg.rows) {
        if (PAGE_FOOTER.test(row)) continue;
        if (row.trim()) buf.push(row.trim());
        else flush();
      }
    }
    flush();
    if (cur.title || cur.paras.length) sections.push(cur);
    return sections;
  }

  function renderWalkthrough(root) {
    root.textContent = "";
    // No heading: the tab strip above already says which section this is.
    const head = el("div", { style: "display:flex;align-items:baseline;gap:1rem;flex-wrap:wrap" });
    const toggle = el("button", {
      className: "toggle", type: "button",
      textContent: ui.rawPages ? "Original 51-column layout" : "Reflowed for reading",
    });
    toggle.setAttribute("aria-pressed", String(ui.rawPages));
    toggle.onclick = () => { ui.rawPages = !ui.rawPages; renderWalkthrough(root); };
    head.append(toggle);
    root.append(head);

    const sections = ui.rawPages ? null : walkthroughSections();
    root.append(el("p", {
      className: "note",
      // Pages are a fact about the original layout, so they are only worth
      // counting in the view that shows them.
      textContent: ui.rawPages
        ? `${D.walkthrough.length} pages, ${D.walkthrough_index.length} locations.`
        : `${sections.filter((s) => s.title).length} locations, start to finish.`,
    }));

    if (ui.rawPages) {
      for (const pg of D.walkthrough) {
        const body = pg.rows.join("\n");
        if (query && !matches(body)) continue;
        const page = el("div", { className: "page" }, [
          el("span", { className: "pageno", textContent: `${pg.page} / ${D.walkthrough.length}` }),
        ]);
        const pre = el("pre", { className: "raw" });
        pre.append(highlight(body));
        page.append(pre);
        root.append(page);
      }
    } else {
      // Searching filters by location rather than by page: a location is the
      // unit the reader is looking for, and it is what the headings promise.
      const prose = el("div", { className: "prose walkthrough" });
      for (const sec of sections) {
        const body = [sec.title, ...sec.paras].join(" ");
        if (query && !matches(body)) continue;
        const box = el("section", { className: "wt-section" });
        if (sec.title) box.append(el("h4", { textContent: `${sec.n}. ${sec.title}` }));
        for (const para of sec.paras) {
          const p = el("p");
          p.append(highlight(sentenceCase(para)));
          box.append(p);
        }
        prose.append(box);
      }
      if (prose.children.length) root.append(prose);
    }
    if (!root.querySelector(".page, .wt-section")) {
      root.append(el("p", {
        className: "empty",
        textContent: ui.rawPages ? "No page matches." : "No location matches.",
      }));
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

    // What stands on this map, before the legend, because a player reaching
    // for a map wants to know what is on it first. Seven of the 54 slots hold
    // nothing: the Athaneum, the two orders, Elfin City, Delia's Island, the
    // Gold Mine and the first level of Vishan's Stronghold.
    const here = SPAWNS[shown.title];
    if (here) {
      root.append(el("h3", { className: "curve-head",
        textContent: `Monsters (${here.total})` }));
      const mobs = el("div", { className: "chips" });
      for (const [name, count] of Object.entries(here.monsters)) {
        const m = BY_NAME.get(name);
        mobs.append(censusChip(name, count,
          () => goTo("f2", () => { ui.monsterPick = name; }),
          m ? `Level ${m.level}, ${m.experience.toLocaleString()} experience `
              + `each. Open its page.`
            : "Open its page."));
      }
      root.append(mobs);
      root.append(el("p", { className: "note", style: "margin:.5rem 0 0",
        textContent: `${here.experience.toLocaleString()} experience and `
          + `${here.gold.toLocaleString()} gold.` }));
    }

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
  function upgrades(name, cost) {
    const mine = [];
    for (const s of damageSpells()) {
      for (const c of s.classes) if (c.class === name) mine.push({ level: c.level, s });
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
      for (const name of shown) {
        const steps = upgrades(name, cost);
        if (!steps.length) continue;
        const col = el("div", { className: "curve-class" });
        col.append(el("h4", { textContent: titleCase(name) }));
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

  /* --- leveling --------------------------------------------------------- */
  //
  // The clue book has no page for any of this. The game shows you one rung at
  // a time on the character screen and one price at a time at a trainer, so the
  // ladder as a whole is the panel's own addition.

  function renderLeveling(root) {
    root.textContent = "";
    const lv = D.leveling;
    if (!lv) return;

    const trainers = lv.trainers || [];
    // The cheapest trainer who will still take you. The factor-5 trainers all
    // stop at 25, so the same level-up doubles in price the moment they do.
    const factorAt = (level) => {
      const able = trainers.filter((t) => t.through >= level + 1
                                      && (t.from || 1) <= level);
      return able.length ? Math.min(...able.map((t) => t.factor)) : null;
    };

    root.append(el("p", { className: "note", textContent:
      `Experience is a running total, so the ladder below is what you need in `
      + `hand, not what the level costs. A trainer sells one level a visit, `
      + `and level ${lv.cap} is the last one the ladder fills in.` }));

    const table = el("table", { className: "tiers" });
    const head = el("tr");
    for (const h of ["Level", "Experience", "Step up", "Cheapest training"]) {
      head.append(el("th", { textContent: h }));
    }
    table.append(el("thead", {}, head));
    const body = el("tbody");
    for (const row of lv.experience) {
      const tr = el("tr");
      const from = row.level - 1;
      const factor = factorAt(from);
      for (const cell of [
        String(row.level),
        row.total.toLocaleString(),
        row.step.toLocaleString(),
        factor === null ? "\u2014"
          : (lv.train_base * factor * from).toLocaleString(),
      ]) tr.append(el("td", { textContent: cell }));
      body.append(tr);
    }
    table.append(body);
    root.append(table);

    root.append(el("h4", { className: "curve-sub", textContent: "Trainers" }));
    root.append(el("p", { className: "note", textContent:
      `One training costs ${lv.train_base} gold, times the price factor below, `
      + `times the level you are training away from. A factor of 5 is therefore `
      + `${lv.train_base * 5} gold a level and a factor of 10 is `
      + `${(lv.train_base * 10).toLocaleString()}. The ladder above is priced at `
      + `the cheapest factor available to you at each level.` }));

    const caps = el("table", { className: "tiers" });
    const ch = el("tr");
    for (const h of ["Covers levels", "Price factor"]) {
      ch.append(el("th", { textContent: h }));
    }
    caps.append(el("thead", {}, ch));
    const cbody = el("tbody");
    trainers.forEach((t) => {
      const tr = el("tr");
      for (const cell of [
        `${t.from || 1} to ${t.through}`,
        String(t.factor),
      ]) tr.append(el("td", { textContent: cell }));
      cbody.append(tr);
    });
    caps.append(cbody);
    root.append(caps);

    root.append(el("p", { className: "note", textContent:
      "The last trainer refuses anyone under level 30, and the one below it "
      + "stops at exactly 30, so the two hand over with no overlap. From "
      + "level 25 up, one trainer at a time is the most that will take you." }));

    root.append(el("h4", { className: "curve-sub", textContent: "Bonus points" }));
    root.append(el("p", { className: "note", textContent:
      `Each training hands you 13% of your base charisma, rounded, up to `
      + `${lv.bonus_cap}. Charisma rises 2 a level on its own, so the payout `
      + `climbs with you and stops climbing here.` }));

    // The payout is a staircase, and only the steps are worth showing.
    const steps = lv.bonus_points.filter(
      (r, i, a) => i === 0 || r.points !== a[i - 1].points);
    const stair = el("table", { className: "tiers" });
    const sh = el("tr");
    for (const h of ["Charisma", "Points a training"]) {
      sh.append(el("th", { textContent: h }));
    }
    stair.append(el("thead", {}, sh));
    const sbody = el("tbody");
    for (const r of steps) {
      const tr = el("tr");
      tr.append(el("td", { textContent: `${r.charisma}+` }));
      tr.append(el("td", { textContent: String(r.points) }));
      sbody.append(tr);
    }
    stair.append(sbody);
    root.append(stair);

    root.append(el("p", { className: "note", textContent:
      `Promotions land at level ${lv.promotions.second} and level `
      + `${lv.promotions.third}, and change your title only. Spells arrive on `
      + `even levels, at most two at a time.` }));
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

  /* --- guides ----------------------------------------------------------- */

  // Everything that reads as a document rather than a table to look something
  // up in: the two written guides, the game's own walkthrough, and the leveling
  // ladder. Four selectors inside one tab instead of four tabs.
  const DOCS = (window.GUIDES || []).concat([
    { key: "walkthrough", label: "Walkthrough", render: renderWalkthrough },
    { key: "leveling", label: "Leveling", render: renderLeveling },
  ]);
  const FILES = new Map(DOCS.map((d) => [d.key, d]));
  if (!FILES.has(ui.docPick)) ui.docPick = DOCS.length ? DOCS[0].key : null;

  // The guides are written for two readers. Someone working on the project
  // wants to know which script produced a table and where the addresses are
  // written down; someone playing the game does not, and a path into a source
  // tree is noise on the page. `<!-- panel:skip -->` in the markdown drops the
  // block after it from the panel, and nothing else. The provenance stays in
  // the file, where it is read, and stays out of the rendering, where it is
  // not: an HTML comment is invisible wherever markdown is rendered anyway, so
  // the marker itself never shows up either.
  const SKIP = "panel:skip";

  function forReader(blocks) {
    const out = [];
    for (let i = 0; i < blocks.length; i++) {
      if (blocks[i].tag !== "comment") { out.push(blocks[i]); continue; }
      if (blocks[i].note === SKIP) i++;      // and the block it marks
    }
    return out;
  }

  const parsed = new Map();
  const blocksFor = (doc) => {
    if (!parsed.has(doc.key)) {
      parsed.set(doc.key, forReader(parseMarkdown(doc.text)));
    }
    return parsed.get(doc.key);
  };

  /**
   * Search inside a guide keeps whole sections rather than loose lines: a
   * table row on its own says nothing without the heading it sits under.
   */
  function sections(blocks) {
    const out = [];
    for (const b of blocks) {
      if (b.tag === "h" && b.level <= 3) out.push({ heading: b, blocks: [] });
      if (!out.length) out.push({ heading: null, blocks: [] });
      out[out.length - 1].blocks.push(b);
    }
    return out;
  }

  const blockText = (b) => b.text || (b.items || []).join(" ")
                           || (b.rows || []).flat().join(" ") || "";

  function renderGuides(root) {
    root.textContent = "";
    if (!DOCS.length) {
      root.append(el("p", { className: "empty",
                            textContent: "No guides were built into this panel." }));
      return;
    }

    // Which document is above the layout rather than inside it: at the width
    // the panel is docked beside the game there is one column, and anything in
    // the sidebar falls below the document it is meant to navigate.
    const picker = el("div", { className: "guide-picker" });
    for (const d of DOCS) {
      const b = el("button", { type: "button", textContent: d.label,
                               dataset: { doc: d.key } });
      b.setAttribute("aria-current", String(d.key === ui.docPick));
      b.onclick = () => { ui.docPick = d.key; renderGuides(root); };
      picker.append(b);
    }
    root.append(picker);

    const layout = el("div", { className: "guide-layout" });
    const article = el("article", { className: "guide-doc" });
    const side = el("nav", { className: "guide-side" });
    layout.append(article, side);
    root.append(layout);

    const doc = FILES.get(ui.docPick) || DOCS[0];
    if (doc.render) {                       // the leveling tables
      doc.render(article);
      return;
    }

    // The guides cross-reference each other by filename; make those switch
    // documents instead of pointing at a file the panel cannot open.
    const links = new Map();
    for (const g of window.GUIDES || []) {
      links.set(`${g.label.toUpperCase()}.md`, {
        label: g.label,
        open: () => { ui.docPick = g.key; renderGuides(root); },
      });
    }

    const all = sections(blocksFor(doc));
    const shown = all.filter((s) => !query
      || s.blocks.some((b) => matches(blockText(b))));

    if (!shown.length) {
      article.append(el("p", { className: "empty",
                               textContent: "Nothing in this guide matches." }));
    }
    const outline = el("div", { className: "guide-toc" });
    for (const s of shown) {
      for (const b of s.blocks) article.append(renderBlock(b, links));
      // The document's own title is not an outline entry; it is the thing the
      // outline is of.
      const h = s.heading;
      if (!h || h.level < 2 || h.level > 3) continue;
      const link = el("button", { type: "button",
                                  className: `toc-${h.level}` },
                      document.createTextNode(h.text.replace(/[*`]/g, "")));
      link.onclick = () => {
        const target = article.querySelector(`#${CSS.escape(slug(h.text))}`);
        if (target) target.scrollIntoView({ block: "start", behavior: "smooth" });
      };
      outline.append(link);
    }
    side.append(outline);
  }

  /* --- the planner ------------------------------------------------------ */
  //
  // What the goals in STRATEGY.md look like against one character. A goal is a
  // number a character has to hold from some level on -- land every swing, be
  // hit less than a quarter of the time, act before what it is fighting -- and
  // the planner walks every level from where the character stands to the cap
  // saying where each goal holds, where it breaks, what it costs to hold, and
  // which monster set the bar.
  //
  // What it measures against is the worst the level can put in front of you:
  // per stat, the highest value among every monster met by that level. That
  // is deliberately not one monster. A character that lands every swing on
  // the level's hardest monster and misses the one wearing the most armor has
  // not met the goal, so each stat comes from whichever monster carries the
  // most of it and the evidence rows name them. Bosses are left out until
  // asked for; a monster above the cap is one a character at the cap meets,
  // which is how Paltivar enters a level-40 plan.
  //
  // The trainer is not needed. With it on, the character is read out of the
  // running game rather than typed, which is the difference between planning a
  // character and planning yours.
  //
  // The model is the game's arithmetic and `tools/combat_model.py` is the same
  // model offline, where the tables in the guides are computed. It runs here
  // rather than being precomputed because the answer depends on the character
  // in front of it; what does not depend on the character -- the class table,
  // the armor prices, the shop's weapons -- is decoded into `planner` by
  // tools/planner.py and read from there.

  const PLAN = D.planner || null;
  const K = PLAN && PLAN.constants;

  const pctOf = (value, percent) => Math.floor((value * percent + 50) / 100);

  /** P(an attack lands) at this margin. rand(55) is a d64 folded over, so
   *  margins 1 to 8 come up twice as often as anything above them. */
  function rollOdds(margin) {
    if (margin < 0) return 0;
    let raw = 1;
    while (raw <= K.attack_roll) raw *= 2;
    const twice = raw - 1 - K.attack_roll;
    const t = Math.min(margin, K.attack_roll);
    return (t + 1 + Math.min(twice, t)) / raw;
  }

  // A landed hit delivers the margin as a percentage of the damage stat, and
  // always at least 1.
  const perHit = (damage, margin) =>
    (margin < 0 ? 0 : Math.max(1, pctOf(damage, margin)));
  const attributeBonus = (value) => (value > K.bonus_threshold
    ? pctOf(value - K.bonus_threshold, K.bonus_pct) : 0);
  const swing = (damage, accuracy, absorption) =>
    rollOdds(accuracy - absorption) * perHit(damage, accuracy - absorption);

  // A landed hit delivers the margin as a percentage of the damage stat, so
  // this is the margin at which it delivers the whole of it. Nothing caps it:
  // past here a hit is worth more than the stat.
  const FULL_DAMAGE = 100;

  /* Section 7 of the strategy guide counts dead levels from here. */
  const DEAD_FROM = 12;

  /** The smallest margin that lands at least this often. */
  function marginFor(odds) {
    for (let m = 0; m <= K.attack_roll; m += 1) if (rollOdds(m) >= odds) return m;
    return K.attack_roll;
  }

  /* --- what you are up against ------------------------------------------ */

  const CAP = PLAN ? K.level_cap : 40;
  const GROUP_BITS = 0xe000;
  const groupSize = (e) => {
    const bits = (e.masks || {}).w96 & GROUP_BITS;
    return !bits ? 1 : (bits === 0xa000 ? 3 : 2);
  };

  // A boss carries food -- the ten named individuals -- or stands above the
  // cap, which is Paltivar. Neither is what a character meets on an ordinary
  // floor of a dungeon: they are the fights a party plans for rather than the
  // ones it budgets a career around.
  /* Attacks one of these lands on one character in a round. An ordinary
     monster draws its target from the four party slots, so it averages a
     quarter; one carrying PARTY ATTACK swings at every character, so it lands
     a whole one on each. */
  const PARTY_ATTACK_BIT = 0x1000;
  const attacksEach = (e) =>
    (((e.masks || {}).w96 & PARTY_ATTACK_BIT) ? 1 : 0.25);

  const isBoss = (e) => !!e.food || e.level > CAP;
  // The ladder stops at the cap, so anything above it is what a character at
  // the cap fights.
  const facedAt = (e) => Math.min(e.level, CAP);

  const ADVERSARY = ["absorption", "accuracy", "dexterity", "damage", "health"];
  // Absorption, dexterity and health are the monster's. Accuracy and damage
  // are an attack's, and a shooter has two attacks.
  const OF_ATTACK = new Set(["accuracy", "damage"]);

  /**
   * A monster's attacks, each kept whole.
   *
   * Accuracy and damage come twice in the record: 34 and 40 for the blow, 50
   * and 52 for the shot. Which one a monster uses is settled by distance
   * rather than chosen: it shoots only while it has not closed, in a phase of
   * its own that walks the spawn slots, and once it is engaged it swings. The
   * two never land in the same round. So the pairs come back whole -- melee
   * damage behind ranged accuracy is a blow the game cannot throw.
   *
   * The two pairs are close on eleven of the thirteen shooters, at most five
   * points of accuracy and twenty-five of damage apart.
   * The exceptions are the dwarf towers, which cannot close: the Fire Dwarf
   * Tower shoots at 160 for 115 and carries 10 and 10 in the melee rows it
   * never reaches.
   */
  function attacksOf(e) {
    const blow = { accuracy: e.accuracy, damage: e.damage, shot: false };
    return e.ranged
      ? [blow, { accuracy: e.ranged_accuracy, damage: e.ranged_damage,
                 shot: true }]
      : [blow];
  }

  const worstCache = new Map();

  /** Per stat, the most of it anything met by this level carries. */
  function worstAt(level, bosses) {
    const key = `${level}:${bosses}`;
    if (worstCache.has(key)) return worstCache.get(key);
    const counted = D.enemies.filter((e) => e.listed && (bosses || !isBoss(e)));
    // Below the first monster in the game there is nothing to measure
    // against, so the lowest level that has one stands in for it.
    const met = counted.filter((e) => facedAt(e) <= level);
    const rows = met.length ? met
      : counted.filter((e) => facedAt(e) === Math.min(...counted.map(facedAt)));
    const out = { group: { value: 1, monster: null },
                  attacks: { value: 0.25, monster: null } };
    for (const e of rows) {
      for (const f of ADVERSARY) {
        /* A threshold is priced against one stat at a time, so each attack's
           own figure counts: the tower's 160 is an accuracy a character of 16
           meets, whatever the tower swings for. */
        for (const a of (OF_ATTACK.has(f) ? attacksOf(e) : [e])) {
          if (!out[f] || a[f] > out[f].value) {
            out[f] = { value: a[f], monster: e, shot: !!a.shot };
          }
        }
      }
      const size = groupSize(e);
      if (size > out.group.value) out.group = { value: size, monster: e };
      const rate = attacksEach(e);
      if (!out.attacks || rate > out.attacks.value) {
        out.attacks = { value: rate, monster: e };
      }
    }
    worstCache.set(key, out);
    return out;
  }

  /* --- the character ----------------------------------------------------- */

  // Where each number sits in the sheet the game prints, which is the order
  // the record holds them in.
  const SHEET_AT = {};
  SHEET.forEach((label, i) => { SHEET_AT[label.toLowerCase()] = i; });
  const WEAPON_SKILLS = ["slashing", "bashing", "polearm", "projectile"];

  const classAt = (code) => PLAN.classes.find((c) => c.code === code)
    || PLAN.classes[0];
  /** The attribute a class's pool is built out of. */
  const poolAttribute = (cls) => (cls.magic_blend.length
    ? cls.magic_blend[0][0] : null);

  /**
   * What a character attacks with.
   *
   * One resolver settles every attack in the game -- melee, missile, spell and
   * monster alike -- so a spell rolls against absorption exactly as a swing
   * does, reading CASTING where the swing reads the weapon skill. A goal about
   * landing an attack is therefore about whichever of the two the character
   * actually uses, and for a mage that is never the weapon.
   */
  const attacksWithCasting = (casting, weapon) => casting > weapon;

  /**
   * Whether this class has a route to choose.
   *
   * A blend that sums to a hundred is a caster that happens to carry a weapon;
   * one that sums to half bought that weapon skill with half its pool, and is
   * the class STRATEGY.md prices both ends of without picking. Paladin and
   * marksman are the two, and the blend is what says so rather than a list.
   */
  const canDoEither = (cls) =>
    cls.magic_blend.reduce((n, [, weight]) => n + weight, 0) < 100
    && !!cls.magic_blend.length;

  /** The weapon skill a class is least penalized in. */
  function bestSkill(cls) {
    let best = WEAPON_SKILLS[0];
    for (const s of WEAPON_SKILLS) if (cls.modifier[s] > cls.modifier[best]) best = s;
    return best;
  }

  /** Health at a level: a quarter of the stamina roll at creation, then 30% of
   *  the stamina as it stood at each training. Not retroactive, which is why
   *  it is walked rather than multiplied. */
  function healthAt(staminaRoll, level) {
    let total = pctOf(staminaRoll, K.health_at_creation);
    for (let l = 1; l < level; l += 1) {
      total += pctOf(staminaRoll + K.per_level * (l - 1), K.pct_health_from_stamina);
    }
    return total;
  }

  /** The magic pool, accumulated the same way out of the class's own blend. */
  function magicAt(cls, intRoll, wisRoll, level) {
    if (!cls.magic_blend.length) return 0;
    let total = cls.magic;
    for (let l = 1; l < level; l += 1) {
      total += poolStep(cls, intRoll + K.per_level * (l - 1),
                        wisRoll + K.per_level * (l - 1));
    }
    return total;
  }

  /** What one training adds to the pool at these attributes. */
  function poolStep(cls, intelligence, wisdom) {
    const attrs = { intelligence, wisdom };
    let blend = 0;
    for (const [attr, weight] of cls.magic_blend) blend += pctOf(attrs[attr], weight);
    return pctOf(blend, K.pct_magic);
  }

  /**
   * A character by hand: the class as it rolls at the cap, grown to a level.
   *
   * The roll cap is what every table in the guides assumes, and a character
   * rolled lower is behind by the difference on every line. Armor and weapon
   * are what the gold affords by then rather than what is worn, since a
   * character that does not exist yet is carrying nothing.
   */
  function byHand(code, level, weapon, armorShare, weaponShare) {
    const cls = classAt(code);
    const grown = K.roll_cap + K.per_level * (level - 1);
    const skill = bestSkill(cls);
    const armor = armorAfforded(level, armorShare, weapon !== "two_handed");
    const damage = weaponAfforded(level, weaponShare, weapon === "two_handed");
    return {
      source: "hand", name: null, code, level, skill,
      strength: grown, dexterity: grown, stamina: grown,
      intelligence: grown, wisdom: grown, charisma: grown,
      accuracy: grown + cls.modifier[skill],
      casting: cls.casting ? cls.casting + K.per_level * (level - 1) : 0,
      casts: attacksWithCasting(cls.casting, K.roll_cap + cls.modifier[skill]),
      armor,
      weapon: damage,
      absorption: armor + attributeBonus(grown),
      damage: damage + attributeBonus(grown),
      // Both accumulators walk the climb themselves, so they are given the
      // roll rather than the attribute as it stands at this level.
      health: healthAt(K.roll_cap, level),
      magic: magicAt(cls, K.roll_cap, K.roll_cap, level),
    };
  }

  /**
   * A character read out of the running game, from whichever of its two
   * columns holds the number in question.
   *
   * The record keeps every field twice. CURRENT is what the game rolls with
   * and what equipment is added into: worn armor is in its absorption, a ring
   * that lifts casting is in its casting. BASE is the stored character, and it
   * is what the level-up formulas read: charisma decides the next grant,
   * stamina the health it adds, intelligence and wisdom the pool.
   *
   * So the fight reads CURRENT and the career reads BASE. Health and magic are
   * the pair where the two columns mean something else again -- now and
   * maximum -- and the maximum is the one a plan is about.
   */
  function fromParty(person) {
    const now = (label) => u16(person.rec, CHAR.live + SHEET_AT[label] * CHAR.statStride);
    const base = (label) => u16(person.rec, CHAR.max + SHEET_AT[label] * CHAR.statStride);
    let skill = WEAPON_SKILLS[0];
    for (const s of WEAPON_SKILLS) if (now(s) > now(skill)) skill = s;
    const dexterity = now("dexterity");
    const strength = now("strength");
    const absorption = now("absorption");
    const damage = now("damage");
    return {
      source: "game", name: person.name, slot: person.slot,
      code: person.classCode % 10,
      level: person.level, skill,
      strength, dexterity, stamina: base("stamina"),
      intelligence: base("intelligence"), wisdom: base("wisdom"),
      charisma: base("charisma"),
      accuracy: now("accuracy"), casting: now("casting"),
      casts: attacksWithCasting(now("casting"), now("accuracy")),
      absorption, damage,
      // The sheet shows armor plus the dexterity bonus, and weapon plus the
      // strength bonus. Taking the bonus back out is what says how much of
      // each is equipment, which is the part gold moves and points do not.
      armor: Math.max(0, absorption - attributeBonus(dexterity)),
      weapon: Math.max(0, damage - attributeBonus(strength)),
      health: base("health"), magic: base("magic"),
    };
  }

  /* --- what gold has bought by a level ----------------------------------- */

  const experience = new Map(
    (D.leveling.experience || []).map((r) => [r.level, r.total]));
  const experienceFor = (level) => experience.get(level) || 0;

  /** One character's share of the party's gold, less what training cost. */
  function spareGold(level, share) {
    const A = PLAN.armor;
    const earned = experienceFor(level) * A.gold_per_xp / A.party;
    return (earned - A.train_base * level * (level - 1) / 2) * share;
  }

  /** Absorption the gold stretches to. Armor is cheap up to the plain set and
   *  about a hundred times dearer past it, where the money is buying
   *  enchantment rather than another piece. */
  const afforded = new Map();
  function armorAfforded(level, share, shield) {
    const key = `a${level}:${share}:${shield}`;
    if (afforded.has(key)) return afforded.get(key);
    const value = armorValue(level, share, shield);
    afforded.set(key, value);
    return value;
  }

  function armorValue(level, share, shield) {
    const spare = spareGold(level, share);
    if (spare <= 0) return 0;
    const set = shield ? PLAN.armor.shield : PLAN.armor.two_handed;
    const [plainCap, plainCost] = set.plain;
    const [topCap, topCost] = set.top;
    if (spare <= plainCost) return Math.floor(spare / (plainCost / plainCap));
    const perPoint = (topCost - plainCost) / (topCap - plainCap);
    return Math.min(topCap, plainCap + Math.floor((spare - plainCost) / perPoint));
  }

  /** Damage of the best weapon the gold stretches to. A two-handed build
   *  reads both lists, since the best affordable may still be a one-hander. */
  function weaponAfforded(level, share, twoHanded) {
    const key = `w${level}:${share}:${twoHanded}`;
    if (afforded.has(key)) return afforded.get(key);
    const value = weaponValue(level, share, twoHanded);
    afforded.set(key, value);
    return value;
  }

  function weaponValue(level, share, twoHanded) {
    const spare = spareGold(level, share);
    const stock = twoHanded
      ? PLAN.weapons.two_handed.concat(PLAN.weapons.one_handed)
        .sort((a, b) => b.damage - a.damage)
      : PLAN.weapons.one_handed;
    for (const w of stock) if (w.price <= spare) return w.damage;
    return 1;                                // bare hands until the first knife
  }

  /**
   * The points one training hands over, level by level.
   *
   * A level-up grants 13% of base charisma, capped at 15, and charisma climbs
   * 2 a level on its own. Charisma bought reaches the base column when the
   * screen closes (docs/leveling.md, the commit at image 0x0a631), so it
   * raises every grant after it, which is what the first few levels are for.
   *
   * These are not cumulative. Levels can be banked -- experience sits there
   * until a trainer is paid -- but points cannot: the screen does not close
   * with any in hand, so what a level grants is spent at that level or not at
   * all.
   */
  /**
   * Where to stop buying charisma.
   *
   * Not a constant: the best stop depends on the charisma the character has,
   * because the climb of 2 a level only ever lands on values of one parity and
   * buying past what it will reach is spent twice. A roll of 60 reaches 96 at
   * level 5 on its own, so a plan that buys to 100 pays 4 points for what was
   * coming anyway and holds 8 at level 5 instead of 12.
   *
   * Scored on the points a career frees, then on how early it frees them,
   * which is what the pool reads: a point of the attribute is worth what the
   * trainings after it make of it.
   */
  /* The payout staircase ends at 112, so the sweep looks a step past it and no
     further: charisma above that buys nothing at any level. */
  const CHARISMA_TOP = 116;
  const stops = new Map();
  function charismaStop(charisma, from, to) {
    const key = `${charisma}:${from}:${to}`;
    if (stops.has(key)) return stops.get(key);
    let best = charisma, score = [-1, -1];
    for (let stop = charisma; stop <= CHARISMA_TOP; stop += 1) {
      let cha = charisma, free = 0, early = 0;
      for (let lvl = from; lvl < to; lvl += 1) {
        const grant = Math.min(K.bonus_cap, pctOf(cha, K.pct_bonus_from_charisma));
        cha += K.per_level;
        const buy = Math.max(0, Math.min(stop - cha, grant));
        cha += buy;
        free += grant - buy;
        early += free;
      }
      if (free > score[0] || (free === score[0] && early > score[1])) {
        best = stop;
        score = [free, early];
      }
    }
    stops.set(key, best);
    return best;
  }

  function grantsFrom(charisma, from, to, topUp) {
    const stop = topUp ? charismaStop(charisma, from, to) : 0;
    const out = new Map();
    let cha = charisma;
    for (let lvl = from; lvl < to; lvl += 1) {
      /* The level-up reads the grant off base charisma, then adds 2 to it, and
         only then opens the bonus screen: image 0x09a7d reads [si+0x86] and
         stashes the result at 0x09a91, before the magic dispatch at 0x09a9a and
         the climb after it. So the climb is in hand when the points are spent,
         and buying what it was about to supply spends them twice. */
      const granted = Math.min(K.bonus_cap, pctOf(cha, K.pct_bonus_from_charisma));
      cha += K.per_level;
      const buy = Math.max(0, Math.min(stop - cha, granted));
      cha += buy;
      out.set(lvl + 1, { granted, charisma: buy, free: granted - buy });
    }
    return out;
  }

  /* --- the projection ---------------------------------------------------- */

  // Every attribute and every skill climbs 2 a level whatever else happens, so
  // a character at a later level is itself, plus the climb, plus whatever the
  // schedule has bought by then. Armor and weapon are the better of what it
  // carries now and what the gold affords by then: nobody sells their armor.
  //
  // The levers are the five places a point can go. Dexterity is one lever
  // serving three goals, which is why what they need is taken as a maximum
  // rather than added up.
  const LEVERS = ["attack", "dexterity", "strength", "pool", "casting"];
  /** The lever this goal buys for this character: a goal about landing an
   *  attack buys casting for a caster and weapon skill for everyone else. */
  const leverOf = (goal, plan) =>
    (goal.lever === "attack" && plan.character.casts ? "casting" : goal.lever);
  const LEVER_LABEL = {
    attack: "weapon skill", dexterity: "dexterity", strength: "strength",
    pool: "pool attribute", casting: "casting",
    // Not a lever a goal buys: it is what the first trainings go into, and it
    // pays for itself by raising every grant after it.
    charisma: "charisma",
  };
  /* The same levers, for the column that names one on every row. */
  const LEVER_SHORT = {
    attack: "skill", dexterity: "dex", strength: "str", pool: "pool",
    casting: "casting", charisma: "cha",
  };

  // Health is the same at a level whatever is bought, so it is kept against
  // the character it was walked for.
  let healthFor = null;
  let healthCache = new Map();

  function project(plan, level, bought) {
    const c = plan.character;
    if (healthFor !== c) { healthFor = c; healthCache = new Map(); }
    const cls = classAt(c.code);
    const grown = K.per_level * (level - c.level);
    const dexterity = c.dexterity + grown + bought.dexterity;
    const strength = c.strength + grown + bought.strength;
    const armor = Math.max(c.armor, armorAfforded(
      level, plan.armorShare, plan.weapon !== "two_handed"));
    const weapon = Math.max(c.weapon, weaponAfforded(
      level, plan.weaponShare, plan.weapon === "two_handed"));

    // Health and the pool are both non-retroactive: each training adds a share
    // of the attribute as it stands then, so both are walked from where the
    // character is rather than recomputed from a roll it may not have had.
    let health = healthCache.get(level);
    if (health === undefined) {
      health = c.health;
      for (let l = c.level; l < level; l += 1) {
        health += pctOf(c.stamina + K.per_level * (l - c.level),
                        K.pct_health_from_stamina);
      }
      healthCache.set(level, health);
    }
    // Which is why the pool attribute is the one lever whose purchases are
    // dated. A point of intelligence bought at level 5 widens the pool at every
    // training after it and the same point at 35 widens one, so crediting the
    // whole purchase from the start would promise a pool the character cannot
    // have. `bought.pool` is the running total; `bought.poolAt` is when each
    // part of it was paid for.
    let magic = c.magic;
    if (cls.magic_blend.length) {
      const attr = poolAttribute(cls);
      const held = (l) => (bought.poolAt || []).reduce(
        (n, [when, points]) => n + (when <= l ? points : 0), 0);
      for (let l = c.level; l < level; l += 1) {
        const climb = K.per_level * (l - c.level);
        const bonus = held(l);
        magic += poolStep(
          cls,
          c.intelligence + climb + (attr === "intelligence" ? bonus : 0),
          c.wisdom + climb + (attr === "wisdom" ? bonus : 0));
      }
    }

    const accuracy = c.accuracy + grown + bought.attack;
    const casting = c.casting ? c.casting + grown + bought.casting : 0;
    return {
      level, dexterity, strength, armor, weapon, health, magic,
      accuracy, casting,
      // What an attack of this character's rolls with, and what a landed one
      // delivers. A caster's blow is the spell, so the damage behind it is
      // read off the spell rather than off the weapon it is not swinging.
      attack: c.casts ? casting : accuracy,
      absorption: armor + attributeBonus(dexterity),
      damage: weapon + attributeBonus(strength),
    };
  }

  /* --- the goals --------------------------------------------------------- */

  // Each goal names the lever that buys it, answers yes or no for a
  // projection, and can show its own working. The evidence rows are the
  // numbers the answer was reached with rather than a second derivation of
  // them.
  //
  // Every goal is monotone in its lever -- more points never make one harder
  // to hold -- which is what lets the solver bisect for the price instead of
  // inverting a step function and a lookup table.

  const percentTarget = (t) => `${Math.round(t * 100)}%`;

  /* Working is a comparison, so it is written as one: what the character has
     on one side, what it is up against on the other, and the line that decides
     the verdict marked as such. `mine` or `theirs` may be absent where a row
     has only one side to it. */
  const versus = (mine, theirs) => ({ mine, theirs });
  const decides = (label, value, needs, ok, monster) =>
    ({ label, value, needs, ok, monster });

  /**
   * The monsters that can take a turn away by this level, and the absorption
   * that shuts those out.
   *
   * Measured against what a character of this level meets, like every other
   * goal: the Ice Dwarf's 185 is what a level-30 character has to answer, and
   * asking a level-20 character for it would be pricing a fight it has not
   * reached. The four arrive at 19, 26, 28 and 30, so the bar rises with them
   * and stops at 186 for good.
   */
  function incapacitatorsBy(level) {
    const met = PLAN.incapacitating.monsters
      .filter((c) => Math.min(c.level, CAP) <= level);
    return { met,
             needs: met.length ? Math.max(...met.map((c) => c.accuracy)) + 1 : 0 };
  }

  /** One round with every engaged monster landing on the same character. */
  const worstRound = (me, at) =>
    at.group.value * perHit(at.damage.value, at.accuracy.value - me.absorption);

  const GOALS = {
    first_strike: {
      label: "First strike",
      lever: "dexterity",
      target: null,
      describe: () => "First strike",
      holds: (plan, me, at) => me.dexterity >= at.dexterity.value,
      rows: (plan, me, at) => [
        decides("Dexterity", me.dexterity, at.dexterity.value,
                me.dexterity >= at.dexterity.value, at.dexterity.monster),
      ],
    },

    hit: {
      label: "100% hit",
      lever: "attack",
      target: null,
      // Margin 55 is where the odds curve reaches 1: the roll is rand(55), so
      // 55 beats every face of it.
      describe: () => "100% hit",
      holds: (plan, me, at) => me.attack - at.absorption.value >= K.attack_roll,
      rows(plan, me, at) {
        const margin = me.attack - at.absorption.value;
        return [
          versus([attackName(plan), me.attack],
                 ["Absorption", at.absorption.value, at.absorption.monster]),
          versus(["Hit", percentTarget(rollOdds(margin))], null),
          decides("Margin", margin, K.attack_roll, margin >= K.attack_roll),
        ];
      },
    },

    damage: {
      label: "100% damage",
      lever: "attack",
      target: null,
      // A hit delivers the margin as a percentage of the damage stat, so
      // margin 100 is the whole of it and anything above is more.
      describe: () => "100% damage",
      holds: (plan, me, at) => me.attack - at.absorption.value >= FULL_DAMAGE,
      rows(plan, me, at) {
        const margin = me.attack - at.absorption.value;
        const blow = blowOf(plan, me, at);
        return [
          versus([attackName(plan), me.attack],
                 ["Absorption", at.absorption.value, at.absorption.monster]),
          versus([blow.name, blow.damage], null),
          versus(["Per hit", perHit(blow.damage, margin)], null),
          decides("Margin", margin, FULL_DAMAGE, margin >= FULL_DAMAGE),
        ];
      },
    },

    untouchable: {
      label: "Untouchable",
      lever: "dexterity",
      target: null,
      // Their margin below zero. Margin 0 is not nothing: the curve puts it at
      // 2%, so the stop is one point past their accuracy rather than level
      // with it, which is the 241 against Paltivar's 240 in STRATEGY.md.
      describe: () => "Untouchable",
      holds: (plan, me, at) => at.accuracy.value - me.absorption < 0,
      rows: (plan, me, at) => [
        versus(["Armor", me.armor],
               ["Accuracy", at.accuracy.value, at.accuracy.monster,
                at.accuracy.shot && "shot"]),
        versus(["They hit", percentTarget(rollOdds(at.accuracy.value - me.absorption))],
               null),
        decides("Absorption", me.absorption, at.accuracy.value + 1,
                me.absorption > at.accuracy.value),
      ],
    },

    take_hit: {
      label: "Take hit %",
      lever: "dexterity",
      target: { kind: "percent", value: 0.266, label: "%" },
      describe: (t) => `Take hit ${percentTarget(t)}`,
      holds: (plan, me, at, target) =>
        rollOdds(at.accuracy.value - me.absorption) <= target + 1e-9,
      rows(plan, me, at, target) {
        const margin = at.accuracy.value - me.absorption;
        return [
          versus(["Absorption", me.absorption],
                 ["Accuracy", at.accuracy.value, at.accuracy.monster,
                  at.accuracy.shot && "shot"]),
          versus(["Armor", me.armor],
                 ["Per hit", perHit(at.damage.value, margin), at.damage.monster,
                  at.damage.shot && "shot"]),
          decides("They hit", percentTarget(rollOdds(margin)),
                  percentTarget(target), rollOdds(margin) <= target + 1e-9),
        ];
      },
    },

    one_round: {
      label: "One-round kill",
      lever: "attack",
      target: { kind: "number", value: 4, label: "attackers" },
      describe: (t) => `One-round kill, ${t} focus-firing`,
      holds: (plan, me, at, target) =>
        target * output(plan, me, at) >= at.health.value,
      rows(plan, me, at, target) {
        const one = output(plan, me, at);
        const blow = blowOf(plan, me, at);
        return [
          versus([blow.name, blow.damage],
                 ["Absorption", at.absorption.value, at.absorption.monster]),
          versus(["Output", Math.round(one)], null),
          decides(`Output × ${target}`, Math.round(one * target),
                  at.health.value, one * target >= at.health.value,
                  at.health.monster),
        ];
      },
    },

    conditions: {
      label: "Condition proof",
      lever: "dexterity",
      target: null,
      describe: () => "Condition proof",
      holds: (plan, me) => me.absorption >= incapacitatorsBy(me.level).needs,
      rows(plan, me) {
        /* The same absorption the other two defensive goals read, and its
           armor half shown the same way: what a shield is worth is the whole
           difference between the stops. */
        const { met, needs } = incapacitatorsBy(me.level);
        const rows = [versus(["Armor", me.armor], null)];
        for (const c of met) {
          /* The label is the monster's name, so tagging the value with it
             again would say it twice. */
          rows.push(versus(null, [titleCase(c.name), c.accuracy, null,
                                  c.condition.toLowerCase()]));
        }
        rows.push(decides("Absorption", me.absorption, needs,
                          me.absorption >= needs));
        return rows;
      },
    },

    survive: {
      label: "Survive a round",
      lever: "dexterity",
      target: null,
      describe: () => "Survive a round",
      holds: (plan, me, at) => me.health > worstRound(me, at),
      rows: (plan, me, at) => [
        versus(["Absorption", me.absorption],
               ["Accuracy", at.accuracy.value, at.accuracy.monster,
                at.accuracy.shot && "shot"]),
        versus(null, ["Damage", at.damage.value, at.damage.monster,
                      at.damage.shot && "shot"]),
        versus(null, [`Engaged`, at.group.value, at.group.monster]),
        decides("Health", me.health, Math.round(worstRound(me, at)),
                me.health > worstRound(me, at)),
      ],
    },

    one_cast: {
      label: "One-cast kill",
      lever: "casting",
      target: null,
      describe: () => "One-cast kill",
      holds(plan, me, at) {
        const cast = bestCast(plan, me, at);
        return !!cast && cast.landed >= at.health.value;
      },
      rows(plan, me, at) {
        const cast = bestCast(plan, me, at);
        if (!cast) {
          return [decides("Spell", "\u2014", at.health.value, false,
                          at.health.monster)];
        }
        const rows = [
          versus(["Casting", me.casting],
                 ["Absorption", at.absorption.value, at.absorption.monster]),
          versus(["Spell", titleCase(cast.spell.name)], null),
          versus(["Damage", cast.spell.damage], null),
          versus(["Cost", cast.spell.mp], null),
        ];
        if (cast.halved) {
          rows.push(versus(null, ["Resisted", "\u00d70.5", at.health.monster]));
        }
        rows.push(decides("Lands", Math.round(cast.landed), at.health.value,
                          cast.landed >= at.health.value, at.health.monster));
        return rows;
      },
    },

    kills: {
      label: "Kills per rest",
      lever: "attack",
      target: { kind: "number", value: 20, label: "kills" },
      describe: (t) => `Kills per rest ${t}`,
      holds: (plan, me, at, target) => killsPerRest(plan, me, at) >= target,
      rows(plan, me, at, target) {
        const foe = worstRestFoe(plan, me, at);
        if (!foe) return [decides("Kills", 0, target, false)];
        const cast = plan.character.casts ? castAgainst(plan, me, foe) : null;
        const output = cast ? cast.landed
          : swing(me.damage, me.attack, foe.absorption);
        /* The fight is one monster's, so it is named once, on the first row
           it appears in rather than against every number it carries. */
        const rows = [
          versus(["Output", Math.round(output)], ["Health", foe.health, foe]),
          versus(["Health", me.health], ["Engaged", groupSize(foe)]),
          versus(null, ["Takes a round", Math.round(takenPerRound(me, foe))]),
        ];
        if (cast) rows.push(versus(["Casts", Math.floor(me.magic / cast.spell.mp)], null));
        rows.push(decides("Kills", killsPerRest(plan, me, at), target,
                          killsPerRest(plan, me, at) >= target));
        return rows;
      },
    },

    spells: {
      label: "Spells per rest",
      lever: "pool",
      /* The pool is what this is, and the pool is bought early or not at all,
         so it is served by the policy exactly as a pool target is. */
      policy: "poolThrough",
      nearness: (plan, me, at, target) =>
        Math.min(1, spellsPerRest(plan, me, at) / target),
      target: { kind: "number", value: 10, label: "casts" },
      describe: (t) => `Spells per rest ${t}`,
      holds: (plan, me, at, target) => spellsPerRest(plan, me, at) >= target,
      rows(plan, me, at, target) {
        const cast = bestCast(plan, me, at);
        return [
          versus(["Magic", me.magic], null),
          versus(["Spell", cast ? titleCase(cast.spell.name) : "\u2014"], null),
          versus(["Cost", cast ? cast.spell.mp : "\u2014"], null),
          decides("Casts", spellsPerRest(plan, me, at), target,
                  spellsPerRest(plan, me, at) >= target),
        ];
      },
    },

    pool: {
      label: "Magic pool",
      lever: "pool",
      /* Served by the pool policy rather than bought when the goal asks. The
         pool is not retroactive, so points spent at the level the goal wants
         them buy almost nothing: what reaches a target is having fed the pool
         from the first training, which is how long the policy runs for. */
      policy: "poolThrough",
      /* How close it came, for choosing between policies that all fall short.
         Without it every candidate scores the same nothing and the fit has no
         reason to prefer the one that got furthest. */
      nearness: (plan, me, at, target) => Math.min(1, me.magic / target),
      target: { kind: "number", value: 500, label: "points" },
      describe: (t) => `Magic pool ${t}`,
      holds: (plan, me, at, target) => me.magic >= target,
      rows(plan, me, at, target) {
        const attr = poolAttribute(classAt(plan.character.code));
        return [
          versus(["From", attr ? titleCase(attr) : "\u2014"], null),
          decides("Magic", me.magic, target, me.magic >= target),
        ];
      },
    },
  };

  /** What the character rolls its attack with, named for the evidence. */
  const attackName = (plan) => (plan.character.casts ? "Casting" : "Accuracy");

  /**
   * What a landed attack of this character's delivers, and what it is called.
   *
   * A caster's blow is its best spell rather than the weapon it is not
   * swinging, so the damage behind the tempo and full-damage goals is read off
   * the spell -- and a spell the monster resists or is immune to is picked
   * around by bestCast rather than counted at full value.
   */
  function blowOf(plan, me, at) {
    if (!plan.character.casts) return { name: "Damage", damage: me.damage };
    const cast = bestCast(plan, me, at);
    return cast ? { name: titleCase(cast.spell.name), damage: cast.spell.damage }
                : { name: "Spell", damage: 0 };
  }

  /**
   * What one rest is worth, as casts and as kills.
   *
   * Two currencies bound a stretch of play. Magic runs out, and a caster's
   * pool divided by what it throws is how many times it throws it. Health runs
   * out, and what refills it is the same rest, so the damage taken killing one
   * monster says how many can be killed before that rest is due. A weapon
   * costs nothing to swing, so a martial is bounded by the second alone; a
   * caster is bounded by whichever runs out first.
   *
   * Incoming is the expected rate rather than the worst round: everything
   * connecting at once is what `Survive a round` asks about, and a stretch of
   * play is the average of many rounds.
   */
  function spellsPerRest(plan, me, at) {
    if (!plan.character.casts) return 0;
    const cast = bestCast(plan, me, at);
    if (!cast || !cast.spell.mp) return 0;
    return Math.floor(me.magic / cast.spell.mp);
  }

  /**
   * A rate is priced against one real monster, not against the worst of every
   * stat at once.
   *
   * Taking each stat from whichever monster carries the most of it is right
   * for a threshold: landing every swing on the best-armored thing of the
   * level and being untouchable by the fastest are separate promises, and each
   * has to hold. A rate is not a promise, it is a fight repeated, and the
   * chimera describes a fight nobody has: at level 30 it puts three monsters
   * in front of you, each with the Ice Dwarf's damage, the Ghoul's accuracy,
   * the Wisp's health and party attack, and every character in the game
   * manages one kill against it.
   *
   * So the rate is measured against each monster that is extreme in something
   * -- five or six of them a level -- and the worst answer wins. That is still
   * the worst case, and it is a fight that exists.
   */
  function restFoes(at) {
    const seen = new Map();
    for (const field of ADVERSARY.concat(["group", "attacks"])) {
      const found = at[field] && at[field].monster;
      if (found) seen.set(found.name, found);
    }
    return [...seen.values()];
  }

  /* A rate is a fight repeated, so it is measured against attacks that exist:
     each of the monster's own, whole, and the one that costs the most. For a
     shooter that is the worst round of the fight rather than every round of
     it, since which attack it has is the distance's to say. */
  function takenPerRound(me, foe) {
    return Math.max(...attacksOf(foe).map((a) => {
      const margin = a.accuracy - me.absorption;
      return groupSize(foe) * attacksEach(foe)
        * rollOdds(margin) * perHit(a.damage, margin);
    }));
  }

  /** Kills before a rest, against one monster. */
  function killsAgainst(plan, me, foe) {
    const cast = plan.character.casts ? castAgainst(plan, me, foe) : null;
    const output = plan.character.casts
      ? (cast ? cast.landed : 0)
      : swing(me.damage, me.attack, foe.absorption);
    if (!output) return 0;
    const rounds = Math.max(1, foe.health / output);
    const taken = takenPerRound(me, foe);
    const byHealth = taken > 0 ? me.health / (rounds * taken) : Infinity;
    let byMagic = Infinity;
    if (plan.character.casts && cast && cast.spell.mp) {
      byMagic = Math.floor(me.magic / cast.spell.mp) / Math.max(1, rounds);
    }
    return Math.min(byHealth, byMagic);
  }

  function killsPerRest(plan, me, at) {
    const foes = restFoes(at);
    if (!foes.length) return 0;
    return Math.floor(Math.min(...foes.map((foe) => killsAgainst(plan, me, foe))));
  }

  /** The monster a rate is worst against, for the evidence to name. */
  function worstRestFoe(plan, me, at) {
    let worst = null, least = Infinity;
    for (const foe of restFoes(at)) {
      const kills = killsAgainst(plan, me, foe);
      if (kills < least) { least = kills; worst = foe; }
    }
    return worst;
  }

  /** Expected damage in a round: one swing, or one cast. */
  function output(plan, me, at) {
    if (!plan.character.casts) {
      return swing(me.damage, me.attack, at.absorption.value);
    }
    const cast = bestCast(plan, me, at);
    return cast ? cast.landed : 0;
  }

  // A spell's blow carries bit 13 when it is the kind a spell-resistant
  // monster halves, which is 59 of the 70 damage spells.
  const BLOW_SPELL = 0x2000;

  /** The best spell the character knows here, and what it delivers.
   *
   * Immunity removes a spell from the list rather than reducing it, and
   * resistance halves what lands. Both are read off the monster whose health
   * the cast has to clear, which is the one the goal is about. */
  const bestCast = (plan, me, at) =>
    castAgainst(plan, me, at.health.monster, at.absorption.value);

  /** The same, against one monster and its own armor. */
  function castAgainst(plan, me, foe, absorption) {
    const cls = classAt(plan.character.code);
    if (!cls.magic_blend.length) return null;
    const name = cls.name.toUpperCase();
    const immune = new Set((foe && foe.immune) || []);
    const margin = me.casting
      - (absorption === undefined ? (foe ? foe.absorption : 0) : absorption);
    let best = null;
    for (const s of D.spells) {
      if (!s.listed || !s.damage) continue;
      const learned = (s.classes || []).filter((c) => c.class === name)
        .map((c) => c.level);
      if (!learned.length || Math.min(...learned) > me.level) continue;
      // A monster immune to the spell's element takes nothing at all from it,
      // so the spell is not an option rather than a halved one. The 39 damage
      // spells that carry no element cannot be shut out this way.
      if ((s.element || []).some((e) => immune.has(e.toUpperCase()))) continue;
      const halved = !!(foe && foe.resist_magic && (s.blow & BLOW_SPELL));
      const landed = rollOdds(margin) * perHit(s.damage, margin) * (halved ? 0.5 : 1);
      if (!best || landed > best.landed) best = { spell: s, landed, margin, halved };
    }
    return best;
  }

  /* --- the walk ---------------------------------------------------------- */

  // One pass from where the character stands to the cap. Points are permanent,
  // so a lever only ever rises: what a goal needs at a level is bought when the
  // budget covers it and the goal is passed over when it does not, in the order
  // the goals are listed. That is what a player does at a trainer, and it is
  // why the order is a control rather than a fixed ranking.
  const HEADROOM = 600;   // points past what is already bought that a search
                          // will consider before calling a goal out of reach

  /**
   * The state after raising one lever to `points`, bought at this level.
   *
   * The pool attribute is the one that has to remember when: everything else a
   * point buys is worth the same whenever it is bought.
   */
  function raise(bought, lever, points, level) {
    const next = Object.assign({}, bought, { [lever]: points });
    if (lever === "pool") {
      next.poolAt = (bought.poolAt || []).concat(
        [[level, points - bought.pool]]);
    }
    return next;
  }

  /** The lever total this goal needs at this level, or null if no purchase
   *  reaches it. Bisected, since every goal is monotone in its lever. */
  function pointsNeeded(plan, goal, spec, level, bought, at) {
    const lever = leverOf(goal, plan);
    const held = (p) => goal.holds(
      plan, project(plan, level, raise(bought, lever, p, level)),
      at, spec.target);
    let lo = bought[lever];
    if (held(lo)) return lo;
    let hi = lo + HEADROOM;
    if (!held(hi)) return null;
    while (hi - lo > 1) {
      const mid = Math.floor((lo + hi) / 2);
      if (held(mid)) hi = mid; else lo = mid;
    }
    return hi;
  }

  /**
   * The career: what each training's points buy, level by level.
   *
   * The rule that shapes this is that levels can be banked and points cannot.
   * Experience sits there until a trainer is paid, but the bonus screen does
   * not close with points in hand, so a level's grant is spent at that level
   * or it is not spent at all. There is no saving up for the stop two levels
   * ahead: what a goal costs has to have been going into that lever all along.
   *
   * So each level spends its whole grant, in this order:
   *
   *   1. what an active goal needs now, down the list, so the order decides
   *      which one gives way when one training will not cover both;
   *   2. toward what a goal further up the career will ask for, in the same
   *      order, which is the only way to arrive at a stop able to pay for it;
   *   3. strength, to the crossover, when that is switched on;
   *   4. whatever is left, into the lever the first goal uses, since a point
   *      of skill is never worth nothing.
   */
  function walk(plan) {
    const active = plan.goals.filter((g) => g.on && GOALS[g.type]);
    const { need, reach } = eventualNeeds(plan, active);
    /* A goal nothing can reach still takes what is left over -- it is the one
       that was asked for -- but it must not starve a goal that could have been
       met, so it is served after those rather than in place of them. Whether a
       goal is reachable is asked of the goal alone, against a character that
       has bought nothing: asking it of the plan as it stands would call a goal
       hopeless whenever the goal above it had taken the money. */
    const hopeless = new Set();
    for (const g of active) {
      const goal = GOALS[g.type];
      if (!goal.policy) {
        if (!reach.has(g)) hopeless.add(g);
        continue;
      }
      /* A policy goal is reached by the policy or not at all, so it is walked
         on its own to find out. There is at most one of them. */
      const solo = [g];
      const rows = walkOnce(plan, solo, eventualNeeds(plan, solo).need, new Set());
      if (!rows.some((r) => r.results[0] && r.results[0].state === "held")) {
        hopeless.add(g);
      }
    }
    return walkOnce(plan, active, need, hopeless);
  }

  /**
   * The most each lever is asked for anywhere in the career.
   *
   * Priced against a character that has bought nothing, so a goal whose cost
   * depends on another lever -- the tempo goal reads the damage strength
   * feeds -- is quoted a little high. It errs toward buying early, which is
   * the side to err on when nothing can be saved up.
   */
  function eventualNeeds(plan, active) {
    const zero = { poolAt: [] };
    for (const lever of LEVERS) zero[lever] = 0;
    const need = {};
    for (const lever of LEVERS) need[lever] = 0;
    /* Priced against a character that has bought nothing, so a goal is in
       `reach` when its lever can carry it at some level whatever else the
       career is doing. That is the test for whether a goal is worth serving
       first: one no purchase can reach is not being given up on, it is being
       served last, out of what the others leave. */
    const reach = new Set();
    for (let level = plan.character.level; level <= CAP; level += 1) {
      const at = worstAt(level, plan.bosses);
      for (const g of active) {
        if (level < g.from) continue;
        const goal = GOALS[g.type];
        if (goal.policy) continue;
        const points = pointsNeeded(plan, goal, g, level, zero, at);
        if (points !== null) {
          const lever = leverOf(goal, plan);
          need[lever] = Math.max(need[lever], points);
          reach.add(g);
        }
      }
    }
    return { need, reach };
  }

  function walkOnce(plan, active, eventual, hopeless) {
    // Replaced rather than mutated as the career goes on, so that a row can
    // keep the state it was drawn from.
    let bought = { poolAt: [] };
    for (const lever of LEVERS) bought[lever] = 0;
    const c = plan.character;
    const granted = grantsFrom(c.charisma, c.level, CAP, plan.topUpCharisma);
    const rows = [];

    for (let level = c.level; level <= CAP; level += 1) {
      const at = worstAt(level, plan.bosses);
      const training = granted.get(level) || { granted: 0, charisma: 0, free: 0 };
      const spent = training.charisma ? [["charisma", training.charisma]] : [];
      let purse = training.free;
      const buy = (lever, points) => {
        const take = Math.min(Math.max(0, points), purse);
        if (take <= 0) return;
        bought = raise(bought, lever, bought[lever] + take, level);
        purse -= take;
        spent.push([lever, take]);
      };

      /* A goal's level is a deadline, not a start: "condition proof from 24"
         is a promise about level 24, and a stop is reached by having bought
         toward it, never by beginning to buy on the day it falls due. So a
         goal not yet due is priced at the level it comes due and bought
         toward from here, in its own place in the order. */
      /* The pool takes the early trainings before anything else asks for them.
         Every other lever is worth the same whenever it is bought, so a goal
         that waits loses nothing; the pool is not retroactive, so a point of
         the attribute is worth what the trainings after it make of it. Feeding
         it a share at a time, in its place in the order, spreads it across
         levels where it buys almost nothing. It is bought from the first
         training or it is not bought.
         A target nothing can reach is left out: it takes the leftovers below
         rather than the career. */
      const early = active.find((g) => GOALS[g.type].policy && !hopeless.has(g));
      if (early && plan.poolThrough && level <= plan.poolThrough
          && classAt(c.code).magic_blend.length) {
        /* Measured at the level the goal comes due, not at this one. What a
           pool is worth at 40 is settled by the trainings before it, and a
           target met today can be missed tomorrow when a costlier spell is
           learned. Stopping on today's answer buys the pool again later, at
           levels where it is worth a fraction. */
        const due = Math.max(level, early.from);
        const then = project(plan, due, bought);
        if (!GOALS[early.type].holds(plan, then, worstAt(due, plan.bosses),
                                     early.target)) {
          buy("pool", purse);
        }
      }

      const results = [];
      const claim = (g) => {
        const goal = GOALS[g.type];
        if (goal.policy) {
          /* Bought above, before any goal took a share of the training. A
             target nothing can reach buys nothing at all: the pool is worth
             what the trainings after it make of it, so points put into a
             target that will be missed anyway are spent at the levels where
             they are worth least. */
          if (level < g.from) return { goal: g, state: "later" };
          const now = project(plan, level, bought);
          return { goal: g,
                   state: goal.holds(plan, now, at, g.target) ? "held" : "missed" };
        }
        const lever = leverOf(goal, plan);
        const due = level >= g.from;
        const when = due ? level : g.from;
        const need = pointsNeeded(plan, goal, g, when, bought,
                                  due ? at : worstAt(when, plan.bosses));
        if (need === null) {
          /* Nothing reaches it here. Points are permanent and this goal is the
             one that was asked for, so what is left goes on its lever anyway. */
          buy(lever, purse);
          return { goal: g, state: due ? "unreachable" : "later" };
        }
        buy(lever, need - bought[lever]);
        if (!due) return { goal: g, state: "later" };
        const short = need - bought[lever];
        return short > 0 ? { goal: g, state: "short", short }
                         : { goal: g, state: "held" };
      };

      for (const g of active) {
        if (!hopeless.has(g)) results.push(claim(g));
      }
      /* What nothing can meet is served last, so that it takes the leftovers
         rather than the trainings a reachable goal needed. */
      for (const g of active) {
        if (hopeless.has(g)) results.push(claim(g));
      }
      results.sort((a, b) => active.indexOf(a.goal) - active.indexOf(b.goal));
      if (purse && plan.spare === "strength") {
        buy("strength", strengthCrossover(plan, level, bought, purse, at));
      }
      /* Strength stops paying at the crossover, and the training still has to
         close, so whatever is over goes where the choice says. */
      if (purse) buy(plan.spare === "dexterity" ? "dexterity" : leverOf(GOALS.hit, plan), purse);

      const me = project(plan, level, bought);
      rows.push({
        level, grant: training.granted, spent, me, at, bought,
        results: results.map((r) => Object.assign({ me }, r)),
      });
    }
    return rows;
  }

  /** Points of strength worth buying here, out of what the goals left. */
  function strengthCrossover(plan, level, bought, spare, at) {
    let best = 0, bestOut = -1;
    for (let p = 0; p <= spare; p += 1) {
      const me = project(plan, level,
                         raise(bought, "strength", bought.strength + p, level));
      const out = swing(me.damage, me.accuracy, at.absorption.value);
      if (out > bestOut) { bestOut = out; best = p; }
    }
    return best;
  }

  /* --- the archetypes ---------------------------------------------------- */

  // The builds STRATEGY.md prices, as goal lists. A stop is a chance of being
  // hit and everything else follows from where the character stands when it
  // buys one, so the stops are the targets and the order of each row is the
  // order the points are spent in.
  const ARCHETYPES = [
    ["berserker", "Berserker", "two_handed", [
      ["first_strike", 6], ["hit", 6], ["one_round", 15, 4]]],
    ["half", "Half the time", "one_handed", [
      ["first_strike", 6], ["hit", 6], ["one_round", 15, 4],
      ["take_hit", 15, 0.5]]],
    ["rarely", "Rarely hit", "one_handed", [
      ["first_strike", 6], ["hit", 6], ["take_hit", 15, 0.266],
      ["conditions", 15]]],
    ["untouchable", "Untouchable", "one_handed", [
      ["first_strike", 6], ["untouchable", 15], ["hit", 6]]],
    ["caster", "Caster", "one_handed", [
      ["first_strike", 6], ["one_cast", 12], ["take_hit", 20, 0.5],
      ["pool", 20, 500]]],
    ["healer", "Healer", "one_handed", [
      ["first_strike", 6], ["pool", 12, 800], ["conditions", 15],
      ["take_hit", 20, 0.266]]],
  ];

  const goalFrom = (type, from, target) => ({
    type, from, on: true,
    target: target === undefined
      ? (GOALS[type].target ? GOALS[type].target.value : null) : target,
  });

  const archetypeGoals = (key) => {
    const found = ARCHETYPES.find((a) => a[0] === key);
    return found ? found[3].map((g) => goalFrom(g[0], g[1], g[2])) : [];
  };

  /* --- the tab ----------------------------------------------------------- */

  let planCharacter = null;      // read out of the game, once it has been
  let planNote = null;

  /* --- the policies, fitted to the goals --------------------------------- */
  //
  // What the character carries, which skill it attacks with, how long it feeds
  // the pool and where its leftovers go are not settings a player should have
  // to guess. A goal that fails only because the plan is holding a two-hander,
  // or is not buying the pool at all, has not failed: the plan was wrong. So
  // whatever the player has not chosen for themselves, the planner chooses, by
  // walking the career under each candidate and keeping whichever holds the
  // goals for the most levels -- taken in the order the goals are listed, so
  // the first one settles a tie.
  //
  // Choosing a value in one of those fields pins it, and Fit again lets go of
  // every pin. A pinned policy is never overruled: a player who wants to see
  // what a two-handed berserker cannot hold is asking a real question.
  const POLICIES = ["weapon", "attacksWith", "poolThrough", "spare"];
  /* Named for what the field is rather than for the key behind it. */
  const POLICY_CLASS = {
    weapon: "plan-weapon", attacksWith: "plan-attack",
    poolThrough: "plan-pool", spare: "plan-spare",
  };

  /** What a policy could be, for this plan, or null where it has no choice. */
  function policyCandidates(plan, key) {
    const cls = classAt(plan.character.code);
    if (key === "weapon") return ["one_handed", "two_handed"];
    if (key === "attacksWith") {
      return canDoEither(cls) ? ["weapon", "casting"] : null;
    }
    if (key === "poolThrough") {
      return cls.magic_blend.length ? [0, 8, 12, 16, 20, 26, 32, CAP] : null;
    }
    return spareRoutes(plan).map(([value]) => value);
  }

  /** Levels held, one count per goal, in the order the goals are listed. */
  function scoreOf(plan) {
    const active = plan.goals.filter((g) => g.on && GOALS[g.type]);
    if (!active.length) return [];
    const rows = walk(plan);
    const score = [];
    for (const g of active) {
      const goal = GOALS[g.type];
      let held = 0, near = 0;
      for (const row of rows) {
        const hit = row.results.find((x) => x.goal === g);
        if (!hit || hit.state === "later") continue;
        if (hit.state === "held") held += 1;
        else if (goal.nearness) near += goal.nearness(plan, hit.me, row.at, g.target);
      }
      score.push(held, near);
    }
    return score;
  }

  /** Whether the first score beats the second, first goal first. */
  function beats(a, b) {
    for (let i = 0; i < a.length; i += 1) {
      if (a[i] !== b[i]) return a[i] > b[i];
    }
    return false;
  }

  // Solving is a career a candidate, so the answer is kept against everything
  // that could change it rather than recomputed for a redraw.
  const fitted = new Map();

  function fitPolicies(stored, settings) {
    const open = POLICIES.filter((key) => settings[key] === null
                                          || settings[key] === undefined);
    if (!open.length) return settings;
    /* The whole character, because it is watched now: a point spent or a piece
       of armor bought changes what the policies should be, and a key of name
       and level would hand back the fit from before it. */
    const key = JSON.stringify([settings, stored.goals, stored.bosses,
                                stored.code, planCharacter]);
    if (fitted.has(key)) return fitted.get(key);

    let best = Object.assign({}, settings);
    let score = scoreOf(buildPlan(stored, best));
    for (const policy of open) {
      const options = policyCandidates(buildPlan(stored, best), policy);
      if (!options) continue;
      for (const option of options) {
        const trial = Object.assign({}, best, { [policy]: option });
        const mark = scoreOf(buildPlan(stored, trial));
        if (beats(mark, score)) { best = trial; score = mark; }
      }
    }
    fitted.set(key, best);
    return best;
  }

  /** The plan these settings describe. */
  function buildPlan(stored, settings) {
    const archetype = stored.archetype || "rarely";
    const plan = {
      archetype,
      // A plan kept from a build with a different goal set is not this build's
      // plan: dropping the rows it names would leave a plan the player did not
      // make, so the archetype is used instead.
      goals: stored.goals && stored.goals.length
        && stored.goals.every((g) => GOALS[g.type])
        ? stored.goals : archetypeGoals(archetype),
      code: stored.code || 1,
      bosses: !!stored.bosses,
      evidence: !!stored.evidence,
      armorShare: stored.armorShare === undefined ? 0.5 : stored.armorShare,
      weaponShare: stored.weaponShare === undefined ? 0.2 : stored.weaponShare,
      /* Whether this tab listens to the game. Off, the character is the class
         as it rolls; on, it is whoever the party holds, watched. */
      source: stored.source || (TRAINER ? "game" : "hand"),
      /* Which slot of the party is being planned. The slot is the identity: a
         character can be renamed, and two can carry the same name. */
      who: stored.who === undefined ? null : stored.who,
      weapon: settings.weapon || "one_handed",
      spare: settings.spare,
      poolThrough: settings.poolThrough || 0,
      pinned: new Set(POLICIES.filter((k) => stored[k] !== null
                                             && stored[k] !== undefined)),
    };
    plan.character = (plan.source === "game" && planCharacter)
      || byHand(plan.code, 1, plan.weapon, plan.armorShare, plan.weaponShare);
    if (settings.attacksWith && canDoEither(classAt(plan.character.code))) {
      plan.character = Object.assign({}, plan.character,
                                     { casts: settings.attacksWith === "casting" });
    }
    // The charisma policy runs while a point could still buy a payout: past
    // the last step of the staircase it buys nothing. Where it stops below
    // that is charismaStop's answer, not a number stated here.
    plan.topUpCharisma = plan.character.charisma < CHARISMA_TOP;
    // A choice this character cannot use is not a choice: a mage offered
    // strength would be offered a point that buys it nothing.
    const routes = spareRoutes(plan).map(([value]) => value);
    if (!routes.includes(plan.spare)) plan.spare = routes[0];
    return plan;
  }

  function planState() {
    const stored = ui.plan || {};
    const settings = {};
    for (const key of POLICIES) {
      settings[key] = stored[key] === undefined ? null : stored[key];
    }
    return buildPlan(stored, fitPolicies(stored, settings));
  }

  /**
   * Where leftover points can usefully go, for this character.
   *
   * The pool attribute is not among them, at any level. Points are left over
   * once the goals have what they need, which is late, and the pool is not
   * retroactive: a point of intelligence adds to the pool at every training
   * still to come, so one bought at level 5 is worth about ten magic and the
   * same point at 35 is worth one. It is bought at the start of a career or it
   * is not worth buying, which is what the pool field is for.
   */
  function spareRoutes(plan) {
    if (!plan.character.casts) {
      return [["strength", "Strength"], ["attack", "Weapon skill"]];
    }
    return [["attack", "Casting"], ["dexterity", "Dexterity"]];
  }

  const savePlan = (changes) => {
    ui.plan = Object.assign({}, ui.plan || {}, changes);
  };

  function renderPlanner(root) {
    root.textContent = "";
    const plan = planState();

    root.append(characterBox(root, plan), goalBox(root, plan),
                careerBox(root, plan));
    watchParty(root, plan);
  }

  /** Who is being planned. */
  function characterBox(root, plan) {
    const c = plan.character;
    const box = el("div");
    const heading = el("div", { className: "plan-heading" });
    heading.append(el("h4", { className: "curve-sub", textContent: "Character" }));
    box.append(heading);

    /* Where the character comes from, when there is a game to take one out of.
       The party is read on the press rather than polled: a sheet does not move
       while you are planning against it, and a tab that re-read it every second
       would fight with the fields underneath. */
    /* Read out of the game, or built here. One button carrying its own state,
       beside the heading it belongs to, with the party it reads next to it. */
    if (TRAINER) {
      const live = plan.source === "game";
      const toggle = el("button", { type: "button", className: "toggle plan-source",
                                    textContent: live ? "Game" : "Hand" });
      toggle.setAttribute("aria-pressed", String(live));
      toggle.setAttribute("aria-label", "Character source");
      toggle.onclick = () => {
        if (live) planCharacter = null;
        savePlan({ source: live ? "hand" : "game" });
        renderPlanner(root);
      };
      heading.append(toggle);

      const who = el("select", { className: "picker plan-who" });
      who.setAttribute("aria-label", "Party");
      for (const person of planParty) {
        who.append(el("option", { value: String(person.slot),
                                  textContent: titleCase(person.name) }));
      }
      if (c.source === "game") who.value = String(c.slot);
      who.hidden = !live || !planParty.length;
      who.onchange = () => {
        const person = planParty.find((p) => String(p.slot) === who.value);
        if (!person) return;
        planCharacter = fromParty(person);
        savePlan({ who: person.slot });
        renderPlanner(root);
      };
      heading.append(who);
      planNote = el("span", { className: "note plan-note" });
      heading.append(planNote);
    }

    /* One field per setting, each under its own name. */
    const fields = el("div", { className: "plan-fields" });
    const field = (label, control) => {
      const wrap = el("label", { className: "plan-field" });
      wrap.append(el("span", { textContent: label }), control);
      fields.append(wrap);
      return control;
    };

    const picker = el("select", { className: "picker plan-class" });
    for (const cls of PLAN.classes) {
      picker.append(el("option", { value: String(cls.code),
                                  textContent: titleCase(cls.name) }));
    }
    picker.value = String(c.code);
    picker.disabled = c.source === "game";
    picker.onchange = () => {
      /* A new class comes with its own default route rather than inheriting
         the last one's: a paladin set to the weapon must not quietly make the
         next mage swing one. */
      savePlan({ code: Number(picker.value), attacksWith: null, spare: null });
      renderPlanner(root);
    };
    field("Class", picker);

    /* An archetype is a character, not a goal: it names a build the strategy
       guide prices, and what it puts in the goal list is how that build is
       recognized. Edit any row and the plan is no longer that build, which the
       list says by falling to Custom. */
    const archetype = el("select", { className: "picker plan-archetype" });
    const matches = (key) => {
      const want = archetypeGoals(key);
      return want.length === plan.goals.length
        && want.every((g, i) => g.type === plan.goals[i].type
                                && g.from === plan.goals[i].from
                                && g.target === plan.goals[i].target
                                && plan.goals[i].on);
    };
    const named = ARCHETYPES.find(([key]) => matches(key));
    for (const [key, label] of ARCHETYPES) {
      archetype.append(el("option", { value: key, textContent: label }));
    }
    if (!named) archetype.append(el("option", { value: "", textContent: "Custom" }));
    archetype.value = named ? named[0] : "";
    archetype.onchange = () => {
      const found = ARCHETYPES.find(([key]) => key === archetype.value);
      if (!found) return;
      savePlan({ archetype: found[0], goals: archetypeGoals(found[0]),
                 weapon: found[2] });
      renderPlanner(root);
    };
    field("Archetype", archetype);

    /* One control a policy, each carrying its own state: Auto is the default
       and names what the planner chose, and picking a value pins it. Nothing
       appears or disappears -- a field that only exists once you have overruled
       it is a field you cannot find to overrule. */
    const policyField = (label, key, value, options) => {
      const select = el("select", { className: `picker ${POLICY_CLASS[key]}` });
      const shown = options.find(([v]) => String(v) === String(value));
      select.append(el("option", { value: "",
                                   textContent: `Auto · ${shown ? shown[1] : "\u2014"}` }));
      for (const [option, text] of options) {
        select.append(el("option", { value: String(option), textContent: text }));
      }
      select.value = plan.pinned.has(key) ? String(value) : "";
      select.onchange = () => {
        const picked = select.value === "" ? null
          : (typeof value === "number" ? Number(select.value) : select.value);
        savePlan({ [key]: picked });
        renderPlanner(root);
      };
      field(label, select);
    };

    policyField("Weapon", "weapon", plan.weapon,
                [["one_handed", "One-handed and shield"],
                 ["two_handed", "Two-handed"]]);

    if (canDoEither(classAt(c.code))) {
      policyField("Attack", "attacksWith", c.casts ? "casting" : "weapon",
                  [["weapon", "Weapon"], ["casting", "Casting"]]);
    }

    /* How long the pool is fed. It compounds, so it is bought from the first
       training or not at all; none is not at all. */
    if (classAt(c.code).magic_blend.length) {
      policyField("Pool through", "poolThrough", plan.poolThrough,
                  policyCandidates(plan, "poolThrough")
                    .map((n) => [n, n ? `Level ${n}` : "None"]));
    }

    /* Where a training's points go once every goal has what it needs. They go
       somewhere: the screen does not close with any in hand. */
    policyField("Spare points", "spare", plan.spare, spareRoutes(plan));
    box.append(fields);

    /* What that choice is worth, against the two ways of getting it wrong.
       Closed by default: each row is a career walked under that policy. */
    if (classAt(c.code).magic_blend.length) {
      const cost = el("details", { className: "curve-box plan-pool-box" });
      cost.open = !!ui.planPool;
      cost.addEventListener("toggle", () => { ui.planPool = cost.open; });
      cost.append(el("summary", { textContent: "Pool cost" }));
      const body = el("div", { className: "curve-body" });
      const table = el("table", { className: "tiers plan-pool-table" });
      table.append(el("thead", {}, el("tr", {},
        ["Pool through", "Magic at 40", "Casts", "Dead levels"]
          .map((t) => el("th", { scope: "col", textContent: t })))));
      const rows = el("tbody");
      for (const row of poolComparison(plan)) {
        const tr = el("tr", { className: row.here ? "plan-here" : "" });
        tr.append(el("th", { scope: "row",
                             textContent: row.through ? String(row.through) : "None" }));
        for (const value of [row.magic, row.casts, row.dead]) {
          tr.append(el("td", { textContent: String(value) }));
        }
        rows.append(tr);
      }
      table.append(rows);
      body.append(table);
      body.append(el("p", { className: "note", textContent:
        `A dead level is one from ${DEAD_FROM} up where nothing you know kills `
        + "the toughest thing of your level in one cast. Casts are of the "
        + "largest spell you would throw. Every level spent widening the pool "
        + "is a level not spent on the casting that makes it land, and the "
        + "pool is not retroactive: a point is worth what the trainings after "
        + "it make of it." }));
      cost.append(body);
      box.append(cost);
    }

    const switches = el("div", { className: "plan-switches" });
    const bosses = el("input", { type: "checkbox", id: "plan-bosses" });
    bosses.checked = plan.bosses;
    bosses.onchange = () => { savePlan({ bosses: bosses.checked }); renderPlanner(root); };
    switches.append(el("label", { className: "plan-switch" },
                       [bosses, document.createTextNode("Bosses")]));
    box.append(switches);

    /* What the character is, in the numbers the goals read. Shown rather than
       typed: with the trainer these came out of the game, and by hand they are
       what the class rolls at the cap and what the gold affords by the level. */
    const sheet = el("dl", { className: "stats plan-sheet" });
    /* Only a character out of the game has a level to state, and it is a fact
       about it rather than a setting: one built here is the class as it rolls,
       planned from the first training, because points cannot be banked. */
    const shown = c.source === "game" ? [["Level", c.level]] : [];
    shown.push(["Accuracy", c.accuracy], ["Damage", c.damage],
                ["Absorption", c.absorption], ["Dexterity", c.dexterity],
                ["Health", c.health], ["Charisma", c.charisma]);
    if (c.casting) shown.push(["Casting", c.casting]);
    if (c.magic) shown.push(["Magic", c.magic]);
    /* Each name and its value are one cell, so a narrow panel wraps between
       pairs rather than between a label and the number it belongs to. */
    for (const [label, value] of shown) {
      sheet.append(el("div", {}, [
        el("dt", { textContent: label }),
        el("dd", { className: `plan-${label.toLowerCase()}`,
                   textContent: String(value) })]));
    }
    box.append(sheet);
    return box;
  }

  let planParty = [];

  /**
   * The party, watched rather than fetched.
   *
   * The trainer's tab reads the game every 700ms because what it shows is a
   * fight in progress. A plan changes when the character does -- a training, a
   * piece of armor, a point spent -- which is minutes apart, so this reads at a
   * fraction of that rate and redraws only when the numbers it planned against
   * have actually moved. Redrawing on a tick that changed nothing would take
   * the field being edited away mid-edit.
   */
  const PLAN_TICK = 4000;
  let planTimer = null;

  function watchParty(root, plan) {
    clearInterval(planTimer);
    if (!TRAINER || !emulator || plan.source !== "game") return;
    const tick = async () => {
      if (!root.isConnected || root.hidden) { clearInterval(planTimer); return; }
      try {
        const { party } = await anchor();
        planParty = party;
        /* The character being planned, then the slot the last visit left, then
           the first slot. A slot this party does not fill falls through. */
        const known = planCharacter ? planCharacter.slot : plan.who;
        const person = party.find((p) => p.slot === known) || party[0];
        if (!person) return;
        const next = fromParty(person);
        if (planNote) planNote.textContent = "";
        if (JSON.stringify(next) === JSON.stringify(planCharacter)) return;
        planCharacter = next;
        renderPlanner(root);
      } catch (e) {
        if (planNote) {
          planNote.textContent = e.waiting ? "Waiting for the game\u2026" : e.message;
        }
      }
    };
    planTimer = setInterval(tick, PLAN_TICK);
    tick();
  }

  /**
   * What stopping the pool earlier or later is worth, for this character.
   *
   * The two ends of section 7 of the strategy guide, computed rather than
   * quoted: buying the pool longer widens it, and every level spent buying it
   * is a level not spent on casting, which is what makes the spell land. A
   * dead level is one where nothing the character knows kills a monster of
   * its own level in one cast, and the fallback there is a level-1 spell and
   * twenty casts.
   *
   * Each row is a whole career walked under that policy, so this is behind a
   * disclosure rather than computed on every keystroke.
   */
  function poolComparison(plan) {
    const stops = [...new Set([0, 8, 12, 16, 20, plan.poolThrough])]
      .filter((n) => n === 0 || n >= plan.character.level)
      .sort((a, b) => a - b);
    const active = plan.goals.filter((g) => g.on && GOALS[g.type]);
    return stops.map((through) => {
      const trial = Object.assign({}, plan, { poolThrough: through });
      const rows = walk(trial);
      const last = rows[rows.length - 1];
      /* Counted from level 12, where a caster first has a spell worth the
         question. Below it nothing kills a monster of its level in one cast
         whatever the pool, so counting those levels would say the same thing
         about every policy. */
      let dead = 0, cost = 0;
      for (const row of rows) {
        const cast = bestCast(trial, row.me, row.at);
        if (cast) cost = cast.spell.mp;
        if (row.level < DEAD_FROM) continue;
        if (!cast || cast.landed < row.at.health.value) dead += 1;
      }
      return {
        through,
        magic: last.me.magic,
        casts: cost ? Math.floor(last.me.magic / cost) : 0,
        dead,
        here: through === plan.poolThrough,
      };
    });
  }

  /** The goals, in the order they are paid for. */
  function goalBox(root, plan) {
    const box = el("div");
    box.append(el("h4", { className: "curve-sub", textContent: "Goals" }));

    const table = el("table", { className: "tiers plan-goals" });
    table.append(el("thead", {}, el("tr", {},
      ["", "#", "Goal", "From", "Target", "Buys", ""]
        .map((t) => el("th", { scope: "col", textContent: t })))));
    const body = el("tbody");

    plan.goals.forEach((g, i) => {
      const goal = GOALS[g.type];
      const tr = el("tr");

      const on = el("input", { type: "checkbox" });
      on.checked = g.on;
      on.setAttribute("aria-label", goal.label);
      on.onchange = () => changeGoal(root, plan, i, { on: on.checked });
      tr.append(el("td", {}, [on]));
      /* The number the career's column is headed with. */
      tr.append(el("td", { className: "plan-key", textContent: String(i + 1) }));
      tr.append(el("td", { textContent: goal.label }));

      const from = el("input", { type: "number", min: "1", max: String(CAP),
                                 className: "trainer-num plan-from",
                                 value: String(g.from) });
      from.setAttribute("aria-label", "from level");
      from.onchange = () => changeGoal(root, plan, i, {
        from: Math.max(1, Math.min(CAP, Number(from.value) | 0)) });
      tr.append(el("td", {}, [from]));

      // A target is a percentage for the two goals that read the odds curve, a
      // plain number for the pool and for how many are focus-firing, and
      // nothing at all for the goals that are a threshold in themselves.
      const cell = el("td");
      if (goal.target) {
        const spec = goal.target;
        const percent = spec.kind === "percent";
        const input = el("input", { type: "number", min: "0",
                                    max: percent ? "100" : "",
                                    className: "trainer-num plan-target",
                                    value: String(percent
                                      ? Math.round(g.target * 100) : g.target) });
        input.setAttribute("aria-label", `${goal.label} target`);
        input.onchange = () => {
          const raw = Number(input.value);
          changeGoal(root, plan, i, {
            target: percent ? Math.max(0, Math.min(100, raw)) / 100
              : Math.max(0, raw),
          });
        };
        cell.append(input, el("span", { className: "note",
                                        textContent: ` ${spec.label}` }));
      } else {
        cell.append(el("span", { className: "note", textContent: "—" }));
      }
      tr.append(cell);
      tr.append(el("td", { className: "note",
                           textContent: LEVER_LABEL[leverOf(goal, plan)] }));

      const buttons = el("td", { className: "plan-buttons" });
      const move = (label, by, disabled) => {
        const b = el("button", { type: "button", className: "toggle",
                                 textContent: label });
        b.setAttribute("aria-label", by < 0 ? "Pay for this one first"
          : "Pay for this one later");
        b.disabled = disabled;
        b.onclick = () => moveGoal(root, plan, i, by);
        return b;
      };
      const drop = el("button", { type: "button", className: "toggle",
                                  textContent: "×" });
      drop.setAttribute("aria-label", "Remove this goal");
      drop.onclick = () => {
        const goals = plan.goals.slice();
        goals.splice(i, 1);
        savePlan({ goals });
        renderPlanner(root);
      };
      buttons.append(move("↑", -1, i === 0),
                     move("↓", 1, i === plan.goals.length - 1), drop);
      tr.append(buttons);
      body.append(tr);
    });
    table.append(body);
    box.append(table);

    const add = el("div", { className: "picker-row" });
    const pick = el("select", { className: "picker plan-add" });
    pick.setAttribute("aria-label", "Goal to add");
    // A goal already in the list is not one to add. It stays visible so the
    // list of what the tab can do does not change shape as goals are added,
    // and a second copy of a goal is not something to offer.
    const already = new Set(plan.goals.map((g) => g.type));
    for (const [key, goal] of Object.entries(GOALS)) {
      const option = el("option", { value: key, textContent: goal.label });
      option.disabled = already.has(key);
      pick.append(option);
    }
    const first = [...pick.options].find((o) => !o.disabled);
    if (first) pick.value = first.value;
    const button = el("button", { type: "button", className: "toggle",
                                  textContent: "Add" });
    // Nothing left to add once every goal is in the list.
    button.disabled = !first;
    button.onclick = () => {
      savePlan({ goals: plan.goals.concat(
        [goalFrom(pick.value, plan.character.level)]) });
      renderPlanner(root);
    };
    add.append(pick, button);
    box.append(add);
    return box;
  }

  function changeGoal(root, plan, i, changes) {
    savePlan({ goals: plan.goals.map(
      (g, j) => (j === i ? Object.assign({}, g, changes) : g)) });
    renderPlanner(root);
  }

  function moveGoal(root, plan, i, by) {
    const goals = plan.goals.slice();
    const [g] = goals.splice(i, 1);
    goals.splice(i + by, 0, g);
    savePlan({ goals });
    renderPlanner(root);
  }

  /** The answer: every level from where the character stands to the cap. */
  function careerBox(root, plan) {
    const box = el("div");
    box.append(el("h4", { className: "curve-sub", textContent: "Career" }));

    const active = plan.goals.filter((g) => g.on);
    if (!active.length) {
      box.append(el("p", { className: "empty", textContent: "No goals" }));
      return box;
    }

    const rows = walk(plan);
    const lines = el("div", { className: "plan-summary" });
    summary(plan, rows, active).forEach((line, i) => {
      const row = el("span", { className: line.held ? "plan-holds" : "plan-fails" });
      row.append(el("span", { className: "plan-key", textContent: String(i + 1) }),
                 document.createTextNode(`${line.held ? "✓" : "✗"} ${line.text}`));
      lines.append(row);
    });
    box.append(lines);

    const evidence = el("button", { type: "button",
                                    className: "toggle plan-evidence",
                                    textContent: "Evidence" });
    evidence.setAttribute("aria-pressed", String(plan.evidence));
    evidence.onclick = () => {
      savePlan({ evidence: !plan.evidence });
      renderPlanner(root);
    };
    box.append(el("div", { className: "chipbar" }, [evidence]));
    box.append(el("div", { className: "plan-legend" }, [
      el("span", { className: "plan-legend-name", textContent: "Key" }),
      el("span", { textContent: "✗ n — points short" }),
      el("span", { textContent: "✗ ∞ — out of reach" }),
    ]));

    const table = el("table", { className: "tiers plan-career" });
    const head = el("tr");
    head.append(el("th", { scope: "col", textContent: "Level" }));
    /* A goal's column holds one glyph, so heading it with the goal's name sets
       the column's width to the name: "Condition proof" is a hundred and fifty
       pixels to hold a tick, and a plan with several of those does not fit
       beside the game. The number is what the summary above lists it as. */
    active.forEach((g, i) => {
      const th = el("th", { scope: "col", className: "plan-goal-col",
                            textContent: String(i + 1) });
      th.title = GOALS[g.type].describe(g.target);
      head.append(th);
    });
    head.append(el("th", { scope: "col", textContent: "Points" }),
                el("th", { scope: "col", textContent: "Spend" }));
    table.append(el("thead", {}, head));

    const body = el("tbody");
    for (const row of rows) {
      const tr = el("tr", { dataset: { level: String(row.level) } });
      tr.append(el("th", { scope: "row", textContent: String(row.level) }));
      for (const g of active) {
        const result = row.results.find((r) => r.goal === g);
        tr.append(el("td", { className: `plan-${result.state}` },
                    [verdict(result)]));
      }
      // The level the character stands at has no training in it: a character
      // is created at level 1 and the first training takes it to 2, so the
      // first row is where it is rather than something it was granted.
      tr.append(el("td", { className: "note",
                           textContent: row.grant ? String(row.grant) : "—" }));
      // Two goals can buy the same lever at one level, and what the player
      // does at the trainer is one purchase, so they are added up rather than
      // listed twice.
      const buys = new Map();
      for (const [lever, n] of row.spent) {
        buys.set(lever, (buys.get(lever) || 0) + n);
      }
      /* Short names here and the full ones in the Buys column of the goal
         table above: this column is a line of instructions per level and the
         panel beside the game is narrow. */
      tr.append(el("td", { className: "note", textContent: buys.size
        ? [...buys].map(([lever, n]) => `${LEVER_SHORT[lever]} +${n}`).join(", ")
        : "—" }));
      body.append(tr);
      // A level where every goal is still ahead of the character has nothing
      // to show its working for, and an empty row under it would read as one.
      if (plan.evidence) {
        const working = evidenceRow(plan, row, active);
        if (working) body.append(working);
      }
    }
    table.append(body);
    // A column a goal, so the table is as wide as the plan is ambitious. In
    // the cabinet's frame that is wider than the panel, so it scrolls in its
    // own column rather than pushing the page sideways -- the same wrapper the
    // guides put round their wide tables.
    box.append(el("div", { className: "md-table-wrap" }, [table]));
    return box;
  }

  // Held, short by so many points, or out of reach at any price. The legend
  // beside the table carries those two meanings so the cells do not have to.
  function verdict(result) {
    if (result.state === "later") {
      return el("span", { className: "note", textContent: "—" });
    }
    if (result.state === "held") return document.createTextNode("✓");
    if (result.state === "short") {
      return document.createTextNode(`✗ ${result.short}`);
    }
    if (result.state === "missed") return document.createTextNode("✗");
    return document.createTextNode("✗ ∞");
  }

  /** What each goal was measured against here, and by which numbers. */
  function evidenceRow(plan, row, active) {
    const tr = el("tr", { className: "plan-evidence-row" });
    const cell = el("td", { colSpan: String(active.length + 3) });
    /* The working wraps inside a box of its own rather than laying every goal
       out on one line: eight of them side by side made a row wider than any
       window, and a table is as wide as its widest cell. */
    const working = el("div", { className: "plan-working" });
    let shown = 0;
    for (const g of active) {
      const result = row.results.find((r) => r.goal === g);
      if (result.state === "later") continue;
      const goal = GOALS[g.type];
      const block = el("div", { className: "plan-evidence-block" });
      /* The working says what the numbers are; the heading says which way they
         came out, in the same mark and color the row above uses, so a block
         read on its own is not a page of figures with no verdict. */
      const held = result.state === "held";
      block.append(el("strong", { className: held ? "plan-holds" : "plan-fails",
                                  textContent: `${held ? "\u2713" : "\u2717"} ${goal.describe(g.target)}` }));

      /* Yours on the left, what you are up against on the right, and the line
         that settles it across the bottom. A monster's name goes under the
         number it carries rather than beside it, where it would set the
         column's width. */
      const grid = el("div", { className: "plan-versus" });
      const side = (cell, which) => {
        if (!cell) return [el("span", {}), el("span", {})];
        const [label, value, monster, aside] = cell;
        const box = el("span", { className: `plan-${which}-value` },
                       [document.createTextNode(String(value))]);
        if (monster && monster.name) {
          box.append(el("span", { className: "note", textContent:
            `${titleCase(monster.name)} ${monster.level}` }));
        }
        if (aside) box.append(el("span", { className: "note", textContent: aside }));
        return [el("span", { className: "plan-label", textContent: label }), box];
      };
      /* Two headings, each over its own label-and-value pair: four columns. */
      grid.append(el("span", { className: "plan-column", textContent: "You" }),
                  el("span", { className: "plan-column", textContent: "Them" }));
      for (const entry of goal.rows(plan, result.me, row.at, g.target)) {
        if (entry.label === undefined) {
          grid.append(...side(entry.mine, "mine"), ...side(entry.theirs, "theirs"));
          continue;
        }
        /* The comparison the verdict turns on, across the width of the block
           and colored by which way it went. */
        const settled = el("span", {
          className: `plan-decides ${entry.ok ? "plan-holds" : "plan-fails"}` });
        settled.append(el("span", { className: "plan-label", textContent: entry.label }),
                       el("strong", { textContent: String(entry.value) }),
                       el("span", { className: "plan-needs",
                                    textContent: `needs ${entry.needs}` }));
        if (entry.monster && entry.monster.name) {
          settled.append(el("span", { className: "note", textContent:
            `${titleCase(entry.monster.name)} ${entry.monster.level}` }));
        }
        grid.append(settled);
      }
      block.append(grid);
      working.append(block);
      shown += 1;
    }
    if (!shown) return null;
    cell.append(working);
    tr.append(cell);
    return tr;
  }

  /** A goal and the levels it does not hold at, one line each. */
  function summary(plan, rows, active) {
    return active.map((g) => {
      const failed = rows.filter((r) => {
        const hit = r.results.find((x) => x.goal === g);
        return hit && hit.state !== "held" && hit.state !== "later";
      }).map((r) => r.level);
      const from = Math.max(g.from, plan.character.level);
      return {
        held: !failed.length,
        text: `${GOALS[g.type].describe(g.target)} · `
          + (failed.length ? `fails ${runs(failed)}` : `${from}\u2013${CAP}`),
      };
    });
  }

  /** A list of levels as runs: "26-29" rather than "26, 27, 28, 29". */
  function runs(levels) {
    const out = [];
    let start = null, last = null;
    for (const l of levels) {
      if (start === null) { start = last = l; continue; }
      if (l === last + 1) { last = l; continue; }
      out.push(start === last ? String(start) : `${start}\u2013${last}`);
      start = last = l;
    }
    if (start !== null) {
      out.push(start === last ? String(start) : `${start}\u2013${last}`);
    }
    return out.join(", ");
  }

  /* --- tabs ------------------------------------------------------------- */

  const TABS = [
    { key: "f1", label: "Maps", render: renderMaps },
    { key: "f2", label: "Monsters", render: renderMonsters },
    { key: "f3", label: "Spells", render: renderSpells },
    { key: "f5", label: "Items", render: renderItems },
    { key: "gd", label: "Guides", render: renderGuides },
    // The planner needs the model tables, which a panel built from an older
    // decode does not carry; without them the tab would be an error message.
    ...(PLAN ? [{ key: "pl", label: "Planner", render: renderPlanner }] : []),
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

    // Nothing here fires while a field has focus, so typing a monster's name
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
