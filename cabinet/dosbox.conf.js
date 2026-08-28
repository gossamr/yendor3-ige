// DOSBox configuration for Yendorian Tales III.
//
// Deliberately small: every setting here is one this game needs or one whose
// DOSBox default is wrong for a browser. Three are not optional:
//
//  * ems=true. REGISTER.EXE aborts with "Required Expanded Memory Manager
//    (EMM Ver 4.0 or later) was not found" without it, and README.DOC confirms
//    the game needs EMM386 with at least 1MB EMS.
//
//  * autolock=false. DOSBox otherwise ignores mouse input until the pointer
//    has been "captured", which a browser canvas cannot do.
//
//  * The game is launched through SW.BAT, never REGISTER.EXE directly. SW.BAT
//    sets SWGAMES, conditionally loads the SBFMDRV.COM FM driver when BLASTER
//    is set, and passes the /B /W flags the executable expects. Run the EXE by
//    hand and it prints "Please run Tyrants of Thaine from SW.BAT" and exits.

// YENDOR_ARGS lets the switches be set for the browser cabinet, which builds its
// configuration server-side. `/P` is the developers' debug mode, not an intro
// skip, since walls stop clipping under it, so it is left out of the default and
// the intro is skipped by the force-skip-intro patch in tools/patch.py
// instead. Headless drivers that want no-clip pass it against the build
// `make patched-debug` writes.
export function dosboxConf({
  sound = true,
  extra = process.env.YENDOR_ARGS ?? "",
  cycles = process.env.YENDOR_CYCLES ?? "20000",
} = {}) {
  return `
[sdl]
autolock=false
sensitivity=100
usescancodes=true
; DOSBox-X only: mouse_emulation defaults to "locked", meaning the guest gets
; no mouse at all until the pointer is captured, which a browser canvas
; cannot do. Plain DOSBox ignores this key.
mouse_emulation=always

[dosbox]
machine=svga_s3
memsize=16

[dos]
ems=true
xms=true

; The splash screens are wall-clock driven, so cycles buy nothing before the
; main menu and over-cycling starves the host: to the menu, cycles=3000 takes
; about 10s, cycles=max about 20s and cycles=200000 about 40s. That was the
; reason for the old 3000 default, and the force-skip-intro patch removes it --
; there are no splash screens left to wait through. In play the trade runs the
; other way: at 3000 a single step takes about a second.
[cpu]
core=auto
cputype=auto
cycles=${cycles}

[mixer]
rate=44100
blocksize=1024
prebuffer=20

[sblaster]
sbtype=${sound ? "sb16" : "none"}
oplmode=auto

[render]
aspect=false

[autoexec]
mount c .
c:
SW.BAT ${extra}
`;
}

export const DOSBOX_CONF = dosboxConf();
