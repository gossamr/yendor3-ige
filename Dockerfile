# syntax=docker/dockerfile:1

# The runtime for the cabinet: bun, js-dos, and the server. No game data.
#
# Nothing derived from the game is copied in.
#
# What is left in the image is the emulator, the decoder, the cabinet's own
# code, and the server. The game's files are mounted at run time and the
# patched copy is built inside the container, so nothing here can be pushed to
# a registry with the game inside it.
#
# Multi-arch: linux/amd64 and linux/arm64, which is what bun publishes. There
# are no 32-bit bun builds, so armv7 and i386 cannot run this.
#
#   docker buildx build --platform linux/amd64,linux/arm64 -t yendor3-cabinet .

FROM oven/bun:1.4.0-slim AS deps

# js-dos, resolved from the lockfile alone so this layer is rebuilt only when
# the lockfile changes. bun or yarn, never npm: npm produces a js-dos tree the
# cabinet cannot boot.
WORKDIR /app/cabinet
COPY cabinet/package.json cabinet/bun.lock ./
RUN bun install --frozen-lockfile

# The hooked emulator, written beside the stock one so `?trainer` has something
# to load. It is js-dos's own shim with a hook injected where `Module` is in
# scope, which is how the trainer reads and writes the guest's memory.
#
# Built here rather than at run time because js-dos will not load an emulator
# whose filename does not start with "w" after the last slash, so it has to
# be a real file, and a server cannot conjure one for a page that has already
# asked. It costs 9 MB: js-dos derives the wasm's URL from the shim's name, so
# the renamed shim needs a renamed wasm beside it.
WORKDIR /app
COPY cabinet/boot.js cabinet/dosbox.conf.js cabinet/trainer.js cabinet/
COPY tools/build_trainer.js tools/
RUN bun tools/build_trainer.js


# What the browser runs: the closure of pack_maps, extract, world_map and
# patch, seventeen of the forty-seven modules in tools/. Pruned in a stage of
# its own rather than in the final image, so the instruments that are left out
# are absent from it rather than merely deleted in a later layer, since an image's
# history is as public as its contents.
FROM oven/bun:1.4.0-slim AS decoder
WORKDIR /app
COPY cabinet/boot.js cabinet/dosbox.conf.js cabinet/
COPY docker/prune-decoders.js docker/
COPY tools/ tools/
RUN bun docker/prune-decoders.js


FROM oven/bun:1.4.0-slim

# python3 applies the byte patches. Standard library only: capstone reads the
# executable, nothing at run time does, so there is no pip install here.
RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY cabinet/ cabinet/
COPY web/panel.css web/panel.js web/
# build_panel.py builds the shell below and is not in the closure, so it is
# named. patch.py and mz.py are in the closure, since the entrypoint patches a
# mounted copy and the browser patches the player's own, and they arrive with it
# below; naming them here too costs nothing and keeps this line readable as
# "what the server itself needs".
COPY tools/patch.py tools/mz.py tools/build_panel.py tools/
COPY --from=decoder /app/tools/ tools/
COPY docker/entrypoint.sh /usr/local/bin/entrypoint
COPY --from=deps /app/cabinet/node_modules cabinet/node_modules

# The panel shell: our own CSS and JS, no game content, so it is built into
# the image rather than mounted. build_panel imports the extractor lazily, so
# --shell works here where no copy of the game exists.
RUN python3 tools/build_panel.py --shell

# tmp/ is where the patched copy is written. The server only reads.
RUN mkdir -p tmp \
 && chmod +x /usr/local/bin/entrypoint \
 && chown -R bun:bun /app
USER bun

# The mounted game, and where the patched copy goes. cabinet/boot.js looks for
# the second of these by default.
ENV YENDOR_GAME_SRC=/app/game \
    YENDOR_GAME_DIR=/app/tmp/game-patched \
    PORT=8080

EXPOSE 8080

# The emulator runs in the browser, not here, so serving the shell is the whole
# of what "healthy" means.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD bun -e "const r = await fetch('http://127.0.0.1:'+(process.env.PORT??8080)+'/'); process.exit(r.ok?0:1)"

ENTRYPOINT ["entrypoint"]
