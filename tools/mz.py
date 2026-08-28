"""The parts of an MZ executable a patch has to respect, without a disassembler.

Split out of disasm.py so that patching, which only reads bytes and the
relocation table, does not pull in capstone. tools/disasm.py adds the
disassembly on top of this.

Coordinates: *image* offsets count from the start of the load image (file
offset minus the header), which is what a far call's `seg:off` resolves
against. File offsets count from the start of the file.
"""

from __future__ import annotations

import struct
from pathlib import Path

HEADER = 0x400 * 16  # e_cparhdr paragraphs


class Image:
    def __init__(self, path: str | Path = "game/REGISTER.EXE"):
        self.data = Path(path).read_bytes()
        self.relocs = self._relocations()

    def _relocations(self) -> set[int]:
        """File offsets of the words the loader rewrites at load time.

        A patch must never land on one of these: whatever we write would be
        overwritten with a fixed-up segment value when the program starts.
        """
        count = struct.unpack_from("<H", self.data, 6)[0]
        table = struct.unpack_from("<H", self.data, 0x18)[0]
        out = set()
        for i in range(count):
            off, seg = struct.unpack_from("<HH", self.data, table + i * 4)
            out.add(HEADER + seg * 16 + off)
        return out

    @staticmethod
    def image_of(seg: int, off: int) -> int:
        return seg * 16 + off

    @staticmethod
    def file_of(image: int) -> int:
        return HEADER + image

    def touches_reloc(self, file_off: int, size: int) -> bool:
        return any(file_off <= r < file_off + size for r in self.relocs)
