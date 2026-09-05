"""Which sound each spell plays, by walking the cast dispatcher.

A spell's sound is not a field of its record. The dispatcher at image `0x1C4E4`
branches on record offset 72 and then on four bits of record 76, and the branch
decides: some play a literal, some read offset 32, 34 or 40, and the
restoratives play nothing at all ([audio.md](../docs/audio.md)).

The record is read into a buffer at `DS:0x5DA6`, so `DS:0x5DEE` is its offset
72 and `DS:0x5DF2` its 76. That is what makes the dispatcher readable: every
test names an offset of the record being cast.

**A cast that does nothing is silent.** Several branches test the damage the
applier at image `0x1D93D` wrote into `DS:0x0F34` and `DS:0x0F36` and leave
without a sound where it is zero, so immunity and a failed roll both come out
quiet. There is no miss sound.

This walks each branch as a graph rather than as a byte range: both arms of a
conditional, the target of an unconditional jump, and into a near call, until
the path returns or leaves the spell region. What it finds is checked against
the three branches read by hand in `docs/audio.md`.

    python tools/spell_sounds.py            # branch -> sound, and the spells
    python tools/spell_sounds.py --spells   # every spell and what it plays
"""

from __future__ import annotations

import argparse
import struct

from capstone import CS_ARCH_X86, CS_MODE_16, Cs

import extract as EX
import sections as S
from disasm import Exe

# The buffer the record being cast is read into, and the two words the
# dispatcher tests, which are its offsets 72 and 76.
RECORD_BUFFER = 0x5DA6
AFFECTS_AT = 0x5DEE
BLOW_AT = 0x5DF2
AFFECTS, BLOW = 72, 76

DISPATCH = 0x1C4E4
# Where the dispatcher gives up and the cast ends, which every branch jumps
# back to. Nothing past it belongs to a branch.
DONE = 0x1C5AF
REGION = (0x1C400, 0x1DA00)

# The entries that take a sound index in ax.
PLAY_SOUND = 0x18648
WRAPPERS = (0x0C6D8, 0x1D91F)
AUDIO = {PLAY_SOUND, *WRAPPERS}

# Image 0x0357E resolves an attack table entry by number, handing back a far
# pointer to it in ax:bx. A branch that hands it a record offset is not playing
# that offset: it is queuing the entry the offset names onto the character's
# own animation slot, and what is heard is the entry's own +0. Image 0x0AEB9
# is the same lookup read the same way on the monster's side.
ATTACK_LOOKUP = 0x0357E
ATTACK_SOUND = 0        # the entry's own first word

LCALL = 0x9A
CONDITIONAL = {
    "je", "jne", "jz", "jnz", "jg", "jge", "jl", "jle", "ja", "jae", "jb",
    "jbe", "js", "jns", "jo", "jno", "jp", "jnp", "jcxz", "loop", "loope",
}

SPELL_RESTORATIVE = 0xC000


def _u16(blob: bytes, at: int) -> int:
    return struct.unpack_from("<H", blob, at)[0]


class Walk:
    """One image, disassembled on demand and followed as a graph."""

    def __init__(self, exe: Exe):
        self.exe = exe
        self.md = Cs(CS_ARCH_X86, CS_MODE_16)

    def far_target(self, at: int) -> int | None:
        data = self.exe.data
        file_at = self.exe.file_of(at)
        if data[file_at] != LCALL:
            return None
        off = int.from_bytes(data[file_at + 1:file_at + 3], "little")
        seg = int.from_bytes(data[file_at + 3:file_at + 5], "little")
        return Exe.image_of(seg, off)

    def sounds(self, entry: int, limit: int = 4000) -> list[dict]:
        """Every audio call reachable from `entry`, with what feeds it."""
        found: list[dict] = []
        seen: set[int] = set()
        todo = [entry]
        while todo:
            at = todo.pop()
            if at in seen or not REGION[0] <= at < REGION[1] or at == DONE:
                continue
            block = self.exe.data[self.exe.file_of(at):self.exe.file_of(at) + limit]
            literal: int | None = None
            record: int | None = None
            for ins in self.md.disasm(block, at):
                if ins.address in seen:
                    break
                seen.add(ins.address)
                text = f"{ins.mnemonic} {ins.op_str}"
                # What is standing in ax when a call lands.
                if text.startswith("mov ax, 0x") or (
                        text.startswith("mov ax, ") and text[8:].isdigit()):
                    literal, record = int(ins.op_str.split(", ")[1], 0), None
                elif text.startswith("mov ax, word ptr [0x5d") \
                        or text.startswith("mov ax, word ptr [0x5e"):
                    record = int(text.split("[")[1].split("]")[0], 0) - RECORD_BUFFER
                    literal = None
                elif ins.op_str.startswith("ax") and ins.mnemonic in ("xor", "sub", "pop"):
                    literal = record = None

                if ins.mnemonic == "lcall":
                    target = self.far_target(ins.address)
                    if target in AUDIO:
                        found.append({"at": ins.address, "literal": literal,
                                      "record": record, "queued": False})
                    elif target == ATTACK_LOOKUP and record is not None:
                        found.append({"at": ins.address, "literal": None,
                                      "record": record, "queued": True})
                    continue
                if ins.mnemonic == "call":
                    try:
                        target = int(ins.op_str, 0)
                    except ValueError:
                        continue
                    if target in AUDIO:
                        found.append({"at": ins.address, "literal": literal,
                                      "record": record, "queued": False})
                    else:
                        todo.append(target)
                    continue
                if ins.mnemonic == "jmp":
                    try:
                        todo.append(int(ins.op_str, 0))
                    except ValueError:
                        pass
                    break
                if ins.mnemonic in CONDITIONAL:
                    try:
                        todo.append(int(ins.op_str, 0))
                    except ValueError:
                        pass
                    continue
                if ins.mnemonic in ("ret", "retf", "iret"):
                    break
        return found


def branches(exe: Exe) -> list[dict]:
    """The dispatcher's own table: which record bit sends a cast where."""
    walk = Walk(exe)
    out: list[dict] = []
    block = exe.data[exe.file_of(DISPATCH):exe.file_of(DISPATCH) + 400]
    field = bit = None
    for ins in walk.md.disasm(block, DISPATCH):
        text = f"{ins.mnemonic} {ins.op_str}"
        if text.startswith(f"test word ptr [{AFFECTS_AT:#x}],"):
            field, bit = AFFECTS, int(text.split(", ")[1], 0)
        elif text.startswith(f"test word ptr [{BLOW_AT:#x}],"):
            field, bit = BLOW, int(text.split(", ")[1], 0)
        elif ins.mnemonic == "jmp" and bit is not None:
            out.append({"field": field, "bit": bit, "at": int(ins.op_str, 0)})
            field = bit = None
        elif ins.mnemonic in ("ret", "retf"):
            break
    return out


# The refusal beep, which several branches reach on the path that turns a cast
# down rather than on the one that spends it. It is not the spell's own sound.
REFUSAL = 3


def plays(exe: Exe) -> list[dict]:
    """Each branch, with the sounds it can reach and the one it leads with.

    A branch can reach several: the refusal beep on the path that turns the
    cast down, and its own sound on the path that spends it. The one that
    counts is the first the branch can reach that is not the beep, since a
    branch plays its own sound before it walks off into whatever it shares
    with the others.
    """
    walk = Walk(exe)
    out = []
    for b in branches(exe):
        heard = sorted(walk.sounds(b["at"]), key=lambda s: s["at"])
        lead = next((s for s in heard if s["literal"] != REFUSAL), None)
        out.append({**b, "sounds": heard, "lead": lead})
    return out


def sound_of(record: bytes, table: list[dict], attacks: list[dict]) -> int:
    """What casting this spell plays, 0 for the families that play nothing.

    A queued lead is an attack table entry rather than a sound: the branch
    hands the record offset to image 0x0357E and drops the entry on the
    character's animation slot, so what is heard is the entry's own sound
    beside the animation it draws over the portrait.
    """
    one = spell_branch(record, table)
    if one is None or one["lead"] is None:
        return 0
    lead = one["lead"]
    if lead["literal"] is not None:
        return lead["literal"]
    if lead["record"] is None:
        return 0
    value = _u16(record, lead["record"])
    if not lead.get("queued"):
        return value
    return attacks[value]["sound"] if value < len(attacks) else 0


def spell_branch(record: bytes, table: list[dict]) -> dict | None:
    """The branch a spell takes, which is the first test its record answers."""
    for one in table:
        word = _u16(record, one["field"])
        if word & one["bit"]:
            return one
    return None


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("game", nargs="?", default="game")
    p.add_argument("--spells", action="store_true")
    args = p.parse_args()

    d = S.load(args.game)
    exe = Exe(f"{args.game}/REGISTER.EXE")
    table = plays(exe)
    records = d[S.SPELLS].records(d.world, S.SPELL_RECORD)
    names = [s["name"] for s in EX.extract_spells(d)]

    attacks = EX.attack_table(exe.data)
    counts: dict[int, int] = {}
    for rec in records:
        one = spell_branch(rec, table)
        key = id(one) if one else 0
        counts[key] = counts.get(key, 0) + 1

    print(f"{len(table)} branches out of the dispatcher at {DISPATCH:#07x}")
    for one in table:
        held = counts.get(id(one), 0)
        lead = one["lead"]
        queued = lead and lead.get("queued")
        what = ("nothing" if lead is None
                else f"literal {lead['literal']}" if lead["literal"] is not None
                else f"attack entry named by record offset {lead['record']}" if queued
                else f"record offset {lead['record']}" if lead["record"] is not None
                else "a worked-out value")
        print(f"  record {one['field']} bit {one['bit']:#06x} -> {one['at']:#07x}"
              f"  {held:3d} spells  plays {what}")
    print(f"  no branch: {counts.get(0, 0)} spells")

    if args.spells:
        print()
        for name, rec in zip(names, records):
            one = spell_branch(rec, table)
            if one is None:
                print(f"  {name:<24} no branch")
                continue
            heard = sound_of(rec, table, attacks)
            print(f"  {name:<24} record {one['field']} bit {one['bit']:#06x} -> "
                  + (f"sound {heard}" if heard else "nothing"))


if __name__ == "__main__":
    main()
