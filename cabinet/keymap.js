// Browser KeyboardEvent.code -> js-dos key code.
//
// js-dos keeps these as KBD_* constants inside its bundle rather than exporting
// them; the values used here are checked against that bundle by the test suite.
const letters = {};
for (let i = 0; i < 26; i++) {
  letters["Key" + String.fromCharCode(65 + i)] = 65 + i;
}
const digits = {};
for (let i = 0; i < 10; i++) {
  digits["Digit" + i] = 48 + i;
}

export const KEY_CODES = {
  ...letters,
  ...digits,
  Escape: 256,
  Space: 32,
  Enter: 257,
  Tab: 258,
  Backspace: 259,
  ArrowRight: 262,
  ArrowLeft: 263,
  ArrowDown: 264,
  ArrowUp: 265,
  F1: 290, F2: 291, F3: 292, F4: 293, F5: 294,
  F6: 295, F7: 296, F8: 297, F9: 298, F10: 299,
  ControlLeft: 341, ShiftLeft: 340, AltLeft: 342,
};
