// The service worker: the cabinet with no network.
//
// Everything the page loads is kept as it is fetched, and served from the
// copy when the network does not answer. Network first, because a fetch that
// succeeds is the current build and the copy is only for when there is none:
// nothing has to be versioned or invalidated, and a deploy is live on the
// next load the way it always was.
//
// Hosted, the player's copy of the game is in IndexedDB already, put there
// when it was dropped, and the tables decoded from it beside it. Locally the
// server holds both, and they are kept like everything else so a local
// server that is down is something to be offline from. The live-reload
// stream is never kept: a cached event stream is a stream that never ends.
//
// Served at the site root by cabinet/serve.js and tools/build_pages.js, since
// a worker controls only what is under it.
const CACHE = "yendor-v1";

// game/ and its list are the development server's, which holds the game
// itself; a static host has neither, and answers 404 to both. Kept so that
// the development server is a fair offline test too.
const KEEP = /^\/(|index\.html|favicon\.ico|dosbox\.conf|decoder-files\.json|decoder-version\.json|game-files\.json|cabinet\/.*|web\/.*|emulators\/.*|pyodide\/.*|tools\/.*|game\/.*|data\/.*)$/;

// The shell, fetched by the worker itself as it installs. The first visit's
// own requests go out before the worker is in place to see them, so what
// that visit loaded would not be kept, and the next visit with no network
// would have no page to show. The emulator and the decoder are not here:
// they are large, and the page fetches them while the worker is watching.
const SHELL = [
  "./", "./index.html", "./favicon.ico", "./dosbox.conf",
  "./decoder-files.json", "./decoder-version.json",
  "./web/panel.html",
  "./cabinet/manifest.webmanifest", "./cabinet/icon.svg", "./cabinet/icon-192.png",
  "./cabinet/icon-512.png", "./cabinet/icon-maskable-512.png",
  "./cabinet/cabinet.css", "./cabinet/cabinet.js", "./cabinet/audio.js",
  "./cabinet/decode.js", "./cabinet/decode.worker.js", "./cabinet/dosbox.conf.js",
  "./cabinet/keymap.js", "./cabinet/keys.js", "./cabinet/mouse.js", "./cabinet/persist.js",
  "./cabinet/png.js", "./cabinet/roster.js", "./cabinet/touch.js", "./cabinet/trainer.js",
  "./cabinet/zip.js",
];

self.addEventListener("install", (e) => {
  e.waitUntil((async () => {
    const cache = await caches.open(CACHE);
    // One at a time and each on its own: a file that is not there on some
    // host, such as decoder-version.json on the development server, must
    // not stop the rest being kept.
    for (const file of SHELL) {
      try {
        const res = await fetch(file, { cache: "no-cache" });
        if (res.ok) await cache.put(new Request(new URL(file, location.href).href), res);
      } catch { /* kept on the next visit, when the page asks for it */ }
    }
    await self.skipWaiting();
  })());
});
self.addEventListener("activate", (e) => {
  e.waitUntil((async () => {
    for (const name of await caches.keys()) {
      if (name !== CACHE) await caches.delete(name);
    }
    await self.clients.claim();
  })());
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== location.origin) return;
  // The site may sit under a path prefix. The worker's own directory is it.
  const base = new URL("./", location.href).pathname;
  if (!url.pathname.startsWith(base)) return;
  const path = "/" + url.pathname.slice(base.length);
  if (!KEEP.test(path)) return;
  // The version stamp the page adds to the panel's URL is not part of what
  // the file is: dropped, so every load of the panel is one entry.
  const key = new Request(url.origin + url.pathname);
  e.respondWith((async () => {
    try {
      const fresh = await fetch(req);
      if (fresh.ok) {
        const cache = await caches.open(CACHE);
        cache.put(key, fresh.clone()).catch(() => {});
      }
      return fresh;
    } catch (err) {
      const kept = await caches.match(key);
      if (kept) return kept;
      throw err;
    }
  })());
});
