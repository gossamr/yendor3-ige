# Yendorian Tales III — Integrated Gaming Environment

[![tests](../../actions/workflows/tests.yml/badge.svg)](../../actions/workflows/tests.yml)

This project runs *Yendorian Tales: The Tyrants of Thaine* (1997, Spectrum Pacific Publishing) in a browser under [js-dos]. Beside the game it renders the game's own clue book as a panel, built from tables decoded out of the game's data files.

**You supply the game.** This repository contains no part of the game, and it ships no data decoded from it. You can run the project against a copy on your own disk, or host it and let each player supply a copy. In both cases the decode runs on the machine that holds the game.

[js-dos]: https://js-dos.com

## What it does

- The game runs under DOSBox in the browser, with mouse, keyboard and sound. Saved games are held in the browser's own storage and can be exported to a file.
- Restoration, the clue book that shipped with the game, is rebuilt as a searchable panel. It holds 71 creatures with every statistic, immunity and the game's own picture of them, 107 spells, 304 items, all 54 maps drawn from the game's own tiles, and the 33 page walkthrough.
- Three byte patches are applied to a copy of the executable, never to the original. They skip the introduction, stop the main menu entering its attract loop, and stop a change of character class discarding the attributes already rolled.

## Reverse engineering

The list below records how far the decode of the game's own file formats has progressed. [docs/](docs/) holds the offsets, the record layouts and the evidence for every item marked as settled.

- [x] Section directory
- [x] Map grid and object layer ([docs/map.md](docs/map.md))
- [x] Map registry and names ([docs/map.md](docs/map.md))
- [x] Legend markers ([docs/map.md](docs/map.md))
- [x] Text and prose
- [x] Leveling and skills ([docs/leveling.md](docs/leveling.md))
- [x] Character roster
- [x] Artwork (the ten picture runs, the palette and the creature art, [docs/pictures.md](docs/pictures.md))
- [x] Tile artwork (which tile a map id draws, [docs/map.md](docs/map.md))
- [x] The world grid (one plane of 800 by 168 cells, and which cells the party may stand on, [docs/map.md](docs/map.md))
- [x] Item record (every row of a clue book page, the properties and effects tables, and the book's own filing, [docs/items.md](docs/items.md))
- [x] Enemy record (every offset except one is named, [docs/monsters.md](docs/monsters.md))
- [x] Spell record (every row of a clue book page, and which classes may cast, [docs/spells.md](docs/spells.md))
- [ ] NPCs, conversation, shops (the records, the services and the prices are decoded, what gates a service and what a shop stocks are not, [docs/shops.md](docs/shops.md))
- [x] Combat (the resolver, damage, resistance and rewards, [docs/combat.md](docs/combat.md))
- [x] Save file (the seven sections, the seek that addresses them, the header's position and clock, and the seen grid, [docs/saves.md](docs/saves.md))
- [x] Map transitions (the cell event table, and the destination of each door, [docs/map.md](docs/map.md))

## Running it locally

You need `python3`, and `bun` for the development server. `yarn install` installs the pinned copy of bun into `node_modules`. The Makefile tries each candidate copy of bun in turn and uses the first one that runs on this platform. That copy of bun then installs the cabinet's own dependencies against [cabinet/bun.lock](cabinet/bun.lock), which is the lockfile that the Dockerfile and the CI workflows also resolve from. Do not use npm, because it produces a js-dos tree that the cabinet cannot boot.

    yarn install                           # bun
    cd cabinet && npx bun install && cd .. # js-dos and pyodide

Decoding the game and building the panel use the Python standard library and nothing else. That constraint is what allows the same scripts to run in the browser under pyodide, where no package can be installed. Two other jobs each require one package. `capstone` disassembles the executable for [tools/disasm.py](tools/disasm.py) and [tools/xref.py](tools/xref.py), and `pytest` runs the test suite.

    uv venv && uv pip install capstone pytest

Put your copy of the game in `game/`, then run:

    make all      # decode the game and build the panel, about 3 seconds on an older machine
    make serve    # http://localhost:8080

`make serve` builds the patched copy of the game first, if it is not already current. When the patched copy is current, the patcher confirms its hash and does nothing further.

    make serve PORT=8090   # serve on another port
    make serve-stock       # the game exactly as it shipped, including the introduction
    make test              # 332 python, 54 javascript, panel, persistence, boot

## The trainer

`make trainer` writes a second copy of the emulator that carries a hook. The hook can read and write the memory of the running game. Opening `http://localhost:8080/?trainer` then adds a Trainer tab to the panel, which locates the party in memory and edits it. Without that flag the cabinet runs js-dos exactly as it ships, and the hosted build does not contain the hooked copy at all.

The tab holds each character's health, magic and conditions. Behind those it holds the character sheet, which is twenty six attributes and skills in both the current column and the maximum column. It also holds the party's purse, the party's position and the in-game time, any item in the game, and the health of each creature in the current fight.

Below those controls, collapsed by default, is a Debug block. It is intended for taking the game apart rather than for playing it. It edits the party's band, cell and facing one number at a time. It edits a creature's own record in place, which is what [tools/fight_probe.js](tools/fight_probe.js) does without booting the game separately. It also opens a window on the game's memory. That window re-reads a region on every tick and reports what changed since the snapshot was taken, searches for a value that the game is currently displaying and returns the addresses that could hold it, and writes or freezes the address that the search returns.

The same hook is available from the command line, which is how a question about the game is settled by measurement. [tools/fight_probe.js](tools/fight_probe.js) patches a creature's record, fights the creature, and reports how much health each blow removed.

## Hosting it

The server does no work beyond serving files, so a static host is sufficient. `make pages` writes `build/pages`, which holds the page, the panel shell and the emulator, with no game and no decoded data.

The page determines which deployment it is running in by asking the server whether it lists any game files. It requests a zip archive from the player only when the server lists none. The archive is read in the browser tab and is never uploaded.

## With Docker

    make all && docker compose up            # local, game mounted read only
    docker compose -f compose.hosted.yml up  # hosted, nothing mounted

There are two files rather than one file and an override. Compose merges volume lists instead of replacing them, and the hosted deployment is defined by having no volumes at all.

## Layout

| | |
|---|---|
| [cabinet/](cabinet/) | The page, the emulator host, and the development server |
| [web/](web/) | The panel's CSS and JavaScript, and the two builds of the page |
| [tools/](tools/) | The decoders, the disassembler, and the capture drivers |
| [docs/](docs/) | What has been decoded, and how the game is run. Start at [world-dat.md](docs/world-dat.md) |
| [game/](game/) | Your copy of the game. Not in this repository |

[docs/world-dat.md](docs/world-dat.md) indexes the rest. [map.md](docs/map.md), [items.md](docs/items.md), [monsters.md](docs/monsters.md), [spells.md](docs/spells.md), [saves.md](docs/saves.md), [shops.md](docs/shops.md) and [pictures.md](docs/pictures.md) describe the file formats. [combat.md](docs/combat.md) and [leveling.md](docs/leveling.md) describe the rules those formats encode. [running.md](docs/running.md), [patching.md](docs/patching.md) and [panel.md](docs/panel.md) describe the harness around them.

[MANUAL.md](MANUAL.md) is a player's manual written from the decoded tables.

## License

The code in this repository is licensed under the MIT license. See [LICENSE](LICENSE).

That license covers this project only. *Yendorian Tales III* belongs to Spectrum Pacific Publishing, and the license of your copy of the game governs that copy.
