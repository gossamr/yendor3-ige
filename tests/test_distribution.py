"""What may be distributed, and what may not.

The project is meant to be given to other people. It cannot carry the game
with it: the shareware license forbids modifying or reverse engineering the
Software and forbids altered files in every one of its distribution clauses,
and no reading of it permits shipping the game's *content* decoded out of its
data files. The EU software directive's interoperability provisions (Art. 5(3),
Art. 6, and Art. 8 which voids contract terms against them) protect a lawful
user studying their own copy. They do not make that user's copy ours to hand
on.

So the shape of the project is: **ship the tools, never the content.** Each
user brings their own copy of the game, and the decode happens on their
machine, from their files. Nothing here is a substitute for reading the
license; these tests keep the tree honest about which side of the line each
file is on.

Adding a file to SHIPPABLE is a decision to distribute it. Adding one to
GAME_DERIVED is a decision that it may never be.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# Directories whose contents are the game's, decoded or photographed. None of
# this may be distributed, and none of it may be committed except where it is
# already tracked as a stopgap with its provenance recorded.
GAME_DERIVED = [
    "game",             # the game itself
    "data",             # WORLD.DAT decoded into JSON
    "observed",         # content read off the game's screens
    "web/restoration.html",   # the panel with every decoded table inlined
]

# What the distributed artifact is allowed to contain.
SHIPPABLE = [
    "cabinet",          # the emulator host
    "web/panel.css",    # how the panel looks
    "web/panel.js",     # how the panel draws
    "tools",            # the decoders themselves
    "docker",
    "tools/build_pages.js",
    ".github",
    "Dockerfile", "compose.yml", "compose.hosted.yml",
    "Makefile", "package.json",
    "web/panel.html",   # the shell that ships
    # Our own writing about the game, not the game's writing. Both are inlined
    # into the panel by tools/build_panel.py, so shipping the shell ships them;
    # they are listed here so that the content check reads them too.
    "MANUAL.md", "STRATEGY.md",
]

def content_markers() -> list[str]:
    """Distinctive strings taken from the decoded output at test time.

    Prose, not names. A character or a place is a name, and names are not
    protected on their own: a decoder is free to say PALTIVAR while
    explaining how the level field is encoded. What may not be copied out is
    the game's *writing*: its walkthrough, its spell and item descriptions.
    Those are the sentences this looks for.

    Taken from data/ rather than written down here, so the test embeds none of
    the prose it is guarding, and so it keeps working when the decode changes.
    """
    data = ROOT / "data" / "restoration.json"
    if not data.exists():
        return []
    d = json.loads(data.read_text())
    out = []
    for page in d.get("walkthrough", [])[:3]:
        for line in (page if isinstance(page, list) else page.get("rows", [])):
            line = line.strip()
            if len(line) > 40:
                out.append(line)
                break
    for spell in d.get("spells", [])[:40]:
        text = spell.get("description") or ""
        if isinstance(text, list):
            text = " ".join(text)
        if len(text) > 40:
            out.append(text[:60].strip())
    return out[:8]


def test_the_game_is_not_in_the_shippable_tree():
    for name in ("REGISTER.EXE", "WORLD.DAT", "PICTURES.VGA"):
        for entry in SHIPPABLE:
            hits = list((ROOT / entry).rglob(name)) if (ROOT / entry).is_dir() else []
            assert not hits, f"{name} found under {entry}: {hits}"


def _code_only(path: Path) -> str:
    """The file with its comments and docstrings removed.

    A decoder has to talk about what it decodes, and naming one creature to
    show how a field is encoded ("PALTIVAR's 1,000,000 is stored as
    01 00 00 00") is documentation, not distribution. What may not appear is
    the content itself, in a position where the program uses it as data.
    """
    text = path.read_text(errors="ignore")
    if path.suffix == ".py":
        import io
        import tokenize
        kept, prev = [], None
        try:
            for tok in tokenize.generate_tokens(io.StringIO(text).readline):
                if tok.type == tokenize.COMMENT:
                    continue
                # A string on its own, after a newline or a block open, is a
                # docstring rather than a value.
                if tok.type == tokenize.STRING and prev in (
                        tokenize.INDENT, tokenize.NEWLINE, tokenize.NL, None):
                    prev = tok.type
                    continue
                kept.append(tok.string)
                if tok.type not in (tokenize.NL, tokenize.NEWLINE):
                    prev = tok.type
        except (tokenize.TokenError, IndentationError):
            return text
        return " ".join(kept)
    if path.suffix in (".js", ".css"):
        import re
        text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
        return re.sub(r"(?m)^\s*//.*$", " ", text)
    return text


def test_no_shippable_file_carries_the_game_s_content():
    """The decoders may name a format. They may not embed what it decodes."""
    markers = content_markers()
    if not markers:
        pytest.skip("no decoded data to take markers from; run `make data`")
    offenders = []
    for entry in SHIPPABLE:
        path = ROOT / entry
        files = sorted(path.rglob("*")) if path.is_dir() else [path]
        for f in files:
            if not f.is_file() or "node_modules" in f.parts:
                continue
            if f.suffix not in (".py", ".js", ".json", ".css", ".html", ".sh", ""):
                continue
            try:
                code = _code_only(f)
            except OSError:
                continue
            for marker in markers:
                if marker in code:
                    offenders.append(f"{f.relative_to(ROOT)}: {marker}")
    assert not offenders, offenders


def test_game_derived_paths_are_kept_out_of_the_docker_image():
    """The image is built and pushed; the game is mounted at run time."""
    ignore = (ROOT / ".dockerignore").read_text()
    patterns = {ln.strip().rstrip("/*").rstrip("/")
                for ln in ignore.splitlines()
                if ln.strip() and not ln.startswith(("#", "!"))}
    for entry in GAME_DERIVED:
        head = entry.split("/")[0]
        assert head in patterns or entry in patterns, \
            f"{entry} is game-derived but .dockerignore does not exclude it"


def test_the_observations_record_what_would_replace_them():
    """Each stopgap names the decode that retires it, so none becomes permanent.

    A tree without the directory has no stopgaps to account for.
    """
    if not (ROOT / "observed").is_dir():
        return
    readme = (ROOT / "observed" / "README.md").read_text()
    for f in sorted((ROOT / "observed").glob("*.json")):
        assert f.name in readme, f"{f.name} is not accounted for in its README"


@pytest.mark.parametrize("name", [p.name for p in sorted((ROOT / "observed").glob("*.json"))])
def test_every_observation_is_still_needed(name):
    """A file nothing reads is a decode that landed and was not cleaned up."""
    stem = name[:-len(".json")]
    readers = [p for p in list((ROOT / "tools").glob("*.py")) + list((ROOT / "tests").glob("*.py"))
               if stem in p.read_text()]
    assert readers, f"{name} is read by nothing; delete it"
