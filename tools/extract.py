#!/usr/bin/env python3
"""Decode WORLD.DAT into JSON, driven by the section directory in REGISTER.EXE.

Runs once per copy of the game rather than per page load: the Makefile runs
it at build time, and the hosted cabinet runs this same file under pyodide in
the tab when a player brings their own copy. Either way the panel is built
from its output rather than reading WORLD.DAT itself.

Field naming policy: a field is given a real name only where its meaning was
confirmed against evidence (the prose descriptions, the creature families, a
monotonic difficulty progression, or a targeted immunity test). Everything
else keeps an `unknown_<offset>` name so that unverified guesses can never be
mistaken for facts. See README in tools/ for what is confirmed and how.
"""

from __future__ import annotations

import base64
import json
import sys
import re
import struct
from pathlib import Path

import items as I
import labels as L
import levels as LV
import markers
import pictures as P
import pngutil
import sections as S
import tiles

# --- text ------------------------------------------------------------------

text = L.text  # one stored string, in the game's charset; see labels.CHARSET


def reflow(lines: list[str]) -> str:
    """Join fixed-width lines back into prose.

    Lines are hard-wrapped at a fixed column with the remainder space-padded,
    so a single space at each join reconstructs the sentence.
    """
    return " ".join(line.strip() for line in lines if line.strip())


# --- enemies ---------------------------------------------------------------

# Enemy record layout.
#
# Everything named here was confirmed against the game's own F2 "MONSTER
# STATISTICS" screen. tools/capture_monsters.js walks all 71 listed creatures
# and tools/ocr.py reads the values straight off the frames, so each field below
# was checked on every creature rather than on a sample:
#
#   * the five combat statistics match on 355/355 readings
#   * the twelve immunity and resistance rows match on all 71 creatures
#   * the four reward figures match on 71/71
#
# The game omits the placeholder record named "NOT USED" from its own list,
# which is how the alignment between the alphabetical screen order and the
# table order was pinned down.
ENEMY_FIELDS = {
    "health": 30,
    "accuracy": 34,
    "dexterity": 36,
    "absorption": 38,
    "damage": 40,
    # Only 13 creatures carry ranged attacks; the rest show these rows blank.
    "ranged_accuracy": 50,
    "ranged_damage": 52,
    "family": 28,      # INFERRED: groups insects, undead, dwarves, elves,
                       # dragons and humans; what INSECT / UNDEAD key off.
    # The creature's level. It runs 1 (WASP, CENTIPEDE) to 45 (PALTIVAR), and
    # ranking the 71 creatures by it gives almost exactly the ranking by
    # absorption or damage: every other stat is grown from it.
    "level": 32,
    # The creature's sprite. The draw loop keeps the current frame at struct
    # offset 8 and sets it from here: at animation step 0x49 it stores this
    # value plus six (the attack frame) and at 0x4f it stores this value back
    # (image 0x80b0 and 0x80e9). Creatures that would share artwork share it --
    # WASP with WASP QUEEN, the three giants, the three dragons.
    "sprite": 26,
    # The two sounds, both indexes into the executable's 141-entry VOC table.
    # The resolver plays 42 when the creature's blow lands and 44 when it
    # misses (image 0x1053 and 0x109e); 42 plays again from the attack
    # animation itself, at step 0x4a (image 0x80c7). Where a creature has no
    # weapon the two are the same value; the fifteen that swing one share a
    # single miss sound, 35, and keep their own for the hit. Both towers have
    # neither, which is right: they only shoot.
    "sound_hit": 42,
    "sound_miss": 44,
}

FIELD_CONFIDENCE = {
    "health": "verified", "accuracy": "verified", "dexterity": "verified",
    "absorption": "verified", "damage": "verified", "family": "inferred",
    "experience": "verified", "gold": "verified", "food": "verified",
    "nuore": "verified", "immune": "verified", "resist_magic": "verified",
    "resist_physical": "verified", "resist_shot": "verified",
    "resist_unmatched": "verified",
    "ranged_accuracy": "verified",
    "ranged_damage": "verified", "attacks": "partial",
}

# Special attacks. Two are pinned to single bits of the word at 96; the rest --
# the condition-inflicting ones, match no bit, byte or pair of bits anywhere
# in the record, so they are not a bitmask and are left undecoded. Twenty pairs
# of creatures hold identical words at 96 and 98 and are still shown different
# attack lists by the game (SNOW GIANT and FIRE GIANT, DWARF SCOUT and ICE
# DWARF), which rules those words out as the sole source.
ATTACK_BITS = {(96, 12): "PARTY ATTACK", (96, 9): "BREAK SHIELD"}

# The condition-inflicting attacks, which are not a mask in the record at all.
# Offset 60 is an *id*, and the routine that prints the SPECIAL ATTACK line
# (image 0x7ee4) resolves it before testing anything:
#
#     mov ax, es:[si+0x6e]   ; the creature's offset 60, +50 for the in-memory
#     lcall 0x357:0xe        ; struct this routine walks
#     ...                    ; -> bx = 0x96da + id*12
#     test word [di+8], 0x8000 / "SICK, "   and so on down the bits
#
# So the mask lives in a twelve-byte table in the executable, keyed by the id.
# That is why a decade of looking for it inside the 106-byte record failed:
# ACOKNIGHT and FUNGUS really do share every masky-looking word, and differ
# only in this id.
ATTACK_TABLE = 0x96DA          # DS offset of the twelve-byte entries
ATTACK_ENTRY = 12
ATTACK_MASK_AT = 8             # the condition mask within an entry
ENEMY_ATTACK_ID = 60

# In bit order, exactly as the printer appends them.
ATTACK_EFFECT_BITS = {
    0x8000: "SICK", 0x4000: "POISON", 0x2000: "DISEASE", 0x1000: "PARALYZE",
    0x0800: "FROZEN", 0x0400: "STONING", 0x0200: "JINXING", 0x0100: "HEXING",
    0x0080: "CURSING", 0x0001: "STEAL GOLD", 0x0004: "STEAL FOOD",
    0x0002: "STEAL NUORE",
}


# Offsets 64-69: how one drawing serves several creatures.
#
# When bit 2 of word 96 is set, the draw loop copies these six bytes out and
# the renderer splits each into its two nibbles (`shl ax,1` four times then
# `shr al,1` four times, at image 0x19ce0), so a byte is a pair, the high
# nibble a color and the low nibble what to draw instead. Six pairs, stopping
# at a zero byte.
#
# The record does not say that; its shape does. All 32 creatures carrying a
# list stop at the first zero byte, and in all 32 the colors being replaced
# are distinct: neither would survive if these bytes were something else. And
# it explains the sprite groups: FROST GIANT carries no list and SNOW GIANT and
# FIRE GIANT recolour it, SLIME carries none and PURPLE SLIME swaps one color.
ENEMY_PALETTE = 64
ENEMY_PALETTE_BYTES = 6
ENEMY_PALETTE_BIT = (96, 2)


def palette_swaps(rec: bytes, at: int = None, length: int = None) -> list[dict]:
    """A color substitution list, in order, stopping at the first zero byte."""
    at = ENEMY_PALETTE if at is None else at
    length = ENEMY_PALETTE_BYTES if length is None else length
    out = []
    for byte in rec[at:at + length]:
        if not byte:
            break
        out.append({"from": byte >> 4, "to": byte & 0xF})
    return out


def attack_effects(exe: bytes, attack_id: int) -> list[str]:
    """The conditions an attack id inflicts, read from the executable's table."""
    at = L.DGROUP + ATTACK_TABLE + attack_id * ATTACK_ENTRY + ATTACK_MASK_AT
    mask = struct.unpack_from("<H", exe, at)[0]
    return [n for b, n in ATTACK_EFFECT_BITS.items() if mask & b]

# Rewards are packed BCD, most significant pair first, which is what the
# original notes meant by "decimal-encoded". WASP's 15 experience is stored as
# 00 00 00 15 and PALTIVAR's 1,000,000 as 01 00 00 00. Nothing holds these as
# plain integers, which is why searching for them as such found nothing.
REWARD_FIELDS = {
    "gold": (76, 4),
    "nuore": (82, 2),
    "food": (86, 2),
    "experience": (88, 4),
}

# Immunity. Six condition effects occupy the top bits, most significant first,
# and the damage types occupy the bottom of the word. Bit 5 is never set by any
# creature: nothing is immune to physical damage, only resistant to it.
IMMUNITY_WORD = 100
IMMUNITY_BITS = {
    15: "POISON", 14: "DISEASE", 13: "PARALYSIS",
    12: "FREEZING", 11: "HEXING", 10: "CURSING",
    4: "MAGIC DAMAGE", 3: "FIRE", 2: "COLD", 1: "ELECTRIC", 0: "POWER",
}

# Resistance is a set of things the creature shrugs off. Every blow builds a
# word describing itself and the applier ANDs it with this one, halving the
# damage once for each bit that survives (image 0x0C690 for a blow, image
# 0x1D8AF for a spell, and the chain at 0x1D72F written out bit by bit.
#
# The game's own F2 renderer sorts the bits into its two rows, and the masks it
# passes are where the grouping comes from rather than from us: image 0x07E9C
# prints PHYSICAL DAMAGE for 0xC000 and image 0x07E6A prints MAGIC DAMAGE for
# 0x3A00.
#
#   physical  bit 15  the blow is a shot (image 0x0C746), or the fixed item
#                     damage (image 0x0C8E4)
#             bit 14  nothing sets it
#   magic     bit 13  the spell is one of the 63 ordinary damage spells
#             bit 12  nothing sets it
#             bit 11  the weapon behind the shot is enchanted (image 0x0C752)
#             bit  9  the spell is one of the 7 anti-undead spells
#
# An enchanted weapon filed under magic is the grouping making sense of itself:
# the blow is part magical, so magic resistance takes half of it.
#
# Creatures carry only 15, 14 and 13, so the two row masks pick out the same
# creatures the single bits would. The masks are still what the fields are
# defined as, because they are what the game asks.
#
# A melee swing builds no word at all: image 0x00E73 resolves the blow and
# image 0x00EC8 subtracts the result from the creature's health directly. It is
# the one blow with no bit, and bit 14 is the one physical bit with no blow.
RESISTANCE_WORD = 102
RESIST_PHYSICAL_ROW = 0xC000
RESIST_MAGIC_ROW = 0x3A00
RESIST_SHOT = 0x8000
RESIST_UNMATCHED = 0x4000

# Magic resistance has two sources: this bit of the resistance word, and bit 4
# of the immunity word. The game shows RESISTANT when either is set, verified
# on all 71 creatures, including the four (BLAZIOS, CHAMELEON MAN, FIRE DWARF,
# SORCERER) that carry only the immunity-word bit.
MAGIC_VIA_IMMUNITY_BIT = 0x0010

# Special attacks. Both words carry bits that no reading has yet explained; the
# game prints the attack names in blue on a line the reader does not decode.
ENEMY_MASK_WORDS = [96, 98]

# What is left of the 106 bytes: 104, which is zero in all 73 records.
#
# Every other offset is now named. The in-memory creature is the record copied
# to an origin 50 bytes earlier (80 of them, 156 bytes each, at `DS:0x122C`,
# image 0x1234e), so record offset N is `[si+N+50]` in the code, and
# `tools/xref.py` finds the instructions that read it. The character record is
# a separate 500-byte struct at `DS:0xD0D1` and reads at the same
# displacements belong to it, which is what makes the search need reading
# rather than counting.
ENEMY_UNKNOWN = [104]


# --- the ranged attack -----------------------------------------------------
#
# Thirteen creatures shoot. The code that launches the shot (image 0x12579)
# fills a 24-byte projectile record from the creature's, and every field it
# takes is one that was undecoded:
#
#     projectile +0x04  <- record 46   the picture, in PICTURES.VGA run 1
#     projectile +0x14  <- record 48   the sound, played on impact (0x123b8)
#     projectile +0x12  <- record 62   an id into the attack table below
#     projectile +0x0c  <- &record 70  a recolour list, six bytes
#     projectile +0x10  <- word 96 bit 1, which turns that list on
#
# The picture is drawn from run 1 with `[0xfc5] = 0x10` (image 0x123df), and
# the seven values in use are arrows, spores, throwing stars, lightning, fire,
# a white bolt and a comet, each picture holding the four angles the shot
# can travel at.
RANGED_PICTURE, RANGED_SOUND, RANGED_ATTACK_ID = 46, 48, 62
RANGED_RECOLOUR, RANGED_RECOLOUR_BYTES = 70, 6
RANGED_RECOLOR_BIT = (96, 1)

# How often the creature shoots rather than closing. The AI rolls 1..100 and
# compares it with a threshold picked by the highest of these four bits, or 5
# where none is set (image 0x129f8). Exactly the thirteen shooters carry one:
# the three that cannot move (FUNGUS and the two towers) carry the 90, and
# the other ten the 25.
RANGED_CHANCE_BITS = {12: 90, 11: 75, 10: 50, 9: 25}
RANGED_CHANCE_DEFAULT = 5

# The creature's ordinary attack, resolved through the same twelve-byte table
# as the special one (image 0x13ed). It is 2 for every creature but FIRE
# MANTIS, whose 38 is the table's other entry that inflicts no condition.
ENEMY_ORDINARY_ATTACK_ID = 58

# Where an effect graphic is drawn on the creature. The draw loop picks a base
# position, adds these two, and blits a picture from run 6 there (image
# 0x10443). They go with the artwork rather than the creature: everything that
# shares a picture shares them, and they are the same 35, 45 for most of the
# creatures drawn tall.
HIT_OFFSET = (54, 56)

# How the walk cycle runs, from two bits of word 96 (image 0x15398). Bit 5
# runs the six frames and snaps back to the first; bit 4 runs them and comes
# back down, using bit 3 to remember which way it is going; bit 6 stops the
# animation altogether. Every creature the game lists carries exactly one of
# the first two, and none carries the third.
WALK_BITS = {4: "bounce", 5: "loop", 6: "still"}
WALK_BIT_WORD = 96

# What a steal takes, in the same packed BCD as the four rewards, carried into
# the pending-effect record with the attack id (image 0x13ce). Only the three
# creatures whose special attack is STEAL GOLD have one.
ENEMY_STEAL = (92, 4)


def ranged_attack(exe: bytes, rec: bytes) -> dict | None:
    """The creature's ranged attack, or None where it has none."""
    picture = u16(rec, RANGED_PICTURE)
    if not picture:
        return None
    word, bit = RANGED_RECOLOR_BIT
    flags = u16(rec, 98)
    attack_id = u16(rec, RANGED_ATTACK_ID)
    return {
        "picture": picture,
        "sound": u16(rec, RANGED_SOUND),
        "chance": next((pct for b, pct in sorted(RANGED_CHANCE_BITS.items(),
                                                 reverse=True) if flags >> b & 1),
                       RANGED_CHANCE_DEFAULT),
        "attack_id": attack_id,
        "attacks": attack_effects(exe, attack_id),
        "recolour": (palette_swaps(rec, RANGED_RECOLOUR, RANGED_RECOLOUR_BYTES)
                     if u16(rec, word) >> bit & 1 else []),
    }


def bcd(rec: bytes, off: int, length: int) -> int | None:
    """Packed BCD, most significant byte first. None if a nibble is not a digit."""
    value = 0
    for i in range(length):
        hi, lo = rec[off + i] >> 4, rec[off + i] & 0xF
        if hi > 9 or lo > 9:
            return None
        value = value * 100 + hi * 10 + lo
    return value


def u16(rec: bytes, off: int) -> int:
    return struct.unpack_from("<H", rec, off)[0]


def enemy_name(rec: bytes) -> str:
    """Names occupy two 13-byte fields so two-word names fit (DWARF / TOWER)."""
    parts = [text(rec[0:13]).strip(), text(rec[13:26]).strip()]
    return " ".join(p for p in parts if p)


def extract_enemies(d: S.Directory) -> list[dict]:
    # Which creatures the clue book indexes, from the book's own list registry
    # rather than from the placeholder's name. Record 0 is a zero-filled
    # sentinel, so a record's 1-based id is its index.
    book = set(I.book_list(d.exe, I.CREATURE_LIST))
    out = []
    for i, rec in enumerate(d[S.ENEMIES].records(d.world, S.ENEMY_RECORD)):
        name = enemy_name(rec)
        if not name:
            continue  # record 0 is a zero-filled sentinel
        immunity = u16(rec, IMMUNITY_WORD)
        resistance = u16(rec, RESISTANCE_WORD)
        e: dict = {"index": i, "name": name}
        e.update({k: u16(rec, off) for k, off in ENEMY_FIELDS.items()})
        for k in ("ranged_accuracy", "ranged_damage"):
            if not e[k]:
                e[k] = None   # the game leaves these rows blank, not zero
        e.update({k: bcd(rec, off, n) for k, (off, n) in REWARD_FIELDS.items()})
        e["immune"] = [name_ for bit, name_ in sorted(IMMUNITY_BITS.items(), reverse=True)
                       if immunity >> bit & 1 and name_ != "MAGIC DAMAGE"]
        e["resist_magic"] = bool(resistance & RESIST_MAGIC_ROW
                                 or immunity & MAGIC_VIA_IMMUNITY_BIT)
        # The game prints one row for two bits; what sets them differs.
        e["resist_physical"] = bool(resistance & RESIST_PHYSICAL_ROW)
        e["resist_shot"] = bool(resistance & RESIST_SHOT)
        e["resist_unmatched"] = bool(resistance & RESIST_UNMATCHED)
        e["recolour"] = palette_swaps(rec)
        e["walk"] = next((n for b, n in WALK_BITS.items()
                          if u16(rec, WALK_BIT_WORD) >> b & 1), None)
        e["hit_offset"] = [u16(rec, o) for o in HIT_OFFSET]
        e["ranged"] = ranged_attack(d.exe, rec)
        e["ordinary_attack_id"] = u16(rec, ENEMY_ORDINARY_ATTACK_ID)
        e["steal"] = bcd(rec, *ENEMY_STEAL)
        e["attack_id"] = u16(rec, ENEMY_ATTACK_ID)
        # The two record bits plus the conditions the attack id's table
        # carries. This reproduces every row of every F2 screen the capture
        # walk photographed (the same 30 monsters, the same attacks), so
        # observed_attacks.json is the check on it, in tests/, and no longer
        # its source.
        e["attacks"] = ([n for (w, b), n in ATTACK_BITS.items()
                         if u16(rec, w) >> b & 1]
                        + attack_effects(d.exe, e["attack_id"]))
        e["listed"] = i in book
        e["masks"] = {f"w{off}": u16(rec, off) for off in ENEMY_MASK_WORDS}
        e["unknown"] = {f"u{off}": u16(rec, off) for off in ENEMY_UNKNOWN}
        out.append(e)
    return out


# --- monster art -----------------------------------------------------------

# The picture a creature is drawn with. tools/pictures.py has the file's shape;
# what is decided here is which of the ten pictures to show and how to store it.
#
# The first of the ten is the creature standing still. The other nine are the
# rest of the walk cycle, the attack and the death, which a still picture has
# no use for.
MONSTER_FRAME = 0
# Section 12's first palette. The map screen draws with it too. Drawing these
# pictures with it reproduces the clue book's own monster screens pixel for
# pixel on 64 of the 71 creatures the game lists; on the other seven the
# capture caught the page mid-refresh, with the top of the creature on one
# step of the walk cycle and the bottom on the next. tools/verify_monsters.py
# measures this.
MONSTER_PALETTE = 0


def monster_art(d: S.Directory, pics: bytes, enemies: list[dict]) -> dict[str, dict]:
    """name -> a PNG of the creature, cropped to its own pixels.

    Each picture carries a palette of just the colors it uses, which is what
    keeps 71 of them inside a quarter of a megabyte. Index 0 is the
    transparent one; the game's own transparent value, 0xFF, would need a
    256-entry alpha table to say so.
    """
    runs = P.read_runs(d.exe, len(pics))
    palette = tiles.palette(d, MONSTER_PALETTE)
    out = {}
    for e in enemies:
        # The game omits the placeholder record from its own list and never
        # draws it, so the picture its sprite field points at is not a
        # creature: it is the scenery that run 2 starts with.
        if not e["listed"]:
            continue
        run, raw = P.creature(
            pics, runs, e["sprite"], e["masks"]["w96"], e["masks"]["w98"],
            {s["from"]: s["to"] for s in e["recolour"]}, MONSTER_FRAME)
        w, h, crop = _cropped(raw, run.width)
        png = _indexed(w, h, crop, palette)
        out[e["name"]] = _png_entry(w, h, png)
    return out


# The projectile run. Each picture holds the shot at the four angles it can
# travel at, so it is shown whole rather than cut up: which of the four the
# game picks is a property of the shot, not of the creature.
PROJECTILE_RUN = 1


def projectile_art(d: S.Directory, pics: bytes, enemies: list[dict]) -> dict[str, dict]:
    """picture number -> a PNG of the shot, for every picture a creature fires.

    Keyed by the picture rather than by the creature because seven pictures
    serve all thirteen shooters: three of them fire the same arrows.
    """
    runs = P.read_runs(d.exe, len(pics))
    run = runs[PROJECTILE_RUN]
    palette = tiles.palette(d, MONSTER_PALETTE)
    out = {}
    for e in enemies:
        shot = e["ranged"]
        if not shot or str(shot["picture"]) in out:
            continue
        raw = P.recoloured(P.picture(pics, run, shot["picture"]),
                           {s["from"]: s["to"] for s in shot["recolour"]})
        w, h, crop = _cropped(raw, run.width)
        out[str(shot["picture"])] = _png_entry(w, h, _indexed(w, h, crop, palette))
    return out


def _cropped(raw: bytes, width: int) -> tuple[int, int, bytes]:
    x0, y0, x1, y1 = P.bounds(raw, width)
    return x1 - x0, y1 - y0, b"".join(raw[y * width + x0:y * width + x1]
                                      for y in range(y0, y1))


def _indexed(w: int, h: int, crop: bytes, palette: list[bytes]) -> bytes:
    """A PNG carrying only the colors this picture uses, transparent at 0."""
    used = sorted(set(crop) - {P.TRANSPARENT})
    slot = {v: i + 1 for i, v in enumerate(used)}
    return pngutil.encode_indexed(
        w, h, bytes(slot.get(v, 0) for v in crop),
        [b"\x00\x00\x00"] + [palette[v] for v in used], transparent=0)


def _png_entry(w: int, h: int, png: bytes) -> dict:
    return {"width": w, "height": h,
            "src": "data:image/png;base64," + base64.b64encode(png).decode()}


# --- spells ----------------------------------------------------------------

SPELL_NAME_LEN = 21
# Verified against the game's own F3 screen for all 98 spells the clue book
# lists: MP and nuore match exactly at these offsets. Damage was confirmed
# separately against the numbers each spell's own description quotes.
SPELL_DAMAGE = 46
# The spell's own level: what a scroll requires before a class can learn it.
# Exact on all 23 spells the screens show with a SCROLL row, and equal to the
# lowest class level for 95 of the 98 listed spells; the three exceptions are
# training-only, where the table teaches it earlier or later than the spell's
# nominal level.
SPELL_LEVEL = 22
# Offset 34 is an amount whose meaning follows the spell's effect. For the
# healing family it is the health restored, verified against the game's own
# prose: HEAL 10, IMPROVE HEALTH 50, PARTY HEAL 100, RESTORE HEALTH 200, GREAT
# HEAL 500, PERFECT HEALTH 9999 ("all health points"). HARDY PARTY is the one
# mismatch: the record says 600 where the prose says 650, the same kind of
# content discrepancy as ERADICATE's damage. Damage spells also carry a nonzero
# value here, so it is only read as healing for the healing family.
# Offset 74 is the spell's element, and it uses the *same bit layout as the
# enemy immunity word* at ENEMY offset 100, which is the whole point of it:
# the game checks one against the other. Verified per bit against the prose
# (74.3 FIRE, 74.2 COLD, 74.1 ELECTRIC, 74.0 POWER, 74.15 POISON, 74.14
# DISEASE), and never set on a spell that does no damage. Zero means untyped,
# which no immunity stops.
SPELL_ELEMENT = 74

SPELL_AMOUNT = 34
# Offset 32 is 18 for every healing and every cure spell and for nothing that
# does damage, so it marks the restorative family.
SPELL_FAMILY = 32
SPELL_FAMILY_RESTORATIVE = 18
SPELL_HEAL_ALL = 9999          # PERFECT HEALTH: "all health points"

SPELL_FIELDS = {"mp": 24, "nuore": 26, "damage": SPELL_DAMAGE,
                "level": SPELL_LEVEL}

# The AFFECTS and WHEN rows, read off the F3 printer's own branches rather
# than off the screen. The AFFECTS row is built at image 0x0776E and the WHEN
# row at image 0x07889, and between them they test four words of the record
# and nothing else: 72 carries scope, what the spell acts on and how far it
# reaches; 76 selects two of the nouns; 30 tells INSECT from UNDEAD; and 70
# bit 10 is the out-of-melee restriction. Those are the offsets, not a fitted
# mapping: each branch below is one `test` in the printer, in its order.
#
# Offset 76 is the spell's blow word, which the combat model already reads for
# its bit 13 (`tools/combat_model.py`, measured against a live creature): one
# word, two readings, because the printer asks what kind of blow it is in
# order to say what the blow reaches.
SPELL_AFFECTS_WORD = 72
SPELL_BLOW = 76
SPELL_KIND = 30
SPELL_WHEN_WORD = 70

# The printer leaves the AFFECTS row blank when any of the low eight bits of
# 72 is set: the nine utility spells (MARK OR RETURN, the two MINER'S LIGHTs,
# SAFE UNLOCK and the rest) print nothing there.
SPELL_NO_AFFECTS = 0x00FF
# `test [affects], 6` on 76 or `test [affects], 0x5E00` on 72, and either makes
# the row read ALL rather than ONE.
SPELL_SCOPE_ALL_76, SPELL_SCOPE_ALL_72 = 0x0006, 0x5E00
SPELL_CHARACTER = 0xC000        # 72: the row says CHARACTER, not MONSTER
SPELL_VISIBLE = 0x0200          # 72: ... VISIBLE MONSTERS
SPELL_NARROW = 0x0100           # 76: with 30, narrows the noun
SPELL_KIND_INSECT, SPELL_KIND_UNDEAD = 9, 13
SPELL_PLURAL = 0x5C00           # 72: the noun takes an S
# The reach phrases, in the order the printer tests them. Melee is two bits
# because 0x1000 and 0x2000 both mean it, and the WHEN row reads the same pair.
SPELL_MELEE = 0x3000
SPELL_REACH = ((SPELL_MELEE, "in hand to hand"),
               (0x0800, "in a straight line"),
               (0x0400, "in a 3x3 area"),
               (0x0100, "at a distance"))
SPELL_OUT_OF_MELEE = 0x0400     # 70: WHEN says out of hand to hand
# Who may learn a spell from a scroll: a six-bit mask, read in spell_classes.
SPELL_SCROLL_MASK = 68

SPELL_UNKNOWN = [c for c in range(22, 80, 2)
                if c not in (*SPELL_FIELDS.values(), SPELL_AMOUNT,
                             SPELL_ELEMENT, SPELL_FAMILY, SPELL_SCROLL_MASK,
                             SPELL_AFFECTS_WORD, SPELL_BLOW,
                             SPELL_KIND, SPELL_WHEN_WORD)]


def spell_affects(rec: bytes) -> tuple[str | None, str | None, str | None, str]:
    """The AFFECTS and WHEN rows: scope, what it acts on, reach, and when.

    Follows image 0x0776E branch for branch. Two of them stop the row early
    and are easy to miss: a blank AFFECTS row when any low bit of 72 is set,
    and the VISIBLE branch, which prints its noun and jumps straight to the
    WHEN row, so a VISIBLE spell never takes a plural or a reach phrase.
    """
    affects = u16(rec, SPELL_AFFECTS_WORD)
    select = u16(rec, SPELL_BLOW)
    kind = u16(rec, SPELL_KIND)
    when = ("out of hand to hand" if u16(rec, SPELL_WHEN_WORD) & SPELL_OUT_OF_MELEE
            else "in hand to hand" if affects & SPELL_MELEE else "anytime")
    if affects & SPELL_NO_AFFECTS:
        return None, None, None, when

    wide = select & SPELL_SCOPE_ALL_76
    scope = "all" if wide or affects & SPELL_SCOPE_ALL_72 else "one"
    narrow = select & SPELL_NARROW
    if affects & SPELL_CHARACTER:
        noun, stop = "character", False
    elif wide or affects & SPELL_VISIBLE:
        noun = ("visible undeads" if narrow and kind == SPELL_KIND_UNDEAD
                else "visible monsters")
        stop = True
    elif narrow and kind == SPELL_KIND_INSECT:
        noun, stop = "insect", False
    elif narrow and kind == SPELL_KIND_UNDEAD:
        noun, stop = "undead", False
    else:
        noun, stop = "monster", False
    if stop:
        return scope, noun, None, when
    if affects & SPELL_PLURAL:
        noun += "s"
    reach = next((phrase for bit, phrase in SPELL_REACH if affects & bit), None)
    return scope, noun, reach, when

# The clue book's own readings, kept as the cross-check on the decode above
# rather than as the source: `tests/test_extract.py` asserts that the first
# three decoded class rows reproduce every screen exactly. Still the source of
# four fields (scope, target, reach and when) which no field of the record
# and no flat table in either file determines, so they ship as observations,
# kept separate from the decoded fields around them.
# When each class is *taught* a spell, straight from the executable.
#
# `DS:0xb8b5 + 0x50 * class` is twenty four-byte slots, one per even level from
# 2 to 40, holding up to two 1-based spell numbers each; the six rows are monk,
# alchemist, paladin, mage, druid, marksman (see docs/leveling.md). That covers
# every TRAINING row the F3 screens show (165 of them, all exact), so those
# rows are decoded rather than read.
#
# It does not cover the other 59: a class that can learn a spell but is not in
# this table gets it from a scroll, at the spell's own level (offset 22), or
# free when that level is 1. Which classes those are is still only known from
# the screens, so those rows stay marked as observations.
def _training_levels() -> dict:
    table = LV.spells_by_level(LV.load())
    out: dict[tuple[str, int], int] = {}
    for klass, rows in table.items():
        for level, ids in rows.items():
            for spell_id in ids:
                out[(klass.upper(), spell_id - 1)] = level
    return out


TRAINING_LEVELS = _training_levels()

# The two spells each class already knows at level 1, at DS:0xb89d: two
# 1-based spell numbers per class, immediately before the training table.
FREE_SPELLS_TABLE = 0xB89D
# Most significant class first: monk 0x20 down to marksman 0x01.
SCROLL_BITS = [0x20, 0x10, 0x08, 0x04, 0x02, 0x01]
MAGIC_CLASSES = ["MONK", "ALCHEMIST", "PALADIN", "MAGE", "DRUID", "MARKSMAN"]
# The clue book's page has room for three class rows and prints the first
# three in this order, so 22 rows exist that it cannot show. The decode keeps
# them; `tests/test_extract.py` checks the first three against the screens.
SPELL_CLASS_ROWS = 3


def _free_spells(exe: bytes) -> dict[str, set[int]]:
    at = L.DGROUP + FREE_SPELLS_TABLE
    return {name: {v for v in struct.unpack_from("<2H", exe, at + k * 4) if v}
            for k, name in enumerate(MAGIC_CLASSES)}


def spell_classes(exe: bytes, rec: bytes, index: int, level: int) -> list[dict]:
    """Every class that can cast a spell, how, and at what level.

    Follows the printer at image 0x7660, which asks three things per class in
    order: is it one of the two the class starts with (DS:0xb89d), is it in the
    class's training row (DS:0xb8b5), and failing both, is the class's bit set
    in the spell's scroll mask. That order matters: a class in the mask that
    also trains the spell shows as TRAINING.
    """
    free = _free_spells(exe)
    number = index + 1
    mask = u16(rec, SPELL_SCROLL_MASK)
    out = []
    for k, name in enumerate(MAGIC_CLASSES):
        if number in free[name]:
            out.append({"class": name, "level": 1, "source": None})
        elif (taught := TRAINING_LEVELS.get((name, index))) is not None:
            out.append({"class": name, "level": taught, "source": "TRAINING"})
        elif mask & SCROLL_BITS[k]:
            out.append({"class": name, "level": level, "source": "SCROLL"})
    return out


# The description index: (start_line, line_count) u16 pairs into the 39-column
# description stream. Entry 0 is a sentinel, so spell i uses pair i+1.
SPELL_TEXT_INDEX = 3


def extract_spells(d: S.Directory) -> list[dict]:
    recs = d[S.SPELLS].records(d.world, S.SPELL_RECORD)
    # Which spells the clue book's F3 section pages through, from the same
    # list registry the item categories come out of. It names 98 of the 107
    # records (the eight ERROR placeholders and SHARD OF ICE are the nine it
    # leaves out) and agrees with every screen the capture walk reached.
    book = set(I.book_list(d.exe, I.SPELL_LIST))
    st = d.spell_text_section()
    stream = d.world[st.offset:st.end]
    n_lines = st.size // S.SPELL_TEXT_COLS

    def line(i: int) -> str:
        return text(stream[i * S.SPELL_TEXT_COLS:(i + 1) * S.SPELL_TEXT_COLS])

    idx_sec = d.rest(SPELL_TEXT_INDEX)
    pairs = struct.unpack_from(f"<{idx_sec.size // 2}H", d.world, idx_sec.offset)

    out = []
    for i, rec in enumerate(recs):
        start, count = pairs[(i + 1) * 2], pairs[(i + 1) * 2 + 1]
        assert start + count <= n_lines, f"spell {i} text runs past the section"
        s: dict = {
            "index": i,
            "name": text(rec[:SPELL_NAME_LEN]).strip(),
            "description": reflow([line(start + k) for k in range(count)]),
        }
        s.update({k: u16(rec, off) for k, off in SPELL_FIELDS.items()})
        # Eight records are placeholders named ERROR, and their bytes are
        # leftovers, and decoding a scroll mask out of them invents spells.
        s["classes"] = ([] if s["name"] == "ERROR"
                        else spell_classes(d.exe, rec, i, s["level"]))
        # The AFFECTS row names the scope, what a spell acts on and, for most
        # spells, how far it reaches. The reach is kept apart from the noun,
        # or every card repeats itself ("one monster in hand to hand" beside a
        # "melee" chip).
        s["scope"], s["target"], s["reach"], s["when"] = spell_affects(rec)
        # The raw amount and the family flag, not an interpretation: offset 34
        # is health restored for a heal, but plain magnitude elsewhere (FEET OF
        # FEATHERS carries 5, its dexterity bonus). Naming it "healing" here
        # would bake a guess into the data; the panel decides from the effect.
        element = u16(rec, SPELL_ELEMENT)
        s["element"] = [n for bit, n in sorted(IMMUNITY_BITS.items(), reverse=True)
                        if element >> bit & 1]
        s["restorative"] = rec[SPELL_FAMILY] == SPELL_FAMILY_RESTORATIVE
        s["amount"] = u16(rec, SPELL_AMOUNT) or None
        # The blow word, which says both what a resistant creature halves and
        # what the AFFECTS row reaches.
        s["blow"] = u16(rec, SPELL_BLOW)
        s["listed"] = i + 1 in book
        s["unknown"] = {f"u{off}": u16(rec, off) for off in SPELL_UNKNOWN}
        out.append(s)
    return out


# --- walkthrough -----------------------------------------------------------

def extract_walkthrough(d: S.Directory) -> list[dict]:
    sec = d.rest(S.WALKTHROUGH)
    pages = []
    for p in range(sec.size // S.WALKTHROUGH_PAGE):
        base = sec.offset + p * S.WALKTHROUGH_PAGE
        rows = [
            text(d.world[base + r * S.WALKTHROUGH_COLS:
                         base + (r + 1) * S.WALKTHROUGH_COLS])
            for r in range(S.WALKTHROUGH_ROWS)
        ]
        pages.append({"page": p + 1, "rows": rows})
    return pages


def walkthrough_sections(pages: list[dict]) -> list[dict]:
    """The `NN. LOCATION` headings, for a navigation index."""
    out = []
    for pg in pages:
        for row in pg["rows"]:
            s = row.strip()
            head = s.split(".", 1)
            if len(head) == 2 and head[0].isdigit() and head[1].startswith(" "):
                out.append({"n": int(head[0]), "title": head[1].strip(),
                            "page": pg["page"]})
    return out


# --- fixed-width name tables ----------------------------------------------

def fixed_width(buf: bytes, width: int) -> list[str]:
    return [text(buf[i:i + width]).strip()
            for i in range(0, len(buf) - width + 1, width)]


def extract_maps(d: S.Directory) -> list[str]:
    names = fixed_width(d[S.MAP_NAMES_20].slice(d.world), 20)
    return [n for n in names if n]


# 25 visible characters plus a NUL terminator. Slot 0 is a column ruler
# ("1234567890123456789012345") the developers left in the data; it is kept so
# the indices here line up with the game's own, and skipped by the panel.
LEGEND_RECORD = 26
LEGEND_RULER = "1234567890123456789012345"


# --- items -----------------------------------------------------------------
#
# 631 records of 58 bytes: 19 bytes of fields then three 13-byte name fields, a
# name running across all three ("BROKEN" + "BO STICK" is one item).
#
# The decoding lives in `tools/items.py`, which reads the record, the three
# properties tables, the effects table and the six category lists in
# REGISTER.EXE. What that module returns for an item is exactly the set of rows
# the game's own F5 page prints for it, so the captures below are the check on
# the decode rather than its source.
ITEM_BASE = 0x083EE8
ITEM_RECORD = I.RECORD
ITEM_FIELD_BYTES = I.FIELD_BYTES
ITEM_NAME_LEN = I.NAME_LEN
ITEM_NAME_FIELDS = I.NAME_FIELDS

# Every row of an F5 page is decoded. The captures are the check, in
# tests/test_extract.py.

# The clue book files items under eight categories, in this order. Six of them
# are lists, and their contents come out of REGISTER.EXE; the other two are
# pages of their own: ATTRIBUTE ENHANCERS is a page of rules and
# TRANSPORTATIONS is three things that are not items at all.
ITEM_CATEGORIES = L.ITEM_CATEGORIES

# Enhancement runs to +10, so the digits are not always one: `\d` alone left
# the nine +10 items unmatched, which both leaked them into the list as items
# in their own right and hid them from the variant table.
#
# The optional space is for `RUBY MORNING STAR + 2`, which the game's own data
# spells with a stray space. Without it that single entry stayed outside its
# own series, which showed up as a hole between +1 and +3 exactly where its
# value belongs. How far a series runs is per item (that weapon stops at +8,
# the nine longest reach +10), so the fold walks to MAX_PLUS rather than to
# any one item's ceiling.
PLUS = re.compile(r"^(.*?) \+ ?(\d+)$")
MAX_PLUS = 10


def item_name(rec: bytes) -> str:
    return I.name(rec)


def extract_items(d: S.Directory) -> list[dict]:
    """Every item, with the rows its clue-book page prints.

    An item's category is the list it appears in, and its fields are what the
    F5 renderers would print for it, so an item the book never indexes still
    gets its value, weight and where it fits, and the 461 records the capture
    never reached are no longer blank.
    """
    items = I.Items(d)
    category_of = {}
    for category, ids in items.categories().items():
        for item_id in ids:
            category_of[item_id] = category

    rows = []
    for item_id, rec in enumerate(items.records, 1):
        name = items.names[item_id - 1]
        if not name:
            continue
        page = items.page(item_id)
        rows.append({
            "id": item_id,
            "name": name,
            "value": page["base value"],
            "weight": page["weight"],
            "absorption": page.get("absorption"),
            # A magic scroll names the spell it teaches; the F5 page does not
            # print it, so it is a key of its own rather than a field.
            "spell": items.scroll_spell(rec),
            # Which slot it occupies; the F5 page has no such row either.
            "slot": items.equip_slot(rec),
            "category": category_of.get(item_id),
            "listed": item_id in category_of,
            # Value, weight and absorption are their own keys on the item, so
            # the page's copy of them would be printed twice.
            "fields": {k: v for k, v in page.items()
                       if k not in ("base value", "weight", "absorption")},
        })

    # The book lists a base item once and puts its enchanted forms behind a
    # +0..+10 selector, so fold "CLOTHES +1" into CLOTHES rather than listing it
    # as a separate item the way the record does. Only the top tier of gear
    # reaches +10: nine items, all Royal Plate, Gold Shield or a heavy weapon.
    by_name = {r["name"]: r for r in rows}
    out = []
    for row in rows:
        if PLUS.match(row["name"]):
            continue
        variants = []
        for plus in range(1, MAX_PLUS + 1):
            variant = (by_name.get(f"{row['name']} +{plus}")
                       or by_name.get(f"{row['name']} + {plus}"))
            if variant:
                # The enchanted form's own id, which the panel needs to hand
                # one over. It is the base plus the enchantment on all 327 of
                # them, but it is read rather than computed.
                variants.append({"plus": plus, "id": variant["id"],
                                 "value": variant["value"],
                                 "weight": variant["weight"],
                                 "absorption": variant["absorption"]})
        out.append({**row, "variants": variants})
    return out


# The clue book's maps are drawn pictures, not tile grids: the 37 x 64 table
# at 0x8CDDE holds tile-placement coordinates into a graphics bank, so there is
# nothing to decode into cells. The pages are captured from the running game
# instead (tools/capture_maps.js) and indexed by the title read off each frame.
# Each page as its tile grid plus the handful of 8x8 tiles it is drawn with:
# about 2 kB a page, against 6 kB for a PNG of the same thing, and the panel
# draws it at whatever size it has rather than scaling a bitmap.
_MAP_PAGES = ROOT / "data" / "map_pages.json" if (ROOT := Path(__file__).resolve().parent.parent) else None
MAP_PAGES = json.loads(_MAP_PAGES.read_text()) if _MAP_PAGES and _MAP_PAGES.exists() else []

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pack_maps import WALKED_LINKS as _WALKED_LINKS  # noqa: E402
import links as K  # noqa: E402

def extract_legend(d: S.Directory) -> list[str]:
    """The map legend labels, which stop well short of the section's end.

    The Restoration directory entry runs to the start of the next one, but the
    labels themselves fill only the first 138 records; after that comes the
    spell-text index and then the descriptions. Striding 26 bytes over those
    produces convincing-looking garbage ("To a Single Player.", "Of Cold
    Damage. Be Caref"), so the run is cut at the first record that is not a
    clean NUL-terminated label.
    """
    raw = d.rest(S.LEGEND).slice(d.world)
    labels = []
    for i in range(len(raw) // LEGEND_RECORD):
        rec = raw[i * LEGEND_RECORD:(i + 1) * LEGEND_RECORD]
        end = rec.find(b"\x00")
        if end < 0 or any(c and not (32 <= c < 127) for c in rec[:end]) \
                or any(rec[end:]):
            break
        labels.append(text(rec[:end]))
    return labels


# --- proper nouns ----------------------------------------------------------
#
# Every string in the game is stored upper case, so rendering it readably means
# re-capitalizing it, and that needs to know which words are names. Rather than
# hand-listing them, harvest the candidates from places the game itself marks as
# named things (area names, walkthrough section titles, and the single-word
# map legend labels, which are the NPCs it labels on its maps) then subtract
# the generic vocabulary those lists also contain.

# Words that appear in area names and legend labels but are ordinary nouns:
# "CASTLE OF BARIAG" names a castle, not a Castle. Kept explicit so the
# decision for each word is visible and reviewable.
GENERIC_WORDS = {
    "A", "AND", "OF", "THE", "TO", "INTO", "WITHIN", "AT", "IN", "ON",
    "CASTLE", "CAVE", "CHAMBER", "CITY", "DUNGEON", "HOMELAND", "ISLAND",
    "KEEP", "KINGDOM", "LEVEL", "LEVELS", "MAP", "MINE", "ORDER", "PLANE",
    "PRISON", "SEWER", "SEWERS", "STRONGHOLD", "TOWER", "TUNNEL",
    "UNDERGROUND", "WAY", "SOULS", "HOLY",
    "COPPER", "GOLD", "SILVER", "IRON", "ICE", "FIRE", "QUARTZ", "NUORE",
    "ARROW", "CAST", "ILLUSION", "POINTS", "WALLS",
}

# Fragments of longer labels that the single-token harvest picks up.
NOISE_WORDS = {"LL", "U", "E", "CTER'S"}

# Individuals named in the prose who are not labeled on any map, so the
# harvest below cannot reach them.
EXTRA_NAMES = {"PALTIVAR", "VISHAN", "SAXON", "MINX", "DEVON", "BLAZIOS"}

_WORD = re.compile(r"[A-Z][A-Z']*")


def proper_nouns(payload: dict) -> list[str]:
    found: set[str] = set(EXTRA_NAMES)
    for name in payload["maps"]:
        found |= set(_WORD.findall(name))
    for section in payload["walkthrough_index"]:
        found |= set(_WORD.findall(section["title"]))
    for label in payload["legend"]:
        if label and _WORD.fullmatch(label):
            found.add(label)
    found -= GENERIC_WORDS | NOISE_WORDS
    # Trim possessives to the name itself; the renderer matches on word stems.
    return sorted({w[:-2] if w.endswith("'S") else w for w in found if len(w) > 2})


# --- driver ----------------------------------------------------------------

# The NPC and conversation-topic tables, decoded in docs/shops.md. Only the
# training service is read here; the rest of what an NPC does is not in the
# panel.
NPC_BASE, NPC_REC, NPC_COUNT = 0x3D8EB9, 40, 141
TOPIC_BASE, TOPIC_REC, TOPIC_COUNT = 0x3DA4C1, 60, 1073
TRAIN_SELECT = 0x0800  # topic +18, the handler the dispatch at 0x02ac9 picks

# A trainer's ceiling is `+0x16` of its record and the refusal above it is coded
# at image 0x09d80. A *floor* is not in the record, and nothing found reads one,
# but NPC 33 states one in its own dialogue ("once you are level 30, I can
# handle all of your training needs") and it holds in play. The hand-off is the
# corroboration: NPC 104 trains through exactly 30 and NPC 33 begins there, so
# the two cover 1-30 and 30-40 between them with no gap and no overlap.
TRAINER_FLOOR = {33: 30}


def extract_trainers(world: bytes) -> list[dict]:
    """Every NPC that sells levels, with the ceiling and the price it charges.

    Found by the topic's dispatch field rather than its keyword, so a trainer
    named something other than TRAIN would still be caught. `+0x16` of the NPC
    record is the highest level it will train you to and `+0x18` its price
    factor; offsets past those are zero on all five, so there is no floor and
    every trainer starts at level 1.
    """
    def word(buf, off):
        return struct.unpack_from("<H", buf, off)[0]

    npcs = [world[NPC_BASE + i * NPC_REC: NPC_BASE + (i + 1) * NPC_REC]
            for i in range(NPC_COUNT)]
    owner = {}
    for i, rec in enumerate(npcs):
        first, count = word(rec, 8), word(rec, 4)
        for t in range(first, first + count):
            owner[t] = i

    out = []
    for t in range(1, TOPIC_COUNT + 1):
        rec = world[TOPIC_BASE + (t - 1) * TOPIC_REC: TOPIC_BASE + t * TOPIC_REC]
        if word(rec, 14) or word(rec, 18) != TRAIN_SELECT:
            continue
        i = owner.get(t)
        if i is None:
            continue
        out.append({"npc": i,
                    "from": TRAINER_FLOOR.get(i, 1),
                    "through": word(npcs[i], 0x16),
                    "factor": word(npcs[i], 0x18)})
    return sorted(out, key=lambda r: (r["through"], r["from"]))


def extract_leveling(d: S.Directory) -> dict:
    """The leveling tables, which the clue book has no page for.

    All of this is compiled into REGISTER.EXE rather than stored in WORLD.DAT,
    so the game never shows it: the trainer quotes one price and the character
    screen names one level. The panel can show the whole ladder.
    """
    table = LV.experience_table(d.exe)
    real = {lvl: xp for lvl, xp in table.items() if xp < LV.SENTINEL_XP}
    tier2, tier3 = LV.promotion_levels(d.exe)
    return {
        # Cumulative experience for each level that can actually be reached.
        "experience": [{"level": lvl,
                        "total": real[lvl],
                        "step": real[lvl] - real.get(lvl - 1, 0)}
                       for lvl in sorted(real)],
        "cap": max(real),
        # price = base x the trainer's own factor x the level you train away
        # from, so the factor is the only part that varies between towns.
        "train_base": LV.TRAIN_BASE_PRICE,
        # min(15, round(base charisma x 13%)), which is worth showing as the
        # staircase it is rather than as a formula.
        "bonus_points": [{"charisma": c, "points": LV.bonus_points(c)}
                         for c in range(45, 121)],
        "bonus_cap": LV.BONUS_CAP,
        "promotions": {"second": tier2, "third": tier3},
        "trainers": extract_trainers(d.world),
        "spells_by_level": LV.spells_by_level(d.exe),
    }


def build(game_dir: str | Path = "game", out_dir: str | Path = "data") -> dict:
    d = S.load(game_dir)
    missing = L.verify(d.exe)
    assert not missing, f"EXE is missing expected labels: {missing}"
    pics = (Path(game_dir) / "PICTURES.VGA").read_bytes()

    pages = extract_walkthrough(d)
    enemies = extract_enemies(d)
    payload = {
        "enemies": enemies,
        "monster_art": monster_art(d, pics, enemies),
        "projectile_art": projectile_art(d, pics, enemies),
        "spells": extract_spells(d),
        "walkthrough": pages,
        "walkthrough_index": walkthrough_sections(pages),
        "maps": extract_maps(d),
        "legend": extract_legend(d),
        "map_pages": MAP_PAGES,
        "map_marks": markers.by_page(d.world, MAP_PAGES),
        "map_unplaced": markers.unplaced(d.world, MAP_PAGES),
        # Where each door goes, keyed "<map>|<legend line>" so the panel can
        # look a legend line up directly. Decoded: section 28 places the
        # doors and DS:0xBA95 says where each one lands (`tools/links.py`).
        # The walked links are merged over the top for what the decode does
        # not reach: Saxon's ship is a script cell rather than a door, so no
        # door record carries its destination.
        "map_links": {**K.by_label(d, MAP_PAGES,
                                   markers.by_page(d.world, MAP_PAGES)),
                      **{f"{a}|{b}": v for (a, b), v in _WALKED_LINKS.items()}},
        "items": extract_items(d),
        "leveling": extract_leveling(d),
        "enhancers": I.Items(d).enhancers(),
        "transports": I.Items(d).transports(),
        "propers": [],
        "labels": {
            "effects": L.EFFECTS,
            "monster_stats": L.MONSTER_STATS,
            "special_attacks": L.SPECIAL_ATTACKS,
            "item_categories": L.ITEM_CATEGORIES,
            "class_tiers": [list(t) for t in L.CLASS_TIERS],
            "skill_ratings": L.SKILL_RATINGS,
            "spell_affects": L.SPELL_AFFECTS,
            "spell_when": L.SPELL_WHEN,
            "menu": L.RESTORATION_MENU,
        },
    }

    payload["propers"] = proper_nouns(payload)

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for key, value in payload.items():
        (out / f"{key}.json").write_text(json.dumps(value, indent=1))
    (out / "restoration.json").write_text(json.dumps(payload, separators=(",", ":")))
    return payload


if __name__ == "__main__":
    import sys

    p = build(sys.argv[1] if len(sys.argv) > 1 else "game")
    print(f"enemies       {len(p['enemies']):>4}")
    print(f"spells        {len(p['spells']):>4}")
    print(f"walkthrough   {len(p['walkthrough']):>4} pages, "
          f"{len(p['walkthrough_index'])} sections")
    print(f"maps          {len(p['maps']):>4}")
    print(f"legend        {len(p['legend']):>4}")
    print(f"\nwrote data/*.json")
