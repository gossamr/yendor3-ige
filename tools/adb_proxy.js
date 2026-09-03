// A TCP door to an Android device's Chrome DevTools socket, through the host's
// adb server.
//
//   bun tools/adb_proxy.js &          # then connect Playwright to :9222
//
// `adb forward` binds on the host, where a container cannot reach it, but the
// adb protocol lets a client open a device stream itself, which is what this
// does. Chrome on the device must have USB debugging on, and the page under
// test must be open in a foreground tab: Chrome freezes background ones.
const ADB = {
  hostname: process.env.ADB_HOST ?? "host.docker.internal",
  port: Number(process.env.ADB_PORT ?? 5037),
};
// Which device to open. `transport-any` is adb's own answer when exactly one
// is attached, so an emulator and a phone both work with nothing set. With two
// attached it refuses and asks for a choice: ADB_SERIAL names one, as `adb -s`
// would, and `adb devices` lists them.
const SERIAL = process.env.ADB_SERIAL ?? "";
const TRANSPORT = SERIAL ? `host:transport:${SERIAL}` : "host:transport-any";
const PORT = Number(process.env.ADB_PROXY_PORT ?? 9222);

const enc = (s) => s.length.toString(16).padStart(4, "0") + s;
const log = (...a) => console.error(...a);

Bun.listen({
  hostname: "127.0.0.1", port: PORT,
  socket: {
    open(client) {
      const state = { stage: 0, queue: [], up: null };
      client.data = state;
      Bun.connect({
        ...ADB,
        socket: {
          open(s) { state.up = s; s.write(enc(TRANSPORT)); },
          data(s, chunk) {
            if (state.stage === 2) { client.write(chunk); return; }
            const t = new TextDecoder().decode(chunk);
            if (!t.startsWith("OKAY")) {
              // The refusal carries its reason after a four-digit length, and
              // "more than one device" is the one worth acting on.
              log(SERIAL
                ? `adb refused ${SERIAL}: ${t.slice(8)}`
                : `adb refused: ${t.slice(8)} -- set ADB_SERIAL to one of "adb devices"`);
              client.end(); s.end(); return;
            }
            // Two OKAYs: one for the transport, one for the socket on it.
            if (state.stage === 0) {
              state.stage = 1;
              s.write(enc("localabstract:chrome_devtools_remote"));
              return;
            }
            state.stage = 2;
            for (const q of state.queue) s.write(q);
            state.queue = [];
            if (chunk.length > 4) client.write(chunk.slice(4));
          },
          close() { client.end(); },
          error(s, e) { log("adb error", e.message); client.end(); },
        },
      }).catch((e) => { log("connect failed", e.message); client.end(); });
    },
    data(client, chunk) {
      const state = client.data;
      // Anything the client says before the stream is up waits for it.
      if (state.stage === 2) state.up.write(chunk);
      else state.queue.push(chunk);
    },
    close(client) { client.data.up?.end(); },
    error(client) { client.data.up?.end(); },
  },
});
log(`proxy on 127.0.0.1:${PORT} -> ${TRANSPORT}`);
