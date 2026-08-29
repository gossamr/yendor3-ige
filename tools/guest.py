#!/usr/bin/env python3
"""Find the guest's memory inside an emulator dump, and address into it.

`tools/dump_memory.js` writes the whole wasm heap, 64 MB and most of it the
emulator's own state. DOSBox keeps the guest's RAM as one block inside it, and
where that block lands differs from run to run, so it has to be found rather
than assumed.

The anchor is the BIOS data area, which DOS keeps at guest physical `0x400`:
`0x449` holds the current video mode and `0x463` the CRTC port, which is
`0x3D4` on color hardware. Searching for that pair, with the video mode
sane, has given exactly one candidate on every dump so far, and it can be
checked afterwards: a DOS program's PSP begins with `INT 20h`, sits 256 bytes
before its load image, and must land on a paragraph boundary.

    from guest import Guest
    g = Guest(Path("tmp/memory.bin").read_bytes())
    g.at(0x2F90)          # heap offset of a guest physical address
    g.seg(0x02F9, 0)      # the same, from segment and offset
"""

from __future__ import annotations

from dataclasses import dataclass

BIOS = 0x400
VIDEO_MODE = 0x449       # 0x13 while the game runs; 0x03 at a DOS prompt
CRTC_PORT = 0x463        # 0x3D4 on color hardware
CONVENTIONAL = 0x413     # KB of conventional memory


@dataclass
class Guest:
    """One dump, with the guest's RAM located inside it."""

    heap: bytes
    base: int = -1

    def __post_init__(self):
        if self.base < 0:
            self.base = self.find(self.heap)

    @staticmethod
    def find(heap: bytes) -> int:
        cands = []
        at = 0
        while True:
            at = heap.find(b"\xd4\x03", at)
            if at < 0:
                break
            base = at - CRTC_PORT
            if base >= 0:
                mode = heap[base + VIDEO_MODE]
                kb = int.from_bytes(heap[base + CONVENTIONAL:
                                         base + CONVENTIONAL + 2], "little")
                if mode in (0x03, 0x13) and 100 <= kb <= 640:
                    cands.append(base)
            at += 1
        if not cands:
            raise LookupError("no BIOS data area in this dump")
        if len(cands) > 1:
            raise LookupError(f"{len(cands)} candidate guest bases: {cands}")
        return cands[0]

    def at(self, physical: int) -> int:
        """Heap offset of a guest physical address."""
        return self.base + physical

    def seg(self, segment: int, offset: int = 0) -> int:
        return self.at(segment * 16 + offset)

    def read(self, physical: int, length: int) -> bytes:
        at = self.at(physical)
        return self.heap[at:at + length]

    def psp(self) -> int:
        """Guest physical address of the game's PSP, or -1.

        Found from the load image rather than assumed: the image is the
        executable's own bytes, and the PSP is the paragraph-aligned 256 bytes
        before it that start with INT 20h.
        """
        from pathlib import Path
        exe = Path("game/REGISTER.EXE").read_bytes()
        at = self.heap.find(exe[0x14000:0x14000 + 48])
        if at < 0:
            return -1
        image0 = at - 0x10000
        psp = image0 - 0x100
        if self.heap[psp:psp + 2] != b"\xcd\x20":
            return -1
        return psp - self.base


if __name__ == "__main__":
    import sys
    from pathlib import Path

    g = Guest(Path(sys.argv[1] if len(sys.argv) > 1 else "tmp/memory.bin").read_bytes())
    psp = g.psp()
    print(f"guest RAM at heap 0x{g.base:X}")
    print(f"  video mode 0x{g.heap[g.at(VIDEO_MODE)]:02X}, "
          f"{int.from_bytes(g.read(CONVENTIONAL, 2), 'little')} KB conventional")
    if psp >= 0:
        print(f"  PSP at guest 0x{psp:05X}, segment 0x{psp // 16:04X}; "
              f"load image at segment 0x{(psp + 0x100) // 16:04X}")
