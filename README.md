# Yendorian Tales III — Integrated Gaming Environment

This project runs *Yendorian Tales: The Tyrants of Thaine* (1997, Spectrum Pacific Publishing) in a browser under [js-dos]. It rebuilds the game's own clue book from tables decoded out of the game's data files.

**You supply the game.** This repository contains no part of the game, and it ships no data decoded from it. The decode runs on the machine that holds the game.

[js-dos]: https://js-dos.com

## Running it locally

You need `python3`, and `bun` for the development server. `yarn install` installs the pinned copy of bun into `node_modules`.

    yarn install
    cd cabinet && bun install
    uv venv && uv pip install capstone pytest

Put your copy of the game in `game/`, then run:

    make serve         # http://localhost:8080, against a patched copy
    make serve-stock   # the game exactly as it shipped, including the introduction

`make serve` builds the patched copy of the game first, if it is not already current. When the patched copy is current, the patcher confirms its hash and does nothing further.

## Reverse engineering

The list below records how far the decode of the game's own file formats has progressed. `docs/` holds the offsets, the record layouts and the evidence for every item marked as settled.

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

## License

The code in this repository is licensed under the MIT license. See [LICENSE](LICENSE).

That license covers this project only. *Yendorian Tales III* belongs to Spectrum Pacific Publishing, and the license of your copy of the game governs that copy.
