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

.PHONY: all data maps pages panel panel-shell test-py test-js test-panel \
        test-cabinet test-away test-persist test-decode test-hosted-trainer \
        test hosted hosted-dev cabinet-deps serve trainer test-trainer \
        serve-byo serve-stock session clean patched patched-debug characters \
        serve-headless

all: data panel

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

## Crop the captured clue-book map pages into web/maps/
maps:
	PYTHONPATH=tools $(PY) tools/build_maps.py

## The static site: the whole thing, with no game and no server. Needs no copy
## of the game to build, which is what lets it run in CI.
pages: panel-shell
	$(BUN) tools/build_pages.js

## Build the Restoration page, both ways.
##
## web/restoration.html is self-contained, with CSS, JS and every decoded table in
## one file, so it opens off disk with no server. It holds the game's content
## and therefore cannot be distributed.
##
## web/panel.html is the same panel with the tables fetched at run time. It
## holds nothing but our own code, so it is the file that ships: the cabinet loads
## it and the decode of the player's own copy fills it in.
panel: panel-shell
	PYTHONPATH=tools $(PY) tools/build_panel.py

## Just the shell. Separate because it needs no game: the Pages build runs
## where there is no copy of it.
panel-shell:
	PYTHONPATH=tools $(PY) tools/build_panel.py --shell

## Everything that can run without a browser
test-py:
	$(PY) -m pytest tests/ -q

test-js:
	cd cabinet && $(BUN) test

## Render the panel in headless Chromium and assert each section populates
test-panel: panel
	$(BUN) tools/panel_check.js

## Boot the game in a browser and assert it paints and exposes its filesystem.
## Starts and stops its own server.
test-cabinet: patched panel
	@YENDOR_ARGS="$(TEST_ARGS)" $(BUN) cabinet/serve.js --port=$(PORT) & echo $$! > tmp/serve.pid; \
	sleep 2; \
	$(BUN) tools/cabinet_check.js --url=http://localhost:$(PORT)/; \
	status=$$?; kill `cat tmp/serve.pid` 2>/dev/null; rm -f tmp/serve.pid; \
	exit $$status

## Stop the emulator while the player is away. Start it again when they come
## back. Runs in each browser. Away is two conditions: a hidden tab, and a tab
## on screen in an application that is no longer active. Safari reports only
## the second. Watching visibility alone left the game running in the
## background, and minutes behind the input on the way back.
##
## Backgrounding is driven through stubs. No headless engine models the real
## thing: Playwright's Firefox calls a page visible and focused with another
## tab in front of it.
test-away: patched panel
	@YENDOR_ARGS="$(TEST_ARGS)" $(BUN) cabinet/serve.js --port=$(AWAY_PORT) & echo $$! > tmp/away.pid; \
	sleep 2; \
	status=0; \
	for browser in $(BROWSERS); do \
	  $(BUN) tools/away_check.js --url=http://localhost:$(AWAY_PORT)/ \
	    --browser=$$browser || status=1; \
	done; \
	kill `cat tmp/away.pid` 2>/dev/null; rm -f tmp/away.pid; \
	exit $$status

## Prove the browser's storage is on disk: write, quit the browser, start a new
## one against the same profile, read back. Also round-trips an export.
test-persist: patched
	@YENDOR_ARGS="$(TEST_ARGS)" $(BUN) cabinet/serve.js --port=$(PERSIST_PORT) & echo $$! > tmp/persist.pid; \
	sleep 2; \
	$(BUN) tools/persist_check.js --url=http://localhost:$(PERSIST_PORT)/; \
	status=$$?; kill `cat tmp/persist.pid` 2>/dev/null; rm -f tmp/persist.pid; \
	exit $$status

## Drive the bring-your-own path: zip the game, drop it in a real browser,
## decode it there with pyodide, and assert the panel fills in from the result.
## Also asserts nothing is uploaded and that a second visit is served from
## storage. Starts and stops its own server.
##
## A port of its own for the same reason test-persist has one.
DECODE_PORT ?= 8082
test-decode: patched panel-shell
	@YENDOR_ARGS="$(TEST_ARGS)" $(BUN) cabinet/serve.js --port=$(DECODE_PORT) & echo $$! > tmp/decode.pid; \
	sleep 2; \
	status=0; \
	for browser in $(BROWSERS); do \
	  $(BUN) tools/decode_check.js --url=http://localhost:$(DECODE_PORT)/ \
	    --browser=$$browser || status=1; \
	done; \
	kill `cat tmp/decode.pid` 2>/dev/null; rm -f tmp/decode.pid; \
	exit $$status

## The same path with the trainer on: boot the dropped copy, walk to a party
## and read it out of the running game's memory. Separate from test-decode
## because it boots the game, which the rest of that check does not need --
## and because the hooked emulator has to have been published by whatever is
## serving, which is the part nothing else covers.
test-hosted-trainer: patched panel-shell trainer
	@YENDOR_ARGS="$(TEST_ARGS)" $(BUN) cabinet/serve.js --port=$(DECODE_PORT) & echo $$! > tmp/ht.pid; \
	sleep 2; \
	$(BUN) tools/decode_check.js --url=http://localhost:$(DECODE_PORT)/ --trainer; \
	status=$$?; kill `cat tmp/ht.pid` 2>/dev/null; rm -f tmp/ht.pid; \
	exit $$status

test: test-py test-js test-panel test-persist test-cabinet test-away \
      test-decode test-hosted-trainer

## The hosted cabinet in Docker: no game on the server, each player brings
## their own copy and it is decoded and patched in their browser.
##
## --build every time, because `docker compose up` does not rebuild on a source
## change: it builds only when the image is absent, and there is no option to
## change that. Leaving it off is how a container comes to serve an old build.
hosted:
	docker compose -f compose.hosted.yml up --build

## The same, with the browser's files mounted from the tree, so an edit is live
## on the next page load rather than on the next rebuild. panel.css and
## panel.js are inlined into the shell, so this builds it first.
##
## compose.dev.yml mounts the host's cabinet/ over the image's, node_modules
## included, so both have to be here before the container starts: the emulator
## js-dos ships, and the hooked copy of it that ?trainer loads.
hosted-dev: panel-shell cabinet-deps trainer
	docker compose -f compose.hosted.yml -f compose.dev.yml up --build

## js-dos and pyodide, in cabinet/. Only when they are not there already: this
## is a prerequisite of targets that need them, not a step to run every time.
cabinet-deps:
	@test -d cabinet/node_modules/js-dos -a -d cabinet/node_modules/pyodide \
	  || (cd cabinet && $(BUN) install --frozen-lockfile)

## Serve the cabinet for interactive use, against the patched build
serve: patched
	$(BUN) cabinet/serve.js --port=$(PORT)

## Build the emulator the trainer needs: a second copy of js-dos's shim with a
## hook that reads and writes the guest's memory, written beside the stock one.
## Nothing serves it unless the page is opened with ?trainer, and the hosted
## build does not ship it: it is for playing with your own copy, locally.
##
##   make trainer && make serve      then http://localhost:8080/?trainer
trainer:
	$(BUN) tools/build_trainer.js

## Boot the cabinet with the trainer on, reach a party, and read it back out of
## the running game's memory. Starts and stops its own server.
test-trainer: trainer patched panel
	@YENDOR_ARGS="$(TEST_ARGS)" $(BUN) cabinet/serve.js --port=$(PORT) & echo $$! > tmp/serve.pid; \
	sleep 2; \
	$(BUN) tools/trainer_check.js --url=http://localhost:$(PORT)/; \
	status=$$?; kill `cat tmp/serve.pid` 2>/dev/null; rm -f tmp/serve.pid; \
	exit $$status

## Serve the cabinet with no game on it, the way a static host does. The page
## finds an empty manifest and offers the drop zone. The player's own copy is
## unpacked, patched and decoded in the browser.
##
## Not the same as `make serve` and ?byo. That reaches the same code on a
## server that still holds the game, where a route reading the server's copy
## passes unnoticed. GitHub Pages and the hosted container have nothing to
## read, and neither does this.
serve-byo: panel-shell
	@mkdir -p tmp/no-game
	YENDOR_GAME_DIR=$(PWD)/tmp/no-game $(BUN) cabinet/serve.js --port=$(PORT)

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

## Same as serve, but silent as well: for automated runs, not for playing
serve-headless: patched panel
	YENDOR_ARGS="$(TEST_ARGS)" $(BUN) cabinet/serve.js --port=$(PORT)
