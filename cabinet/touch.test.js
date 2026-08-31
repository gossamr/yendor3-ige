import { describe, expect, test } from "bun:test";
import { Taps, keysForText, codeForLabel, DRAWER, STRIP,
         LONG_PRESS_MS, DOUBLE_TAP_MS, TAP_SLOP } from "./touch.js";
import { KEY_CODES } from "./keymap.js";
import { BUTTONS } from "./keys.js";

/** A Taps with a clock we turn by hand. */
function rig() {
  const out = [];
  let timers = [];
  const taps = new Taps((a) => out.push(a), {
    schedule: (fn, ms) => { const t = { fn, ms }; timers.push(t); return t; },
    cancel: (t) => { timers = timers.filter((x) => x !== t); },
  });
  const fire = () => { for (const t of timers.splice(0)) t.fn(); };
  return { taps, out, fire, pending: () => timers.length };
}

describe("a finger on the canvas", () => {
  test("a tap is a left click where the finger landed", () => {
    const { taps, out } = rig();
    taps.down({ id: 1, x: 10, y: 20, t: 0 });
    taps.up({ id: 1, x: 12, y: 21, t: 80 });
    expect(out).toEqual([{ type: "tap", x: 10, y: 20, button: BUTTONS.left, again: false }]);
  });

  test("a second tap on the same spot is the second click of a double click", () => {
    const { taps, out } = rig();
    taps.down({ id: 1, x: 10, y: 20, t: 0 });
    taps.up({ id: 1, x: 10, y: 20, t: 80 });
    taps.down({ id: 2, x: 14, y: 22, t: 200 });
    taps.up({ id: 2, x: 14, y: 22, t: 260 });
    expect(out[1]).toEqual({ type: "tap", x: 14, y: 22, button: BUTTONS.left, again: true });
    // And a third is a first again, not a triple.
    taps.down({ id: 3, x: 14, y: 22, t: 300 });
    taps.up({ id: 3, x: 14, y: 22, t: 360 });
    expect(out[2].again).toBe(false);
  });

  test("a tap late or far away is a new first tap", () => {
    const { taps, out } = rig();
    taps.down({ id: 1, x: 10, y: 20, t: 0 });
    taps.up({ id: 1, x: 10, y: 20, t: 80 });
    taps.down({ id: 2, x: 10, y: 20, t: 80 + DOUBLE_TAP_MS + 1 });
    taps.up({ id: 2, x: 10, y: 20, t: 80 + DOUBLE_TAP_MS + 60 });
    taps.down({ id: 3, x: 200, y: 20, t: 600 });
    taps.up({ id: 3, x: 200, y: 20, t: 650 });
    expect(out.map((a) => a.again)).toEqual([false, false, false]);
  });

  test("a finger that travels is a drag: motion, and no click on lifting", () => {
    const { taps, out, pending } = rig();
    taps.down({ id: 1, x: 10, y: 20, t: 0 });
    taps.move({ id: 1, x: 10 + TAP_SLOP + 1, y: 20, t: 50 });
    taps.move({ id: 1, x: 40, y: 20, t: 90 });
    taps.up({ id: 1, x: 40, y: 20, t: 120 });
    expect(out).toEqual([{ type: "move", x: 10 + TAP_SLOP + 1, y: 20 }, { type: "move", x: 40, y: 20 }]);
    expect(pending()).toBe(0);   // the long-press timer went with it
  });

  test("a small wobble is still a tap", () => {
    const { taps, out } = rig();
    taps.down({ id: 1, x: 10, y: 20, t: 0 });
    taps.move({ id: 1, x: 14, y: 22, t: 50 });
    taps.up({ id: 1, x: 14, y: 22, t: 120 });
    expect(out).toEqual([{ type: "tap", x: 10, y: 20, button: BUTTONS.left, again: false }]);
  });

  test("a finger held still presses the right button until it lifts", () => {
    const { taps, out, fire } = rig();
    taps.down({ id: 1, x: 10, y: 20, t: 0 });
    fire();
    expect(out).toEqual([{ type: "press", x: 10, y: 20, button: BUTTONS.right }]);
    taps.move({ id: 1, x: 30, y: 20, t: LONG_PRESS_MS + 50 });
    taps.up({ id: 1, x: 30, y: 20, t: LONG_PRESS_MS + 100 });
    expect(out.slice(1)).toEqual([{ type: "move", x: 30, y: 20 }, { type: "release", button: BUTTONS.right }]);
  });

  test("a second finger is a right click at the first", () => {
    const { taps, out } = rig();
    taps.down({ id: 1, x: 10, y: 20, t: 0 });
    taps.down({ id: 2, x: 100, y: 120, t: 40 });
    taps.up({ id: 2, x: 100, y: 120, t: 90 });
    taps.up({ id: 1, x: 10, y: 20, t: 110 });
    expect(out).toEqual([{ type: "tap", x: 10, y: 20, button: BUTTONS.right, again: false }]);
  });

  test("the R key arms one right click, or every one while held", () => {
    const { taps, out } = rig();
    taps.button = BUTTONS.right;
    taps.down({ id: 1, x: 1, y: 1, t: 0 });
    taps.up({ id: 1, x: 1, y: 1, t: 50 });
    taps.down({ id: 2, x: 90, y: 1, t: 500 });
    taps.up({ id: 2, x: 90, y: 1, t: 550 });
    expect(out.map((a) => a.button)).toEqual([BUTTONS.right, BUTTONS.left]);
    taps.holdButton = true;
    taps.down({ id: 3, x: 200, y: 1, t: 1000 });
    taps.up({ id: 3, x: 200, y: 1, t: 1050 });
    expect(out[2].button).toBe(BUTTONS.right);
  });

  test("a canceled hold lets go of the button", () => {
    const { taps, out, fire } = rig();
    taps.down({ id: 1, x: 10, y: 20, t: 0 });
    fire();
    taps.cancel({ id: 1, x: 10, y: 20, t: 600 });
    expect(out.at(-1)).toEqual({ type: "release", button: BUTTONS.right });
    expect(taps.active).toBeNull();
  });
});

describe("typing", () => {
  test("letters, capitals, digits, spaces and a newline become keys", () => {
    expect(keysForText("Ab 1\n")).toEqual([
      { code: "KeyA", shift: true },
      { code: "KeyB", shift: false },
      { code: "Space", shift: false },
      { code: "Digit1", shift: false },
      { code: "Enter", shift: false },
    ]);
  });

  test("a character with no key is dropped rather than sent as something else", () => {
    expect(keysForText("a-b!")).toEqual([
      { code: "KeyA", shift: false },
      { code: "KeyB", shift: false },
    ]);
  });
});

describe("the drawn keys", () => {
  test("every key the strip and drawer draw is one the keymap can send", () => {
    const codes = [
      ...STRIP.pad.flatMap((k) => k.keys),
      ...STRIP.actions.flatMap((k) => k.keys),
      ...STRIP.main.filter((k) => k.keys).flatMap((k) => k.keys),
      ...DRAWER.flat().map(codeForLabel),
      ...keysForText("azAZ09 \n").map((k) => k.code),
    ];
    for (const code of codes) expect(KEY_CODES[code], code).toBeDefined();
  });
});
