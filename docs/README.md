# How to read these documents

[world-dat.md](world-dat.md) indexes the rest. This file defines the terms they
use.

## What belongs here

`docs/` holds settled findings and how each was settled: a record layout, a
field's meaning, an address, the rule a tool implements, and the evidence for
each. Work in progress is not here.

## How a finding is marked

Every field is classified, once for the whole file format or field by field in
an Evidence column. There are six classifiers.

| Classifier | What was done |
|---|---|
| **measured** | the field was changed in the running game and the game's behavior changed with it, or a value was read back out of it and compared against the field. [tools/fight_probe.js](../tools/fight_probe.js), the cabinet's trainer, a scripted session. |
| **observed** | the game was run and what it did was recorded rather than what it held: which byte ranges it read ([tools/trace_fs.js](../tools/trace_fs.js)), or what stopped being drawn when a range was blanked ([tools/probe_map_data.js](../tools/probe_map_data.js)). |
| **screens** | the game printed a value on its own clue-book page, and that value was compared against the field, for every record the book lists. The page and the count are given. A mismatch is the field's. |
| **rendered** | the game drew from the field, and the drawing was rebuilt from the field and diffed pixel for pixel against a capture of the same page. This is how a field the book prints no value for is checked, a picture number or a recolor list. The comparison covers the drawing model as well, so a mismatch can be in either. |
| **code** | the field was read off the disassembly. The image address of the instruction that uses it is given. |
| **shape** | none of the above. The reading is fixed by the data's own arithmetic: a size that divides exactly, a partition with nothing left over, a run that stops where the next section begins. |

**The order is strongest first.** Under the first two the game runs, so
agreement shows what a field does. Under the next two the comparison is against
what the game prints or draws from it, so agreement shows only what the field
holds: a page can print a number nothing else in the game reads, and the match
looks the same. Under **code** nobody has checked the reading but the person who
made it, which is why [leveling.md](leveling.md) and [combat.md](combat.md) flag
that at the top and carry corroborations at the bottom. A reading can satisfy
**shape** and still be wrong: the item record's word at 16 partitions all 631
records cleanly and is still **undecoded**.

**undecoded** marks a field whose meaning is not established.

Put a count beside the classifier. Where it falls short of the whole, name the
remainder.

## The clue book's pages

Most **screens** evidence comes from Restoration, the clue book that shipped
with the game. The documents name its six sections by their function key.

| Key | Page | Captured by |
|---|---|---|
| F1 | maps | [tools/capture_maps.js](../tools/capture_maps.js), and the legends by [tools/capture_legend.js](../tools/capture_legend.js) |
| F2 | monster statistics | [tools/capture_monsters.js](../tools/capture_monsters.js) |
| F3 | spells | [tools/capture_spells.js](../tools/capture_spells.js) |
| F4 | magic users | [tools/capture_classes.js](../tools/capture_classes.js) |
| F5 | inventory items | [tools/capture_items.js](../tools/capture_items.js) |
| F6 | the walkthrough | stored as text, so it is read rather than captured |

[tools/ocr.py](../tools/ocr.py) reads the figures off the frames. The frames
live in `tmp/` and are not kept, so re-checking a **screens** count means
running the capture again.

## Reproducing a claim

The decoders run against a copy of the game in `game/`:

    make data      # rebuild data/*.json from game/; rewrites the same bytes
    make test-py   # the decoders and every layout claim they rest on

Addresses are **image offsets** unless a `DS:` prefix says otherwise, meaning
the file offset minus the 16 KB MZ header. `DS:0` sits at image `0x1DDB0`.
[world-dat.md](world-dat.md) says the rest.
