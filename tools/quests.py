"""The game's progress: 224 bits, what writes each and what reads each.

[docs/quests.md](../docs/quests.md) says what the bits are. This module reads
the three tables that document had nobody reading, and assembles the
writers and readers of every flag from them and from the conversation tables
in [npcs.py](npcs.py).

* **The flag array** is fourteen words at `DS:0xCFAF`, at roster header
  offsets 210 to 236. Image `0x17AFE` resolves a 1-based number: flag `n` is
  word `(n - 1) // 16`, bit `0x8000 >> ((n - 1) % 16)`.

* **The gate table** is 35 records of 22 bytes at `DS:0xC45B`, ending at a word
  of `0xFFFF`. A record names a door destination, a pointer to one of the
  fourteen words and the bit to test in it, and either a twelve-character
  password or an item id. Image `0x055A3` walks it for the door handler and
  image `0x1DB02` walks it for a traveling item.

* **The kill table** is 23 records of six bytes at `DS:0xCE51`, ending at a
  zero key. A record names a spawn id and two signed flag numbers. Image
  `0x126C8` copies the pair into the monster's own slot and image `0x1273E`
  writes it on the death.

* **The six world scripts** are the `0x0400` cell-event kind, each with a
  hand-written handler. Image `0x0B751` says which object the cell draws and
  image `0x0B7A8` runs when the party steps on it. Their constants are
  immediates in those two routines rather than a table, so `SCRIPTS` below
  carries them and `check_world_scripts` holds every one to the bytes at the address
  it was read from.

    python tools/quests.py              # one row per flag: writers, readers
    python tools/quests.py --gates      # 35 gates
    python tools/quests.py --kills      # 23 kills
    python tools/quests.py --scripts    # six world scripts
    python tools/quests.py --uses       # three items with a handler
"""

from __future__ import annotations

import struct
from collections import defaultdict

import audio as AU
import labels as LB
import links as K
import npcs as NP
import sections as S
import spawns as SP

DGROUP = K.DGROUP

# Flag array, and fourteen words image 0x17AFE divides a number over.
FLAG_WORDS_AT = 0xCFAF
FLAG_WORDS = 14
FLAG_COUNT = FLAG_WORDS * 16            # 224

GATE_TABLE_AT = K.GATE_TABLE
GATE_RECORD = 22
GATE_END = 0xFFFF
PASSWORD_AT = 0x0A
PASSWORD_LENGTH = 12
# Password prompt a gate raises, 1-based into the registry at DS:0xE265.
PASSWORD_PROMPT = 26
PROMPT_REGISTRY_AT = 0xE265
PROMPT_HEAD = 8                 # then one ten-byte line apiece
PROMPT_TEXT_AT = 6              # the line's fourth word: where its text starts
PROMPT_TEXT_COUNT = 8           # and its fifth: how many strings to take

# The destination record's own +0x0E, which picks how a shut gate refuses.
GATE_ASKS_PASSWORD = 0x8000
GATE_REFUSES = 0x4000

KILL_TABLE_AT = 0xCE51
KILL_RECORD = 6
KILL_FLAGS = 2

# The message tables the handlers print out of, as DGROUP offsets.
LOCK_MESSAGES_AT = 0x7F00

FACINGS = {0x8000: "north", 0x4000: "south", 0x2000: "west", 0x1000: "east"}

# DS:0xCEF9, the arrival word a door writes and four of the scripts touch by
# hand (docs/map.md). Bit 13 is the indoor shade set and bit 0 refuses a rest.
ENV_INDOOR = K.ENV_INDOOR
ENV_COLD = K.ENV_COLD


def _u16(blob: bytes, at: int) -> int:
    return struct.unpack_from("<H", blob, at)[0]


def _s16(blob: bytes, at: int) -> int:
    return struct.unpack_from("<h", blob, at)[0]


def _text(blob: bytes) -> str:
    return blob.split(b"\0")[0].decode("latin-1").rstrip()


def flag_of(word_address: int, bit: int) -> int:
    """The 1-based flag number a gate's pointer-and-bit pair names.

    Image `0x17AFE` counts bits down from the high one, so bit `0x8000` of the
    first word is flag 1 and bit `0x0001` of it is flag 16.
    """
    assert word_address >= FLAG_WORDS_AT, f"{word_address:#06x} is below the array"
    place = (word_address - FLAG_WORDS_AT) // 2
    assert place < FLAG_WORDS, f"{word_address:#06x} is past the array"
    assert bit and not (bit & (bit - 1)), f"{bit:#06x} is not one bit"
    return place * 16 + (16 - bit.bit_length()) + 1


def message_lines(exe: bytes, offset: int, count: int) -> list[str]:
    """`count` consecutive NUL-terminated strings from a DGROUP offset.

    The game's font has no apostrophe, so a stored string writes `~` where one
    belongs and `labels.CHARSET` puts it back (labels.py).
    """
    out, at = [], DGROUP + offset
    for _ in range(count):
        end = exe.index(b"\0", at)
        out.append(exe[at:end].decode("latin-1").rstrip().translate(LB.CHARSET))
        at = end + 1
    return out


def prompt_lines(exe: bytes, number: int) -> list[str]:
    """What a prompt number asks, out of the panel registry at `DS:0xE265`.

    Image `0x058F0` takes the word at `(n - 1) * 2` past the table. That points
    at an eight-byte head and then a ten-byte line apiece, and a line's fourth
    word is where its text starts with its fifth saying how many strings to
    take from there ([docs/party.md](../docs/party.md)). Prompt 26, which is
    the one every password gate raises, is the two lines WHAT IS THE PASSWORD?
    """
    panel = _u16(exe, DGROUP + PROMPT_REGISTRY_AT + (number - 1) * 2)
    at = _u16(exe, DGROUP + panel + PROMPT_HEAD + PROMPT_TEXT_AT)
    count = _u16(exe, DGROUP + panel + PROMPT_HEAD + PROMPT_TEXT_COUNT)
    return message_lines(exe, at, count)


# -- the gate table --

def gates(exe: bytes) -> list[dict]:
    """The 35 gated crossings and doors: which flag each tests and what opens it."""
    table = K.destinations(exe)
    out, at = [], DGROUP + GATE_TABLE_AT
    while (destination := _u16(exe, at)) != GATE_END:
        record = exe[at:at + GATE_RECORD]
        mask = table[destination - 1]["gate_mask"]
        password = _text(record[PASSWORD_AT:PASSWORD_AT + PASSWORD_LENGTH])
        out.append({
            "destination": destination,
            "flag": flag_of(_u16(record, 0x02), _u16(record, 0x04)),
            "prompt": _u16(record, 0x06) or None,
            "itemId": _u16(record, 0x08) or None,
            "password": password or None,
            # Which of the three refusals a shut gate gives, out of the
            # destination record rather than out of this one.
            "asksPassword": bool(mask & GATE_ASKS_PASSWORD),
            "refuses": bool(mask & GATE_REFUSES),
        })
        at += GATE_RECORD
    return out


# -- the kill table --

def kills(d: S.Directory) -> list[dict]:
    """The 23 monsters whose death writes a flag, with the monster named."""
    spawn_to_enemy = SP.spawn_table(d)
    enemies = {e["index"]: e["name"] for e in _enemies(d)}
    placed = {p["id"]: p for p in SP.placements(d)}
    out, at = [], DGROUP + KILL_TABLE_AT
    while (spawn := _u16(d.exe, at)):
        record = d.exe[at:at + KILL_RECORD]
        enemy = spawn_to_enemy[spawn]
        where = placed.get(spawn)
        out.append({
            "spawnId": spawn,
            "flags": [f for f in (_s16(record, 2 + 2 * i) for i in range(KILL_FLAGS)) if f],
            "enemy": enemy,
            "name": enemies.get(enemy, ""),
            "x": where["x"] if where else None,
            "y": where["y"] if where else None,
        })
        at += KILL_RECORD
    return out


def _enemies(d: S.Directory) -> list[dict]:
    import extract as EX
    return EX.extract_enemies(d)


# -- the six world scripts --

# What each handler does, read off images 0x0B751 and 0x0B7A8. Every field is
# an immediate in one of those two routines, and `check_world_scripts` holds each one
# to the bytes at the address named here.
#
#   object        what image 0x0B751 answers for the cell
#   objectFlag    signed: the object is drawn while that flag is in that state
#   needsFlag     signed: the step is refused unless that flag is in that state
#   refusal       the message a refused step prints, by DGROUP offset and count
#   writes        signed flag numbers the step writes, as a topic's slots go
#   to            where the step lands the party
#   environment   what it ORs into and ANDs out of DS:0xCEF9
#   area          DS:0xCF33, which picks the ambient list (docs/audio.md)
#   message       what a step that went through prints
#   swap          find this item and put that one in its place, over and over
#   destroys      find and destroy every one of these
#   marksCarried  set this flag where the party carries that item
WORLD_SCRIPTS = [
    {
        "script": 1, "area": 2, "at": 0x0B7B1, "drawnAt": 0x0B757,
        "object": 210, "objectFlag": -5,
        "needsFlag": -5, "refusal": None,
        "writes": [5],
        "to": {"x": 397, "y": 94, "facing": "west"},
        "environment": {"set": 0, "clear": 0},
        "message": (0x9301, 3),
        "what": "Saxon's ship, which carries the party to Thaine",
    },
    {
        "script": 2, "area": 4, "at": 0x0B84D, "drawnAt": 0x0B76E,
        "object": 223, "objectFlag": 27,
        "needsFlag": 27, "refusal": None,
        "writes": [],
        "to": {"x": 540, "y": 121, "facing": "south"},
        "environment": {"set": ENV_INDOOR, "clear": 0xE003},
        "message": None,
        "what": "the keep, once NPC 18 has built it",
    },
    {
        "script": 3, "area": 5, "at": 0x0B8C2, "drawnAt": 0x0B785,
        "object": 224, "objectFlag": 0,
        "needsFlag": 46, "refusal": (LOCK_MESSAGES_AT, 1),
        "writes": [],
        "to": {"x": 638, "y": 36, "facing": "west"},
        "environment": {"set": ENV_INDOOR, "clear": 0},
        "message": None,
        "what": "the way into the Prison",
    },
    {
        "script": 4, "area": 5, "at": 0x0B959, "drawnAt": 0x0B78F,
        "object": 231, "objectFlag": 0,
        "needsFlag": 0, "refusal": None,
        "writes": [],
        "to": {"x": 619, "y": 37, "facing": "north"},
        "environment": {"set": ENV_INDOOR, "clear": 0},
        "message": None,
        "swap": {"from": 198, "to": 205, "message": (0x9507, 3)},
        "what": "the drain, which takes the invisibility out of a ring",
    },
    {
        "script": 5, "area": 8, "at": 0x0BA1B, "drawnAt": 0x0B799,
        "object": 212, "objectFlag": 0,
        "needsFlag": 145, "refusal": (LOCK_MESSAGES_AT, 1),
        "writes": [157],
        "to": {"x": 604, "y": 123, "facing": "east"},
        "environment": {"set": 0x4000, "clear": 0},
        "message": None,
        "what": "the way into the Plane of Souls",
    },
    {
        "script": 6, "area": 2, "at": 0x0BAA7, "drawnAt": 0x0B79D,
        "object": 250, "objectFlag": 0,
        "needsFlag": 0, "refusal": None,
        "writes": [-157],
        "to": {"x": 332, "y": 70, "facing": "south"},
        "environment": {"set": 0, "clear": 0x4000},
        "message": None,
        "marksCarried": {"item": 387, "flag": 158},
        "destroys": {"first": 383, "last": 385, "message": (0x9581, 3)},
        "what": "the way back out of the Plane of Souls",
    },
]

# The party's own words the handlers write, which is what check_world_scripts looks
# for: `mov word ptr [addr], immediate` is C7 06 <addr> <immediate>.
PARTY_X, PARTY_Y, PARTY_FACING = 0xCF75, 0xCF77, 0xCF73
# DS:0xCF33, the area word that picks the ambient list. A door destination
# carries it at its own +0x0C and every handler writes it by hand.
PARTY_AREA = 0xCF33
HANDLER_SPAN = 0xC0

# The pair image 0x0B1FC searches the party between, which every handler that
# looks for an item writes first. Equal ends search for one id.
SEARCH_FIRST, SEARCH_LAST = 0x53EE, 0x53F0


def check_world_scripts(exe: bytes) -> None:
    """Hold every constant in WORLD_SCRIPTS to the bytes it was read from.

    A script's landing is three `mov word ptr` immediates in its own handler
    and its object is a `mov ax` immediate in the drawing dispatch, so each one
    is a byte string that either is there or is not.
    """
    facings = {name: bit for bit, name in FACINGS.items()}
    for one in WORLD_SCRIPTS:
        start = exe_offset(one["at"])
        for address, value in ((PARTY_X, one["to"]["x"]),
                               (PARTY_Y, one["to"]["y"]),
                               (PARTY_AREA, one["area"]),
                               (PARTY_FACING, facings[one["to"]["facing"]])):
            want = b"\xc7\x06" + struct.pack("<HH", address, value)
            assert want in exe[start:start + HANDLER_SPAN], (
                f"script {one['script']} does not write {value} to {address:#06x} "
                f"at image {one['at']:#07x}")
        # `mov ax, <object>` then `retf`, which is what image 0x0B751 answers.
        want = b"\xb8" + struct.pack("<H", one["object"]) + b"\xcb"
        start = exe_offset(one["drawnAt"])
        assert want in exe[start:start + 0x20], (
            f"script {one['script']} does not draw object {one['object']} "
            f"at image {one['drawnAt']:#07x}")


def exe_offset(image: int) -> int:
    """An image address as a file offset into REGISTER.EXE."""
    from mz import HEADER
    return image + HEADER


def world_scripts(d: S.Directory) -> list[dict]:
    """The six, with the cell each stands on and its messages read out."""
    check_world_scripts(d.exe)
    cells = {e["arg"]: (e["x"], e["y"]) for e in K.events(d) if e["kind"] == "script"}
    assert set(cells) == {one["script"] for one in WORLD_SCRIPTS}, (
        f"the cell events place scripts {sorted(cells)}")
    out = []
    for one in WORLD_SCRIPTS:
        x, y = cells[one["script"]]
        record = {k: v for k, v in one.items() if k not in ("at", "drawnAt", "message")}
        record["x"], record["y"] = x, y
        record["message"] = message_lines(d.exe, *one["message"]) if one["message"] else None
        if one["refusal"]:
            record["refusal"] = message_lines(d.exe, *one["refusal"])
        for key in ("swap", "destroys"):
            if key in record:
                inner = dict(record[key])
                inner["message"] = message_lines(d.exe, *inner["message"])
                record[key] = inner
        out.append(record)
    return out


# -- what using an item does --

# Image 0x19978 dispatches USE on the item's own properties entry, and image
# 0x0B490 is the branch three items reach (docs/items.md). Each handler's
# constants are immediates, the way a script's are, and `check_uses` holds
# every one to the bytes at the address it was read from.
#
#   standAt      the cell and facing the handler refuses anywhere else
#   needsFlag    signed: the use is refused unless that flag is in that state
#   writes       signed flag numbers a use that went through writes
#   wants        item ids the party must hold, all of them
#   destroys     item ids a use that went through destroys
#   opensNpc     the conversation the handler opens directly, by NPC number
#   to           where the handler lands the party, once that is over
ITEM_HANDLERS = [
    {
        "item": 374, "at": 0x19763,
        "what": "unlocks the portal its own gate record names",
        "gateKey": True,
    },
    {
        "item": 382, "at": 0x0B4DB,
        "what": "opens the way into the Plane of Souls",
        "standAt": {"x": 352, "y": 67, "facing": "south"},
        "writes": [145],
        "message": (0x7EE0, 1),
    },
    {
        "item": 631, "at": 0x0B507,
        "what": "ends the game: King Thaine, and then Paltivar",
        "standAt": {"x": 246, "y": 30, "facing": "west"},
        "outOfPlace": (0x95E5, 3),
        "needsFlag": 223,
        "refusal": (0x95A8, 2),
        "wants": [214, 300, 523, 548, 630],
        "wantsRefusal": (0x95C0, 3),
        "destroys": [214, 300, 523, 548, 630],
        "opensNpc": 140,
        "to": {"x": 660, "y": 132, "facing": "north"},
        "area": 3,
        "environment": {"set": ENV_INDOOR | ENV_COLD, "clear": 0},
    },
]

# The travel guard at image 0x1DA90, which is what the two traveling items
# pass through before their door destination is looked up.
TRAVEL_GUARD = {
    "flag": 157,
    "first": 383, "last": 385,
    "at": 0x1DA9B,
    "refusal": (0x90BA, 3),
    "what": "the weapons of Light do not leave the Plane of Souls",
}

HANDLER_BYTES = 0x200


def _compares(blob: bytes, address: int, value: int) -> bool:
    """Whether `cmp word ptr [address], value` is in the bytes.

    A value that fits a signed byte is assembled as `83 /7 ib` with the
    immediate sign-extended, and anything larger as `81 /7 iw`, so a test that
    looked for one form alone would miss half the comparisons in the image.
    """
    wide = b"\x81\x3e" + struct.pack("<HH", address, value)
    if wide in blob:
        return True
    if not -128 <= value <= 127:
        return False
    return b"\x83\x3e" + struct.pack("<Hb", address, value) in blob


def check_item_handlers(exe: bytes) -> None:
    """Hold every constant in ITEM_HANDLERS and TRAVEL_GUARD to the bytes it came from."""
    facings = {name: bit for bit, name in FACINGS.items()}
    for one in ITEM_HANDLERS:
        start, span = exe_offset(one["at"]), HANDLER_BYTES
        if "area" in one:
            want = b"\xc7\x06" + struct.pack("<HH", PARTY_AREA, one["area"])
            assert want in exe[start:start + span], (
                f"item {one['item']} does not write area {one['area']}")
        if "standAt" in one:
            for address, value in ((PARTY_X, one["standAt"]["x"]),
                                   (PARTY_Y, one["standAt"]["y"])):
                assert _compares(exe[start:start + span], address, value), (
                    f"item {one['item']} does not test {value} at {address:#06x}")
            want = b"\xf7\x06" + struct.pack("<HH", PARTY_FACING,
                                             facings[one["standAt"]["facing"]])
            assert want in exe[start:start + span], (
                f"item {one['item']} does not test facing {one['standAt']['facing']}")
        for item in one.get("wants", []):
            want = b"\xc7\x06" + struct.pack("<HH", SEARCH_FIRST, item)
            assert want in exe[start:start + span], (
                f"item {one['item']} does not search for item {item}")
    start = exe_offset(TRAVEL_GUARD["at"])
    for address, value in ((SEARCH_FIRST, TRAVEL_GUARD["first"]),
                           (SEARCH_LAST, TRAVEL_GUARD["last"])):
        want = b"\xc7\x06" + struct.pack("<HH", address, value)
        assert want in exe[start:start + HANDLER_BYTES], (
            f"the travel guard does not search {value} at {address:#06x}")


def item_handlers(exe: bytes) -> list[dict]:
    """The three item handlers, with their messages read out."""
    check_item_handlers(exe)
    out = []
    for one in ITEM_HANDLERS:
        record = {k: v for k, v in one.items() if k != "at"}
        for key in ("message", "refusal", "outOfPlace", "wantsRefusal"):
            if key in record:
                record[key] = message_lines(exe, *record[key])
        out.append(record)
    return out


def travel_guard(exe: bytes) -> dict:
    check_item_handlers(exe)
    record = {k: v for k, v in TRAVEL_GUARD.items() if k != "at"}
    record["refusal"] = message_lines(exe, *TRAVEL_GUARD["refusal"])
    return record


# -- what a cell's own tile does on arrival --

# Image 0x0ABD2 runs on every arrival and branches on the pad record's `+2`
# ([docs/map.md](../docs/map.md)). Six of the nineteen records carry none of
# those branch bits and land `+4` as an attack id instead. Where the record
# carries bit 0, image 0x0ADAC compares a character's feet word against one
# item and skips whoever is wearing it.
SHOD_AGAINST_TILES = 0x275          # RED DRAGON SKIN BOOTS
FEET_AT = 0x158                     # the feet word of a character record
SHOD_TEST_AT = 0x0ADAC


def check_tiles(exe: bytes) -> None:
    """Hold the boots and the word they are worn in to the image."""
    want = b"\x81\xbf" + struct.pack("<HH", FEET_AT, SHOD_AGAINST_TILES)
    at = exe_offset(SHOD_TEST_AT)
    assert exe[at:at + len(want)] == want, (
        f"image {SHOD_TEST_AT:#07x} does not test item {SHOD_AGAINST_TILES} "
        f"at character offset {FEET_AT:#x}")


def shod_against_tiles(exe: bytes) -> int:
    """The item that spares a character from a tile's own attack."""
    check_tiles(exe)
    return SHOD_AGAINST_TILES


# -- the ending --

# Image `0x05290` is what flag 224 sends the main loop to, and nothing else
# calls it. Three routines in order: `0x05472` clears a 320 x 200 buffer,
# `0x0531F` draws the first page and speaks over it, and `0x053C0` does the
# second. Every field below is an immediate in one of those, and
# `check_ending` holds each to the bytes at the address it was read from.
#
# The two pages are run 0 pictures, the run the menu and the assembly are
# painted into as well (docs/creation.md). The epilogue is paint rather than
# text, so there is no string to read: the picture is the words.
#
# A `sound` is a spoken line, and image 0x05501 waits for it to finish before
# the next one starts: image 0x184B4 spins on DS:0xF2E while a sound is
# playing and answers ZF set, which is what skips the wait beside it. That
# wait is therefore what stands in for the line's own length where sound is
# switched off. A `pause` runs either way. The twelve lines are 37 seconds of
# speech between them (audio.md).
ENDING = {
    "at": 0x0529F,
    "song": 0x18,
    "pages": [
        {
            "at": 0x0531F, "picture": 0x0D,
            "speaks": [
                {"sound": 0x82, "quiet": 0x0D},
                {"sound": 0x83, "quiet": 0x0D},
                {"sound": 0x84, "quiet": 0x0D},
                {"pause": 7},
                {"sound": 0x85, "quiet": 0x0D},
                {"pause": 4},
                {"sound": 0x86, "quiet": 0x0D},
                {"sound": 0x87, "quiet": 0x0D},
                {"pause": 7},
            ],
        },
        {
            "at": 0x053C0, "picture": 0x0E,
            "speaks": [
                {"sound": 0x88, "quiet": 0x0D},
                {"sound": 0x89, "quiet": 0x0D},
                {"pause": 7},
                {"sound": 0x8A, "quiet": 0x0D},
                {"pause": 4},
                {"sound": 0x8B, "quiet": 0x0D},
                {"pause": 4},
                {"sound": 0x8C, "quiet": 0x0D},
                {"pause": 4},
                {"sound": 0x8D, "quiet": 0x0D},
            ],
        },
    ],
    # What image 0x05299 waits before it gives the screen up, and what it
    # waits each time round after that while a sound is still playing.
    "heldFor": 0x1E,
    "heldWhileSpeaking": 0x14,
    "run": 0,
}

# Both waits count PC timer ticks: image 0x05461 spins on DS:0x536A bit 0x400
# and image 0x0A67C compares int 1Ah's own count. audio.py has the rate.
TICK_MS = round(1000 / AU.TICKS_PER_SECOND, 3)

ENDING_SPAN = 0xA0
PICTURE_AT = 0xFC3              # the picture number image 0x19AFC draws
RUN_AT = 0xFC5                  # a byte offset into the run table at DS:0x7B5C


def check_ending(exe: bytes) -> None:
    """Hold the song, the two pictures and the twelve sounds to the image."""
    want = b"\xb8" + struct.pack("<H", ENDING["song"])
    start = exe_offset(ENDING["pages"][0]["at"])
    assert want in exe[start:start + 8], "the ending does not open on its song"
    for page in ENDING["pages"]:
        start, span = exe_offset(page["at"]), ENDING_SPAN
        for address, value in ((RUN_AT, ENDING["run"]), (PICTURE_AT, page["picture"])):
            want = b"\xc7\x06" + struct.pack("<HH", address, value)
            assert want in exe[start:start + span], (
                f"the ending's page does not draw {value} at {address:#06x}")
        for step in page["speaks"]:
            if "sound" not in step:
                continue
            want = b"\xb8" + struct.pack("<H", step["sound"])
            assert want in exe[start:start + span], (
                f"the ending's page does not play sound {step['sound']}")


def ending(exe: bytes) -> dict:
    """The two pages, their speech and the song, with the waits in ms."""
    check_ending(exe)
    out = {k: v for k, v in ENDING.items() if k not in ("at", "pages")}
    out["tickMs"] = TICK_MS
    out["pages"] = [{"picture": page["picture"], "speaks": page["speaks"]}
                    for page in ENDING["pages"]]
    return out


# -- the writers and readers of every flag --

# What no table covers: the writers and readers that are instructions.
# docs/quests.md, "The other flags the code reads". The five flags the world
# scripts write and the four they read are left to the script table, which the
# table below walks for itself.
ITEM_WRITES = {
    121: "using the JEWELED PORTAL KEY (image 0x197CF)",
    145: "the ENHANCED LENS at (352, 67) (image 0x0B4DB)",
}
CODE_READS = {
    32: "the map rebuild (image 0x02EAA)",
    157: "the weapons of Light (image 0x1DA9E)",
    223: "the ORB OF ZAMORA (image 0x0B56E)",
    224: "the ending (image 0x00070)",
}


def flag_writers_and_readers(p: NP.People) -> list[dict]:
    """One row per flag: everything that writes it and everything that reads it.

    The conversation side comes out of the topic tables, the kill side out of
    the kill table, the door side out of the gate table, and the rest is the
    two lists above.
    """
    writes: dict[int, list[str]] = defaultdict(list)
    reads: dict[int, list[str]] = defaultdict(list)

    def keyword(topic: int) -> str:
        return NP._text(p.topics[topic - 1][:NP.KEYWORD])

    for npc in range(NP.NPC_COUNT):
        for topic in p.topic_block(npc):
            where = f"NPC {npc} {keyword(topic)}"
            for signed in p.flags_written(topic):
                writes[abs(signed)].append(where + ("" if signed > 0 else " (clears)"))
            for signed in p.flags_tested(topic):
                reads[abs(signed)].append(
                    f"{'offers' if signed > 0 else 'withdraws'} {where}")
        record = p.npcs[npc]
        for n, at in enumerate(NP.OPENS_ON):
            flag = NP._w(record, at)
            if flag:
                reads[flag].append(f"NPC {npc} greeting {n + 2}")
        once = NP._w(record, NP.ONE_SHOT)
        if once:
            writes[once].append(f"NPC {npc} service")
            reads[once].append(f"NPC {npc} service spent")
        gone = NP._w(record, NP.GONE_IF)
        if gone:
            reads[gone].append(f"NPC {npc} silent")

    for record in kills(p.d):
        for signed in record["flags"]:
            writes[abs(signed)].append(
                f"killing {record['name']} (spawn {record['spawnId']})")
    for gate in gates(p.d.exe):
        reads[gate["flag"]].append(f"door to destination {gate['destination']}")
        if gate["password"]:
            writes[gate["flag"]].append(f"password {gate['password']}")
    for one in world_scripts(p.d):
        for signed in one["writes"]:
            writes[abs(signed)].append(
                f"script {one['script']}" + ("" if signed > 0 else " (clears)"))
        if one["needsFlag"]:
            reads[abs(one["needsFlag"])].append(f"script {one['script']}")
        if one["objectFlag"]:
            reads[abs(one["objectFlag"])].append(f"script {one['script']} object")
        if "marksCarried" in one:
            writes[one["marksCarried"]["flag"]].append(f"script {one['script']}")
    for flag, what in ITEM_WRITES.items():
        writes[flag].append(what)
    for flag, what in CODE_READS.items():
        reads[flag].append(what)

    return [{"flag": n,
             "writtenBy": sorted(set(writes[n])),
             "readBy": sorted(set(reads[n]))}
            for n in range(1, FLAG_COUNT + 1)]


def summary(p: NP.People) -> dict:
    """The counts docs/quests.md states, for the command line and the tests."""
    rows = flag_writers_and_readers(p)
    return {
        "flags": FLAG_COUNT,
        "gates": len(gates(p.d.exe)),
        "passwords": sum(1 for g in gates(p.d.exe) if g["password"]),
        "keyed": sum(1 for g in gates(p.d.exe) if g["itemId"]),
        "kills": len(kills(p.d)),
        "scripts": len(world_scripts(p.d)),
        "used": sum(1 for r in rows if r["writtenBy"] or r["readBy"]),
        "unused": [r["flag"] for r in rows if not r["writtenBy"] and not r["readBy"]],
        "writtenNeverRead": [r["flag"] for r in rows
                             if r["writtenBy"] and not r["readBy"]],
        "readNeverWritten": [r["flag"] for r in rows
                             if r["readBy"] and not r["writtenBy"]],
    }


def load(game_dir: str = "game") -> NP.People:
    return NP.People(S.load(game_dir))


if __name__ == "__main__":
    import argparse
    import json

    ap = argparse.ArgumentParser()
    ap.add_argument("--game", default="game")
    ap.add_argument("--gates", action="store_true")
    ap.add_argument("--kills", action="store_true")
    ap.add_argument("--scripts", action="store_true")
    ap.add_argument("--uses", action="store_true")
    args = ap.parse_args()

    people = load(args.game)
    if args.gates:
        for gate in gates(people.d.exe):
            opens = gate["password"] or (gate["itemId"] and f"item {gate['itemId']}") or "-"
            print(f"destination {gate['destination']:3d}  flag {gate['flag']:3d}  {opens}")
    elif args.kills:
        for record in kills(people.d):
            print(f"spawn {record['spawnId']:5d}  flag {record['flags']}  "
                  f"{record['name']}  ({record['x']}, {record['y']})")
    elif args.scripts:
        print(json.dumps(world_scripts(people.d), indent=1))
    elif args.uses:
        print(json.dumps({"itemHandlers": item_handlers(people.d.exe),
                          "travelGuard": travel_guard(people.d.exe)}, indent=1))
    else:
        print(json.dumps(summary(people), indent=1))
        for row in flag_writers_and_readers(people):
            print(f"{row['flag']:3d}  {'; '.join(row['writtenBy']) or '-':<60}  "
                  f"{'; '.join(row['readBy']) or '-'}")
