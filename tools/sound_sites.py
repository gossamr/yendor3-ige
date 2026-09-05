"""Every place the game plays a sound or a song, and what it plays there.

[audio.md](../docs/audio.md) names the entries. Three of them take a sound
index in `ax`, one takes a song index, and the rest of the bank is reached by a
record field or by the ambient table. This finds the call sites of all four and
the literal each is handed, so the list is the executable's rather than a
transcription of it.

A 16-bit image cannot be disassembled linearly, since data sits between
functions and a byte inside one instruction decodes as another. So this reads
every offset as if an instruction began there, the superset disassembly
[xref.py](xref.py) uses, and keeps the far calls whose target is one of the
entries. A call reached that way is real: a five-byte `lcall` landing exactly
on an audio entry is not something a misaligned read invents.

What feeds the call is then read backward. `mov ax, imm16` within a short
window and with nothing in between that writes `ax` is the literal; anything
else is a value the routine worked out, which is a record field or a variable
and is named in `docs/audio.md` rather than here.

    python tools/sound_sites.py                 # every site, by what it plays
    python tools/sound_sites.py --index 3       # the sites that play one sound
    python tools/sound_sites.py --unnamed       # the sites no routine is named for
"""

from __future__ import annotations

import argparse
from collections import defaultdict

from capstone import CS_ARCH_X86, CS_MODE_16, Cs

from disasm import Exe

# The entries, by what handing them a number means. docs/audio.md, "Playing a
# song" and "Playing a sound".
PLAY_SOUND = 0x18648          # the index in ax, straight to the driver
WAIT_WRAPPER = 0x0C6D8        # the index in ax, 6 ticks where sound is off
CAST_WRAPPER = 0x1D91F        # the same, on the cast's own path
PLAY_SONG = 0x184CC           # a song number in ax
STOP_SONG = 0x186EB
CUT_SOUND = 0x186D8           # cuts whatever is playing short
WAIT_SOUND = 0x184B4          # spins until the current sound ends

SOUND_ENTRIES = {PLAY_SOUND: "sound", WAIT_WRAPPER: "sound", CAST_WRAPPER: "sound"}
ENTRIES = SOUND_ENTRIES | {
    PLAY_SONG: "song", STOP_SONG: "stop song",
    CUT_SOUND: "cut sound", WAIT_SOUND: "wait",
}

# How far back to look for the `mov ax, imm16` that feeds a call. Every site
# that has one has it within this many bytes; past that the value came from
# somewhere else.
LOOK_BACK = 24

LCALL = 0x9A
LCALL_BYTES = 5


def sites(exe: Exe) -> list[dict]:
    """Every far call landing on one of the entries, with what feeds it."""
    md = Cs(CS_ARCH_X86, CS_MODE_16)
    data = exe.data
    found = []
    for at in range(len(data) - LCALL_BYTES):
        if data[at] != LCALL:
            continue
        off = int.from_bytes(data[at + 1:at + 3], "little")
        seg = int.from_bytes(data[at + 3:at + 5], "little")
        target = Exe.image_of(seg, off)
        if target not in ENTRIES:
            continue
        image = at - exe.file_of(0)
        found.append({"at": image, "target": target, "kind": ENTRIES[target],
                      "index": feeds(md, exe, image)})
    return found


def feeds(md: Cs, exe: Exe, call: int) -> int | None:
    """The literal in `ax` at a call, or None where it is not a literal.

    Read from the furthest start that decodes through the call itself, so the
    instructions between are the ones the processor runs rather than whatever
    a misaligned read produces.
    """
    start = exe.aligned_start(call, LOOK_BACK)
    if start is None:
        return None
    blob = exe.data[exe.file_of(start):exe.file_of(call)]
    value = None
    for ins in md.disasm(blob, start):
        text = f"{ins.mnemonic} {ins.op_str}"
        if text.startswith("mov ax, 0x") or text.startswith("mov ax, ") and text[8:].isdigit():
            try:
                value = int(ins.op_str.split(", ")[1], 0)
            except ValueError:
                value = None
        # Anything else that writes ax throws the literal away.
        elif ins.op_str.startswith("ax") and ins.mnemonic not in ("cmp", "test", "push"):
            value = None
    return value


def by_index(found: list[dict]) -> dict[int, list[int]]:
    """Sound index -> the sites that play it as a literal."""
    out: dict[int, list[int]] = defaultdict(list)
    for one in found:
        if one["kind"] == "sound" and one["index"]:
            out[one["index"]].append(one["at"])
    return {n: sorted(set(v)) for n, v in sorted(out.items())}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--exe", default="game/REGISTER.EXE")
    p.add_argument("--index", type=int, help="only the sites playing this sound")
    p.add_argument("--unnamed", action="store_true",
                   help="only the sites whose value is not a literal")
    args = p.parse_args()

    exe = Exe(args.exe)
    found = sites(exe)
    kinds = defaultdict(int)
    for one in found:
        kinds[one["kind"]] += 1

    if args.index:
        for at in by_index(found).get(args.index, []):
            print(f"  {at:#07x}")
        return
    if args.unnamed:
        for one in found:
            if one["kind"] == "sound" and not one["index"]:
                print(f"  {one['at']:#07x}  -> {one['target']:#07x}")
        return

    print(f"{len(found)} call sites: "
          + ", ".join(f"{n} {k}" for k, n in sorted(kinds.items())))
    table = by_index(found)
    literal = sum(len(v) for v in table.values())
    worked = sum(1 for o in found if o["kind"] == "sound" and not o["index"])
    print(f"{literal} play a literal over {len(table)} sounds; "
          f"{worked} take a value the routine worked out")
    for n, at in table.items():
        print(f"  sound {n:3d}  {len(at):2d}  "
              + " ".join(f"{a:#07x}" for a in at))
    songs = sorted({o["index"] for o in found
                    if o["kind"] == "song" and o["index"]})
    print(f"  songs played as a literal: {songs}")


if __name__ == "__main__":
    main()
