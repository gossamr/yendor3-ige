#!/bin/sh
# Work out which way this container is being run, prepare what that needs, and
# serve.
#
# Two deployments, told apart by whether a game is mounted.
#
#   local   game/ and data/restoration.json are mounted. The executable is
#           patched here and the panel is filled in from the mounted tables.
#
#   hosted  neither is mounted, and nothing about the game is on the server at
#           all. Each player supplies their own copy from the browser, and the
#           decode happens on their machine. That is not a degraded mode to
#           warn about: it is the one the project is built to be given away
#           in, and the only one that carries no game data.
#
# The patch cannot run in hosted mode: there is no executable to patch. Nothing
# is lost that matters: the patches skip the intro, stop the attract loop and
# keep a character's roll, none of which the game needs to run.
set -e

GAME=${YENDOR_GAME_SRC:-/app/game}
OUT=${YENDOR_GAME_DIR:-/app/tmp/game-patched}
DATA=/app/data/restoration.json

fail() { echo "$@" >&2; exit 1; }

cd /app

if [ -f "$GAME/REGISTER.EXE" ]; then
  # Local. A half-mounted game is a mistake worth stopping for, rather than
  # something to discover as a broken emulator later.
  for f in WORLD.DAT PICTURES.VGA SW.BAT; do
    [ -f "$GAME/$f" ] || fail \
      "$GAME has REGISTER.EXE but no $f. Mount the whole game directory."
  done

  [ -f "$DATA" ] || fail \
    "no data/restoration.json. Run \`make all\` on the host to build it."

  echo "local: game from $GAME"
  python3 tools/patch.py force-skip-intro no-attract keep-roll-on-class-change \
    --game "$GAME" --out "$OUT"
else
  echo "hosted: no game mounted; players supply their own copy from the browser"
  [ -f "$DATA" ] || echo "  no data/restoration.json either; the panel fills in from each player's copy"
fi

exec bun cabinet/serve.js --port="${PORT:-8080}"
