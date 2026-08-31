// Aligning the guest cursor with the host pointer.
//
// sendMouseMotion() does not take a 0..1 fraction of the screen on this
// backend. Measured against the running game, the response is linear but with
// roughly twice the expected slope and an origin near 0.44, and the exact
// constants shift with the video mode, so hardcoding them does not survive
// the game changing resolution.
//
// Two measured properties make a better approach possible. The response is
// linear, and it is a *pure function* of the value: sending the same value
// twice lands on the same pixel, and returning to an earlier value returns to
// the same place. So the mapping can be measured once by probing two known
// values per axis, reading the cursor back off the frame, and solving for the
// line. Inverting it then keeps the cursor under the pointer indefinitely --
// there is no drift to correct, which is why a one-off calibration is enough.

/** Brightness sum of one pixel in an ImageData buffer. */
const lum = (d, i) => d[i] + d[i + 1] + d[i + 2];

/**
 * Find the cursor in `a`, given `b` as a reference frame taken with the cursor
 * elsewhere. The arrow is bright against the game's darker backgrounds, so the
 * pixels much brighter in `a` than in `b` are the cursor. Its hotspot is the
 * tip, which is the top-left of that region.
 */
export function locateCursor(a, b, width, height, threshold = 150, floor = 0) {
  const xs = [], ys = [];
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const i = (y * width + x) * 4;
      // `floor` asks for pixels that are bright as well as brighter: the
      // tap's look passes it, so the reference frame's own cursor does not
      // show up as a ghost where its black outline was. Calibration does
      // not.
      if (lum(a, i) - lum(b, i) > threshold && lum(a, i) > floor) { xs.push(x); ys.push(y); }
    }
  }
  const count = xs.length;
  // The cursor sprite is a few dozen pixels. Anything much larger is the game
  // redrawing part of the screen, not the pointer.
  if (count < 8 || count > 600) return null;

  // The cursor is a small compact sprite. Take the median as a robust center,
  // then keep only the pixels near it: a stray highlight elsewhere in the
  // frame would otherwise drag a min or a mean right across the screen.
  const median = (v) => v.slice().sort((p, q) => p - q)[v.length >> 1];
  const cx = median(xs), cy = median(ys);
  const near = [];
  for (let i = 0; i < count; i++) {
    if (Math.abs(xs[i] - cx) <= 24 && Math.abs(ys[i] - cy) <= 24) near.push(i);
  }
  if (near.length < 8 || near.length > 200) return null;
  // The hotspot is the arrow's tip: the top-left of the compact blob.
  let minX = Infinity, minY = Infinity;
  for (const i of near) { if (xs[i] < minX) minX = xs[i]; if (ys[i] < minY) minY = ys[i]; }
  return { x: minX, y: minY, count: near.length, stray: count - near.length };
}

/**
 * Probe the mapping and return a transform from canvas pixels to the values
 * sendMouseMotion wants, or null if the cursor could not be found (which
 * happens on animated screens, where frame differencing is meaningless).
 */
/**
 * The mapping measured by hand against the running game, used when automatic
 * calibration cannot get a clean reading. Roughly right, in that the cursor
 * follows the pointer and reaches every part of the screen, but not pixel accurate.
 */
export function fallbackTransform(canvas) {
  // Origin and span measured against the running game; the two origins differ
  // slightly because the guest cursor sits a little right of and below the
  // pointer at a shared origin, and that residual was measured and removed.
  const SPAN = 0.5;
  const ORIGIN_X = 0.4175;
  const ORIGIN_Y = 0.4125;
  return {
    width: canvas.width,
    height: canvas.height,
    approximate: true,
    toSend: (px, py) => [
      ORIGIN_X + (px / canvas.width) * SPAN,
      ORIGIN_Y + (py / canvas.height) * SPAN,
    ],
  };
}

export async function calibrate(ci, canvas, ctx, { settle = 450 } = {}) {
  const { width, height } = canvas;
  const read = () => ctx.getImageData(0, 0, width, height).data;
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const park = async (x, y) => { ci.sendMouseMotion(x, y); await wait(settle); return read(); };

  // Probe values chosen to sit inside the responsive part of the range; below
  // about 0.44 the cursor is clamped against the left/top edge and two probes
  // there would give a slope of zero.
  const LOW = 0.50, MID = 0.70, HIGH = 0.90, HOLD = 0.7;

  // Frame differencing only means anything on a still screen, so wait for two
  // consecutive frames to agree before probing.
  const quiet = async (tries = 20) => {
    let last = read();
    for (let i = 0; i < tries; i++) {
      await wait(160);
      const now = read();
      let diff = 0;
      for (let j = 0; j < now.length; j += 4 * 53) {
        if (Math.abs(lum(now, j) - lum(last, j)) > 30) diff++;
      }
      last = now;
      if (diff < 3) return true;
    }
    return false;
  };

  const solve = async (axis) => {
    const at = (v) => (axis === "x" ? park(v, HOLD) : park(HOLD, v));
    const pick = (pt) => (axis === "x" ? pt.x : pt.y);
    const points = [];
    for (const v of [LOW, MID, HIGH]) {
      const here = await at(v);
      const away = await at(v === HIGH ? LOW : HIGH);   // reference elsewhere
      const found = locateCursor(here, away, width, height);
      if (found) points.push([v, pick(found)]);
    }
    if (points.length < 2) return null;
    // A real reading is monotonic: a larger value must put the cursor further
    // along the axis. Anything else means the differencing latched onto the
    // game redrawing rather than onto the cursor.
    for (let i = 1; i < points.length; i++) {
      if (points[i][1] <= points[i - 1][1]) return null;
    }
    const n = points.length;
    const sv = points.reduce((t, [v]) => t + v, 0);
    const sp = points.reduce((t, [, q]) => t + q, 0);
    const svp = points.reduce((t, [v, q]) => t + v * q, 0);
    const svv = points.reduce((t, [v]) => t + v * v, 0);
    const slope = (n * svp - sv * sp) / (n * svv - sv * sv);
    // Expect roughly twice the axis length per unit; anything far outside that
    // is not a believable measurement.
    const span = axis === "x" ? width : height;
    if (!isFinite(slope) || slope < span * 0.5 || slope > span * 6) return null;
    return { slope, intercept: (sp - slope * sv) / n, points };
  };

  if (!(await quiet())) return null;

  const x = await solve("x");
  const y = await solve("y");
  if (typeof console !== "undefined" && console.debug) {
    console.debug("calibrate " + JSON.stringify({ x, y, width, height }));
  }
  if (!x || !y) return null;
  return {
    width, height,
    /** Canvas pixel -> the value to send. */
    toSend: (px, py) => [(px - x.intercept) / x.slope, (py - y.intercept) / y.slope],
    detail: { x, y },
  };
}

// How long to wait before measuring again after a failed attempt, indexed by
// how many have failed in a row.
//
// An attempt is not free: it waits for the screen to hold still for up to
// three seconds, and if it gets that far it parks the guest cursor at six
// positions, so a run costs several seconds during which the cursor is not
// under the pointer. What makes one fail is an animated screen, and a screen
// that is animated now is likely to still be animated a moment later, so
// retrying on every pointer entry spends more time disturbing the cursor than
// the misalignment it is chasing. Back off instead, and after the last delay
// stop asking: the fallback mapping reaches every part of the screen, and
// `window.__cabinet.calibrate()` re-measures on demand.
export const RETRY_BACKOFF = [15000, 45000, 120000];

/** Milliseconds to wait after `failures` consecutive failures, or null to stop. */
export function retryDelay(failures) {
  return RETRY_BACKOFF[failures - 1] ?? null;
}
