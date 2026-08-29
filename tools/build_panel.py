#!/usr/bin/env python3
"""Assemble the Restoration panel, either self-contained or as a shell.

Two builds, because the panel is used two ways.

`build()` inlines the CSS, the JS *and* the decoded tables into one file. That
works with no server and no fetch, which is what opening it off disk needs.
It also puts the game's content in the file, so the result cannot be
distributed; see tests/test_distribution.py.

`build_shell()` inlines only the CSS and the JS, and fetches the tables at
run time. That file contains nothing but our own code, so it is the one that
ships: each user's own copy of the game is decoded on their machine and the
result handed to the same panel. A host page that already holds the tables can
set `window.RESTORATION` before the shell runs, and no fetch happens at all.

Only `build()` needs the game. `extract` is imported inside it so that the
shell can be built where no copy of the game exists.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"

# Where the shell looks for its tables when the host page has not supplied
# them. This is where cabinet/serve.js serves them from; a build for some other
# layout passes its own url to build_shell().
DATA_URL = "/data/restoration.json"

# The written guides, inlined into both builds. These are ours, not the game's:
# nothing in them is decoded content, so unlike the tables they are as
# shippable as the code is, and the shell carries them rather than fetching
# them. Markdown goes across as written and panel.js parses it.
GUIDES = (
    ("manual", "Manual", "MANUAL.md"),
    ("strategy", "Strategy", "STRATEGY.md"),
)


def guides() -> list[dict]:
    """The guide sources, for inlining. Missing files are skipped rather than
    raising, so a checkout without them still builds a working panel."""
    out = []
    for key, label, name in GUIDES:
        path = ROOT / name
        if path.exists():
            out.append({"key": key, "label": label, "text": path.read_text()})
    return out

TEMPLATE = """<!doctype html>
<meta charset="utf-8">
<title>Restoration</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
{css}
</style>
<header>
  <h1>Restoration</h1>
  <span class="sub">The On-Line Clue Book &middot; Yendorian Tales III</span>
  <span class="spacer"></span>
  <input id="search" type="search" placeholder="Search everything  (/)"
         autocomplete="off" spellcheck="false">
</header>
<nav></nav>
<main></main>
<script>
window.RESTORATION = {data};
window.GUIDES = {guides};
</script>
<script>
{js}
</script>
"""

# Same page, with the tables fetched rather than inlined. panel.js is an IIFE
# that reads window.RESTORATION as it starts, so wrapping it in an async
# function that resolves the data first needs no change to the panel itself.
#
# Where the tables come from depends on the deployment, and the page works it
# out rather than being built two ways. In a frame it asks the page holding it
# first: hosted, the cabinet has decoded the player's own copy and there is no
# data/ on the server to fetch. Asking costs one message locally, where the
# answer is "I have none" and the fetch happens as before.
SHELL = """<!doctype html>
<meta charset="utf-8">
<title>Restoration</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
{css}
</style>
<header>
  <h1>Restoration</h1>
  <span class="sub">The On-Line Clue Book &middot; Yendorian Tales III</span>
  <span class="spacer"></span>
  <input id="search" type="search" placeholder="Search everything  (/)"
         autocomplete="off" spellcheck="false">
</header>
<nav></nav>
<main></main>
<script>
window.GUIDES = {guides};
</script>
<script>
(async () => {{
  // What the page holding this frame has, if anything.
  //
  // The host answers every ask, with tables or with nothing, so this settles
  // on a reply rather than on a timer. A host that has not been taught the
  // exchange never answers (an ordinary page with the panel embedded in it,
  // say) so there is one, and it is short: the reply is posted from a
  // message handler the host installs before the frame is given a src.
  const fromHost = () => new Promise((resolve) => {{
    if (window.parent === window) return resolve(null);
    const done = (value) => {{
      clearTimeout(timer);
      window.removeEventListener("message", listen);
      resolve(value);
    }};
    const listen = (e) => {{
      if (e.source !== window.parent) return;
      if (!e.data || e.data.type !== "restoration") return;
      if (!e.data.text) return done(null);
      const tables = JSON.parse(e.data.text);
      // Where the world map is. Hosted it is a blob the host made out of the
      // decode; there is no /data/ to link to.
      if (e.data.worldMap) tables.world_map = e.data.worldMap;
      done(tables);
    }};
    window.addEventListener("message", listen);
    const timer = setTimeout(() => done(null), 2000);
    window.parent.postMessage({{ type: "restoration?" }}, "*");
  }});

  if (!window.RESTORATION) window.RESTORATION = await fromHost();
  if (!window.RESTORATION) {{
    const res = await fetch({url});
    if (!res.ok) {{
      document.querySelector("main").textContent =
        "No decoded data yet. The panel is filled in from your own copy of "
        + "the game; nothing is shipped with it.";
      return;
    }}
    window.RESTORATION = await res.json();
  }}
{js}
}})();
</script>
"""


def build_shell(out: Path | None = None, url: str = DATA_URL) -> Path:
    """The panel with no game content in it: the file that may be shipped."""
    html = SHELL.format(
        css=(WEB / "panel.css").read_text().strip(),
        js=(WEB / "panel.js").read_text().strip(),
        guides=json.dumps(guides(), separators=(",", ":")),
        url=json.dumps(url),
    )
    out = out or (WEB / "panel.html")
    out.write_text(html)
    return out


def build(game_dir: str | Path = "game", out: Path | None = None) -> Path:
    import extract

    payload = extract.build(game_dir, ROOT / "data")
    # The world map is half a megabyte, so the tables the shell fetches do not
    # carry it: the cabinet serves it as a file. The self-contained build has
    # no server behind it, so that one does.
    world = ROOT / "data" / "world.png"
    if world.exists():
        payload = dict(payload, world_map="data:image/png;base64,"
                       + base64.b64encode(world.read_bytes()).decode())
    html = TEMPLATE.format(
        css=(WEB / "panel.css").read_text().strip(),
        js=(WEB / "panel.js").read_text().strip(),
        data=json.dumps(payload, separators=(",", ":")),
        guides=json.dumps(guides(), separators=(",", ":")),
    )
    out = out or (WEB / "restoration.html")
    out.write_text(html)
    return out


if __name__ == "__main__":
    import sys

    argv = sys.argv[1:]
    if "--shell" in argv:
        p = build_shell()
        print(f"wrote {p} ({p.stat().st_size:,} bytes, no game content)")
    else:
        p = build(argv[0] if argv else "game")
        print(f"wrote {p} ({p.stat().st_size:,} bytes)")
