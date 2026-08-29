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

  const hex = (v, w) => v.toString(16).padStart(w, "0");

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
