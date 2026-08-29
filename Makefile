# Yendorian Tales III - data extraction, Restoration panel, js-dos cabinet.
#
# Python work runs in .venv (uv), JavaScript in bun.

# bun, wherever it is: the copy `yarn install` vendors into node_modules, then
# one on PATH, then the directory bun's own installer uses.
#
# Each candidate is *run*, not merely looked for. node_modules is shared with
# the host when this repo is mounted into a container, so the vendored binary
# is whichever platform last ran `yarn install`. A Mach-O bun sitting in a
# Linux container fails with a shell syntax error from sh trying to parse it,
# which is a puzzling way to learn that a file exists. Asking it for its
# version costs nothing and picks the one that works.
#
# abspath because two targets cd into cabinet/ before running it.
BUN_CANDIDATES := node_modules/.bin/bun $(shell command -v bun 2>/dev/null) $(HOME)/.bun/bin/bun
BUN  ?= $(abspath $(firstword $(foreach b,$(BUN_CANDIDATES), \
          $(shell test -x $(b) && $(b) --version >/dev/null 2>&1 && echo $(b)))))
PY   := .venv/bin/python

ifeq ($(BUN),)
$(error no runnable bun found. `yarn install` vendors one; a vendored copy \
built for another platform is skipped. Or set BUN=/path/to/bun)
endif
PORT ?= 8080
# A port of its own, so the server this target kills cannot still be holding
# the one the next target is about to bind.
PERSIST_PORT ?= 8081
AWAY_PORT ?= 8083

## Browsers the checks run a real page in. Each engine answers differently for
## storage, for iframes, and for what a background page may do. All three have
## disagreed. Narrow the list to shorten a run: `BROWSERS=chromium make test`.
BROWSERS ?= chromium firefox webkit

# The game's own no-music / no-sound switches. Audio is pointless when nothing
# is listening and costs host CPU; unlike sbtype=none in the DOSBox config,
# these are a supported code path and do not hang the game on its splash.
TEST_ARGS ?= /NOM /NOS

.PHONY: data test-py test-js cabinet-deps serve serve-stock session clean \
        patched patched-debug characters

## Decode WORLD.DAT into data/*.json.
##
## Every file the panel is built from is produced here, by a committed script,
## from game/ plus the captures in tmp/. Each step is idempotent: re-running
## this rewrites the same bytes. Nothing is hand-made, because a hand-made file
## is one nobody can rebuild.
##
## The order is a real dependency chain, not a preference:
##   pack_maps    draws every map page from the files    -> map_pages.json
##   extract      decodes WORLD.DAT                      -> data/*.json
data:
	PYTHONPATH=tools $(PY) tools/pack_maps.py
	PYTHONPATH=tools $(PY) tools/extract.py
	PYTHONPATH=tools $(PY) tools/world_map.py

## Everything that can run without a browser
test-py:
	$(PY) -m pytest tests/ -q

test-js:
	cd cabinet && $(BUN) test

## js-dos and pyodide, in cabinet/. Only when they are not there already: this
## is a prerequisite of targets that need them, not a step to run every time.
cabinet-deps:
	@test -d cabinet/node_modules/js-dos -a -d cabinet/node_modules/pyodide \
	  || (cd cabinet && $(BUN) install --frozen-lockfile)

## Serve the cabinet for interactive use, against the patched build
serve: patched
	$(BUN) cabinet/serve.js --port=$(PORT)

## Serve the game exactly as it shipped, intro and attract loop and all
serve-stock:
	YENDOR_GAME_DIR=$(PWD)/game $(BUN) cabinet/serve.js --port=$(PORT)

## Long-lived headless emulator driven by tmp/session.cmd
session:
	cd cabinet && $(BUN) session.js

clean:
	rm -rf tmp/shots tmp/panel tmp/cabinet tmp/*.png tmp/session.* data/*.json web/restoration.html web/panel.html

## Build the patched copy of the game in tmp/game-patched. Everything that
## boots the game uses this build; the original is not touched, since
## tools/patch.py copies the directory and rewrites a few bytes of the copy's
## executable, so the intro is skipped, so the main menu stops falling into
## its attract loop while a driver is thinking, and so changing a character's
## class no longer throws away the roll.
##
## enable-p-switch is not among them: it revives the developers' /P switch,
## which turns on a debug mode rather than an intro skip. See patched-debug.
##
## `serve` depends on this, so it runs on every serve. That is cheap: it hashes
## the 198 kB executable, finds the md5 those patches produce and returns
## without rewriting it or re-copying the 17 MB of artwork. It needs no
## third-party library either; see the note at the top of tools/patch.py.
patched:
	$(PY) tools/patch.py force-skip-intro no-attract keep-roll-on-class-change \
	  --out tmp/game-patched

## tmp/game-debug: the developers' debug mode, which is what /P turns on once
## enable-p-switch stops the dispatcher clearing the flag. Walls stop clipping
## and the level check on training is bypassed. Not for playing, for driving.
## A capture that needs a distant cell can walk there through the walls, and
## one that needs a training screen does not need a party leveled up first.
##
## This build must be booted with /P, and force-skip-intro is left out because
## /P already skips the intro: the patch only makes the branch at 0xeecf
## unconditional, and /P is what makes the test in front of it pass.
##
##   make patched-debug
##   YENDOR_GAME_DIR=$(PWD)/tmp/game-debug YENDOR_ARGS=/P bun tools/capture_x.js
patched-debug:
	$(PY) tools/patch.py enable-p-switch no-attract keep-roll-on-class-change \
	  --out tmp/game-debug

## Carry created characters into the roster the game restores from, so they
## survive a launch and a NEW GAME. FROM is a CURGAME or SAVGAMEn file, from
## the game directory of a normal DOSBox session, or read out of the cabinet with
## `read CURGAME` in a session.
##
##   make characters FROM=game/CURGAME
FROM ?= game/CURGAME
characters: patched
	$(PY) tools/keep_characters.py --from $(FROM) --game tmp/game-patched \
	  --out tmp/game-chars
