"""Crop the captured clue-book maps into web/maps/ and index them by area.

The clue book's maps are drawn pictures, not tile grids: the 37 x 64 table at
0x8CDDE holds tile-placement coordinates into a graphics bank rather than a
grid of cells, so there is nothing to decode into walls and markers. The
captured frame *is* the map, and cropping the game's own title bar off leaves
the map itself: the panel labels it, using the title read by read_maps.

The images are written as files beside the panel rather than inlined: 37
textured maps come to about a megabyte, and base64 would add a third again to a
page that is otherwise a couple of hundred kilobytes.
"""

from __future__ import annotations

import json
from pathlib import Path

import pngutil
import read_maps

# Content read off the game's screens, not decoded from its files. Never
# shipped.
OBSERVED = Path(__file__).resolve().parent.parent / "observed"

ROOT = Path(__file__).resolve().parent.parent
# The title bar is the top 16 rows: the area name on the left and "SELECT
# LEGEND OR ESC" on the right, which means nothing outside the game.
TITLE_BAR = 16


def build(shot_dirs: list[str] | str = "tmp/maps",
          out_dir: str = "web/maps") -> list[dict]:
    """Crop every captured page, taking each area from whichever walk caught it.

    A walk can miss a page, since the game occasionally does not open one, so the
    runs are merged by title rather than trusting any single pass.
    """
    if isinstance(shot_dirs, str):
        shot_dirs = [shot_dirs]
    titles: dict[str, tuple[str, str]] = {}
    for shot_dir in shot_dirs:
        for shot, title in read_maps.read_titles(shot_dir).items():
            titles.setdefault(title, (shot_dir, shot))
    out_path = ROOT / out_dir
    out_path.mkdir(parents=True, exist_ok=True)
    for stale in out_path.glob("*.png"):
        stale.unlink()

    pages = []
    for n, (title, (shot_dir, shot)) in enumerate(sorted(titles.items())):
        src = Path(shot_dir) / shot
        w, h, _ = pngutil.read(str(src))
        name = f"{n:02d}"
        dst = out_path / f"{name}.png"
        cw, ch = pngutil.zoom(str(src), str(dst), (0, TITLE_BAR, w, h), scale=1)
        pages.append({"title": title, "image": f"maps/{name}.png",
                      "width": cw, "height": ch,
                      "bytes": dst.stat().st_size})
    return pages


if __name__ == "__main__":
    pages = build(["tmp/maps4", "tmp/maps3", "tmp/maps", "tmp/maps2"])
    OBSERVED.mkdir(exist_ok=True)
    (OBSERVED / "observed_maps.json").write_text(
        json.dumps(pages, indent=1) + "\n")
    total = sum(p["bytes"] for p in pages) / 1024
    print(f"{len(pages)} maps, {total:.0f} kB in web/maps/")
    for p in pages[:3]:
        print(f"  {p['title']:28} {p['width']}x{p['height']}  {p['bytes'] / 1024:.0f} kB")
