# Patching the executable

Four byte changes to `REGISTER.EXE`, what each does and how each was checked. Settled findings only. [tools/patch.py](../tools/patch.py) applies them to a copy of the game directory, leaving `game/` untouched, and [tests/test_patch.py](../tests/test_patch.py) holds every claim below to the file.

## What the format allows

The file is not packed, has no overlays, and its length matches the MZ header exactly, so a same-length patch needs no other fixup. `e_csum` is zero and DOS ignores the field.

The loader rewrites 4,000 words from the **relocation table** at load time, so a patch landing on one is overwritten. [tools/mz.py](../tools/mz.py) builds that map and [tools/patch.py](../tools/patch.py) refuses any site inside it.

## `enable-p-switch`, the switch the game already has

`REGISTER.EXE` parses five command-line switches at image `0x1e56`, reached through the `lcall 0x1e5:6` at the entry point: `/P`, `/B`, `/W`, `/NOM` and `/NOS`. `/P` sets bit 15 of the flag word at `[0x536a]`.

The initialization routine has an intro-skip branch that tests exactly that bit:

    0eec9  test word [0x536a], 0x8000
    0eecf  jne  0xef32               ; skip the intro
    0eed1  lcall 0x10dc:4            ;   splash
    0eed6  lcall 0xe72:0x28c         ;   splash
    0eee2  lcall 0x1bb7:0xc          ;   splash
    0eeee  mov ax, 0x14 / lcall 0x1834:0    ;   delay

But the dispatcher clears the same bit before initialization ever runs:

    00032  and word [0x536a], 0x7fff

so `/P` can never take effect as shipped. Widening that mask makes the AND a no-op:

    file 0x004037:  0x7f -> 0xff

**Verified.** With the patch applied and `SW.BAT /P`, the main menu appears in about 2 seconds instead of 12. The menu, party assembly and the clue book all render, which shows that the skipped calls only draw. Without `/P` the patched build behaves as the original does.

`/P` is the developers' **debug mode**, not an intro skip. It has twelve readers: under it walls stop clipping, and one of them bypasses `YOUR SKILL IS NOT HIGH ENOUGH!` on training.

## `force-skip-intro`

Skips the intro without the debug mode, by making the branch at `0xeecf` unconditional:

    0x75 -> 0xeb        same length, at image 0x12ecf

`/P` sets the bit the test in front of that branch reads, so under `/P` the two patches have the same effect. A build carrying `enable-p-switch` leaves this one out.

## `no-attract`, the attract loop on the menu

The main menu falls back into the splash chain and the story intro after about half a minute of no input. The loop is a countdown:

    0bf32  mov  word [0x53ee], 0x4b     ; reload, each time the menu is drawn
    0bf44  test word [0x536a], 0x400    ; a timer tick?
    0bf4a  je   0xbfa3                  ;   no, go poll input
    0bf52  dec  word [0x53ee]
    0bf56  cmp  word [0x53ee], 0
    0bf5b  jg   0xbfa3                  ; not expired, go poll input
    0bf5d..0bf9b                        ; expired: splashes, then the intro

Making that `jg` unconditional never takes the expiry path:

    0x7f -> 0xeb        at file 0xff5b

**Verified.** The menu holds indefinitely, measured over one minute, and the Introduction menu item still plays.

The same loop dispatches the menu's hotkeys, `cmp byte [0xe9a], 0x43` for C and `0x41` for A. `[0xe9a]` is the last-key byte.

## `keep-roll-on-class-change`, where changing class discards the roll

Character Creation allows a class change after rolling, and the change rerolls the attributes. Measured: a fighter rolled 48/52/55/60/58/57, and picking MAGE turned it into 56/58/48/55/60/50. The reroll happens when the *replacement* class is picked, not when the class list is opened.

The class-pick handler stores the class and then rebuilds the character:

    140de  mov  si, [0x537c]          ; the character being created
    140e2  mov  [si+0xe], ax          ; class = ax
    140e5  mov  word [si+0x16], 1     ; level = 1
    140ed  test word [0x5370], 0x8000 ; set only from the full creation menu
    140f3  jne  0x140fb               ;   so a first class pick does not roll
    140fb  call 0x14e20               ; roll, then derive health and magic
    140fe  call 0x13af3               ; derive the twelve skills
    14101  lcall 0x649:0xe            ; redraw

`0x14e20` is not only the roll:

    14e38..14eae  six times: mov ax,0xf / lcall 0x174a:0xc / add ax,0x2d
    14eaf         health = 25% of stamina      -> [si+0x52]/[si+0x92]
    14ec7..14f70  magic points, switched on the class at [si+0x0e]
    14f70..14f86  MP -> [si+0x54]/[si+0x94], and [si+0x62]/[si+0xa2]

The magic points depend on the class, and the skill derivation at `0x13af3` reads the magic column that this routine writes. Replacing the call with NOPs leaves a mage with 0 magic points and no casting skill, which was measured and is visible on screen. Health does not depend on the class. It is 25% of stamina with no test of the class, and the dispatch begins only once health is stored, so recomputing it from unchanged attributes produces the same number.

The call is therefore **retargeted rather than removed**, entering the same routine past the six rolls:

    0xe8220d -> 0xe8b10d        call 0x14e20 -> call 0x14eaf

Three bytes for three, only the displacement changing. `SI` holds across it: the routine called immediately before it loads it from the same global, and this compiler treats SI as callee-saved.

**Verified against the game's own arithmetic.** A fighter rolled 48/55/59/60/53/58. Switching to mage kept all six attributes and produced survival 57, projectile 44, slashing 47, bashing 41, polearm 45, casting 70, mapping 64, navigation 55, bartering 40, repair 56, thievery 50, linguistics 61, 15 health and 15 magic. All fourteen figures are exactly what [tools/skills.py](../tools/skills.py) predicts for a mage rolled with those attributes. Switching back to fighter sets casting and magic to zero again, ROLL ATTRIBUTES still rerolls, and a new character is still rolled during creation. The other two callers of `0x14e20` are untouched, and the `[0x5370]` gate means that a first choice of class never reached this path.

## The builds

    make patched         # tmp/game-patched, leaving game/ untouched
    make patched-debug   # tmp/game-debug, for driving under /P

`tmp/game-patched` carries `force-skip-intro`, `no-attract` and `keep-roll-on-class-change`. [cabinet/boot.js](../cabinet/boot.js) picks it whenever it exists and falls back to `game/` when it does not.

`tmp/game-debug` carries `enable-p-switch`, `no-attract` and `keep-roll-on-class-change`, and must be booted with `/P`:

    YENDOR_GAME_DIR=$PWD/tmp/game-debug YENDOR_ARGS=/P bun tools/capture_maps.js

[tests/test_patch.py](../tests/test_patch.py) asserts that every site sits outside the relocation table, still holds the bytes the patch expects, disassembles to the instructions claimed, and that patching changes only those bytes and not the file length.
