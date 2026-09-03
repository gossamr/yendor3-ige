// Sound for the emulator.
//
// The backend hands over decoded samples through onSoundPush; nothing plays
// them unless we do. They arrive faster or slower than the audio device
// consumes them, so they go through a ring buffer and are pulled out by an
// audio node at the device's own pace.
const CAPACITY = 6144;   // ~0.14s at 44.1kHz: enough to ride out jitter
const BLOCK = 2048;
// The ring drains a block per callback and refills between them, so its level
// swings by about a block. A healthy peak is around two. More is a backlog, not
// jitter. A backlog is delay: both sides run at the same rate, so waiting
// samples are never caught up. A hidden page builds one. The emulator keeps
// pushing while the callback is throttled.
const BACKLOG = BLOCK * 2.5;

export class Ring {
  constructor(capacity) {
    this.buf = new Float32Array(capacity);
    this.read = 0;
    this.write = 0;
    this.size = 0;
  }
  get length() { return this.size; }
  push(samples) {
    for (const s of samples) {
      if (this.size === this.buf.length) return;   // drop rather than overwrite unread audio
      this.buf[this.write] = s;
      this.write = (this.write + 1) % this.buf.length;
      this.size++;
    }
  }
  /** Discard the oldest samples, down to `keep`. */
  drop(keep) {
    const n = this.size - keep;
    if (n <= 0) return 0;
    this.read = (this.read + n) % this.buf.length;
    this.size -= n;
    return n;
  }
  writeTo(out, count) {
    for (let i = 0; i < count; i++) {
      if (this.size === 0) { out[i] = 0; continue; }
      out[i] = this.buf[this.read];
      this.read = (this.read + 1) % this.buf.length;
      this.size--;
    }
  }
}

// The player, as source, because a worklet is loaded from a URL and runs in a
// scope of its own. `Ring` is pasted in ahead of it rather than copied out:
// one implementation, and the tests keep covering the one that plays. It is
// bound by name here, since a minified build renames the class.
const PROCESSOR = (ring) => `
const Ring = ${ring};

class Player extends AudioWorkletProcessor {
  constructor(options) {
    super();
    const { capacity, block, backlog } = options.processorOptions;
    this.ring = new Ring(capacity);
    this.block = block;
    this.backlog = backlog;
    this.started = false;
    this.port.onmessage = (e) => {
      if (e.data.reset) {
        this.ring.drop(0);
        this.started = false;
        return;
      }
      this.ring.push(e.data.samples);
      // Trim what a background tab left behind. Carried, it is delay for the
      // rest of the session.
      if (this.ring.length > this.backlog) this.ring.drop(this.block);
    };
  }
  process(inputs, outputs) {
    // Wait for a full block before starting, or the first seconds stutter.
    if (!this.started) this.started = this.ring.length >= this.block;
    if (this.started) {
      for (const channel of outputs[0]) this.ring.writeTo(channel, channel.length);
    }
    return true;
  }
}
registerProcessor("cabinet-audio", Player);
`;

/**
 * The worklet player, or null where the browser has no AudioWorklet or the
 * module will not load. Samples are copied on the way over because the buffer
 * the backend hands us is its own, and the copy is transferred rather than
 * cloned.
 */
async function workletPlayer(context, gain) {
  if (!context.audioWorklet) return null;
  const url = URL.createObjectURL(
    new Blob([PROCESSOR(Ring.toString())], { type: "application/javascript" }));
  try {
    await context.audioWorklet.addModule(url);
  } catch (err) {
    console.warn("audio worklet did not load, playing on the main thread", err);
    return null;
  } finally {
    URL.revokeObjectURL(url);
  }
  const node = new AudioWorkletNode(context, "cabinet-audio", {
    numberOfInputs: 0,
    numberOfOutputs: 1,
    outputChannelCount: [1],
    processorOptions: { capacity: CAPACITY, block: BLOCK, backlog: BACKLOG },
  });
  node.connect(gain);
  return {
    kind: "worklet",
    push(samples) {
      const copy = samples.slice();
      node.port.postMessage({ samples: copy }, [copy.buffer]);
    },
    reset() { node.port.postMessage({ reset: true }); },
  };
}

/**
 * The main-thread player, for browsers with no AudioWorklet. A
 * ScriptProcessorNode is deprecated and does its mixing on the thread the page
 * draws on, which is the reason the worklet above is tried first.
 */
function scriptPlayer(context, gain) {
  const ring = new Ring(CAPACITY);
  const node = context.createScriptProcessor(BLOCK, 0, 1);
  let started = false;
  node.onaudioprocess = (e) => {
    const out = e.outputBuffer;
    if (!started) started = ring.length >= BLOCK;
    if (!started) return;
    for (let c = 0; c < out.numberOfChannels; c++) {
      ring.writeTo(out.getChannelData(c), out.length);
    }
  };
  node.connect(gain);
  return {
    kind: "script",
    push(samples) {
      ring.push(samples);
      if (ring.length > BACKLOG) ring.drop(BLOCK);
    },
    reset() { ring.drop(0); started = false; },
  };
}

/**
 * Start playback. Returns { context, resume }, since browsers refuse to start an
 * AudioContext without a user gesture, so resume() is called from the click
 * that boots the game.
 */
export async function startAudio(ci, { worklet = true } = {}) {
  const rate = ci.soundFrequency();
  if (!rate) {
    console.warn("emulator reports no sample rate; running silent");
    return null;
  }
  const Ctx = window.AudioContext || window.webkitAudioContext;
  if (!Ctx) return null;

  const context = new Ctx({ sampleRate: rate, latencyHint: "interactive" });
  const gain = context.createGain();
  gain.connect(context.destination);

  const player = (worklet && await workletPlayer(context, gain)) || scriptPlayer(context, gain);
  ci.events().onSoundPush((samples) => player.push(samples));

  return {
    context,
    kind: player.kind,
    resume: () => context.resume(),
    /** Drop what is buffered and wait for a full block again. */
    reset: () => player.reset(),
    /** 0..1, shaped so the slider feels linear to the ear. */
    setVolume(v) {
      const clamped = Math.max(0, Math.min(1, v));
      gain.gain.setTargetAtTime(clamped * clamped, context.currentTime, 0.01);
    },
  };
}
