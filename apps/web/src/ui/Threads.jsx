import React, { useEffect, useRef } from 'react';
import { Renderer, Program, Mesh, Triangle } from 'ogl';
import { prefersReducedMotion } from './motion.js';

// Adapted from the react-bits "Threads" background (MIT). Flowing horizontal
// filaments driven by layered value noise — reads as a slow signal trace, the
// SeaCommons motif.
//
// WebGL here is progressive enhancement ONLY. It is skipped entirely when:
//   - the OS asks for reduced motion,
//   - a WebGL context can't be created,
//   - the context is a software rasteriser (SwiftShader / llvmpipe) — a
//     full-screen fragment shader on the CPU pins the main thread,
//   - the device reports very few logical cores.
// In every skip case the element stays empty and the CSS gradient behind it
// (`.hero__bg`) carries the look. It also renders at a capped resolution and
// frame rate, and pauses when scrolled away or the tab is hidden.

const VERT = `
attribute vec2 position;
void main() { gl_Position = vec4(position, 0.0, 1.0); }
`;

const FRAG = `
precision mediump float;
uniform float uTime;
uniform vec3  uColor;
uniform vec2  uResolution;
uniform float uAmplitude;
uniform float uCount;

float hash(vec2 p){ return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float noise(vec2 p){
  vec2 i = floor(p); vec2 f = fract(p);
  vec2 u = f*f*(3.0-2.0*f);
  return mix(mix(hash(i), hash(i+vec2(1.0,0.0)), u.x),
             mix(hash(i+vec2(0.0,1.0)), hash(i+vec2(1.0,1.0)), u.x), u.y);
}

void main(){
  vec2 uv = gl_FragCoord.xy / uResolution.xy;
  float acc = 0.0;
  for (float i = 0.0; i < 10.0; i += 1.0) {
    if (i >= uCount) break;
    float fi = i / uCount;
    float speed = 0.05 + fi * 0.08;
    float base = 0.16 + fi * 0.66;
    float n = noise(vec2(uv.x * 2.4 + i * 12.7, uTime * speed + i));
    float n2 = noise(vec2(uv.x * 6.0 - i * 3.0, uTime * speed * 0.5));
    float y = base + (n - 0.5) * uAmplitude + (n2 - 0.5) * uAmplitude * 0.35;
    float d = abs(uv.y - y);
    acc += (smoothstep(0.006, 0.0, d) * 1.4 + smoothstep(0.11, 0.0, d) * 0.3) * (0.4 + 0.6 * fi);
  }
  vec3 col = mix(uColor, vec3(0.43, 0.9, 0.85), 0.25) * acc;
  gl_FragColor = vec4(col, min(acc, 1.0));
}
`;

function isSoftwareRenderer(gl) {
  try {
    const ext = gl.getExtension('WEBGL_debug_renderer_info');
    const r = ext ? String(gl.getParameter(ext.UNMASKED_RENDERER_WEBGL)) : '';
    return /swiftshader|llvmpipe|software|basic render/i.test(r);
  } catch {
    return false;
  }
}

export default function Threads({ color = [0.78, 1.0, 0.24], amplitude = 0.16, count = 8, className = '' }) {
  const hostRef = useRef(null);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return undefined;
    if (prefersReducedMotion()) return undefined;
    if ((navigator.hardwareConcurrency || 4) < 4) return undefined;

    let renderer;
    try {
      renderer = new Renderer({ alpha: true, antialias: false, dpr: 1, powerPreference: 'low-power' });
    } catch {
      return undefined;
    }
    const gl = renderer.gl;
    if (!gl || isSoftwareRenderer(gl)) {
      try { gl?.getExtension('WEBGL_lose_context')?.loseContext(); } catch { /* noop */ }
      return undefined;
    }

    gl.clearColor(0, 0, 0, 0);
    const canvas = gl.canvas;
    canvas.style.width = '100%';
    canvas.style.height = '100%';
    canvas.style.display = 'block';
    host.appendChild(canvas);

    const program = new Program(gl, {
      vertex: VERT,
      fragment: FRAG,
      uniforms: {
        uTime: { value: 0 },
        uColor: { value: color },
        uResolution: { value: [1, 1] },
        uAmplitude: { value: amplitude },
        uCount: { value: count },
      },
    });
    const mesh = new Mesh(gl, { geometry: new Triangle(gl), program });

    // Render at half CSS resolution — the shader is soft, nobody sees the pixels.
    const RES_SCALE = 0.5;
    const resize = () => {
      const w = Math.max(1, Math.round((host.clientWidth || 1) * RES_SCALE));
      const h = Math.max(1, Math.round((host.clientHeight || 1) * RES_SCALE));
      renderer.setSize(w, h);
      canvas.style.width = '100%';
      canvas.style.height = '100%';
      program.uniforms.uResolution.value = [w, h];
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(host);

    let raf = 0;
    let running = true;
    let last = 0;
    const start = performance.now();
    const FRAME_MS = 1000 / 32; // cap ~32fps — plenty for a slow drift
    const loop = (now) => {
      raf = 0;
      if (!running) return;
      if (now - last >= FRAME_MS) {
        last = now;
        program.uniforms.uTime.value = (now - start) / 1000;
        renderer.render({ scene: mesh });
      }
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);

    const setRunning = (v) => {
      running = v;
      if (running && !raf) raf = requestAnimationFrame(loop);
    };
    const io = new IntersectionObserver(([e]) => setRunning(e.isIntersecting && !document.hidden), { threshold: 0 });
    io.observe(host);
    const onVis = () => setRunning(!document.hidden);
    document.addEventListener('visibilitychange', onVis);

    return () => {
      running = false;
      cancelAnimationFrame(raf);
      ro.disconnect();
      io.disconnect();
      document.removeEventListener('visibilitychange', onVis);
      try { gl.getExtension('WEBGL_lose_context')?.loseContext(); } catch { /* noop */ }
      canvas.remove();
    };
  }, [color, amplitude, count]);

  return <div ref={hostRef} className={`sc-threads ${className}`.trim()} aria-hidden="true" />;
}
