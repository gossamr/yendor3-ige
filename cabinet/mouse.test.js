// The calibration retry schedule.
//
// Calibration parks the guest cursor at six positions and waits for the screen
// to settle first, so a failed attempt costs several seconds during which the
// cursor is not where the pointer is. It used to retry on a flat 4-second
// throttle measured from the *start* of an attempt, shorter than an attempt
// takes, so on a screen it could not read it ran again on every pointer
// entry, indefinitely.
import { expect, test } from "bun:test";

import { RETRY_BACKOFF, locateCursor, retryDelay } from "./mouse.js";

test("retries back off and then stop", () => {
  expect(retryDelay(1)).toBe(RETRY_BACKOFF[0]);
  // Each wait is longer than the one before it.
  for (let n = 2; n <= RETRY_BACKOFF.length; n++) {
    expect(retryDelay(n)).toBeGreaterThan(retryDelay(n - 1));
  }
  // And after the last one it gives up rather than asking forever.
  expect(retryDelay(RETRY_BACKOFF.length + 1)).toBeNull();
  expect(retryDelay(99)).toBeNull();
});

test("the first wait outlasts an attempt", () => {
  // quiet() allows 20 tries at 160ms, then each axis parks three probe pairs
  // at 450ms: about 3.2s before it can fail early, and about 8.6s if it runs
  // to the end. A delay shorter than that is not a delay at all.
  expect(retryDelay(1)).toBeGreaterThan(8600);
});

// The cursor is found in whatever the caller has to hand: an ImageData is four
// bytes to a pixel and the frame the emulator delivers is three. Reading the
// frame is what lets the painter be WebGL, whose buffer the page cannot read
// back.
const W = 40, H = 20;

/** A frame of `stride` bytes a pixel, with a bright 4x4 block at (x, y). */
const frame = (stride, x, y) => {
  const d = new Uint8Array(W * H * stride);
  if (x === null) return d;
  for (let dy = 0; dy < 4; dy++) {
    for (let dx = 0; dx < 4; dx++) {
      const i = ((y + dy) * W + x + dx) * stride;
      d[i] = d[i + 1] = d[i + 2] = 255;
    }
  }
  return d;
};

test("the cursor is found at the same place at either stride", () => {
  for (const stride of [3, 4]) {
    const found = locateCursor(frame(stride, 12, 5), frame(stride, null), W, H, 150, 0, stride);
    expect(found).not.toBeNull();
    expect([found.x, found.y]).toEqual([12, 5]);
  }
});

test("reading a stride of 4 as 3 finds the wrong place", () => {
  // Not a preference: it is why the stride is passed rather than assumed.
  const found = locateCursor(frame(4, 12, 5), frame(4, null), W, H, 150, 0, 3);
  expect(found === null || found.x !== 12 || found.y !== 5).toBe(true);
});

test("a frame that has not arrived yet is not a reading", () => {
  expect(locateCursor(null, frame(3, null), W, H, 150, 0, 3)).toBeNull();
  expect(locateCursor(frame(3, 12, 5), null, W, H, 150, 0, 3)).toBeNull();
});
