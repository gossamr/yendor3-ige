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

.PHONY: test-js cabinet-deps serve-stock session clean

test-js:
	cd cabinet && $(BUN) test

## js-dos and pyodide, in cabinet/. Only when they are not there already: this
## is a prerequisite of targets that need them, not a step to run every time.
cabinet-deps:
	@test -d cabinet/node_modules/js-dos -a -d cabinet/node_modules/pyodide \
	  || (cd cabinet && $(BUN) install --frozen-lockfile)

## Serve the game exactly as it shipped, intro and attract loop and all
serve-stock:
	YENDOR_GAME_DIR=$(PWD)/game $(BUN) cabinet/serve.js --port=$(PORT)

## Long-lived headless emulator driven by tmp/session.cmd
session:
	cd cabinet && $(BUN) session.js

clean:
	rm -rf tmp/shots tmp/panel tmp/cabinet tmp/*.png tmp/session.* data/*.json web/restoration.html web/panel.html
