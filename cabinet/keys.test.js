// js-dos keeps its key codes as KBD_* constants baked into its bundle rather
// than exporting them, so keys.js and keymap.js transcribe the ones we use.
// These tests re-parse the bundle and fail if an upgrade moves a value.
import { expect, test } from "bun:test";
import { readFileSync } from "fs";
import { join } from "path";

import { KEYS, BUTTONS, DOM_BUTTONS } from "./keys.js";
import { KEY_CODES } from "./keymap.js";

const bundle = readFileSync(
  join(import.meta.dir, "node_modules/js-dos/dist/js-dos.js"), "utf8");

function jsDosKeys() {
  const out = {};
  for (const m of bundle.matchAll(/KBD_([A-Za-z0-9_]+):(\d+)/g)) {
    out[m[1]] = Number(m[2]);
  }
  return out;
}

const REF = jsDosKeys();

test("the bundle still defines a KBD_ table", () => {
  expect(Object.keys(REF).length).toBeGreaterThan(80);
});

test("every key we name matches js-dos, where js-dos names it", () => {
  const checked = [];
  for (const [name, code] of Object.entries(KEYS)) {
    if (REF[name] === undefined) continue;
    expect(`${name}=${code}`).toBe(`${name}=${REF[name]}`);
    checked.push(name);
  }
  expect(checked.length).toBeGreaterThan(30);
});

test("letters are uppercase ASCII", () => {
  expect(KEYS.a).toBe(65);
  expect(KEYS.z).toBe(90);
  expect(KEYS.a).toBe(REF.a);
});

// tab and the left-hand modifiers are absent from the bundle's own name table,
// so their codes are interpolated from the surrounding, named entries. tab was
// additionally confirmed by hand: pressing it in the emulator opens the game's
// Restoration help screen.
test("tab sits between enter and backspace", () => {
  expect(REF.enter).toBe(257);
  expect(REF.backspace).toBe(259);
  expect(KEYS.tab).toBe(258);
});

test("left modifiers mirror the named right-hand ones", () => {
  expect(REF.rightshift).toBe(344);
  expect(REF.rightctrl).toBe(345);
  expect(REF.rightalt).toBe(346);
  expect(KEY_CODES.ShiftLeft).toBe(REF.rightshift - 4);
  expect(KEY_CODES.ControlLeft).toBe(REF.rightctrl - 4);
  expect(KEY_CODES.AltLeft).toBe(REF.rightalt - 4);
});

test("browser keymap agrees with the emulator keymap", () => {
  const pairs = [
    ["Escape", "esc"], ["Space", "space"], ["Enter", "enter"], ["Tab", "tab"],
    ["ArrowUp", "up"], ["ArrowDown", "down"], ["ArrowLeft", "left"],
    ["ArrowRight", "right"], ["KeyA", "a"], ["F8", "f8"],
  ];
  for (const [browser, dos] of pairs) {
    expect(`${browser}=${KEY_CODES[browser]}`).toBe(`${browser}=${KEYS[dos]}`);
  }
});

// Mouse buttons are the same kind of transcription as the key codes, and the
// same kind of trap: the number reaches DOSBox's Mouse_ButtonPressed unchanged,
// and DOSBox numbers right 1 and middle 2 where a browser numbers them the
// other way round. Sending e.button through delivered every right-click as a
// middle-click, which the game ignores, so items and scrolls, which are used
// by right-clicking them, could not be used at all.
test("right is 1, as js-dos itself sends it", () => {
  // js-dos's own player normalizes the DOM button before sending it: any
  // non-left button becomes 1. Read that constant back out of the bundle so an
  // upgrade that changes it fails here rather than in the game.
  const m = bundle.match(/button:\s*0===\w+\.button\?0:(\d+)/);
  expect(m).not.toBeNull();
  expect(Number(m[1])).toBe(BUTTONS.right);
});

test("the DOM button order is not DOSBox's", () => {
  // MouseEvent.button: 0 left, 1 middle, 2 right.
  expect(DOM_BUTTONS[0]).toBe(BUTTONS.left);
  expect(DOM_BUTTONS[1]).toBe(BUTTONS.middle);
  expect(DOM_BUTTONS[2]).toBe(BUTTONS.right);
  expect(BUTTONS.right).not.toBe(2);
});

test("the game's documented hotkeys are all mappable", () => {
  // README.DOC lists these as the in-game controls.
  for (const k of ["a", "c", "d", "k", "m", "p", "r", "s", "t", "v"]) {
    expect(KEYS[k]).toBeGreaterThan(0);
  }
  for (const f of ["f1", "f2", "f3", "f4", "f5", "f8"]) {
    expect(KEYS[f]).toBe(REF[f]);
  }
});
