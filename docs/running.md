# Booting and driving the game

The game runs under an emulator, and it can be driven with no person at the keyboard. Settled findings only. The byte changes are in [patching.md](patching.md), and everything described here is implemented in [cabinet/](../cabinet).

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

## One long session

[cabinet/session.js](../cabinet/session.js) keeps one emulator running and reads commands from `tmp/session.cmd`, so the cost of booting is paid once rather than once per interaction. `--backend=x` selects DOSBox-X, and `--trace` logs every filesystem mutation beside the command that caused it. [cabinet/cabinet.js](../cabinet/cabinet.js) accepts `?backend=dosbox|dosboxX` and `?mouse=absolute|relative`.
