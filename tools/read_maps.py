"""Read the titles off the captured clue-book map pages.

The clue book's maps are drawn pictures rather than tile grids: the 37 x 64
table at 0x8CDDE holds tile-placement coordinates into a graphics bank, so
there is nothing to decode into cells. The captured frame *is* the map. What
still has to be read is which area each frame belongs to, because the F1 list
is not the record order: it is alphabetical, and it splits multi-level areas
into "<AREA> LEVEL n" entries the name tables do not contain.

Two things make that readable:

  * The title bar uses a **different font from the body text**, so the body
    alphabet is no help, and worse, it silently mis-matches. This starts from an
    empty alphabet.
  * Every map page prints "SELECT LEGEND OR ESC" in red at the right, in that
    same title font. That fixed string is the seed: it gives C D E G L N O R S
    T outright, and from there the area names resolve against the name table.

The trailing digits stay ambiguous after that, since "LEVEL 1" and "LEVEL 2"
are the same length and differ only in a glyph nothing else has taught, so they
come from the list order instead: the list is alphabetical, so pages sharing a
prefix are consecutive and numbered from one.
"""

from __future__ import annotations

import glob
import json
import re
from pathlib import Path

import ocr

TITLE_ROW = 1
NAME_X = (0, 190)
PROMPT_X = (190, 320)
# Printed on every map page, in the title font, and the only text on these
# screens whose content is known before anything has been read.
PROMPT = "SELECTLEGENDORESC"

ocr.COLORS.setdefault("white", lambda r, g, b: r > 185 and g > 185 and b > 185)
ocr.COLORS["mapred"] = lambda r, g, b: r > 120 and g < 70 and b < 70


def vocabulary(names: list[str], levels: int = 8) -> dict[str, str]:
    """Every title the list can print, keyed by its spaceless form."""
    out = {}
    for name in names:
        name = name.replace("~", "'")
        for text in [name, *(f"{name} LEVEL {n}" for n in range(1, levels + 1)),
                     *(f"{name} MAP {n}" for n in range(1, levels + 1))]:
            out.setdefault(text.replace(" ", ""), text)
    return out


def build_alphabet(frames: list[ocr.Frame], vocab: dict[str, str]) -> ocr.Alphabet:
    alpha = ocr.Alphabet()
    for frame in frames:
        try:
            alpha.learn(frame, TITLE_ROW, "mapred", PROMPT, *PROMPT_X)
        except ValueError:
            pass
    for _ in range(12):
        learned = 0
        for frame in frames:
            reading = alpha.read(frame, TITLE_ROW, "white", *NAME_X)
            if not reading or "?" not in reading:
                continue
            hits = [b for b in vocab
                    if len(b) == len(reading)
                    and all(r == "?" or r == c for r, c in zip(reading, b))]
            if len(hits) == 1:
                try:
                    learned += bool(alpha.learn(frame, TITLE_ROW, "white",
                                                hits[0], *NAME_X))
                except ValueError:
                    pass
        if not learned:
            break
    return alpha


def read_titles(shot_dir: str = "tmp/maps", names: list[str] | None = None) -> dict:
    names = names or json.loads(Path("data/maps.json").read_text())
    vocab = vocabulary(names)
    shots = sorted(glob.glob(f"{shot_dir}/m[0-9][0-9].png"))
    frames = [ocr.Frame(p) for p in shots]
    alpha = build_alphabet(frames, vocab)

    readings = [alpha.read(f, TITLE_ROW, "white", *NAME_X).strip() for f in frames]

    # Numbering the runs. The list is alphabetical, so pages that share a
    # prefix sit together and count up from one; that is what the trailing
    # digit has to be, and it is the only thing it can be.
    def resolve(pattern: str) -> str:
        """Match a reading against the vocabulary, "?" standing for any glyph."""
        hits = [v for b, v in vocab.items()
                if len(b) == len(pattern)
                and all(p == "?" or p == c for p, c in zip(pattern, b))]
        return hits[0] if len(hits) == 1 else pattern

    # Learn the digits rather than infer them. Numbering a run by its position
    # in the list is only safe when the run is complete, and it is not: a page
    # that refuses to open leaves a hole, and a hole silently renumbers
    # everything after it: CASTLE OF BARIAG LEVEL 2 reads as LEVEL 1 that way.
    #
    # One run is known to be whole: pages whose list indices are consecutive
    # cannot be missing a member. Those give the digit glyphs outright, and
    # every other trailing digit then reads directly instead of being counted.
    index_of = {Path(p).name: int(re.search(r"\d+", Path(p).name).group())
                for p in shots}
    runs: dict[str, list[tuple[int, ocr.Frame]]] = {}
    for path, frame, reading in zip(shots, frames, readings):
        if reading.endswith("?"):
            runs.setdefault(reading[:-1], []).append((index_of[Path(path).name], frame))
    for stem, members in runs.items():
        members.sort()
        indices = [i for i, _ in members]
        if len(members) < 2 or indices != list(range(indices[0], indices[0] + len(indices))):
            continue                      # a hole here would renumber the rest
        for position, (_, frame) in enumerate(members, start=1):
            try:
                alpha.learn(frame, TITLE_ROW, "white", f"{stem}{position}", *NAME_X)
            except ValueError:
                pass

    # A frame is a map page only if its title bar reads as an area name. The
    # list screen gets captured too, as it has to be, because judging by color
    # threw real pages away, and this is what tells the two apart.
    out = {}
    for path, frame in zip(shots, frames):
        reading = alpha.read(frame, TITLE_ROW, "white", *NAME_X).strip()
        title = resolve(reading)
        if title in vocab.values():
            out[Path(path).name] = title
    return out


if __name__ == "__main__":
    for shot, title in read_titles().items():
        print(f"{shot}  {title}")
