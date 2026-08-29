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
- [ ] Leveling and skills
- [ ] Character roster
- [ ] Artwork
- [x] Tile artwork (which tile a map id draws, [docs/map.md](docs/map.md))
- [x] The world grid (one plane of 800 by 168 cells, and which cells the party may stand on, [docs/map.md](docs/map.md))
- [ ] Item record
- [ ] Enemy record
- [ ] Spell record
- [ ] NPCs, conversation, shops
- [ ] Combat
- [ ] Save file
- [ ] Map transitions

## License

The code in this repository is licensed under the MIT license. See [LICENSE](LICENSE).

That license covers this project only. *Yendorian Tales III* belongs to Spectrum Pacific Publishing, and the license of your copy of the game governs that copy.
