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

/**
 * Start playback. Returns { context, resume }, since browsers refuse to start an
 * AudioContext without a user gesture, so resume() is called from the click
 * that boots the game.
 */
export function startAudio(ci) {
  const rate = ci.soundFrequency();
  if (!rate) {
    console.warn("emulator reports no sample rate; running silent");
    return null;
  }
  const Ctx = window.AudioContext || window.webkitAudioContext;
  if (!Ctx) return null;

  const context = new Ctx({ sampleRate: rate, latencyHint: "interactive" });
  const ring = new Ring(CAPACITY);
  ci.events().onSoundPush((samples) => {
    ring.push(samples);
    // Trim what a background tab left behind. Carried, it is delay for the
    // rest of the session.
    if (ring.length > BACKLOG) ring.drop(BLOCK);
  });

  const gain = context.createGain();
  gain.connect(context.destination);

  const node = context.createScriptProcessor(BLOCK, 0, 1);
  let started = false;
  node.onaudioprocess = (e) => {
    const out = e.outputBuffer;
    // Wait for a full block before starting, or the first seconds stutter.
    if (!started) started = ring.length >= BLOCK;
    if (!started) return;
    for (let c = 0; c < out.numberOfChannels; c++) {
      ring.writeTo(out.getChannelData(c), out.length);
    }
  };
  node.connect(gain);

  return {
    context,
    resume: () => context.resume(),
    /** Drop what is buffered and wait for a full block again. */
    reset() {
      ring.drop(0);
      started = false;
    },
    /** 0..1, shaped so the slider feels linear to the ear. */
    setVolume(v) {
      const clamped = Math.max(0, Math.min(1, v));
      gain.gain.setTargetAtTime(clamped * clamped, context.currentTime, 0.01);
    },
  };
}
