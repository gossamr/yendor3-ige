#!/usr/bin/env python3
"""Which offsets of a saved game the executable reads or writes, all at once.

A save is 81,037 bytes and rebuilding one means knowing what every byte of it
is for. [saves.md](../docs/saves.md) names the fields that have been read so
far; this says, for each of the 1,000 offsets the roster is made of, whether
any instruction in `REGISTER.EXE` touches it and which ones.

Two shapes reach the roster, and this scans for both:

* **A character record** is a pointer with a displacement. `DS:0x537C` holds
  the acting character and the code reads `[si+0x52]`, `[bx+0x16]` and so on,
  which is what [xref.py](xref.py) finds one displacement at a time.
* **The header slot** is the party's own state at a fixed address. The roster
  sits at `DS:0xCEDD`, so header offset *n* is the absolute `DS:0xCEDD + n`.

`xref.find` sweeps the whole image for one displacement. Asking it 500
questions means 500 passes, so this decodes each start once and buckets the
hit by the displacement it names. The same superset disassembly and the same
opcode filter: every offset is read as if an instruction began there, and a
first byte outside the read-or-write set is dropped.

**A miss is not an unused byte.** An offset reached by adding a constant to
the pointer first, indexed through a register pair, or copied whole by a
`rep movsw` names no displacement and lands in no bucket. `saves.md` says
which fields are known to be reached that way.

    PYTHONPATH=tools python tools/save_coverage.py             # both, by offset
    PYTHONPATH=tools python tools/save_coverage.py --header    # the party's own
    PYTHONPATH=tools python tools/save_coverage.py --character # a character's
    PYTHONPATH=tools python tools/save_coverage.py --at 94     # one offset's sites
    PYTHONPATH=tools python tools/save_coverage.py --json      # for a tool
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict

from capstone import CS_ARCH_X86, CS_MODE_16, Cs

import save_map as M
import saves as S
from disasm import Exe
from mz import HEADER
from xref import BASES, OPCODES, PREFIXES, WINDOW

# The roster's own address, which the header slot starts at.
ROSTER_DS = 0xCEDD

# `[reg + 0xNN]` and an absolute `[0xNNNN]`, as Capstone prints them.
FIELD = re.compile(r"\[(%s) \+ (0x[0-9a-f]+)\]" % "|".join(BASES))
ABSOLUTE = re.compile(r"\[(0x[0-9a-f]+)\]")

# A store puts the memory operand first, ahead of the comma. `cmp` and `test`
# read both sides whichever way round they are printed, and `lea` takes the
# address rather than what is at it.
READ_ONLY = {"cmp", "test", "lea"}


def _kind(mnemonic: str, operands: str) -> str:
    """`write` where the instruction stores into the memory operand.

    Capstone prints a size ahead of the brackets, `mov word ptr [0xcf01], ax`,
    so the test is which side of the comma the brackets fall on.
    """
    if mnemonic in READ_ONLY:
        return "read"
    first = operands.split(",")[0]
    return "write" if "[" in first else "read"


def scan(exe: Exe) -> tuple[dict[int, list], dict[int, list]]:
    """(character offset -> sites, header offset -> sites), one pass.

    A site is `(image address, mnemonic, operands, score)`, the same tuple
    `xref.find` returns, with `score` the `Exe.converges` corroboration.
    """
    md = Cs(CS_ARCH_X86, CS_MODE_16)
    data = exe.data[HEADER:]
    slot = S.ROSTER_SLOT
    character: dict[int, list] = defaultdict(list)
    header: dict[int, list] = defaultdict(list)
    prefixed: set[int] = set()

    for start in range(len(data) - 8):
        at = start
        while data[at] in PREFIXES:
            at += 1
        if data[at] not in OPCODES:
            continue
        for address, _size, mnemonic, operands in md.disasm_lite(
                data[start:start + 8], start, 1):
            if address - 1 in prefixed:
                break
            if data[start] in PREFIXES:
                prefixed.add(address)
            field = FIELD.search(operands)
            if field:
                offset = int(field.group(2), 16)
                if offset < slot:
                    character[offset].append((address, mnemonic, operands))
                break
            absolute = ABSOLUTE.search(operands)
            if absolute:
                where = int(absolute.group(1), 16) - ROSTER_DS
                if 0 <= where < slot:
                    header[where].append((address, mnemonic, operands))
            break

    def scored(found):
        return {off: sorted(((a, m, o, exe.converges(a, WINDOW))
                             for a, m, o in sites),
                            key=lambda hit: (-hit[3], hit[0]))
                for off, sites in sorted(found.items())}

    return scored(character), scored(header)


def named(which: str) -> dict[int, str]:
    """Offset -> the name the layout already has for it.

    [save_map.py](save_map.py) holds the two field lists and `save_map._best`
    picks the narrowest one covering an offset, so a byte inside the live block
    reports as `current hit points` rather than as the block. This asks that
    same question per byte rather than keeping a list of its own.
    """
    fields = M.HEADER if which == "header" else M.CHARACTER
    return {offset: name for offset in range(S.ROSTER_SLOT)
            if (name := M._best(fields, offset))}


def report(found: dict[int, list], which: str, sure: int) -> list[str]:
    """One line per offset of the slot, whether or not anything names it."""
    names = named(which)
    lines = []
    for offset in range(S.ROSTER_SLOT):
        sites = [hit for hit in found.get(offset, []) if hit[3] >= sure]
        reads = sum(1 for _, m, o, _ in sites if _kind(m, o) == "read")
        writes = len(sites) - reads
        name = names.get(offset, "")
        if sites or name:
            lines.append(f"{offset:4}  {reads:3} read {writes:3} write  {name}")
    return lines


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--header", action="store_true", help="the party's own slot")
    ap.add_argument("--character", action="store_true", help="a character record")
    ap.add_argument("--at", type=lambda s: int(s, 0), help="one offset's sites")
    ap.add_argument("--sure", type=int, default=WINDOW // 3,
                    help="least corroboration a site needs, out of %d" % WINDOW)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    exe = Exe()
    character, header = scan(exe)
    both = {"character": character, "header": header}
    want = [k for k in ("character", "header")
            if getattr(args, k) or not (args.header or args.character)]

    if args.json:
        print(json.dumps({k: {str(off): [list(h) for h in hits]
                              for off, hits in both[k].items()}
                          for k in want}, separators=(",", ":")))
        return

    for which in want:
        found = both[which]
        if args.at is not None:
            print(f"{which} +{args.at}:")
            for address, mnemonic, operands, score in found.get(args.at, []):
                print(f"    {address:#07x}  {mnemonic} {operands}"
                      f"   ({_kind(mnemonic, operands)}, {score}/{WINDOW})")
            continue
        lines = report(found, which, args.sure)
        touched = len({int(l.split()[0]) for l in lines})
        print(f"--- {which}: {touched} of {S.ROSTER_SLOT} offsets named or touched")
        print("\n".join(lines))


if __name__ == "__main__":
    main()
