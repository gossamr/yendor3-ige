// Touch input for the game: a finger on the canvas as a mouse, and on-screen
// keys for a keyboard the device does not have.
//
// The game is mouse-driven and expects three gestures a finger cannot make on
// its own: a right click, a double click, and a hold. So a touch is read as
// one of a few gestures and each is sent as the mouse events the game wants.
//
// Everything here that decides is a pure function of the events fed to it, so
// touch.test.js can run it without a screen. The DOM wiring is at the bottom.
import { KEY_CODES } from "./keymap.js";
import { BUTTONS } from "./keys.js";

/** A finger that travels further than this is dragging, not tapping. */
export const TAP_SLOP = 12;
/** A finger held still this long is a right click. */
export const LONG_PRESS_MS = 450;
/** A second tap within this, near the first, is the second half of a double
 *  click. */
export const DOUBLE_TAP_MS = 350;
export const DOUBLE_TAP_REACH = 32;

/**
 * Turn pointer events into mouse actions.
 *
 * Fed `down`, `move`, `up` and `cancel` with `{ id, x, y, t }` in canvas
 * pixels and milliseconds. Calls `emit` with:
 *
 *   { type: "move", x, y }               the finger is dragging: follow it
 *   { type: "tap", x, y, button, again } press and release at x, y. `again`
 *                                        is set when this tap lands where the
 *                                        last one did within DOUBLE_TAP_MS,
 *                                        which is the second click of a
 *                                        double click: the guest must see no
 *                                        motion between the two presses or the
 *                                        pair does not register.
 *   { type: "press", x, y, button }      a hold began: the button goes down
 *   { type: "release", button }          the hold ended
 *
 * A second finger put down while the first is held is a right click at the
 * first finger, the way two-finger tap works on a trackpad. A finger held
 * still for LONG_PRESS_MS presses the right button and keeps it down until the
 * finger lifts, so a right-button drag is possible too.
 *
 * `button` is what the next tap should send, set from outside by the on-screen
 * right-button key; it is read at the moment of the tap and then reset.
 */
export class Taps {
  constructor(emit, { schedule = (fn, ms) => setTimeout(fn, ms),
                      cancel = (t) => clearTimeout(t) } = {}) {
    this.emit = emit;
    this.schedule = schedule;
    this.clearTimer = cancel;
    this.button = null;          // BUTTONS.right when armed by the R key
    this.holdButton = false;     // the R key held down: every tap is right
    this.active = null;          // the finger being tracked
    this.last = null;            // the last tap, for double-tap detection
  }

  /** Which button the next tap sends, then disarm the one-shot. */
  takeButton() {
    const b = this.holdButton ? BUTTONS.right : (this.button ?? BUTTONS.left);
    this.button = null;
    return b;
  }

  down(p) {
    if (this.active) {
      // A second finger: right click at the first, and the first finger is
      // spent -- lifting it does nothing more.
      if (!this.active.moved && !this.active.held) {
        this.stopTimer();
        this.active.spent = true;
        this.emit({ type: "tap", x: this.active.x, y: this.active.y,
                    button: BUTTONS.right, again: false });
      }
      return;
    }
    this.active = { id: p.id, x: p.x, y: p.y, x0: p.x, y0: p.y, t0: p.t,
                    moved: false, held: false, spent: false };
    this.timer = this.schedule(() => this.hold(), LONG_PRESS_MS);
  }

  hold() {
    const a = this.active;
    if (!a || a.moved || a.spent) return;
    a.held = true;
    this.emit({ type: "press", x: a.x, y: a.y, button: BUTTONS.right });
  }

  move(p) {
    const a = this.active;
    if (!a || a.id !== p.id || a.spent) return;
    a.x = p.x; a.y = p.y;
    if (!a.moved && Math.hypot(p.x - a.x0, p.y - a.y0) > TAP_SLOP) {
      a.moved = true;
      this.stopTimer();
    }
    // Dragging follows the finger. So does a held right button.
    if (a.moved || a.held) this.emit({ type: "move", x: p.x, y: p.y });
  }

  up(p) {
    const a = this.active;
    if (!a || a.id !== p.id) return;
    this.stopTimer();
    this.active = null;
    if (a.spent) return;
    if (a.held) { this.emit({ type: "release", button: BUTTONS.right }); return; }
    if (a.moved) return;
    const again = !!this.last && p.t - this.last.t <= DOUBLE_TAP_MS
      && Math.hypot(a.x0 - this.last.x, a.y0 - this.last.y) <= DOUBLE_TAP_REACH;
    const button = this.takeButton();
    // A double tap is two taps and stops there: a third is a new first.
    this.last = again ? null : { x: a.x0, y: a.y0, t: p.t };
    this.emit({ type: "tap", x: a.x0, y: a.y0, button, again });
  }

  cancel(p) {
    const a = this.active;
    if (!a || a.id !== p.id) return;
    this.stopTimer();
    this.active = null;
    if (a.held) this.emit({ type: "release", button: BUTTONS.right });
  }

  stopTimer() {
    if (this.timer !== undefined) { this.clearTimer(this.timer); this.timer = undefined; }
  }
}

/**
 * The key presses that type a string.
 *
 * Text arrives from the soft keyboard as characters, and the guest wants
 * keys, so each character becomes the KeyboardEvent.code that produces it. A
 * capital letter is its key with Shift held. Anything the keymap has no key
 * for is dropped: the game's text fields take letters, digits and spaces.
 */
export function keysForText(text) {
  const out = [];
  for (const ch of text) {
    if (ch === "\n" || ch === "\r") { out.push({ code: "Enter", shift: false }); continue; }
    if (ch === " ") { out.push({ code: "Space", shift: false }); continue; }
    if (/^[0-9]$/.test(ch)) { out.push({ code: "Digit" + ch, shift: false }); continue; }
    if (/^[a-z]$/i.test(ch)) {
      out.push({ code: "Key" + ch.toUpperCase(), shift: ch !== ch.toLowerCase() });
    }
  }
  return out;
}

/**
 * The keys the strip draws. `keys` is the KeyboardEvent.code list a button
 * presses, in the order to press them; released in reverse.
 *
 * The game draws its own arrows and its own A, S, C and D on the screen, so
 * `pad` and `actions` repeat what a fingertip can already reach and are shown
 * only when asked for. `main` is what the game has no button for.
 */
export const STRIP = {
  // The game's keys, in the hand that a controller puts them: actions on the
  // left, the arrows on the right.
  // Five across: the party, the actions, the panels, and a last column for
  // the disk panel's own keys, with the answers to what it asks.
  actions: [
    { label: "F1", keys: ["F1"], title: "First party member" },
    { label: "F2", keys: ["F2"], title: "Second party member" },
    { label: "F3", keys: ["F3"], title: "Third party member" },
    { label: "F4", keys: ["F4"], title: "Fourth party member" },
    { label: "L", keys: ["KeyL"], title: "Load, in the disk panel" },
    { label: "A", keys: ["KeyA"], title: "Attack" },
    { label: "S", keys: ["KeyS"], title: "Shoot" },
    { label: "C", keys: ["KeyC"], title: "Cast" },
    { label: "D", keys: ["KeyD"], title: "Disk" },
    { label: "Y", keys: ["KeyY"], title: "Yes" },
    { label: "P", keys: ["KeyP"], title: "Inventory panels" },
    { label: "M", keys: ["KeyM"], title: "Party map" },
    { label: "K", keys: ["KeyK"], title: "Keyring" },
    // Under D, since it is the way back out of what D opens.
    { label: "R", keys: ["KeyR"], title: "Return from the disk panel" },
    { label: "N", keys: ["KeyN"], title: "No" },
  ],
  pad: [
    { label: "⇤", keys: ["ControlLeft", "ArrowLeft"], title: "Sidestep left" },
    { label: "▲", keys: ["ArrowUp"], title: "Forward" },
    { label: "⇥", keys: ["ControlLeft", "ArrowRight"], title: "Sidestep right" },
    { label: "◀", keys: ["ArrowLeft"], title: "Turn left" },
    { label: "▼", keys: ["ArrowDown"], title: "Back" },
    { label: "▶", keys: ["ArrowRight"], title: "Turn right" },
  ],
  // A second column beside `main` on a phone held sideways, for the keys
  // that have no control of the game's own to sit on. The letterbox either
  // side of the game has the room, so the game loses none.
  more: [
    { label: "P", keys: ["KeyP"], title: "Inventory panels" },
    { label: "M", keys: ["KeyM"], title: "Party map" },
    { label: "K", keys: ["KeyK"], title: "Keyring" },
    { label: "R", keys: ["KeyR"], title: "Return from the disk panel" },
    { label: "L", keys: ["KeyL"], title: "Load, in the disk panel" },
    // The digits the game's lists are picked by.
    { label: "1", keys: ["Digit1"] }, { label: "2", keys: ["Digit2"] }, { label: "3", keys: ["Digit3"] },
    { label: "4", keys: ["Digit4"] }, { label: "5", keys: ["Digit5"] }, { label: "6", keys: ["Digit6"] },
  ],
  main: [
    { label: "Pad", action: "pad", title: "The game's keys under the screen: party members, actions and the arrows" },
    { label: "Esc", keys: ["Escape"] },
    { label: "⏎", keys: ["Enter"], title: "Enter" },
    { label: "␣", keys: ["Space"], title: "Space: use what is in front of you" },
    { label: "Right click", icon: "mouse-right", action: "right",
      title: "The next tap is a right click; hold to make every tap one" },
    { label: "⌨", action: "keyboard", title: "Type with the device's keyboard" },
    { label: "⋯", action: "drawer", title: "The rest of the keyboard" },
  ],
};

/** The drawer: every key the game reads, in rows. */
export const DRAWER = [
  "F1 F2 F3 F4 F5 F6 F7 F8 F9 F10",
  "1 2 3 4 5 6 7 8 9 0",
  "Q W E R T Y U I O P",
  "A S D F G H J K L Tab",
  "Z X C V B N M Backspace",
].map((row) => row.split(" "));

/** KeyboardEvent.code for a drawer label. */
export const codeForLabel = (label) => {
  if (/^[A-Z]$/.test(label)) return "Key" + label;
  if (/^[0-9]$/.test(label)) return "Digit" + label;
  return label;   // F1..F10, Tab, Backspace are their own codes
};

// --- DOM wiring --------------------------------------------------------------

/**
 * Build the strip and the drawer into `root` and wire every key.
 *
 * `sendKey(code, down)` takes a KeyboardEvent.code. A key is held for as long
 * as the finger is on it, so movement keys repeat the way a keyboard's do.
 * Every way a finger can leave releases the key: lifting, being canceled by a
 * scroll, or the pointer capture being taken away.
 */
export function mountTouchKeys(root, { sendKey, onAction }) {
  const pad = root.querySelector(".touch-pad");
  const actions = root.querySelector(".touch-actions");
  const main = root.querySelector(".touch-main");
  const more = root.querySelector(".touch-more");
  const drawer = root.querySelector(".touch-drawer");
  const make = (spec) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "touch-key";
    // Never focused: a phone scrolls a focused control into view, and a
    // page that must not scroll has nowhere to put it back.
    b.tabIndex = -1;
    if (spec.icon === "mouse-right") {
      // A mouse with its right button filled: the word did not fit a key
      // on a narrow phone.
      b.innerHTML = '<svg viewBox="0 0 16 20" width="14" height="18" aria-hidden="true" focusable="false">'
        + '<rect x="1.5" y="1.5" width="13" height="17" rx="6" fill="none" stroke="currentColor" stroke-width="1.5"/>'
        + '<path d="M8 1.5v8" stroke="currentColor" stroke-width="1.5"/>'
        + '<path d="M8 2.2h.5A5.3 5.3 0 0 1 13.8 7.5V9.5H8z" fill="currentColor"/></svg>';
      b.setAttribute("aria-label", spec.label);
    } else {
      b.textContent = spec.label;
    }
    if (spec.title) { b.title = spec.title; b.setAttribute("aria-label", spec.title); }
    if (spec.action) {
      b.dataset.action = spec.action;
      return b;
    }
    b.dataset.keys = spec.keys.join(" ");
    return b;
  };
  for (const spec of STRIP.pad) pad.append(make(spec));
  for (const spec of STRIP.actions) actions.append(make(spec));
  for (const spec of STRIP.main) main.append(make(spec));
  for (const spec of STRIP.more) more.append(make(spec));
  for (const row of DRAWER) {
    const line = document.createElement("div");
    line.className = "touch-row";
    for (const label of row) {
      const b = make({ label: label === "Backspace" ? "⌫" : label,
                       keys: [codeForLabel(label)],
                       title: label === "Backspace" ? "Backspace" : undefined });
      line.append(b);
    }
    drawer.append(line);
  }

  const held = new Map();   // pointerId -> codes held down
  root.addEventListener("pointerdown", (e) => {
    // A finger anywhere on the keys is the keys' own, gaps included: it is
    // not to fall through to the game drawn under them.
    e.preventDefault();
    const b = e.target.closest("button.touch-key");
    if (!b) return;
    if (b.dataset.action) {
      onAction(b.dataset.action, b, e);
      return;
    }
    const codes = b.dataset.keys.split(" ");
    for (const c of codes) sendKey(c, true);
    held.set(e.pointerId, codes);
    b.classList.add("down");
    try { b.setPointerCapture(e.pointerId); } catch { /* a pointer that cannot be captured still releases below */ }
  });
  const release = (e) => {
    const codes = held.get(e.pointerId);
    if (!codes) return;
    held.delete(e.pointerId);
    for (const c of codes.slice().reverse()) sendKey(c, false);
    for (const b of root.querySelectorAll("button.touch-key.down")) {
      if (b.dataset.keys === codes.join(" ")) b.classList.remove("down");
    }
  };
  for (const type of ["pointerup", "pointercancel", "lostpointercapture"]) {
    root.addEventListener(type, release);
  }
  // A context menu on a long press would take the finger away mid-hold.
  root.addEventListener("contextmenu", (e) => e.preventDefault());
  // The click a browser still makes after a handled pointerdown would give
  // the key focus. It has done its work already.
  root.addEventListener("click", (e) => {
    if (e.target.closest("button.touch-key")) { e.preventDefault(); e.target.blur(); }
  });
}

/**
 * The device's own keyboard, for text: a field kept off screen that the
 * keyboard types into, with every character forwarded as key presses and the
 * field emptied again.
 *
 * A soft keyboard does not announce keys the way a physical one does: Android
 * sends keydown with no code, and the text arrives as an input event. So text
 * is read from `beforeinput`, and only Enter and the arrows are taken from
 * keydown. Backspace is read as a deletion, which the field can only report
 * while there is something in it, so it always holds one space.
 */
export function mountTyper(field, { sendKey, onClose, hold = 120, gap = 40 }) {
  const SENTINEL = " ";
  const reset = () => { field.value = SENTINEL; field.setSelectionRange(1, 1); };
  // One key at a time, each held long enough for DOS to notice, the way
  // keys.js taps them headlessly, and longer than that: the game reads the
  // keyboard as it goes round its loop, and on a phone one turn can outlast
  // a short press. Sent with no hold, a burst of characters reached the
  // game as a few of them.
  const later = (ms) => new Promise((r) => setTimeout(r, ms));
  let queue = Promise.resolve();
  const press = (code) => { queue = queue.then(async () => {
    sendKey(code, true); await later(hold); sendKey(code, false); await later(gap);
  }); };
  const type = (keys) => {
    for (const { code, shift } of keys) {
      if (shift) queue = queue.then(() => sendKey("ShiftLeft", true));
      press(code);
      if (shift) queue = queue.then(() => sendKey("ShiftLeft", false));
    }
  };
  field.addEventListener("beforeinput", (e) => {
    e.preventDefault();
    if (e.inputType === "insertText" || e.inputType === "insertCompositionText"
        || e.inputType === "insertFromPaste") {
      type(keysForText(e.data ?? ""));
    } else if (e.inputType === "insertLineBreak" || e.inputType === "insertParagraph") {
      type(keysForText("\n"));
    } else if (e.inputType.startsWith("delete")) {
      press("Backspace");
    }
    reset();
  });
  field.addEventListener("keydown", (e) => {
    // Text comes through beforeinput; here only the keys that never do.
    if (!["Enter", "Escape", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "Tab"]
        .includes(e.key)) return;
    e.preventDefault();
    press(e.key);
  });
  field.addEventListener("focus", reset);
  field.addEventListener("blur", () => onClose?.());
  return {
    open: () => { reset(); field.focus({ preventScroll: true }); },
    close: () => field.blur(),
  };
}
