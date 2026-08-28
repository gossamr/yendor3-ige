// DOS key codes as js-dos defines them.
//
// js-dos ships these as KBD_* constants inside its bundle rather than as an
// importable module, so the ones we use are transcribed here. The test suite
// re-parses js-dos.js and fails if any value drifts, which is what keeps this
// honest across dependency upgrades.
export const KEYS = {
  // Letters are plain uppercase ASCII in js-dos's scheme, and the digit row is
  // plain ASCII too. The digits matter: the game's lists (save slots,
  // portraits, party members) are all picked by number, not by clicking.
  ...Object.fromEntries(
    "abcdefghijklmnopqrstuvwxyz".split("").map((c, i) => [c, 65 + i]),
  ),
  ...Object.fromEntries(
    "0123456789".split("").map((c, i) => [c, 48 + i]),
  ),
  esc: 256,
  space: 32,
  enter: 257,
  tab: 258,
  up: 265,
  down: 264,
  left: 263,
  right: 262,
  f1: 290,
  f2: 291,
  f3: 292,
  f4: 293,
  f5: 294,
  f6: 295,
  f8: 297,
};

// Mouse buttons as sendMouseButton() wants them.
//
// These are DOSBox's numbering, reaching Mouse_ButtonPressed() unchanged,
// and not the DOM's. A browser MouseEvent numbers the
// middle button 1 and the right button 2; DOSBox has those the other way
// round, so passing e.button through sends a right-click as a middle-click,
// which the game ignores. js-dos's own player normalizes for the same reason.
export const BUTTONS = { left: 0, right: 1, middle: 2 };

/** Browser MouseEvent.button -> the button sendMouseButton() wants. */
export const DOM_BUTTONS = [BUTTONS.left, BUTTONS.middle, BUTTONS.right];

/** Press and release a key, with a hold long enough for DOS to notice. */
export async function tap(ci, key, holdMs = 60) {
  ci.sendKeyEvent(key, true);
  await new Promise((r) => setTimeout(r, holdMs));
  ci.sendKeyEvent(key, false);
  await new Promise((r) => setTimeout(r, holdMs));
}

/**
 * Yendorian Tales opens with a chain of unskippable-looking splash screens
 * (SW Games, credits, title). Each advances on a keypress or click, so
 * hammering ESC/SPACE/ENTER walks through them without knowing how many
 * there are.
 */
export async function skipSplash(ci, rounds = 12) {
  for (let i = 0; i < rounds; i++) {
    await tap(ci, KEYS.esc);
    await tap(ci, KEYS.space);
    await tap(ci, KEYS.enter);
    ci.sendMouseButton(0, true);
    await new Promise((r) => setTimeout(r, 40));
    ci.sendMouseButton(0, false);
    await new Promise((r) => setTimeout(r, 400));
  }
}

/**
 * Park the DOS mouse cursor at a normalized position (0..1 across the screen).
 *
 * sendMouseMotion() does not move the cursor under the DOSBox backend: the
 * guest's mouse driver tracks its own position and only responds to motion
 * deltas. So home the cursor with an oversized negative delta, then step out
 * to the wanted position in pixels.
 *
 * The guest moves two pixels per unit of delta, in both of the video modes this
 * game uses (320x200 for its menus, 640x400 in the world), so the delta is half
 * the distance wanted. Without the halving every coordinate lands at twice its
 * fraction and anything past the middle of the screen pins to the right edge --
 * which is what made clicks on the save-slot list silently do nothing.
 */
export const MOUSE_SCALE = 2;

export async function moveTo(ci, x, y) {
  ci.sendMouseRelativeMotion(-4000, -4000);
  await new Promise((r) => setTimeout(r, 60));
  ci.sendMouseRelativeMotion(
    Math.round((x * ci.width()) / MOUSE_SCALE),
    Math.round((y * ci.height()) / MOUSE_SCALE),
  );
  await new Promise((r) => setTimeout(r, 120));
}

/**
 * Move to a normalized position (0..1 across the screen) and click.
 * Yendorian Tales is mouse-driven, its menus having no keyboard highlight,
 * so this is how the game actually gets navigated.
 */
export async function click(ci, x, y, button = 0) {
  await moveTo(ci, x, y);
  ci.sendMouseButton(button, true);
  await new Promise((r) => setTimeout(r, 90));
  ci.sendMouseButton(button, false);
  await new Promise((r) => setTimeout(r, 250));
}
