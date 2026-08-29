# Decoders

These tools turn the game's data files into JSON. `make data` runs them once, and `make panel` builds the pages from the JSON they wrote. The panel therefore reads no game file while a reader uses it.

The hosted deployment is the exception. It ships no game and no JSON, so when a player supplies a copy of the game the browser runs [pack_maps.py](pack_maps.py), [extract.py](extract.py) and [world_map.py](world_map.py) under pyodide, in a worker, in that player's own tab. Those three files are the reason the decoders use the Python standard library and nothing else, because a package cannot be installed there.

## The decoders

    sections.py      the WORLD.DAT section directory, read out of REGISTER.EXE
    labels.py        the UI label strings, which name the binary fields
    extract.py       runs the decoders below and writes data/*.json
    items.py         the item record, its properties and effects tables, and
                     the clue book's own filing of them
    levels.py        the leveling tables, and the rolls the game makes
    skills.py        the twelve skills, each a blend of three attributes
    saves.py         the seven sections of a saved game
    registry.py      which of the 140 map slots the game names
    markers.py       the gold markers on a clue book map, and their captions
    links.py         the cell event table, and the destination of each door
    tiles.py         the map's tile artwork and its palette
    pack_maps.py     every map page, drawn from the files as tiles and a grid
    world_map.py     all 140 map slots drawn where they sit, as one PNG
    pictures.py      the ten picture runs in PICTURES.VGA, and the creature art

## The instruments

    disasm.py        segment aware disassembly. --around decodes through an
                     address rather than from it
    mz.py            the MZ header and the relocation table, without capstone
    xref.py          every instruction that reads a given struct offset
    patch.py         the three byte patches, applied to a copy
    combat_model.py  the damage, resistance and reward rules, as a model
    ocr.py           reads the game's own font off a captured frame
    pngutil.py       PNG read, write and crop zoom, for captured frames
    fight_probe.js   patches a creature's record, fights it, measures the damage
    build_trainer.js writes the emulator copy that the Trainer tab talks to

## The checks

    panel_check.js   renders the panel in Chromium and asserts each tab fills
    cabinet_check.js boots the game in a browser and asserts it paints
    decode_check.js  drops a zip into a browser and asserts the decode runs
    trainer_check.js boots the cabinet with the hook and reads the party back
    verify_tiles.py  compares the tiles a page predicts against the cache

## How a field earns a name

A field is given a real name in [extract.py](extract.py) only when there is evidence for it. Every other field keeps an `unknown_<offset>` name. A reader of the JSON can then never mistake a guess for a fact.

**verified** means the value was read off the game's own screen while it ran under emulation, and it matched the decoded field. [cabinet/session.js](../cabinet/session.js) reduces the cost of that, because it keeps one emulator running, reaches the clue book and captures the screen. `pngutil.zoom` then makes the numbers in a 320 by 200 frame legible.

Most of the enemy record is verified this way against every creature the game lists, not against a sample. The five combat statistics come to 355 readings, all of which match. Each of the four rewards matches on all 71 creatures, and so does each of the twelve immunity and resistance rows. See [docs/monsters.md](../docs/monsters.md).

**inferred** means the data supports the field strongly, but the value was not read off the running game. The creature family code at offset 28 is the one field of this kind. It divides the 71 creatures the game lists into eleven groups that match their kinds exactly, and two of those groups are named by the game itself, because `INSECT` and `UNDEAD` appear as targets in the spell `AFFECTS` enumeration.

**unknown** means the field is emitted raw. One offset of the enemy record is in this class. Offset 104 is zero in all 73 records, so nothing distinguishes it and nothing reads it.

## What proves it still works

The tests in [tests/](../tests) assert against the game's own files and screens rather than against a stored snapshot of the decoder's output. A decoder that regresses therefore fails a test, while a decoder whose output merely changes shape does not.

- The section directory tiles `WORLD.DAT` exactly and ends at the length of the file.
- The enemy and spell sections divide evenly into 73 and 107 records.
- The spell description index tiles its own stream with no gap and no overlap.
- At least 60 spells quote a damage figure in their own prose, and at most one of those disagrees with the decoded field. The one is ERADICATE, whose prose states 400 where its record holds 480, which is a discrepancy in the game's content rather than in the decode.
- Every walkthrough page ends with its own `n OF 33` footer.
- Every label named in [labels.py](labels.py) is present in the executable.
- All 650 rows of the 170 captured item pages come back out of the decode.
