// The hooked emulator: js-dos's shim with a way to read and write guest memory.
//
// The transform lives here: taking the stock shim's source and returning the
// hooked source. Writing it to disk is tools/build_trainer.js; publishing it
// is tools/build_pages.js. Both do the same edit, so there is one definition
// of what "hooked" means. The names the page asks for are cabinet/trainer.js.
//
// The seam: the emulator's JavaScript is rewritten with a hook injected where
// `Module` is in scope, and `Module.HEAPU8` is the guest's RAM. It talks over a
// BroadcastChannel, which is same-origin and needs no reference, since js-dos owns
// the Worker object, not us, so the page cannot reach the worker's globals.
// That also reaches the clue-book iframe, which is where the trainer's panel
// lives.
//
// Structured clone moves about a gigabyte a second and the largest thing the
// trainer reads at once is the 12 KB monster table, so the channel is not the
// constraint and a SharedArrayBuffer would buy nothing, which matters,
// because one needs cross-origin isolation and a static host cannot provide it.
import { CHANNEL } from "../cabinet/trainer.js";

/** The hook, injected into the emulator's module scope. Exported for tests. */
export const HOOK = `
var __trainerModule = null;
function __trainerHook(mod) {
  __trainerModule = mod;
  var ch;
  try { ch = new BroadcastChannel(__CHANNEL__); } catch (e) { return; }
  ch.onmessage = function (e) {
    var m = e.data;
    if (!m || m.to !== "emulator") return;
    var heap = __trainerModule.HEAPU8;
    var reply = { to: "page", id: m.id };
    try {
      if (m.op === "peek") {
        reply.bytes = heap.slice(m.at, m.at + m.len);
      } else if (m.op === "poke") {
        for (var i = 0; i < m.bytes.length; i++) heap[m.at + i] = m.bytes[i] & 0xff;
        reply.wrote = m.bytes.length;
      } else if (m.op === "find") {
        // The search runs here, on the heap, so only the answer crosses. The
        // needle is text or raw bytes, and a search can be restricted to the
        // addresses an earlier one returned, which is how a field whose
        // address is unknown gets found: search for the value the game shows,
        // change it in the game, search again among what the first pass left.
        var want = m.bytes || [];
        if (!m.bytes) {
          for (var k = 0; k < m.needle.length; k++) want.push(m.needle.charCodeAt(k));
        }
        var out = [], total = 0, limit = m.limit || 32;
        var list = m.candidates || null;
        var n = list ? list.length : heap.length - want.length + 1;
        for (var i = 0; i < n; i++) {
          var at = list ? list[i] : i;
          if (at < 0 || at + want.length > heap.length) continue;
          var ok = true;
          for (var j = 0; j < want.length; j++) {
            if (heap[at + j] !== want[j]) { ok = false; break; }
          }
          if (!ok) continue;
          total++;
          if (out.length < limit) out.push(at);
          // A narrowed pass counts every survivor, since the list is short. An
          // unnarrowed one walks the whole heap and stops at the cap.
          else if (!list) break;
        }
        reply.found = out;
        reply.total = total;
      } else if (m.op === "ping") {
        reply.size = heap.length;
      } else {
        reply.error = "unknown op " + m.op;
      }
    } catch (err) {
      reply.error = String(err && err.message ? err.message : err);
    }
    ch.postMessage(reply);
  };
}
`;

/** The hooked source, ready to be written beside a copy of the wasm. */
export const trainerShim = (src, from) => hookShim(src, from);

// The hook goes in without its comments or whitespace. Names are kept: the
// shim calls `__trainerHook` by name, so a minifier that renamed it would
// leave the call dangling.
const compact = new Bun.Transpiler({ loader: "js", minifyWhitespace: true });

/**
 * The hooked source, from the stock shim's source.
 *
 * The marker is where js-dos hands the Module out; injecting after it means the
 * hook sees a Module that is already wired up. A shim without it is a js-dos
 * this was not written against, and saying so beats returning something that
 * loads and does nothing.
 */
export function hookShim(src, from = "the emulator") {
  const marker = 'Module["FS"]=FS;';
  if (!src.includes(marker)) throw new Error(`no FS export in ${from}`);
  const hook = compact.transformSync(HOOK.replace("__CHANNEL__", JSON.stringify(CHANNEL))).trim();
  return hook + "\n" + src.replace(marker, marker + "__trainerHook(Module);");
}
