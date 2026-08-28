"""Segment-aware disassembler for REGISTER.EXE.

The game is a real-mode 16-bit program in a large/huge memory model, so its
code lives in many segments and every far call carries a segment value that the
loader relocates. Working in *image* coordinates (bytes from the start of the
load image, i.e. file offset minus the 16 KB header) makes those far calls
followable: a far call to `seg:off` lands at image offset `seg * 16 + off`.

    python tools/disasm.py 0x1e5:6 --count 80     # follow a far call
    python tools/disasm.py 0x5e56 --count 40      # or a raw file offset
    python tools/disasm.py 0x1d737 --around       # decode *through* an address

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

    def aligned_start(self, anchor: int, window: int = 64) -> int | None:
        """The earliest address that decodes *through* `anchor`.

        Reading a 16-bit image from a guessed address is how a decode goes
        wrong: start one byte late and every instruction after it is a
        different instruction, for as long as it takes the stream to
        resynchronise. A `test word ptr [0x5df2], 0x8000` read from its second
        byte becomes `push es / pop bp / add byte ptr [bx+si+0x874], al`, and
        the guard it applies disappears without leaving a hole.

        Given an address that *is* an instruction (one an xref found, say)
        this walks back and keeps the furthest start whose stream lands on it
        exactly. Everything printed from there is then on the same boundaries
        the anchor is.
        """
        best = None
        for back in range(1, window):
            start = anchor - back
            if start < 0:
                break
            blob = self.data[self.file_of(start):self.file_of(anchor) + 16]
            for ins in self.md.disasm(blob, start):
                if ins.address == anchor:
                    best = start
                    break
                if ins.address > anchor:
                    break
        return best

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


def parse_where(arg: str) -> int:
    """Accept `seg:off` (far pointer) or a bare file offset."""
    if ":" in arg:
        seg, off = (int(p, 0) for p in arg.split(":"))
        return Exe.image_of(seg, off)
    value = int(arg, 0)
    return value - HEADER if value >= HEADER else value


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("where", help="seg:off, or a file offset")
    ap.add_argument("--count", type=int, default=60)
    ap.add_argument("--around", action="store_true",
                    help="decode through `where` rather than from it")
    ap.add_argument("--before", type=int, default=24,
                    help="with --around, how far back to look for the start")
    ap.add_argument("--exe", default="game/REGISTER.EXE")
    a = ap.parse_args()
    exe = Exe(a.exe)
    if a.around:
        exe.around(parse_where(a.where), a.before, a.count)
    else:
        exe.show(parse_where(a.where), a.count)
