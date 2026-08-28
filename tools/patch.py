#!/usr/bin/env python3
"""Byte patches for REGISTER.EXE.

The MZ format protects nothing here: `e_csum` is 0 (unused, and DOS ignores it
anyway), the file is not packed and has no overlays, and its length matches the
header exactly. The one structural hazard is the relocation table: the loader
rewrites 4000 words at load time, so a patch must not land on one. Every patch
below is checked against that table before it is applied.

    python tools/patch.py --list
    python tools/patch.py force-skip-intro --out tmp/game-patched
    python tools/patch.py force-skip-intro --out tmp/game-patched --verify

`make patched` builds the set everything else boots against. Rebuilding is
cheap and safe to repeat: the executable is rewritten only when it fails to
verify, and a data file is re-copied only when it is missing or a different
size.

Three recorded facts guard a build, and each catches what the others cannot.
SRC_MD5 is the release these offsets were read from, checked before a byte is
written. BUILD_MD5 is what a finished build hashes to, checked after. And each
patch names the bytes it replaces, which is what says *which* patch is missing
when one is.

Needs the standard library and nothing else. The relocation table is read by
tools/mz.py; capstone is for tools/disasm.py, which reads the game rather than
patching it.
"""

from __future__ import annotations

import hashlib
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mz import HEADER, Image  # noqa: E402

SRC_EXE = Path("game/REGISTER.EXE")

# The release these offsets were read from: Yendorian Tales III v2.00,
# registered, 202,676 bytes. Every patch below names a file offset and the
# bytes it expects to find there, and both are meaningless against a different
# build of the executable (a shareware copy, a later release, an already
# patched one. Checked before anything is written.
SRC_MD5 = "22bc83d3592e68b0b1d5a2462991256d"

# What a finished build hashes to, recorded rather than computed. Computing it
# from whatever source happens to be on disk proves only that patching is
# deterministic: swap the source and the derived digest moves with it, so the
# wrong executable verifies clean. These are the two builds the Makefile makes;
# an ad-hoc combination has no recorded digest and is checked byte by byte.
BUILD_MD5 = {
    ("force-skip-intro", "keep-roll-on-class-change", "no-attract"):
        "feb6d3f80fe9955a45c92531f2c5a03a",
    ("enable-p-switch", "keep-roll-on-class-change", "no-attract"):
        "cff70bbe18f333ce34a273a856fb1749",
}


@dataclass(frozen=True)
class Patch:
    """One byte run, replaced by another of exactly the same length.

    Same length is not a convenience: the file's MZ header records its size,
    the relocation table is indexed by offset, and every near jump is a
    displacement, so anything that moved a byte would have to fix all three.
    Every patch here is therefore a rewrite in place.
    """

    name: str
    file_offset: int
    original: bytes
    replacement: bytes
    why: str

    def __post_init__(self):
        if len(self.original) != len(self.replacement):
            raise ValueError(f"{self.name}: replacement must be the same length")


PATCHES = {
    # The game parses five command-line switches: /P, /B, /W, /NOM and /NOS.
    # /P sets bit 15 of the flag word at [0x536a], and the startup code inside
    # the initialization routine tests exactly that bit and, when set, skips
    # three splash calls and a delay:
    #
    #     0eec9  test word [0x536a], 0x8000
    #     0eecf  jne  0xef32              ; skip the intro
    #     0eed1  lcall 0x10dc:4           ;   splash
    #     0eed6  lcall 0xe72:0x28c        ;   splash
    #     0eee2  lcall 0x1bb7:0xc         ;   splash
    #     0eeee  mov ax, 0x14 / lcall 0x1834:0   ;   delay
    #
    # But the dispatcher clears that same bit before initialization ever runs:
    #
    #     00032  and word [0x536a], 0x7fff
    #
    # so /P can never take effect. Widening the mask to 0xffff makes the AND a
    # no-op and lets the switch work as it was evidently built to.
    #
    # Skipping the intro is not what the flag is for: it has twelve readers,
    # and skipping three splash calls is only the first. Another bypasses
    # "YOUR SKILL IS NOT HIGH ENOUGH!" on training, and under /P walls stop
    # clipping and the party walks through them. That is a debug mode, so a
    # build with it on is not one to play: use force-skip-intro for the
    # intro, in a build meant for a human.
    #
    # It stays useful for driving the game headlessly, which is what
    # `make patched-debug` builds: no-clip walks a capture to a distant cell in
    # a straight line, and the training bypass opens a screen that would
    # otherwise need a party leveled up to earn it. Pair it with /P, and not
    # with force-skip-intro: /P makes the test at 0xeec9 pass, which is the
    # only thing that patch is for.
    "enable-p-switch": Patch(
        name="enable-p-switch",
        file_offset=HEADER + 0x37,
        original=b"\x7f",
        replacement=b"\xff",
        why="stop the dispatcher clearing the /P flag, so `SW.BAT /P` enables debug mode",
    ),
    # The intro skip on its own: turn the conditional jump into an
    # unconditional one, so the branch is taken whether the flag is set or not.
    # Same displacement, so nothing else moves. This is the one to use --
    # enable-p-switch brings the rest of the debug mode with it.
    # (Defined as force-skip-intro at the end of this table.)
    # The main menu runs an attract loop: a countdown at [0x53ee], reloaded to
    # 0x4b each time the menu is drawn and decremented once per timer tick, and
    # when it reaches zero the splash chain and the story intro play again.
    #
    #     0bf32  mov  word [0x53ee], 0x4b      ; reload the countdown
    #     0bf44  test word [0x536a], 0x400     ; a tick?
    #     0bf4a  je   0xbfa3                   ;   no, so go poll input
    #     0bf52  dec  word [0x53ee]
    #     0bf56  cmp  word [0x53ee], 0
    #     0bf5b  jg   0xbfa3                   ; not expired, so go poll input
    #     0bf5d..0bf9b                         ; expired: splashes and intro
    #
    # Making that `jg` unconditional means the expiry path is never taken, so
    # the menu waits indefinitely. The countdown still runs and goes negative,
    # which nothing else reads. Raising the reload constant instead only
    # postpones the problem; this removes it.
    #
    # Not cosmetic: a driver that pauses to look at a screenshot comes back to
    # find the game has wandered off into its own intro, and every keystroke
    # after that goes somewhere unintended.
    "no-attract": Patch(
        name="no-attract",
        file_offset=HEADER + 0xBF5B,
        original=b"\x7f",  # jg
        replacement=b"\xeb",  # jmp
        why="stop the main menu falling into its attract loop after ~30s idle",
    ),
    # Changing a character's class in Character Creation throws the roll away.
    #
    # The point of changing class last is to put a roll you like onto the class
    # that suits it, so this defeats the feature. Measured: a fighter rolled
    # 48/52/55/60/58/57, and picking MAGE turned it into 56/58/48/55/60/50.
    #
    # The class-pick handler stores the class, then rolls and rederives:
    #
    #     140de  mov  si, [0x537c]        ; the character being created
    #     140e2  mov  [si+0xe], ax        ; class = ax
    #     140e5  mov  word [si+0x16], 1   ; level = 1
    #     140ed  test word [0x5370], 0x8000
    #     140f3  jne  0x140fb             ; only from the full creation menu
    #     140fb  call 0x14e20             ;   roll the six attributes
    #     140fe  call 0x13af3             ;   derive the skills from them
    #     14101  lcall 0x649:0xe          ;   redraw
    #
    # `0x14e20` is not only the roll, which is why deleting the call is wrong:
    #
    #     14e38..14eae  six times: mov ax,0xf / lcall rand / add ax,0x2d
    #                              -- 45+rand(15) into both columns
    #     14eaf         health = 25% of stamina           -> [si+0x52]/[si+0x92]
    #     14ec7..14f70  magic points, switched on the class at [si+0x0e]
    #     14f70..14f86  MP -> [si+0x54]/[si+0x94], and [si+0x62]/[si+0xa2]
    #
    # The magic points are what must be recomputed: they are switched on the
    # class, and the skill derivation at `0x13af3` reads the magic column this
    # routine writes, so NOPing the call left a mage with 0 MP and no casting
    # skill. Health is not class-dependent: it is 25% of stamina with no class
    # test, and the dispatch starts after it is stored, so recomputing it
    # from unchanged attributes changes nothing. Only the rolling is unwanted.
    #
    # So the call is retargeted rather than removed: `call 0x14eaf` enters the
    # same routine just past the six rolls, and everything downstream of them
    # runs as before. `SI` is the character being edited, and it holds: the
    # routine called immediately before this one loads it from the same global,
    # `[0x537c]`, and this compiler treats SI as callee-saved.
    #
    # Three bytes for three bytes: only the displacement changes, so nothing
    # moves and the other two callers of 0x14e20 (Roll Attributes, and setting
    # up a new character) still roll.
    "keep-roll-on-class-change": Patch(
        name="keep-roll-on-class-change",
        file_offset=HEADER + 0x140FB,
        original=b"\xe8\x22\x0d",   # call 0x14e20, roll then derive
        replacement=b"\xe8\xb1\x0d",  # call 0x14eaf, derive only
        why="changing class in Character Creation keeps the roll you already made",
    ),
    "force-skip-intro": Patch(
        name="force-skip-intro",
        file_offset=HEADER + 0xEECF,
        original=b"\x75",  # jne
        replacement=b"\xeb",  # jmp
        why="always take the intro-skip branch, switch or not",
    ),
}


def md5(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def recorded_md5(names: list[str]) -> str | None:
    """The digest a build of these patches must have, or None if unrecorded."""
    return BUILD_MD5.get(tuple(sorted(names)))


def patched_bytes(names: list[str], src: Path,
                  expect_src_md5: str | None = SRC_MD5) -> tuple[bytes, list[Patch]]:
    """The executable these patches produce, without writing anything.

    Three checks, in the order that gives the most useful failure. The source
    must be the release the offsets were read from; each patch must sit outside
    the relocation table; and each must find the bytes it claims to replace.
    Pass expect_src_md5=None to patch a file that is deliberately not the
    release, a test fixture say.
    """
    exe = Image(src)
    data = bytearray(exe.data)
    if expect_src_md5 is not None:
        got = md5(bytes(data))
        if got != expect_src_md5:
            raise SystemExit(
                f"{src}: md5 {got}, expected {expect_src_md5}. These patches "
                f"are for Yendorian Tales III v2.00 registered and describe "
                f"byte offsets in that executable; they are not safe to apply "
                f"to a different one.")
    done = []
    for name in names:
        p = PATCHES[name]
        size = len(p.original)
        if exe.touches_reloc(p.file_offset, size):
            raise SystemExit(f"{name}: {p.file_offset:#x} is a relocation target")
        actual = bytes(data[p.file_offset:p.file_offset + size])
        if actual != p.original:
            raise SystemExit(
                f"{name}: expected {p.original.hex()} at {p.file_offset:#x}, "
                f"found {actual.hex()}")
        data[p.file_offset:p.file_offset + size] = p.replacement
        done.append(p)
    return bytes(data), done


def expected_md5(names: list[str], src: Path = SRC_EXE) -> str:
    """What a build of these patches would hash to, computed from `src`.

    Only a cross-check on the recorded digest, and only meaningful because the
    source is verified first: on its own it is circular, since a build made
    from the wrong source would agree with a digest derived from that same
    source. BUILD_MD5 is the authority.
    """
    return md5(patched_bytes(names, src)[0])


def check(names: list[str], exe_path: Path) -> list[str]:
    """Everything wrong with this build, as a list of reasons. Empty is good.

    Three independent checks rather than one, because each catches what the
    others cannot. The recorded digest is the only one that can tell a build of
    the right release from a convincing build of the wrong one. Hashing catches
    damage anywhere in the file, which reading the patch sites cannot. Reading
    the patch sites says which patch is missing, which a digest cannot, and is
    the only check available for a combination with no recorded digest.
    """
    if not exe_path.exists():
        return [f"{exe_path}: not there"]
    data = exe_path.read_bytes()
    problems = []

    want = recorded_md5(names)
    got = md5(data)
    if want is None:
        problems.append(f"no recorded digest for {' '.join(sorted(names))}"
                        f", checked byte by byte only")
    elif got != want:
        problems.append(f"md5 {got}, expected {want}")

    for name in names:
        p = PATCHES[name]
        at = data[p.file_offset:p.file_offset + len(p.replacement)]
        if at != p.replacement:
            problems.append(
                f"{name}: {p.file_offset:#08x} holds {at.hex() or '(past the end)'}, "
                f"expected {p.replacement.hex()}")
    return problems


def verify(names: list[str], exe_path: Path, src: Path = SRC_EXE) -> bool:
    """Is this executable exactly the one these patches produce?

    A rebuild only has to re-patch when this is False, and it does not care how
    or when the file got that way. An unrecorded combination passes on its
    patch sites alone: there is no digest to hold it to.
    """
    problems = check(names, exe_path)
    if recorded_md5(names) is None:
        problems = [p for p in problems if not p.startswith("no recorded digest")]
    return not problems


def apply(names: list[str], src: Path, dst_exe: Path) -> list[Patch]:
    data, done = patched_bytes(names, src)
    want = recorded_md5(names)
    got = md5(data)
    if want is not None and got != want:
        raise SystemExit(
            f"refusing to write {dst_exe}: patching {src} gave md5 {got}, but a "
            f"build of {' '.join(sorted(names))} must be {want}. Either a patch "
            f"changed without its digest in BUILD_MD5 being updated, or the "
            f"source is not the executable it claims to be.")
    dst_exe.write_bytes(data)
    return done


def build_game_dir(names: list[str], game: Path, out: Path) -> Path:
    """A complete game directory with a patched executable.

    Idempotent, and cheap when there is nothing to do: a data file is copied
    only when it is missing or a different size, and the executable is patched
    only when it does not already carry these patches. Nothing in the output
    directory is deleted, so a file that exists only there (a save, say)
    survives a rebuild.
    """
    out.mkdir(parents=True, exist_ok=True)
    for f in game.iterdir():
        if f.is_file() and f.name != "REGISTER.EXE":
            target = out / f.name
            if not target.exists() or target.stat().st_size != f.stat().st_size:
                shutil.copy2(f, target)
    if verify(names, out / "REGISTER.EXE", game / "REGISTER.EXE"):
        return out
    apply(names, game / "REGISTER.EXE", out / "REGISTER.EXE")
    return out


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("patches", nargs="*", help="patch names to apply")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--verify", action="store_true",
                    help="report whether --out already carries these patches, "
                         "and change nothing; exits 1 if it does not")
    ap.add_argument("--game", default="game")
    ap.add_argument("--out", default="tmp/game-patched")
    a = ap.parse_args()

    if a.list or not a.patches:
        for p in PATCHES.values():
            print(f"{p.name:<22} {p.file_offset:#08x}: "
                  f"{p.original.hex():<8} -> {p.replacement.hex():<8}  {p.why}")
        raise SystemExit(0)

    out = Path(a.out)
    src = Path(a.game) / "REGISTER.EXE"
    already = verify(a.patches, out / "REGISTER.EXE", src)

    if a.verify:
        exe = out / "REGISTER.EXE"
        print(f"{out}: {'patched' if already else 'not patched'}")
        print(f"  source   {md5(src.read_bytes())}"
              f"{'' if md5(src.read_bytes()) == SRC_MD5 else f' (expected {SRC_MD5})'}")
        print(f"  recorded {recorded_md5(a.patches) or '(none for this combination)'}")
        print(f"  build    {md5(exe.read_bytes()) if exe.exists() else '(no executable)'}")
        for problem in check(a.patches, exe):
            print(f"  - {problem}")
        raise SystemExit(0 if already else 1)

    build_game_dir(a.patches, Path(a.game), out)
    if already:
        print(f"already patched: {out}")
    else:
        for name in a.patches:
            p = PATCHES[name]
            print(f"applied {p.name}: {p.file_offset:#08x} "
                  f"{p.original.hex()} -> {p.replacement.hex()}")
        print(f"patched game directory: {out}")
