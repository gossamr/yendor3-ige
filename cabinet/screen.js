// Putting a frame on the screen.
//
// The emulator hands over three bytes to a pixel and a 2D canvas wants four,
// so the obvious painter walks the buffer in JavaScript and writes an
// ImageData. At the 640x400 DOSBox-X reports that is 256,000 iterations for
// every frame, on the thread the page draws on, and the game delivers a frame
// whenever the picture changes.
//
// A texture upload is the same conversion done by the driver. The frame goes
// to the GPU as RGB, one triangle pair samples it, and the loop is gone.
//
// The canvas cannot be handed to the worker instead, which would take the
// frame off this thread altogether: a tap places the guest cursor by finding
// the arrow in the frame (see mouse.js and the tap path in cabinet.js), so
// the pixels have to arrive here whatever draws them. The 2D painter is kept
// for anywhere WebGL will not start.

// uv flips y: the frame's first row is the top one and a texture's is the
// bottom one.
const VERTEX = `
attribute vec2 pos;
varying vec2 uv;
void main() {
  uv = vec2((pos.x + 1.0) * 0.5, (1.0 - pos.y) * 0.5);
  gl_Position = vec4(pos, 0.0, 1.0);
}`;

const FRAGMENT = `
precision mediump float;
varying vec2 uv;
uniform sampler2D frame;
void main() { gl_FragColor = texture2D(frame, uv); }`;

function compile(gl, type, source) {
  const shader = gl.createShader(type);
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    throw new Error(gl.getShaderInfoLog(shader) || "shader");
  }
  return shader;
}

/** The WebGL painter, or null where no context can be had. */
function glRenderer(canvas) {
  const attrs = { alpha: false, antialias: false, depth: false, stencil: false,
                  preserveDrawingBuffer: false, desynchronized: true };
  const gl = canvas.getContext("webgl2", attrs) || canvas.getContext("webgl", attrs);
  if (!gl) return null;

  const program = gl.createProgram();
  try {
    gl.attachShader(program, compile(gl, gl.VERTEX_SHADER, VERTEX));
    gl.attachShader(program, compile(gl, gl.FRAGMENT_SHADER, FRAGMENT));
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      throw new Error(gl.getProgramInfoLog(program) || "link");
    }
  } catch {
    return null;
  }
  gl.useProgram(program);

  const buffer = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
  const pos = gl.getAttribLocation(program, "pos");
  gl.enableVertexAttribArray(pos);
  gl.vertexAttribPointer(pos, 2, gl.FLOAT, false, 0, 0);

  const texture = gl.createTexture();
  gl.bindTexture(gl.TEXTURE_2D, texture);
  // NEAREST and no mipmap: the picture is scaled by the page, and a texture
  // whose size is not a power of two has no other legal filter in WebGL 1.
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  // Rows are three bytes to a pixel and are not padded to four.
  gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1);

  let width = 0, height = 0;
  return {
    kind: "webgl",
    lost: () => gl.isContextLost(),
    draw(rgb, w, h) {
      if (w !== width || h !== height) {
        canvas.width = w;
        canvas.height = h;
        gl.viewport(0, 0, w, h);
        gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGB, w, h, 0, gl.RGB, gl.UNSIGNED_BYTE, null);
        width = w; height = h;
      }
      gl.texSubImage2D(gl.TEXTURE_2D, 0, 0, 0, w, h, gl.RGB, gl.UNSIGNED_BYTE, rgb);
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    },
  };
}

/** The 2D painter: one pass over the frame to add the alpha byte. */
function canvasRenderer(canvas) {
  const ctx = canvas.getContext("2d", { alpha: false });
  let image = null;
  return {
    kind: "2d",
    lost: () => false,
    draw(rgb, w, h) {
      if (!image || image.width !== w || image.height !== h) {
        canvas.width = w;
        canvas.height = h;
        image = ctx.createImageData(w, h);
      }
      const out = image.data;
      for (let i = 0, j = 0; i < rgb.length; i += 3, j += 4) {
        out[j] = rgb[i]; out[j + 1] = rgb[i + 1]; out[j + 2] = rgb[i + 2]; out[j + 3] = 255;
      }
      ctx.putImageData(image, 0, 0);
    },
  };
}

/**
 * A painter for `canvas`, WebGL where it starts and 2D where it does not.
 *
 * A canvas keeps the first kind of context it is given for as long as it
 * exists, so this is called once and the answer is kept. `?webgl=0` asks for
 * the 2D painter, which is how the two are compared on the same machine.
 */
export function makeRenderer(canvas, { webgl = true } = {}) {
  return (webgl && glRenderer(canvas)) || canvasRenderer(canvas);
}
