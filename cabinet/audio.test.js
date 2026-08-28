// The sample ring. Its fill level is the delay between the emulator and the
// speaker.
import { expect, test } from "bun:test";

import { Ring } from "./audio.js";

const fill = (ring, n, from = 0) =>
  ring.push(Float32Array.from({ length: n }, (_, i) => from + i));

test("a full ring drops new samples rather than unread ones", () => {
  const ring = new Ring(4);
  fill(ring, 6);
  expect(ring.length).toBe(4);
  const out = new Float32Array(4);
  ring.writeTo(out, 4);
  expect([...out]).toEqual([0, 1, 2, 3]);
});

test("drop discards the oldest samples and keeps the rest in order", () => {
  const ring = new Ring(8);
  fill(ring, 8);
  expect(ring.drop(3)).toBe(5);
  expect(ring.length).toBe(3);
  const out = new Float32Array(3);
  ring.writeTo(out, 3);
  expect([...out]).toEqual([5, 6, 7]);
});

test("drop follows the read pointer around the wrap", () => {
  const ring = new Ring(8);
  fill(ring, 8);
  ring.writeTo(new Float32Array(6), 6);   // read pointer now at 6
  fill(ring, 6, 8);                       // writes wrap past the end
  expect(ring.length).toBe(8);
  expect(ring.drop(2)).toBe(6);
  const out = new Float32Array(2);
  ring.writeTo(out, 2);
  expect([...out]).toEqual([12, 13]);
});

test("drop is a no-op when the ring is already below the level", () => {
  const ring = new Ring(8);
  fill(ring, 2);
  expect(ring.drop(5)).toBe(0);
  expect(ring.length).toBe(2);
});

test("drop(0) empties the ring", () => {
  const ring = new Ring(8);
  fill(ring, 5);
  ring.drop(0);
  expect(ring.length).toBe(0);
  const out = new Float32Array(2);
  ring.writeTo(out, 2);
  expect([...out]).toEqual([0, 0]);   // silence, not stale samples
});
