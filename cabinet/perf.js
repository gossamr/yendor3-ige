// What a measurement needs from whatever is being measured.
//
// tools/perf_check.js drives these names and nothing else, so it stays a
// measurement of the page rather than of this integration. Everything
// specific to running the game behind an emulator stays on this side of the
// line: the emulator handle, the key sequence that gets a party into the
// world, what a step is, which input to send.
//
// Two pages measured this way are asked the same question, because the
// question lives here rather than in the harness.
import { KEYS, tap } from "./keys.js";

const wait = (ms) => new Promise((r) => setTimeout(r, ms));

/**
 * The contract, over a running cabinet.
 *
 * `ci` is the emulator, `frames` reports what it has delivered, and `info`
 * says which of the page's interchangeable paths this session took.
 */
export function cabinetPerf({ ci, frames, info, nextFrame, canvas, taps }) {
  let entered = false;

  /**
   * A key, held long enough for DOS to see it.
   *
   * Two waits, for two kinds of key. One that changes the screen is followed
   * by `turned`, which waits for the picture the change draws: the emulator
   * delivers a frame only when something changes, so that frame is the screen
   * arriving and there is nothing to time. One that ticks a box on a screen
   * already up draws little and is followed by nothing but the hold.
   *
   * Getting this backwards costs either way. Waiting on a frame after every
   * key spends the timeout on each one that draws nothing. Waiting after none
   * of them sends the party keys at a screen that is not up yet, and they go
   * nowhere, which reads as a run that entered the world and found no frames
   * in it.
   */
  const press = (k) => tap(ci, KEYS[k], 120);
  const turned = (cap = 8000) => Promise.race([nextFrame(), wait(cap)]);

  // What each key cost, so a slow run reports which key was slow.
  let steps = [];
  async function keyed(k, waitFor) {
    const t0 = performance.now();
    // Listening before knocking. A key is held for tens of milliseconds, and
    // the picture it causes can arrive inside that hold: a waiter registered
    // afterwards waits for a frame that has already been and gone, and every
    // screen change costs its whole timeout. Measured before it was fixed,
    // that was 4.2s to open a menu and 8.2s to enter the world.
    const answer = waitFor ? turned(waitFor) : null;
    await press(k);
    if (answer) await answer;
    steps.push([k, Math.round(performance.now() - t0)]);
  }

  /** Where the emulated disk put a save slot, or null if it holds none. */
  async function findSave(slot = 1) {
    const tree = await Promise.race([ci.fsTree(), wait(3000).then(() => null)]);
    const want = new RegExp(`SAVGAME${slot}$`, "i");
    // An FsNode is { name, size, nodes }, and `nodes` is an array of them,
    // not a map keyed by name.
    const walk = (node, path) => {
      for (const child of node?.nodes ?? []) {
        // Slash-prefixed, the way the tree names it and the way a read wants
        // it. Without it the file is there and the read still misses.
        const here = `${path}/${child.name}`;
        if (want.test(child.name)) return here;
        const found = walk(child, here);
        if (found) return found;
      }
      return null;
    };
    return tree ? walk(tree, "") : null;
  }

  /**
   * Whether the game has a save to load.
   *
   * Bounded, because asking the emulator for a file that is not there does not
   * always come back: a read that never resolves would stop `enter()` before
   * it pressed a key, which is a hang with nothing on screen to explain it.
   */
  async function hasSave(slot = 1) {
    const read = ci.fsReadFile(`SAVGAME${slot}`).then((b) => b.length > 0, () => false);
    return Promise.race([read, wait(4000).then(() => false)]);
  }

  /**
   * One synthetic finger, through the listeners the page really has.
   *
   * Pointer events with pointerType "touch", because that is what the canvas
   * binds and what `finger()` there tests for. A TouchEvent reaches none of
   * it.
   */
  function finger(type, x, y) {
    canvas.dispatchEvent(new PointerEvent(type, {
      bubbles: true, cancelable: true, pointerId: 1, pointerType: "touch",
      isPrimary: true, clientX: x, clientY: y, button: 0, buttons: type === "pointerup" ? 0 : 1,
    }));
  }

  /**
   * Milliseconds from a finger landing on the game to the game answering.
   *
   * Not to the click being sent, which is halfway: the wait ends at the first
   * picture drawn after the guest has the click, because that is the moment a
   * player sees anything happen. The default spot is inside the view the game
   * draws the world in, not the keys the page puts around it, since those are
   * the page's own and answer immediately.
   */
  // Where a finger has something to press: the game's disk icon, which opens
  // its panel, and RETURN inside that panel, which closes it. Alternating
  // the two leaves the game where it was, and every tap is answered by a
  // screen the game draws rather than by the cursor arriving. docs/running.md
  // has both spots.
  const DISK_ICON = { x: 0.956, y: 0.381 };
  const PANEL_RETURN = { x: 0.572, y: 0.605 };

  async function tapTimes(n, timeout, spot) {
    const out = [];
    for (let i = 0; i < n; i++) {
      // A fraction of the picture, not of the canvas's box: the canvas is
      // drawn with object-fit contain, so the picture sits centered in the
      // box at one scale, and the pointer handler at cabinet.js maps a
      // finger back through that. A fraction of the box lands beside the
      // icon wherever the box is letterboxed.
      const box = canvas.getBoundingClientRect();
      const scale = Math.min(box.width / canvas.width, box.height / canvas.height);
      const w = canvas.width * scale, h = canvas.height * scale;
      const at = spot ?? (i % 2 ? PANEL_RETURN : DISK_ICON);
      const x = box.left + (box.width - w) / 2 + w * at.x;
      const y = box.top + (box.height - h) / 2 + h * at.y;
      const delivered = taps();
      const sent = performance.now();
      finger("pointerdown", x, y);
      await wait(60);
      finger("pointerup", x, y);
      // The click travels a queue, a homing move and two waits for frames
      // that show the cursor arrive and leave a corner. Only once it is out
      // the far end does the next picture belong to it.
      const until = sent + timeout;
      while (taps() === delivered && performance.now() < until) await wait(10);
      if (taps() === delivered) { out.push(null); await wait(400); continue; }
      const answer = await Promise.race([nextFrame(), wait(timeout).then(() => null)]);
      out.push(answer === null ? null : +(answer - sent).toFixed(1));
      // Back to back. A tap after the cursor has parked costs more, and
      // waiting four seconds a sample for that would make a run minutes long.
      await wait(200);
    }
    return out;
  }

  return {
    name: "cabinet",
    // What a pair of taps is, for the rows a measurement prints.
    info: () => ({ ...info(), taps: ["disk icon opens the panel", "RETURN closes it"] }),
    hasSave,
    ready: () => frames() > 0,
    frames,

    /**
     * Put a party in the world, which is where stepping means anything.
     *
     * Two ways in. A save that was on the disk when the emulator started is
     * loaded off the menu in three keys; with none, the four characters the
     * game ships with are assembled a screen at a time, which is what
     * `saveGame` and `takeSave` exist to spare every run after the first.
     */
    async enter(worldWait = 0, gaps = 1) {
      if (entered) return;
      steps = [];
      const loading = await hasSave();
      steps.push(["save?", loading ? 1 : 0]);
      if (loading) {
        // Load, straight off the menu. The party comes with the save, so
        // ENTER THE GAME plays no part and pressing it does nothing at all.
        // The sequence and its waits are tmp/write_probe.js's, which settled
        // them against a save placed in the boot file set.
        await keyed("l", 0); await wait(900);
        await keyed("1", 0); await wait(3000);
        await keyed("y", 0); await wait(16000);
      } else {
        // The long way, which runs once to make that save. The waits are
        // tools/fight_probe.js's, except the one after ENTER THE GAME: 25
        // seconds rather than 13, because that probe runs the emulator under
        // node, where the guest is faster than it is in a page. Short, and
        // every key after it lands on a screen that is not up yet, which reads
        // as a run that entered the world and found no frames in it.
        await keyed("a", 0); await wait(4000 * gaps);
        for (const k of ["6", "7", "8", "9"]) { await keyed(k, 0); await wait(700 * gaps); }
        await keyed("d", 0); await wait(3000 * gaps);
        // Nothing is waited for here. Swept at 0, 500, 1000 and 2000 ms, the
        // party reached the world every time, so the 2,500 after R below
        // covers whatever the transition needs. `worldWait` is kept settable
        // to re-run that sweep on a slower host.
        await keyed("e", 0); if (worldWait) await wait(worldWait);
        await keyed("r", 0); await wait(2500 * gaps);
      }
      entered = true;
      return steps;
    },

    /**
     * Save to a slot, from in the world.
     *
     * Four questions, in this order: which slot, what to call it, ENTER, and
     * then whether to save now. A confirmation sent at the name is typed into
     * the box rather than answering anything, which leaves the game in the
     * naming screen with a save that was never written, and everything
     * measured afterwards is a modal rather than the world.
     */
    async saveGame(slot = 1, name = "PERF") {
      await keyed("d", 2000);
      await keyed("s", 2000);
      await keyed(String(slot), 1000);
      for (const c of name.toLowerCase()) await press(c);
      await keyed("enter", 2000);
      await keyed("y", 4000);   // "do you want to save this game now?"
      // Nothing after the yes. The panel closes itself, and R in the world is
      // Rest, which asks its own question and leaves it on the screen.
    },

    /** A slot's bytes, for a later run to start from, or null where there is none. */
    async takeSave(slot = 1) {
      // By name first, then by looking: the emulated disk decides the case and
      // the directory, and a read that misses returns nothing rather than
      // saying where the file went.
      const path = (await findSave(slot)) ?? `SAVGAME${slot}`;
      const read = ci.fsReadFile(path).then((b) => Array.from(b), () => null);
      return Promise.race([read, wait(3000).then(() => null)]);
    },

    /**
     * Put a save on the emulated disk before the game is asked to load it.
     *
     * The buffer is copied because the emulator takes it rather than borrowing
     * it: js-dos transfers it into the worker, which detaches it here.
     */
    async putSave(bytes, slot = 1) {
      await ci.fsWriteFile(`SAVGAME${slot}`, Uint8Array.from(bytes).slice());
    },

    /**
     * `n` steps, forward and back, so the party ends where it started, one
     * key every `pace` ms. Each key is held 60 ms so DOS sees it, and with
     * no pace beyond that the keys arrive faster than the game steps, so its
     * buffer fills and the frames counted are the rate the game itself can
     * step at.
     */
    async step(n, pace = 0) {
      for (let i = 0; i < n; i++) {
        const key = i % 2 ? KEYS.down : KEYS.up;
        ci.sendKeyEvent(key, true);
        await wait(60);
        ci.sendKeyEvent(key, false);
        await wait(Math.max(10, pace - 60));
      }
    },

    /**
     * Milliseconds from an input to the picture that answers it, `n` times.
     *
     * Two kinds, because they do not travel the same road. A key reaches the
     * guest's keyboard buffer directly. A pointer move goes through the mouse
     * path, which on a touch screen homes the cursor from a corner first, and
     * that is the one a player feels.
     *
     * The press is not released before the answer is timed: `tap` holds a key
     * for tens of milliseconds so DOS notices it, and that hold would be
     * counted as latency it is not.
     *
     * `tap` is the one that goes through the page. It dispatches a real
     * touch on the canvas and waits for the click to come out the far end, so
     * it times the whole path a finger takes rather than the emulator's
     * answer to a delta: the gesture queue, homing the cursor into a corner
     * with a delta larger than the screen, two waits for frames that show the
     * arrow arrive and leave, a nudge, and the button held long enough for a
     * slow guest to notice. `key` and `pointer` skip all of that by design,
     * which is why the three numbers differ by so much.
     *
     * The tap presses the game's disk icon and then RETURN in the panel it
     * opens, in turn, so each one is answered by a screen the game draws and
     * the game is left where it was.
     *
     * An input that draws nothing gets `null` rather than a wait with no end.
     * The game redraws on a step and on a cursor move, but only where there
     * is a party to step: asked at a menu, this reports what it found rather
     * than hanging on a picture that is not coming.
     */
    async react(kind = "key", n = 8, timeout = 5000, spot = null) {
      if (kind === "tap") return tapTimes(n, timeout, spot);
      const out = [];
      for (let i = 0; i < n; i++) {
        // Alternating, so the party ends where it started and the cursor with
        // it; a run of one direction walks away from where it was measured.
        const back = i % 2 === 1;
        const send = kind === "pointer"
          ? () => ci.sendMouseRelativeMotion(back ? -8 : 8, 0)
          : () => ci.sendKeyEvent(back ? KEYS.down : KEYS.up, true);
        const answer = Promise.race([
          nextFrame(),
          wait(timeout).then(() => null),
        ]);
        const sent = performance.now();
        send();
        const drawn = await answer;
        out.push(drawn === null ? null : +(drawn - sent).toFixed(1));
        if (kind !== "pointer") ci.sendKeyEvent(back ? KEYS.down : KEYS.up, false);
        // Let the guest finish drawing before asking it again, or the next
        // measurement times the tail of this one.
        await wait(400);
      }
      return out;
    },

    /** Stop working. The page stays open, which is the floor to measure against. */
    stop() { ci.pause(); },
  };
}
