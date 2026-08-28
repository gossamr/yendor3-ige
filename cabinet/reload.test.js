// The live-reload path rewrites the panel iframe's src. It used to write a
// fresh path, which dropped the `embed` flag the markup sets, so a rebuild
// brought the panel back wearing its own header inside the cabinet, on top of
// the cabinet's. The rule is that a reload changes the cache-buster and
// nothing else.
import { expect, test } from "bun:test";

// The same rewrite cabinet.js does, kept here as the thing under test.
function reloadSrc(current, base, now) {
  const url = new URL(current, base);
  url.searchParams.set("t", String(now));
  return url.pathname + url.search;
}

const BASE = "http://localhost:8080/";

test("a reload keeps every flag the markup set", () => {
  const out = reloadSrc("web/panel.html?embed=1", BASE, 1234);
  expect(out).toBe("/web/panel.html?embed=1&t=1234");
});

test("a reload replaces the cache-buster rather than stacking them", () => {
  const once = reloadSrc("web/panel.html?embed=1", BASE, 1);
  const twice = reloadSrc(BASE + once.slice(1), BASE, 2);
  expect(twice).toBe("/web/panel.html?embed=1&t=2");
  expect(twice.match(/t=/g)).toHaveLength(1);
});

test("a panel opened without flags stays without them", () => {
  expect(reloadSrc("web/panel.html", BASE, 7)).toBe("/web/panel.html?t=7");
});

test("cabinet.js uses the rewrite rather than a literal path", async () => {
  const src = await Bun.file(new URL("./cabinet.js", import.meta.url)).text();
  expect(src).not.toContain("`web/panel.html?t=");
  expect(src).toContain("url.searchParams.set(\"t\"");
});
