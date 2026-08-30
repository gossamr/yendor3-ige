"""What the browser is given to decode with.

Hosted there is no game on the server and no `data/` either. The panel is
filled in by running the project's own Python in the player's browser, under
pyodide, against the copy they brought, so the modules `make data` reaches
have to be published, and the ones it does not must not be.

Hosted there is no executable on the server to patch either, so `tools/patch.py`
runs in the browser too, over the copy the player brought.

`cabinet/boot.js` decides what is published by walking the imports from those
entry points. These tests hold that walk to the closure Python itself produces,
and hold the published set to what the browser actually runs.
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"

# Where `make data` starts.
DECODE_ENTRY = ["pack_maps", "extract", "world_map"]
# And what else the browser runs: hosted there is no executable on the server
# to patch, so the player's own copy is patched in their browser instead.
PATCH_ENTRY = ["patch"]


def bun() -> str:
    """The bun the Makefile would use, or skip.

    The vendored copy is whichever platform last ran an install, so it is run
    rather than merely looked for: a Mach-O binary in a Linux container
    fails as a shell syntax error, which is a confusing way to skip a test.
    """
    for path in (ROOT / "node_modules/.bin/bun",
                 pathlib.Path.home() / ".bun/bin/bun"):
        try:
            subprocess.run([str(path), "--version"], capture_output=True, check=True)
            return str(path)
        except (OSError, subprocess.CalledProcessError):
            continue
    pytest.skip("no runnable bun")


def published() -> list[str]:
    """What cabinet/boot.js says the browser gets."""
    out = subprocess.run(
        [bun(), "-e",
         'import { decoderFiles } from "./cabinet/boot.js";'
         " console.log(JSON.stringify(await decoderFiles()));"],
        cwd=ROOT, capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def imported() -> set[str]:
    """What Python actually loads out of tools/ when the pipeline runs.

    In a subprocess because importing `extract` reads REGISTER.EXE at module
    scope, and because `sys.modules` is not something to leave a test in.
    """
    if not (ROOT / "game" / "REGISTER.EXE").exists():
        pytest.skip("no game/ to import the decoders against")
    code = (
        "import sys, json, pathlib; sys.argv=['x'];"
        f"sys.path.insert(0, {str(TOOLS)!r});"
        "import pack_maps, extract, world_map;"
        f"tools=pathlib.Path({str(TOOLS)!r}).resolve();"
        "print(json.dumps(sorted("
        "  pathlib.Path(m.__file__).name for m in list(sys.modules.values())"
        "  if getattr(m, '__file__', None)"
        "  and pathlib.Path(m.__file__).resolve().parent == tools)))"
    )
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT,
                         capture_output=True, text=True, check=True)
    return set(json.loads(out.stdout.splitlines()[-1]))


def test_the_published_decoder_is_exactly_what_the_browser_runs():
    """Neither short nor generous.

    Short and the browser stops at a ModuleNotFoundError inside a worker, which
    is a long way from the import that caused it. Generous and the deployment
    carries instruments (the disassembler, the OCR, the solvers) that read
    screenshots and memory dumps and have no business on a public host.
    """
    want = imported() | {f"{name}.py" for name in PATCH_ENTRY} | {"mz.py"}
    assert set(published()) == want


def test_the_patcher_is_published_and_needs_only_mz():
    """The browser applies the same three patches the Makefile does, so
    patch.py is served with the decoders. It reads the MZ header through mz.py,
    which the decode already needs, so it costs one file."""
    names = set(published())
    assert {"patch.py", "mz.py"} <= names
    src = (TOOLS / "patch.py").read_text()
    local = {p.stem for p in TOOLS.glob("*.py")}
    reached = {w for w in local if f"from {w} import" in src or f"import {w}" in src}
    assert reached == {"mz"}, reached


def test_the_decoder_is_a_minority_of_tools():
    """A guard on the walk itself: a regex that matched everything would pass
    the test above by publishing the lot."""
    every = {p.name for p in TOOLS.glob("*.py")}
    assert set(published()) < every
    assert len(published()) < len(every) / 2


def test_the_decode_entry_points_are_what_make_data_runs():
    """The walk is seeded from the Makefile's own three steps. If `make data`
    grows a fourth, the browser has to run it too."""
    recipe = (ROOT / "Makefile").read_text().split("\ndata:")[1].split("\n\n")[0]
    for name in DECODE_ENTRY:
        assert f"tools/{name}.py" in recipe, f"{name} is not in `make data`"
    ran = [ln.split("tools/")[1].split(".py")[0]
           for ln in recipe.splitlines() if "tools/" in ln]
    assert ran == DECODE_ENTRY, f"`make data` runs {ran}"


def test_the_browser_applies_the_patches_the_makefile_does():
    """Hosted, the patches are applied in the page instead of by the entrypoint,
    and it must be the same three: a cabinet that skips the intro locally and
    sits through it hosted is two different games."""
    recipe = (ROOT / "Makefile").read_text().split("\npatched:")[1].split("\n\n")[0]
    # The words between the script and its --out, which are the patch names.
    # The recipe is wrapped, so the line continuation is a word too.
    words = [w for w in recipe.split() if w != "\\"]
    wanted = words[words.index("tools/patch.py") + 1:words.index("--out")]
    worker = (ROOT / "cabinet" / "decode.worker.js").read_text()
    applied = json.loads(worker.split("const PATCHES = ")[1].split(";")[0])
    assert applied == wanted, f"Makefile patches {wanted}, the browser {applied}"


def test_no_published_module_needs_a_third_party_package():
    """Pyodide has the standard library and nothing else here: no wheel is
    fetched and no package is installed, which is only true while the decoders
    import nothing but stdlib. capstone is the one to watch, since it reads the
    executable, and `tools/disasm.py` is deliberately outside the closure."""
    third_party = {"capstone", "keystone", "pytest", "numpy", "PIL"}
    for name in published():
        src = (TOOLS / name).read_text()
        for package in third_party:
            assert f"import {package}" not in src, f"{name} imports {package}"
