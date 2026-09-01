// Static server for the cabinet.
//
// Serves the repository root so the page can pull the game files from game/,
// the panel from web/ and the emulator from cabinet/node_modules without any of
// them being copied. Two generated endpoints keep the browser build in step
// with the headless one: /game-files.json lists exactly the files boot.js
// sends to DOSBox, and /dosbox.conf is the same configuration object.
//
//   bun cabinet/serve.js [--port=8080]
import { watch } from "fs";
import { join, extname, resolve, normalize, basename } from "path";

import { dosboxConf } from "./dosbox.conf.js";
import {
  GAME_DIR, PATCHED_DIR, EMU_DIST, PYODIDE_DIST, PYODIDE_FILES,
  gameFiles, decoderFiles, decoderFingerprint, withoutComments,
} from "./boot.js";

const ROOT = resolve(import.meta.dir, "..");
const port = Number(
  (process.argv.find((a) => a.startsWith("--port=")) || "").split("=")[1] || 8080,
);

// Live reload. The panel is rendered in an iframe, so a rebuild can be picked
// up by reloading that frame alone: the emulator lives in the parent
// document and keeps running, so the game is not disturbed.
const clients = new Set();
// One debounce timer per event type. A single shared timer lets one kind of
// change mask another: a cabinet/ edit landing within the debounce window of a
// web/ edit replaced the pending "reload" with a "shell", and the panel iframe
// then never reloaded at all.
const pending = new Map();

function broadcast(event) {
  for (const send of clients) {
    try { send(event); } catch { clients.delete(send); }
  }
}

// Panel files reload the iframe alone. Shell files (this page's own markup,
// styles and script) need a full page reload, which would end the running
// game, so that is announced rather than done, and left to the user.
const WATCHED = { web: "reload", data: "reload", cabinet: "shell" };

// What the panel is served as, and what it is written in. panel.css and
// panel.js are *inlined* into panel.html by tools/build_panel.py, so the built
// file is the artifact and an edit to either source changes nothing that is
// served until it is rebuilt. Reloading the frame on that edit therefore
// re-served the same bytes, which looks exactly like a change that did not
// work. The server runs the build itself instead.
const PANEL_SOURCES = /^panel\.(js|css)$/;
const PYTHONS = [process.env.YENDOR_PY, join(ROOT, ".venv/bin/python"), "python3"]
  .filter(Boolean);
let building = null;

async function buildShell() {
  if (building) return building;
  building = (async () => {
    for (const python of PYTHONS) {
      try {
        const proc = Bun.spawn([python, "tools/build_panel.py", "--shell"], {
          cwd: ROOT,
          env: { ...process.env, PYTHONPATH: join(ROOT, "tools") },
          stdout: "pipe", stderr: "pipe",
        });
        if (await proc.exited === 0) return true;
        // A python that runs but cannot build says why; one that is not there
        // at all is the next candidate's turn.
        const why = (await new Response(proc.stderr).text()).trim();
        if (why) {
          console.warn(`panel rebuild failed:\n${why}`);
          return false;
        }
      } catch (err) { /* no such python; try the next */ }
    }
    console.warn("panel rebuild skipped: no python found."
      + " Set YENDOR_PY, or run `make panel-shell` after editing panel.js/css.");
    return false;
  })();
  const done = await building;
  building = null;
  return done;
}

for (const [dir, event] of Object.entries(WATCHED)) {
  try {
    watch(join(ROOT, dir), { recursive: true }, (_type, file) => {
      if (!file || !/\.(html|css|js|json)$/.test(file)) return;
      if (dir === "cabinet" && /node_modules/.test(file)) return;
      // The build writes panel.html, which arrives here as another web/ event.
      // Only the sources start a build, so the two cannot chase each other.
      const rebuild = dir === "web" && PANEL_SOURCES.test(basename(file));
      clearTimeout(pending.get(event));   // a rebuild touches several files
      pending.set(event, setTimeout(async () => {
        pending.delete(event);
        if (rebuild) await buildShell();
        broadcast(event);
      }, 150));
    });
  } catch (err) {
    console.warn(`not watching ${dir}/: ${err.message}`);
  }
}

const TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json",
  ".wasm": "application/wasm",
  ".zip": "application/zip",
  ".py": "text/x-python; charset=utf-8",
  ".png": "image/png",
  ".woff": "font/woff",
  ".webmanifest": "application/manifest+json",
  ".svg": "image/svg+xml",
  ".ico": "image/x-icon",
};

const server = Bun.serve({
  port,
  // Bind to all interfaces, not just loopback, so the cabinet can be opened from
  // another machine on the network.
  hostname: "0.0.0.0",
  async fetch(req) {
    const url = new URL(req.url);
    let path = decodeURIComponent(url.pathname);
    if (path === "/") path = "/cabinet/index.html";

    // The page itself, with its markup notes taken out.
    if (path === "/cabinet/index.html") {
      const html = await Bun.file(join(ROOT, "cabinet/index.html")).text();
      return new Response(withoutComments(html),
                          { headers: { "content-type": "text/html; charset=utf-8" } });
    }

    // The service worker, at the root: a worker controls what is under it
    // and nothing else, so one kept in cabinet/ would cover only cabinet/.
    if (path === "/sw.js") {
      return new Response(Bun.file(join(ROOT, "cabinet/sw.js")), {
        headers: { "content-type": TYPES[".js"], "cache-control": "no-store" },
      });
    }

    // Asked for at the root by name, by browsers and bookmarks that read no
    // link tag.
    if (path === "/favicon.ico") {
      return new Response(Bun.file(join(ROOT, "cabinet/favicon.ico")), {
        headers: { "content-type": TYPES[".ico"] },
      });
    }

    if (path === "/events") {
      let send;
      const stream = new ReadableStream({
        start(controller) {
          const enc = new TextEncoder();
          send = (msg) => controller.enqueue(enc.encode(`data: ${msg}\n\n`));
          send("connected");
          clients.add(send);
        },
        cancel() { clients.delete(send); },
      });
      return new Response(stream, {
        headers: {
          "content-type": "text/event-stream",
          "cache-control": "no-cache",
          connection: "keep-alive",
        },
      });
    }

    if (path === "/dosbox.conf") {
      return new Response(dosboxConf(), {
        headers: { "content-type": "text/plain; charset=utf-8" },
      });
    }
    // The decoder the browser runs when there is no game on the server. Both
    // of these are static on a Pages build, written by tools/build_pages.js;
    // here they are computed, so a module that grows an import is served
    // without anyone remembering to add it.
    if (path === "/decoder-files.json") {
      return new Response(JSON.stringify(await decoderFiles()), {
        headers: { "content-type": "application/json" },
      });
    }
    // Which build a decode came from. A static host has this as a file that
    // tools/build_pages.js wrote; here it is computed, so an edit to a decoder
    // invalidates a kept decode on the next reload with nothing to rebuild.
    if (path === "/decoder-version.json") {
      return new Response(JSON.stringify({ decoder: await decoderFingerprint() }), {
        headers: { "content-type": "application/json",
                   "cache-control": "no-store" },
      });
    }
    if (path.startsWith("/pyodide/")) {
      const name = path.slice("/pyodide/".length);
      // Serve the five the browser needs and nothing else, so the route
      // cannot be walked into the rest of node_modules.
      if (!PYODIDE_FILES.includes(name)) {
        return new Response("not found", { status: 404 });
      }
      return new Response(Bun.file(join(PYODIDE_DIST, name)), {
        headers: {
          "content-type": TYPES[extname(name)] || "application/octet-stream",
        },
      });
    }
    if (path === "/game-files.json") {
      const names = (await gameFiles()).map((f) => f.path);
      return new Response(JSON.stringify(names), {
        headers: { "content-type": "application/json" },
      });
    }
    // The emulator runtime. The page asks for it at /emulators/ because that
    // is where a static build puts it; here it still lives in node_modules,
    // and this is the one line that reconciles the two.
    if (path.startsWith("/emulators/")) {
      const name = path.slice("/emulators/".length);
      const file = Bun.file(join(EMU_DIST, name));
      if (!(await file.exists())) return new Response("not found", { status: 404 });
      return new Response(file, {
        headers: {
          "content-type": TYPES[extname(name)] || "application/octet-stream",
        },
      });
    }
    if (path.startsWith("/game/")) {
      const file = Bun.file(join(GAME_DIR, path.slice("/game/".length)));
      if (!(await file.exists())) return new Response("not found", { status: 404 });
      return new Response(file);
    }

    // Contain path traversal: resolve, then require the result to stay inside.
    const full = join(ROOT, normalize(path).replace(/^(\.\.[/\\])+/, ""));
    if (!full.startsWith(ROOT)) return new Response("forbidden", { status: 403 });
    const file = Bun.file(full);
    if (!(await file.exists())) return new Response("not found", { status: 404 });
    return new Response(file, {
      headers: {
        "content-type": TYPES[extname(full)] || "application/octet-stream",
        "cache-control": "no-store",
      },
    });
  },
});

console.log(`cabinet on http://localhost:${server.port}/  (also on 0.0.0.0, watching web/ and data/)`);
if ((await gameFiles()).length === 0) {
  // Not a misconfiguration when the cabinet is served publicly: there is no game
  // on the server, and each player supplies their own copy from the browser.
  console.log(`no game at ${GAME_DIR}; serving for players who bring their own`);
} else {
  console.log(`game from ${GAME_DIR}`);
  if (GAME_DIR !== PATCHED_DIR) {
    console.log("  not the patched build; expect the intro and the attract loop.");
    console.log("  `make patched` builds it; `make serve` builds it and serves it.");
  }
}
