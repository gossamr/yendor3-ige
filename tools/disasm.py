"""Segment-aware disassembler for REGISTER.EXE.

The game is a real-mode 16-bit program in a large/huge memory model, so its
code lives in many segments and every far call carries a segment value that the
loader relocates. Working in *image* coordinates (bytes from the start of the
load image, i.e. file offset minus the 16 KB header) makes those far calls
followable: a far call to `seg:off` lands at image offset `seg * 16 + off`.

    python tools/disasm.py 0x1e5:6 --count 80     # follow a far call
    python tools/disasm.py 0x1e56 --count 40      # an image address
    python tools/disasm.py 0x5e56 --file          # a raw file offset
    python tools/disasm.py 0x1d737 --around       # decode *through* an address

An address with no `seg:off` and no `--file` is an image address, which is what
docs/, tools/xref.py and every far-call target quote. Both are printed on every
line, image first and the file offset after an `f`, so a run that came out
somewhere unexpected says so.

`--around` is the one to reach for when the address came from a cross
reference rather than from a call: see `Exe.aligned_start`.
"""

from __future__ import annotations

from pathlib import Path

from capstone import CS_ARCH_X86, CS_MODE_16, Cs

from mz import HEADER, Image  # noqa: F401, re-exported for callers


class Exe(Image):
    """An Image that can also disassemble. capstone is needed for this and
    nothing else, which is why the reading and the relocation table live in
    mz.py, which tools/patch.py imports without it."""

    def __init__(self, path: str | Path = "game/REGISTER.EXE"):
        super().__init__(path)
        self.md = Cs(CS_ARCH_X86, CS_MODE_16)

    def disasm(self, image: int, count: int = 60):
        start = self.file_of(image)
        blob = self.data[start:start + count * 8 + 16]
        out = []
        for ins in self.md.disasm(blob, image):
            out.append(ins)
            if len(out) >= count:
                break
        return out

    def lands_on(self, start: int, anchor: int) -> bool:
        """Whether a stream read from `start` hits `anchor` exactly."""
        if start < 0:
            return False
        blob = self.data[self.file_of(start):self.file_of(anchor) + 16]
        for ins in self.md.disasm(blob, start):
            if ins.address == anchor:
                return True
            if ins.address > anchor:
                break
        return False

    def converges(self, anchor: int, window: int = 48) -> int:
        """How many of the `window` addresses before `anchor` land on it.

        Reading a 16-bit image from a guessed address is how a decode goes
        wrong: start one byte late and every instruction after it is a
        different instruction. A `test word ptr [0x5df2], 0x8000` read from
        its second byte becomes `push es / pop bp / add [bx+si+0x874], al`,
        and the guard it applies disappears without leaving a hole.

        x86 resynchronizes, though, so a real instruction is an attractor:
        a stream started at the wrong byte falls back onto the real boundaries
        within a few instructions and reaches it anyway. An address inside a
        longer instruction is stepped over instead. On this image a real
        boundary scores in the forties out of 48 and an address inside an
        instruction scores single digits.

        A low score is evidence and not proof. A routine entered only by a far
        call scores 0 where the bytes before it are another routine's `retf`
        and a pad, because every prefix stream steps over its first byte:
        image 0x18D12 is real and scores 0. What corroborates one of those is
        the call that reaches it, not the stream before it.
        """
        return sum(self.lands_on(anchor - back, anchor)
                   for back in range(1, window + 1))

    def aligned_start(self, anchor: int, window: int = 64) -> int | None:
        """The address to read from so a run lands on `anchor`.

        Landing on the anchor is not enough on its own: a stream the game
        never executes can hit it by luck, and then every instruction printed
        *before* it is invented. So this takes the furthest start that both
        reaches the anchor and is corroborated, meaning streams of its own
        converge on it too. Where nothing clears that it falls back to the
        best-corroborated start, which is still better than the furthest.
        """
        reaching = [anchor - back for back in range(1, window)
                    if self.lands_on(anchor - back, anchor)]
        if not reaching:
            return None
        sure = [start for start in reaching
                if self.converges(start) >= window // 3]
        return min(sure) if sure else max(reaching, key=self.converges)

    def around(self, anchor: int, before: int = 24, count: int = 40) -> None:
        """Disassemble through `anchor`, on the anchor's own boundaries."""
        start = self.aligned_start(anchor, before + 1)
        if start is None:
            print(f"  (nothing within {before} bytes decodes through "
                  f"{anchor:#07x}; it may not be an instruction)")
            start = anchor
        self.show(start, count)

    def show(self, image: int, count: int = 60) -> None:
        for ins in self.disasm(image, count):
            f = self.file_of(ins.address)
            tag = " <RELOC>" if self.touches_reloc(f, ins.size) else ""
            target = ""
            if ins.mnemonic == "lcall" and "," in ins.op_str:
                # capstone prints far targets as "seg, off", matching the
                # encoding (9A off16 seg16). Reading them the other way round
                # yields off*16+seg, which lands in the middle of an unrelated
                # function and looks plausible enough to follow for a while.
                try:
                    seg, off = (int(x, 0) for x in ins.op_str.split(","))
                    at = self.image_of(seg, off)
                    target = f"   -> image {at:#07x} (file {self.file_of(at):#07x})"
                except ValueError:
                    pass
            print(f"  {ins.address:05x} f{f:06x}  {ins.bytes.hex():<20} "
                  f"{ins.mnemonic} {ins.op_str}{tag}{target}")


def parse_where(arg: str, file_offset: bool = False) -> int:
    """The image address `arg` names.

    `seg:off` is a far pointer, the form a far call carries. A bare number is
    an image address, the form docs/ and tools/xref.py quote, unless
    `file_offset` says it counts from the start of the file instead.
    """
    if ":" in arg:
        seg, off = (int(p, 0) for p in arg.split(":"))
        return Exe.image_of(seg, off)
    value = int(arg, 0)
    return value - HEADER if file_offset else value


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("where", help="seg:off, or an image address")
    ap.add_argument("--count", type=int, default=60)
    ap.add_argument("--around", action="store_true",
                    help="decode through `where` rather than from it")
    ap.add_argument("--before", type=int, default=24,
                    help="with --around, how far back to look for the start")
    ap.add_argument("--file", action="store_true",
                    help="read `where` as a file offset, not an image address")
    ap.add_argument("--exe", default="game/REGISTER.EXE")
    a = ap.parse_args()
    exe = Exe(a.exe)
    if a.around:
        exe.around(parse_where(a.where, a.file), a.before, a.count)
    else:
        exe.show(parse_where(a.where, a.file), a.count)
