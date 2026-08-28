// The calibration retry schedule.
//
// Calibration parks the guest cursor at six positions and waits for the screen
// to settle first, so a failed attempt costs several seconds during which the
// cursor is not where the pointer is. It used to retry on a flat 4-second
// throttle measured from the *start* of an attempt, shorter than an attempt
// takes, so on a screen it could not read it ran again on every pointer
// entry, indefinitely.
import { expect, test } from "bun:test";

import { RETRY_BACKOFF, retryDelay } from "./mouse.js";

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
