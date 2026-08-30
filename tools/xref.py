#!/usr/bin/env python3
"""Find every instruction that touches a given struct offset.

The game keeps a monster, an item or a character in a struct and reads its
fields as `[si+0x5e]`, `[bx+0x5e]` and so on, so the question "what is offset
44 of the enemy record?" becomes "what does the code do with `[reg+0x5e]`?"
-- the in-memory monster struct sits 50 bytes before the record's own origin.

A 16-bit real-mode image cannot be disassembled linearly: data sits between
functions and a byte inside one instruction decodes as another. So this reads
every offset as if an instruction started there, a superset disassembly,
and keeps the ones whose operand names the displacement. That yields false
starts, which is why each hit is printed with the bytes it decoded from: a hit
whose neighbors make no sense is one of them.

    PYTHONPATH=tools python tools/xref.py 0x5e
    PYTHONPATH=tools python tools/xref.py 0x5e --reg si --context 6
"""

from __future__ import annotations

import re
import sys

from capstone import CS_ARCH_X86, CS_MODE_16, Cs

from disasm import Exe
from mz import HEADER

BASES = ("bx", "si", "di", "bp")

# The monster struct the combat code walks is the 106-byte record copied to an
# origin 50 bytes earlier, so record offset N is struct offset N + 50.
RECORD_TO_STRUCT = 50

# Opcodes that read or write a field: the moves, the comparisons, the
# arithmetic and the bit tests. A superset disassembly of a real-mode image is
# mostly noise, and nearly all of it decodes from bytes that are not code at
# all: runs of zeros as `add byte ptr [bx+N], bl`, ASCII as `or`, `sbb` and
# `adc`, x87 opcodes the game does not use. Requiring a first byte from this
# list drops those without dropping any way the game actually reads a struct.
OPCODES = {
    0x01, 0x03, 0x09, 0x0B, 0x21, 0x23, 0x29, 0x2B, 0x31, 0x33, 0x39, 0x3B,
    0x80, 0x81, 0x83, 0x84, 0x85, 0x88, 0x89, 0x8A, 0x8B, 0x8D,
    0xC6, 0xC7, 0xF6, 0xF7, 0xFE, 0xFF,
}
PREFIXES = {0x26, 0x2E, 0x36, 0x3E, 0xF2, 0xF3}


def find(exe: Exe, disp: int, regs=BASES) -> list[tuple[int, str, str]]:
    """(image address, mnemonic, operands) for every decode touching `+disp`.

    A field access names one base register, so the two-register forms
    (`[bx+si+N]` and friends) are excluded: they are how a *table* is
    indexed, not how a struct field is read, and they are where most of the
    surviving noise decodes to. What survives that is then held to
    `Exe.aligned_start`: a hit no surrounding stream decodes through is a hit
    inside some longer instruction, and reading it is how a guard that is
    plainly there gets missed.
    """
    md = Cs(CS_ARCH_X86, CS_MODE_16)
    data = exe.data[HEADER:]
    want = re.compile(r"\[(%s) \+ %s\]" % ("|".join(regs), hex(disp)))
    out = []
    for start in range(len(data) - 8):
        at = start
        while data[at] in PREFIXES:
            at += 1
        if data[at] not in OPCODES:
            continue
        for addr, _size, mnem, ops in md.disasm_lite(data[start:start + 8], start, 1):
            if disp and want.search(ops):
                out.append((addr, mnem, ops))
    # A segment-prefixed instruction is found twice, once at the prefix and
    # once at the opcode after it. The prefixed decode is the real one.
    at = {a for a, _, _ in out}
    out = [(a, m, o) for a, m, o in out
           if not (a - 1 in at and data[a - 1] in PREFIXES)]
    # And a hit is only worth reading if the code around it decodes *through*
    # it. Without that test a hit can sit inside a longer instruction, where
    # the bytes read as something the game never executes.
    return [(a, m, o) for a, m, o in out if exe.aligned_start(a) is not None]


def main(argv: list[str]) -> int:
    disp = int(argv[0], 0)
    regs = BASES
    context = 0
    for i, a in enumerate(argv):
        if a == "--reg":
            regs = (argv[i + 1],)
        if a == "--context":
            context = int(argv[i + 1], 0)
    exe = Exe("game/REGISTER.EXE")
    hits = find(exe, disp, regs)
    print(f"{len(hits)} instructions touch +{disp:#x} "
          f"(record offset {disp - RECORD_TO_STRUCT} if this is a monster)")
    for addr, mnem, ops in hits:
        print(f"  {addr:#07x}  {mnem} {ops}")
        if context:
            # Through the hit, never merely from near it.
            exe.around(addr, context * 3, context * 2)
            print()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
