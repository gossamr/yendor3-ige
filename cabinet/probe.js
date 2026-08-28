// Log a cheap fingerprint of the framebuffer over time, so the boot sequence
// can be timed (how long each splash holds, when the menu appears) without
// writing and eyeballing dozens of screenshots.
import { loadEmulators, initFs, HEADLESS_ARGS } from "./boot.js";
import { KEYS, tap } from "./keys.js";

const arg = (n, d) => {
  const hit = process.argv.find((a) => a.startsWith(`--${n}=`));
  return hit === undefined ? d : hit.split("=").slice(1).join("=");
};
const seconds = Number(arg("seconds", 70));
const hammer = process.argv.includes("--hammer");

const emulators = await loadEmulators();
const ci = await emulators.dosboxNode(await initFs({
  sound: !process.argv.includes("--no-sound"),
  extra: arg("args", HEADLESS_ARGS),
  cycles: arg("cycles", "3000"),
}));
let frame = null;
ci.events().onFrame((rgb) => { if (rgb) frame = rgb; });

const t0 = Date.now();
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function sig() {
  if (!frame) return null;
  let r = 0, g = 0, b = 0, n = frame.length / 3;
  const seen = new Set();
  for (let i = 0; i < frame.length; i += 3) {
    r += frame[i]; g += frame[i + 1]; b += frame[i + 2];
    seen.add((frame[i] >> 4 << 8) | (frame[i + 1] >> 4 << 4) | (frame[i + 2] >> 4));
  }
  return { r: (r / n) | 0, g: (g / n) | 0, b: (b / n) | 0, colors: seen.size };
}

let prev = "";
while ((Date.now() - t0) / 1000 < seconds) {
  if (hammer) { await tap(ci, KEYS.esc, 40); await tap(ci, KEYS.space, 40); }
  await sleep(hammer ? 600 : 1000);
  const s = sig();
  if (!s) continue;
  const key = `${s.r},${s.g},${s.b},${s.colors}`;
  const t = ((Date.now() - t0) / 1000).toFixed(1).padStart(5);
  console.log(`${t}s  mean rgb(${String(s.r).padStart(3)},${String(s.g).padStart(3)},${String(s.b).padStart(3)})  colors=${String(s.colors).padStart(4)}${key === prev ? "" : "   <-- CHANGED"}`);
  prev = key;
}
await ci.exit();
process.exit(0);
