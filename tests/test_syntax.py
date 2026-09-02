"""Every JavaScript file in the tree parses.

Nothing else here reads the browser's own files. The panel is one 8,000-line
IIFE that tools/build_panel.py inlines into a page, so a duplicated line in it
is a SyntaxError the whole file dies on and the tab bar never draws. The first
thing that notices is the browser. tools/panel_check.js opens the page and
catches it, but that wants a game to decode and a headless Chromium, and the
walk over the published history runs test-py and test-js only.

bun parses the files the way the browser would, resolving no import and
running no line, in a tenth of a second. The tree is the fixture, so a
checkout of a published commit parses the files that commit places.
"""
from __future__ import annotations

import pathlib
import subprocess
import tempfile

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
# Directories holding no source of ours: installed packages, the virtualenv,
# the scratch space the checks write into, and the build's copies of files
# already parsed where they are written.
SKIP = {"node_modules", ".venv", "venv", "tmp", "build", ".git", "game"}


def bun() -> str:
    """The bun the Makefile would use, or skip.

    The vendored copy is whichever platform last ran an install, so it is run
    rather than merely looked for: a Mach-O binary in a Linux container fails
    as a shell syntax error, which is a confusing way to skip a test.
    """
    for path in (ROOT / "node_modules/.bin/bun",
                 pathlib.Path.home() / ".bun/bin/bun"):
        try:
            subprocess.run([str(path), "--version"], capture_output=True, check=True)
            return str(path)
        except (OSError, subprocess.CalledProcessError):
            continue
    pytest.skip("no runnable bun")


def sources() -> list[str]:
    return sorted(str(p.relative_to(ROOT)) for p in ROOT.rglob("*.js")
                  if not SKIP & set(p.relative_to(ROOT).parts))


def test_the_browser_files_parse():
    """One bun for the whole tree: eighty starts cost five seconds and one
    costs a tenth, and the report names the file and the line either way.

    --no-bundle transpiles each entry point on its own and resolves no import,
    so a failure is that file's own syntax rather than a missing dependency.
    The output is written to a temporary directory and thrown away; what is
    being read is the exit status.
    """
    files = sources()
    with tempfile.TemporaryDirectory() as out:
        run = subprocess.run([bun(), "build", "--no-bundle", *files, "--outdir", out],
                             cwd=ROOT, capture_output=True, text=True)
    assert run.returncode == 0, run.stderr


def test_the_tree_has_javascript_to_parse():
    """A glob that matches nothing passes the assertion above it."""
    assert len(sources()) > 5
