# Booting and driving the game

The game runs under an emulator, and it can be driven with no person at the keyboard. Settled findings only. The byte changes are in [patching.md](patching.md), and everything described here is implemented in [cabinet/](../cabinet).

Everything here is **measured**. Each configuration below was booted and the result read off the running game, and the tables say which backend and which switches produced it. [README.md](README.md) defines the word. The timings are wall-clock on one machine.

## The backend

`emulators` runs under **bun** in Node mode (`dosboxNode`), so the game boots, runs and produces screenshots with no browser. Under npm the bundle's internal `require` fails to resolve `wdosbox.js`. Under bun it resolves.

Two backends ship. Plain DOSBox delivers keys but no mouse coordinates. **DOSBox-X is the only backend whose mouse reaches the guest**, and it requires `mouse_emulation=always`. The section on the mouse below gives the measurements.

## What the game requires

- **`ems=true`**, or the game aborts on startup. `README.DOC` states `EMM Ver 4.0` and at least 1 MB of expanded memory.
- **Launch `SW.BAT`, never `REGISTER.EXE`.** The batch sets `SWGAMES`, loads `SBFMDRV.COM` when `BLASTER` is set, and passes the `/B /W` flags the game expects. Run the executable directly and it prints `Please run Tyrants of Thaine from SW.BAT`.
- **`cycles=20000`**, not `max`, because `max` starves the host. Cycles buy nothing before the menu is reached, because the splash screens advance on elapsed time rather than on instructions executed. 3,000 cycles reaches the menu in about 10 seconds, `max` in 20 seconds, and `200000` in 40 seconds. During play, 3,000 cycles is slow enough that a single step takes about one second.
- **Do not disable sound in the emulator.** With `sbtype=none` the game hangs on its second splash. Use the game's own switches instead. **`/NOM /NOS`** are supported code paths, and `HEADLESS_ARGS` in [cabinet/boot.js](../cabinet/boot.js) passes them by default.
- **Audio has to be wired up explicitly.** The backend passes samples through `onSoundPush` and plays nothing itself. It requires an `AudioContext`, a ring buffer and a `ScriptProcessorNode`, which are in [cabinet/audio.js](../cabinet/audio.js). Playback starts only once a full block is buffered, so the first seconds do not stutter.

Without the patches, the splash chain takes about 12 seconds. The screens poll for input rather than timing out, so they advance on any key and cannot be skipped outright. Two constraints bound what a driver may send. An ESC that arrives once the menu is up backs straight out of the menu, and the menu starts the introduction after a few idle seconds. The `gomenu` command in [cabinet/session.js](../cabinet/session.js) sends keys until the menu appears, and stops on the same frame.

## The keyboard

Every menu is reachable from the keyboard.

    C  character creation      F/M/R/O/A/P/G/D/K  pick a class
    1-9 portrait               R  roll attributes    I  items
    N  name (then ENTER)       K  keep character     Q  leave creation
    A  assemble a party        1-9 toggle a member   D  done
    E  enter the game
    D  disk panel              S  save   L  load   N  new game   R  return
    1-6 save slot              Y/N  confirm

During play the cursor keys move and turn. Up moves forward, down moves back, left and right turn, and Ctrl with left or right steps sideways. **SPACE uses whatever is in front of the party**, which is how a door is opened. Inside the clue book, the left arrow returns one page and ESC leaves the book.

**Entering the game lands with the disk panel already open**, so a `D` sent to open it selects DOS and reaches "exit to DOS?" instead. **NEW GAME appears in the disk panel only once a save exists.** Before a save exists the panel offers SAVE, DOS, ANIMATION and RETURN.

## The mouse

The game is driven by the mouse, and character creation cannot be completed without one. The guest cursor does not follow the pointer by default.

| Configuration | Result |
|---|---|
| this cabinet, patched build + `/P` | cursor pinned at the origin |
| this cabinet, stock build, no switches | pinned |
| js-dos 8.4.1 stock player, `.jsdos` bundle | pinned |
| js-dos 7.5.0 stock player, same bundle | pinned |
| DOSBox-X, `mouse_emulation=locked` (the default) | pinned |
| DOSBox-X, `mouse_emulation=always` | **both axes respond** |

The cause is DOSBox-X's `[sdl] mouse_emulation`. Its default, `locked`, emulates the mouse only while the pointer is captured, which a browser canvas cannot do.

The coordinates are **not a fraction of the screen between 0 and 1**. The response is linear with roughly twice the expected slope and an origin near 0.44, so the usable input range is about 0.4375 to 0.9375. The mapping depends only on the value passed in. The same value twice lands the cursor on the same pixel, and returning to an earlier value returns the cursor to the same place, with no accumulated drift. [cabinet/mouse.js](../cabinet/mouse.js) inverts the mapping and tracks the pointer to within about 4% of the screen.

**Under DOSBox-X the canvas reports 640×400**, not the game's 320×200, so anything mapping pointer position to guest coordinates must read the canvas size rather than assume mode 13h.

Lists select on a **double** click, and both the save slot list and the clue book ignore a single click. The second press must carry no motion before it, or the pair does not register as a double click. A double *right* click has a meaning of its own rather than being a stronger form of the single right click. On a portrait it toggles every inventory panel at once.

## A phone

The cabinet lays itself out for a phone and takes a finger as its pointer. Everything here was **measured**: in Chromium emulating a Pixel 7 and an iPhone SE, in Firefox and WebKit emulating an iPhone 14, and on an Android emulator running Chrome, all driven by [tools/mobile_check.js](../tools/mobile_check.js) and `adb`.

**The layout.** Under 900 pixels wide the game is drawn across the top at the width of the screen and its own 8:5 shape, with the keys under it. On a screen that is wider than it is tall and at most 520 pixels tall, a phone on its side, the header becomes a column down the left edge, the keys a column down the right, and the game is the full height between them. In both the clue book is a page over the game, put away to start and brought out by the book button; under the game it had whatever height the keys left it, which was not enough to read. The book button and the full screen button are separate: neither changes the other. The header's status line moves onto its own row under 640 pixels, and under 480 the title is cut to *Thaine* so five buttons fit beside it.

**A finger on the game.** [cabinet/touch.js](../cabinet/touch.js) reads pointer events of type `touch` and `pen` before the browser makes mouse events of them, and sends the emulator what the game expects:

| Gesture | Sent |
|---|---|
| tap | the cursor placed at the spot (below), left press, 160 ms, release |
| second tap within 350 ms and 32 px of the first | left press and release with no motion in front of it |
| finger held still 450 ms | the cursor placed, right press, held until the finger lifts, relative motion while it moves |
| second finger while the first is down | right click at the first finger |
| finger moved more than 12 px | relative motion following it, and no click on lifting |
| the Right key, then a tap | that tap is a right click; held down, every tap is one |

**Placing the cursor.** A tap places the cursor the way [cabinet/keys.js](../cabinet/keys.js) places a headless click: a relative motion of -4000 on each axis drives the arrow into the top-left corner, then one relative motion steps it out to the spot at 2 pixels a unit. A tap sending the absolute value the mouse path sends landed a screen away on the phone: the value is right only while the cursor is where the last send left it, and the game moves the cursor itself between screens. Homing starts every tap from a known place.

Three things the placing waits for, all measured on the Android emulator, whose guest runs several times slower than a desktop's:

- The step goes out only once the frame shows the arrow at the corner. Sent 40 ms after the homing, the two deltas reached the driver as one, and their sum still clamped at the corner.
- After homing the arrow's tip rests at `HOME`, (2, 16) at 640x400 on the main menu, and a line or two from there on other screens. So once the frame shows the arrow away from the corner its tip is located and the cursor nudged the rest of the way. One frame read at a time; no probing.
- The button is held 160 ms. The game reads the button as it goes round its loop, and on the phone one turn of the loop outlasted a 60 ms click, which then never happened as far as the game could tell. Typed keys are held 120 ms for the same reason.

The second tap of a double tap carries no motion because the guest drops the pair if any arrives between the presses, which is the same rule the headless double click follows.

**What the game does with a click**, found while playing it by touch, and true with a mouse too:

- On the main menu, R is Credits and I is Introduction. A tap on Character Creation or Assemble a Party opens it. Enter the Game is inert to the mouse until a party has been assigned; the E key enters regardless.
- On Assemble a Party the four stock characters start with their boxes ticked, and a tap on a box, or the keys 6 to 9, toggles one into the party; the screen looks the same either way. DONE takes a click just below its lettering and ignores one on it. D does the same.
- In the world the game's own arrow buttons move the party, Space reports NOTHING HERE when nothing is ahead, a right click on a portrait opens that character's inventory and a double click opens the sheet.

**The keys.** The strip under the screen holds Esc, Enter, Space, the right click, the device's keyboard and a drawer with the digits, F1 to F10 and the letters. Above it, on until put away with the **Pad** key and remembered in `localStorage` under `cabinet.game-keys` once the key has been pressed, are the game's own keys: F1 to F4 for the party members, A, S, C and D, P, M, K and R on the left, R under D as the way back out of the disk panel, and a last column of L, Y and N for what the disk panel asks, and the arrows with the two sidesteps on the right. A key is down for as long as a finger is on it. The device's own keyboard types into a one-pixel field; each character is sent as the key that produces it, with Shift held for a capital, and Backspace as a deletion, which the field can only report while it holds something, so it always holds one space.

**Installing.** The page carries a web manifest and a service worker at the site root, so a browser offers to add it to the home screen and opens it in its own window. The worker fetches the shell itself as it installs, since the first visit's own requests go out before it is in place to see them, and keeps everything else the page loads as it is fetched: the emulator and its wasm at the first boot, pyodide and the decoders at the first decode. It serves a copy only when the network does not answer. [tools/offline_check.js](../tools/offline_check.js) proves the whole of it, as `make test-offline`: the static site is served with no game, a copy is dropped in, decoded and booted, then the server is stopped and the page reloaded, and it comes back with the stored copy offered, the clue book populated from storage and the game painting, every one of its requests answered locally. [tools/build_icons.js](../tools/build_icons.js) draws the icons and `favicon.ico` from [cabinet/icon.svg](../cabinet/icon.svg); both servers answer `/favicon.ico` at the root.

**Sound.** The audio context is resumed from the click that boots the game, and it is running afterwards on the Android emulator's Chrome and on Chrome on an iPhone. Where a browser refuses a resume that comes seconds after the click, the volume icon dims, the status line says so, and the next press or tap resumes it.

**Full screen.** An iPhone lets only a video go full screen, and Chrome there does not report it through `fullscreenEnabled`, so the button is not shown on an iPhone by name, nor anywhere a request is refused as unsupported. The home screen is its full screen, and the manifest offers that. The viewport pins the scale, since WebKit on a phone otherwise rescales the page on every turn of the phone.

**The cursor mapping.** A finger has no pointer to align with, so the calibration in [cabinet/mouse.js](../cabinet/mouse.js) does not run on a touch screen; a tap homes the cursor instead, as above. While the calibration did run there it moved the cursor about to find it, every tap waited behind it, and the tap then landed wherever a probe had left the cursor: that was the tap that did nothing on the Android emulator and on an iPhone. The mouse's calibration is as it was.

## One long session

[cabinet/session.js](../cabinet/session.js) keeps one emulator running and reads commands from `tmp/session.cmd`, so the cost of booting is paid once rather than once per interaction. `--backend=x` selects DOSBox-X, and `--trace` logs every filesystem mutation beside the command that caused it. [cabinet/cabinet.js](../cabinet/cabinet.js) accepts `?backend=dosbox|dosboxX` and `?mouse=absolute|relative`.
