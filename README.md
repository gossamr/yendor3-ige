# Yendorian Tales III — Integrated Gaming Environment

This project runs *Yendorian Tales: The Tyrants of Thaine* (1997, Spectrum Pacific Publishing) in a browser under [js-dos]. It rebuilds the game's own clue book from tables decoded out of the game's data files.

**You supply the game.** This repository contains no part of the game, and it ships no data decoded from it. The decode runs on the machine that holds the game.

[js-dos]: https://js-dos.com

## Reverse engineering

The list below records how far the decode of the game's own file formats has progressed. `docs/` holds the offsets, the record layouts and the evidence for every item marked as settled.

- [ ] Section directory
- [ ] Map grid and object layer
- [ ] Map registry and names
- [ ] Legend markers
- [ ] Text and prose
- [ ] Leveling and skills
- [ ] Character roster
- [ ] Artwork
- [ ] Tile artwork
- [ ] The world grid
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
