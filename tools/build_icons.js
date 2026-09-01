// Rasterize cabinet/icon.svg into the PNGs a home screen wants.
//
//   bun tools/build_icons.js
//
// Four files: 192 and 512 pixels square for the manifest and the Apple touch
// icon, a maskable 512 with the wall carried out to the edge so a round or
// squircle mask cuts stone rather than the letter, and favicon.ico holding
// 16, 32 and 48 for the browsers and bookmarks that ask for that name. A
// browser draws them, because that is the one SVG rasterizer this repository
// already has.
import { chromium } from "playwright";
import { readFile, writeFile } from "fs/promises";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const svg = await readFile(`${ROOT}/cabinet/icon.svg`, "utf8");

const browser = await chromium.launch();
const page = await browser.newPage({ deviceScaleFactor: 1 });

/** Draw the icon at `size`, with the letter scaled to `inner` of it. */
async function render(size, inner, out) {
  const png = await draw(size, inner);
  if (out) {
    await writeFile(`${ROOT}/cabinet/${out}`, png);
    console.log(`${out}: ${size}x${size}`);
  }
  return png;
}

/** The icon at `size` as PNG bytes. */
async function draw(size, inner) {
  await page.setViewportSize({ width: size, height: size });
  // The wall repeats behind a smaller copy of the icon, so the margin a mask
  // needs is more wall rather than a border of another color.
  const cell = Math.round(size / 16);
  const pad = Math.round((size - size * inner) / 2);
  await page.setContent(`<!doctype html><style>
    html, body { margin: 0; width: ${size}px; height: ${size}px; overflow: hidden; }
    body { background: #343434 url("data:image/svg+xml,${encodeURIComponent(svg)}") 0 0 / ${cell * 16}px ${cell * 16}px; }
    body::before { content: ""; position: absolute; inset: 0; background: #1c1c1c;
                   opacity: ${inner < 1 ? 0 : 0}; }
    img { position: absolute; left: ${pad}px; top: ${pad}px;
          width: ${size - 2 * pad}px; height: ${size - 2 * pad}px;
          image-rendering: pixelated; }
  </style><img src="data:image/svg+xml,${encodeURIComponent(svg)}">`);
  return page.screenshot({ omitBackground: false });
}

/**
 * An ICO holding PNG images. The format is a six-byte header, a sixteen-byte
 * directory entry per image, then the images; every browser that asks for
 * favicon.ico reads PNG entries.
 */
function ico(images) {
  const head = Buffer.alloc(6);
  head.writeUInt16LE(0, 0); head.writeUInt16LE(1, 2); head.writeUInt16LE(images.length, 4);
  const dir = [];
  let offset = 6 + 16 * images.length;
  for (const { size, png } of images) {
    const e = Buffer.alloc(16);
    e.writeUInt8(size === 256 ? 0 : size, 0);   // width; 0 stands for 256
    e.writeUInt8(size === 256 ? 0 : size, 1);   // height
    e.writeUInt8(0, 2); e.writeUInt8(0, 3);     // no palette, reserved
    e.writeUInt16LE(1, 4); e.writeUInt16LE(32, 6);   // planes, bits
    e.writeUInt32LE(png.length, 8); e.writeUInt32LE(offset, 12);
    offset += png.length;
    dir.push(e);
  }
  return Buffer.concat([head, ...dir, ...images.map((i) => i.png)]);
}

await render(192, 1, "icon-192.png");
await render(512, 1, "icon-512.png");
await render(512, 0.72, "icon-maskable-512.png");
const small = [];
for (const size of [16, 32, 48]) small.push({ size, png: await draw(size, 1) });
await writeFile(`${ROOT}/cabinet/favicon.ico`, ico(small));
console.log("favicon.ico: 16, 32, 48");
await browser.close();
