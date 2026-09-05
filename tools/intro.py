"""The introduction, image `0x1BB7C`, which the menu's own Introduction plays.

Five scenes with an Escape poll between each, then a teardown that fades out
and puts the menu's song back. [docs/creation.md](../docs/creation.md) says
what each scene is; this reads the constants out of the image.

Nothing here is a table. The whole sequence is hand-written code between image
`0x1BB7C` and `0x1C0D2`, so `SCENES` below carries its constants and
`check_intro` holds every one of them to the bytes at the address it was read
from, the way `quests.check_scripts` does for the world scripts.

Three routines do the work, and two of them are the ending's own shape:

* **`0x1C11E`** cycles `cx` consecutive pictures from `DS:0xFC3`, two ticks
  apiece, polling Escape between them.
* **`0x1C3B4`** waits for a sound to finish, or `cx` ticks where sound is
  switched off. Image `0x05501` is the same routine in the ending.
* **`0x1C13C`** plays a talking-head block, below.

    python tools/intro.py            # the five scenes
    python tools/intro.py --heads    # the three talking heads and their words
"""

from __future__ import annotations

import struct

import audio as AU
import labels as LB
import links as K
import sections as S

DGROUP = K.DGROUP

INTRO_AT = 0x1BB7C
INTRO_END = 0x1C0D2

# The run table entry a picture is drawn out of, as a byte offset at DS:0xFC5,
# and the picture number at DS:0xFC3 (tools/pictures.py). An entry is 16 bytes.
RUN_AT, PICTURE_AT = 0xFC5, 0xFC3
RUN_ENTRY = 16

# What a picture cycle spends on each frame, and what the head player takes off
# its own tick budget per frame. Both are PC timer ticks, and audio.py has the
# rate that turns one into milliseconds.
FRAME_TICKS = 2
HEAD_TICKS_PER_FRAME = 2
TICK_MS = round(1000 / AU.TICKS_PER_SECOND, 3)

# DS:0xCF63 bit 3 is the SOUND FX switch (docs/audio.md). Image 0x1C13C reads
# it to pick which half of a talking head runs.
SOUND_FX_BIT = 0x0008


def _u16(blob: bytes, at: int) -> int:
    return struct.unpack_from("<H", blob, at)[0]


def exe_offset(image: int) -> int:
    from mz import HEADER
    return image + HEADER


def _lines(exe: bytes, offset: int, count: int) -> list[str]:
    out, at = [], DGROUP + offset
    for _ in range(count):
        end = exe.index(b"\0", at)
        out.append(exe[at:end].decode("latin-1").strip().translate(LB.CHARSET))
        at = end + 1
    return out


# -- the talking heads --

# Image 0x1C13C's 14-byte block ([docs/audio.md](../docs/audio.md)). The three
# the intro plays are the only path to sounds 67 to 75 except 71.
#
#   +0x00 first sound        +0x08 pictures cycled per sound
#   +0x02 first picture      +0x0A lines of that caption
#   +0x04 caption address    +0x0C ticks, used only with sound off
#   +0x06 sounds to play
HEAD_BLOCKS = (0x597C, 0x598A, 0x5998)
HEAD_RECORD = 14


def heads(exe: bytes) -> list[dict]:
    """The three blocks, with each caption read out.

    **The caption is the substitute rather than a subtitle.** Image `0x1C13C`
    tests the SOUND FX switch first: with sound on it plays the block's run of
    lines and prints nothing, and with sound off it prints the caption and
    cycles the head for the block's own tick count instead. So the words are on
    screen only where they cannot be heard.
    """
    out = []
    for base in HEAD_BLOCKS:
        r = struct.unpack_from("<7H", exe, DGROUP + base)
        out.append({
            "block": base,
            "firstSound": r[0], "sounds": r[3],
            "firstPicture": r[1], "picturesPerSound": r[4],
            "quiet": r[6],
            "caption": _lines(exe, r[2], r[5]),
        })
    return out


# -- the five scenes --

# Every field is an immediate between image 0x1BB7C and 0x1C0D2.
#
#   at          where the scene's own routine starts
#   run         the run its pictures come from, 0 for the full-screen stills
#   picture     the still it opens on
#   shows       how the still reaches the screen: a palette fade, or the
#               scanline wipe at image 0x1C376, which is the ending's own
#   holdTicks   what it waits after that
#   speaks      runs of consecutive sounds, each followed by image 0x1C3B4
#   caption     a panel of text, by DGROUP offset and line count
#   song        a song started before the scene draws
#   sound       one sound played before it
#   zoom        a picture scaled into place over the still, frame by frame
#   beats       scene 5's own order, which mixes cycles, sounds and heads
SCENES = [
    {
        "scene": 1, "at": 0x1BC75, "run": 0, "picture": 8,
        "shows": "fade", "holdTicks": 7 * 5,
        "what": "the title picture",
    },
    {
        "scene": 2, "at": 0x1BCD1, "run": 0, "picture": 9, "shows": "wipe",
        "speaks": [{"first": 0x33, "count": 3, "quiet": 8},
                   {"pause": 3},
                   {"first": 0x36, "count": 5, "quiet": 10}],
        "what": "the first page of the story",
    },
    {
        "scene": 3, "at": 0x1BD4A, "run": 0, "picture": 10, "shows": "wipe",
        "speaks": [{"first": 0x3B, "count": 8, "quiet": 9}],
        "holdTicks": 5,
        "what": "the second page",
    },
    {
        "scene": 4, "at": 0x1BDB0, "run": 0, "picture": 11, "shows": "fade",
        "song": 0x0A, "sound": 0x53, "holdTicks": 20 * 5,
        "zoom": {"over": 11, "picture": 12, "frames": 0x19,
                 "from": [6, 4, 0x9D, 0x62], "step": [0x0C, 8, -6, -4]},
        "caption": (0x9626, 1),
        "what": "the world, with the title zooming onto it",
    },
    {
        "scene": 5, "at": 0x1BF44, "run": 3, "x": 70, "y": 40,
        "caption": (0x9325, 2),
        "beats": [
            {"picture": 40, "cycle": 7},
            {"head": 0x597C},
            {"picture": 45, "cycle": 5},
            {"sound": 71},
            {"picture": 50, "cycle": 0x17},
            {"head": 0x598A},
            {"song": 0x0B},
            {"picture": 73, "cycle": 7},
            {"head": 0x5998},
        ],
        "what": "Zamora, who says what the party is for",
    },
]

SCENE_SPAN = 0x200


def check_intro(exe: bytes) -> None:
    """Hold every constant in SCENES to the bytes it was read from."""
    assert [one["at"] for one in SCENES] == sorted(one["at"] for one in SCENES)
    for one in SCENES:
        start, span = exe_offset(one["at"]), SCENE_SPAN
        blob = exe[start:start + span]
        want = b"\xc7\x06" + struct.pack("<HH", RUN_AT, one["run"] * RUN_ENTRY)
        assert want in blob, f"scene {one['scene']} does not draw out of run {one['run']}"
        pictures = [one.get("picture")] + [b.get("picture") for b in one.get("beats", [])]
        for picture in [p for p in pictures if p is not None]:
            want = b"\xc7\x06" + struct.pack("<HH", PICTURE_AT, picture)
            assert want in blob, f"scene {one['scene']} does not draw picture {picture}"
        for key in ("song", "sound"):
            played = [one[key]] if key in one else []
            played += [b[key] for b in one.get("beats", []) if key in b]
            for n in played:
                assert b"\xb8" + struct.pack("<H", n) in blob, (
                    f"scene {one['scene']} does not play {key} {n}")
        for run in one.get("speaks", []):
            if "first" not in run:
                continue
            assert b"\xb8" + struct.pack("<H", run["first"]) in blob, (
                f"scene {one['scene']} does not open a run on sound {run['first']}")
        for beat in one.get("beats", []):
            if "head" in beat:
                assert b"\xbe" + struct.pack("<H", beat["head"]) in blob, (
                    f"scene {one['scene']} does not play head {beat['head']:#06x}")


def intro(exe: bytes) -> dict:
    """The five scenes and the three heads, with every caption read out."""
    check_intro(exe)
    by_block = {one["block"]: one for one in heads(exe)}
    scenes = []
    for one in SCENES:
        scene = {k: v for k, v in one.items() if k not in ("at", "caption", "beats")}
        if "caption" in one:
            scene["caption"] = _lines(exe, *one["caption"])
        if "beats" in one:
            scene["beats"] = [dict(b, head=by_block[b["head"]]) if "head" in b else dict(b)
                              for b in one["beats"]]
        scenes.append(scene)
    return {"scenes": scenes, "frameTicks": FRAME_TICKS,
            "headTicksPerFrame": HEAD_TICKS_PER_FRAME, "tickMs": TICK_MS}


def sounds_played(exe: bytes) -> list[int]:
    """Every sound index the intro plays, in order."""
    out = []
    for one in intro(exe)["scenes"]:
        if "sound" in one:
            out.append(one["sound"])
        for run in one.get("speaks", []):
            if "first" in run:
                out += list(range(run["first"], run["first"] + run["count"]))
        for beat in one.get("beats", []):
            if "sound" in beat:
                out.append(beat["sound"])
            if "head" in beat:
                head = beat["head"]
                out += list(range(head["firstSound"], head["firstSound"] + head["sounds"]))
    return out


def load(game_dir: str = "game") -> S.Directory:
    return S.load(game_dir)


if __name__ == "__main__":
    import argparse
    import json

    ap = argparse.ArgumentParser()
    ap.add_argument("--game", default="game")
    ap.add_argument("--heads", action="store_true")
    args = ap.parse_args()

    d = load(args.game)
    if args.heads:
        for one in heads(d.exe):
            print(f"block {one['block']:#06x}  sounds {one['firstSound']} to "
                  f"{one['firstSound'] + one['sounds'] - 1}  "
                  f"picture {one['firstPicture']}  {one['quiet']} ticks quiet")
            for line in one["caption"]:
                print(f"    {line}")
    else:
        print(json.dumps(intro(d.exe), indent=1))
        print("sounds:", sounds_played(d.exe))
