"""Every place the game draws a picture, and which one it draws there.

`PICTURES.VGA` is ten runs of pictures and nothing in the file says what any
one of them is ([pictures.md](../docs/pictures.md)). A picture is identified by
whatever names it, and most of the game's artwork is named by a record: an item
points at its icon, an enemy at its sprite, a terrain id at its wall face. What
is left over is named at the call site instead, by a literal.

The draw takes two words. `DS:0x0FC5` selects the run, as an offset into the
sixteen-byte run table at `DS:0x7B5C`, so the run is that offset over sixteen.
`DS:0x0FC3` is the picture inside it. This finds every write of a literal to
the first and reports the second where that is a literal too:

    mov word ptr [0xfc5], 0x60      ; run 6
    ...
    mov word ptr [0xfc3], 7         ; picture 7

A site that loads `DS:0x0FC3` from a register instead is one where a record or
a variable names the picture, and it is reported with no number rather than
dropped, because that is the question a caller usually wants answered: whether
this site draws one fixed picture or many.

    python tools/picture_sites.py            # every site, by run
    python tools/picture_sites.py --run 0    # one run
    python tools/picture_sites.py --literals # only the sites with a number
"""

from __future__ import annotations

import argparse
import bisect
import struct
from collections import defaultdict

from disasm import Exe

# `mov word ptr [DS:addr], imm16` for the two words the blitter reads.
SELECT_RUN = b"\xc7\x06\xc5\x0f"
SELECT_PICTURE = b"\xc7\x06\xc3\x0f"
# `mov [0xfc3], ax`, which is a picture the routine worked out.
PICTURE_FROM_AX = b"\xa3\xc3\x0f"

RUN_STRIDE = 16

# How far past the run selection to look for the picture. Every site that sets
# both has them within this many bytes; past it the picture belongs to another
# draw.
WINDOW = 64

# How much of the code around a hit has to decode through it before the hit
# reads as a real instruction rather than as bytes inside a longer one.
# `Exe.converges` scores out of WINDOW.
SURE = WINDOW // 3


def selections(exe: Exe) -> list[tuple[int, int]]:
    """(image address, run) for every write of a run offset, in address order."""
    data, base = exe.data, exe.file_of(0)
    out = []
    at = data.find(SELECT_RUN)
    while at >= 0:
        offset = struct.unpack_from("<H", data, at + 4)[0]
        if offset % RUN_STRIDE == 0:
            out.append((at - base, offset // RUN_STRIDE))
        at = data.find(SELECT_RUN, at + 1)
    return sorted(out)


def sites(exe: Exe) -> dict[int, list[dict]]:
    """Run number -> the sites that select it, each with its picture or None."""
    data, base = exe.data, exe.file_of(0)
    found: dict[int, list[dict]] = defaultdict(list)
    for at, run in selections(exe):
        window = data[base + at + 6:base + at + 6 + WINDOW]
        literal = window.find(SELECT_PICTURE)
        register = window.find(PICTURE_FROM_AX)
        picture = None
        if literal >= 0 and (register < 0 or literal < register):
            picture = struct.unpack_from("<H", window, literal + 4)[0]
        found[run].append({"at": at, "picture": picture})
    return dict(found)


def paired(exe: Exe, runs) -> dict[int, set[int]]:
    """Run -> every picture a literal names under it, by nearest selection.

    A routine may select its run well before it names a picture, and a few do:
    the clue book's own backdrop goes through `DS:0x0E98` and the tile passes
    set a run once and then walk. So each `mov [0xfc3], imm16` is paired with
    the **nearest selection before it** rather than with one inside a fixed
    window. That pairs across a routine boundary now and then, which is what
    the range check is for: a picture the run does not hold was paired with the
    wrong selection and is dropped.
    """
    data, base = exe.data, exe.file_of(0)
    starts = selections(exe)
    addresses = [a for a, _ in starts]
    out: dict[int, set[int]] = defaultdict(set)
    at = data.find(SELECT_PICTURE)
    while at >= 0:
        image = at - base
        if exe.converges(image, WINDOW) >= SURE:
            where = bisect.bisect_right(addresses, image) - 1
            if where >= 0:
                run = starts[where][1]
                picture = struct.unpack_from("<H", data, at + 4)[0]
                if run < len(runs) and picture < runs[run].count:
                    out[run].add(picture)
        at = data.find(SELECT_PICTURE, at + 1)
    return dict(out)


def literals(exe: Exe) -> dict[int, set[int]]:
    """Run number -> the pictures the code names outright."""
    return {run: {s["picture"] for s in found if s["picture"] is not None}
            for run, found in sites(exe).items()}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", type=int, help="only this run")
    ap.add_argument("--literals", action="store_true",
                    help="skip the sites whose picture is not a literal")
    args = ap.parse_args()

    exe = Exe()
    found = sites(exe)
    for run in sorted(found):
        if args.run is not None and run != args.run:
            continue
        rows = found[run]
        named = [r for r in rows if r["picture"] is not None]
        print(f"run {run}: {len(rows)} sites, {len(named)} name a picture "
              f"-> {sorted({r['picture'] for r in named})}")
        for row in rows:
            if row["picture"] is None:
                if not args.literals:
                    print(f"    {row['at']:#07x}  from a record or a variable")
            else:
                print(f"    {row['at']:#07x}  picture {row['picture']}")


if __name__ == "__main__":
    main()
