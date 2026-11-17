// The 3D board, drawn by Three.js from code (no model files): a circuit board with a chip, its pins, parts, glowing traces with signals running along
// them, a USB port and a small display. "hero": it turns slowly and follows the mouse. "story": the scroll drives it through five steps (main.js sends
// the progress as the "story-progress" event): the code arrives, the board is found, the tools appear, the traces light up (build, flash), it runs.
import * as THREE from "../vendor/three.module.min.js";      // (relative: the site may live under a sub-path, as on GitHub Pages)

const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const small = window.matchMedia("(max-width: 880px)").matches;
const CYAN = new THREE.Color("#5eead4"), BLUE = new THREE.Color("#60a5fa"), VIOLET = new THREE.Color("#a78bfa"), COPPER = new THREE.Color("#f5a524");

function rng(seed) { let s = seed >>> 0; return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296); }
const smooth = (a, b, x) => { const t = Math.min(1, Math.max(0, (x - a) / (b - a))); return t * t * (3 - 2 * t); };
const lerp = (a, b, t) => a + (b - a) * t;

function glowTexture(color) {
  const c = document.createElement("canvas"); c.width = c.height = 64;
  const g = c.getContext("2d"), r = g.createRadialGradient(32, 32, 0, 32, 32, 32);
  r.addColorStop(0, "rgba(255,255,255,1)"); r.addColorStop(0.25, color); r.addColorStop(1, "rgba(0,0,0,0)");
  g.fillStyle = r; g.fillRect(0, 0, 64, 64);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t;
}

function boardTexture() {
  const c = document.createElement("canvas"); c.width = 1024; c.height = 704;
  const g = c.getContext("2d");
  const grad = g.createLinearGradient(0, 0, 1024, 704);
  grad.addColorStop(0, "#0b3a2f"); grad.addColorStop(1, "#06261f");
  g.fillStyle = grad; g.fillRect(0, 0, 1024, 704);
  g.strokeStyle = "rgba(255,255,255,0.035)"; g.lineWidth = 1;
  for (let x = 0; x < 1024; x += 32) { g.beginPath(); g.moveTo(x, 0); g.lineTo(x, 704); g.stroke(); }
  for (let y = 0; y < 704; y += 32) { g.beginPath(); g.moveTo(0, y); g.lineTo(1024, y); g.stroke(); }
  const r = rng(7);
  for (let i = 0; i < 180; i++) { g.fillStyle = "rgba(201,162,39,0.55)"; g.beginPath(); g.arc(r() * 1024, r() * 704, 2.2, 0, Math.PI * 2); g.fill(); }
  g.strokeStyle = "rgba(201,162,39,0.5)"; g.lineWidth = 6; g.strokeRect(10, 10, 1004, 684);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 4; return t;
}

function makeBoard(seed = 3) {
  const r = rng(seed);
  const group = new THREE.Group();
  const W = 8, D = 5.5;
  const pcb = new THREE.Mesh(new THREE.BoxGeometry(W, 0.16, D), [
    new THREE.MeshStandardMaterial({ color: "#0a2a22", roughness: 0.7 }), new THREE.MeshStandardMaterial({ color: "#0a2a22", roughness: 0.7 }),
    new THREE.MeshStandardMaterial({ map: boardTexture(), roughness: 0.55, metalness: 0.15 }), new THREE.MeshStandardMaterial({ color: "#04140f" }),
    new THREE.MeshStandardMaterial({ color: "#0a2a22", roughness: 0.7 }), new THREE.MeshStandardMaterial({ color: "#0a2a22", roughness: 0.7 })]);
  group.add(pcb);

  // the chip and its pins
  const chip = new THREE.Group();
  const body = new THREE.Mesh(new THREE.BoxGeometry(1.7, 0.26, 1.7), new THREE.MeshStandardMaterial({ color: "#0d0f15", roughness: 0.35, metalness: 0.6 }));
  chip.add(body);
  const dot = new THREE.Mesh(new THREE.CircleGeometry(0.08, 24), new THREE.MeshBasicMaterial({ color: "#2a2f3a" }));
  dot.rotation.x = -Math.PI / 2; dot.position.set(-0.6, 0.131, -0.6); chip.add(dot);
  const core = new THREE.Mesh(new THREE.PlaneGeometry(0.9, 0.9), new THREE.MeshBasicMaterial({ color: CYAN, transparent: true, opacity: 0.0 }));
  core.rotation.x = -Math.PI / 2; core.position.y = 0.132; chip.add(core);
  const pinMat = new THREE.MeshStandardMaterial({ color: "#c9a227", metalness: 1, roughness: 0.3 });
  const pinGeo = new THREE.BoxGeometry(0.06, 0.04, 0.22);
  for (let s = 0; s < 4; s++) for (let i = 0; i < 12; i++) {
    const p = new THREE.Mesh(pinGeo, pinMat), off = -0.72 + i * 0.13;
    if (s < 2) { p.position.set(off, -0.08, (s ? 1 : -1) * 0.95); } else { p.rotation.y = Math.PI / 2; p.position.set((s === 3 ? 1 : -1) * 0.95, -0.08, off); }
    chip.add(p);
  }
  chip.position.y = 0.21;
  group.add(chip);

  // parts (the tools appear as they do)
  const parts = [];
  const partMats = [new THREE.MeshStandardMaterial({ color: "#1b1e26", roughness: 0.4, metalness: 0.4 }), new THREE.MeshStandardMaterial({ color: "#6b4a2b", roughness: 0.6 }),
    new THREE.MeshStandardMaterial({ color: "#a8b0bd", roughness: 0.25, metalness: 0.9 })];
  for (let i = 0; i < (small ? 16 : 26); i++) {
    let x, z;
    do { x = (r() - 0.5) * (W - 1); z = (r() - 0.5) * (D - 1); } while (Math.abs(x) < 1.4 && Math.abs(z) < 1.4);
    const big = r() > 0.75;
    const m = new THREE.Mesh(new THREE.BoxGeometry(big ? 0.7 : 0.3, big ? 0.22 : 0.12, big ? 0.5 : 0.16), partMats[Math.floor(r() * 3)]);
    m.position.set(x, 0.1 + (big ? 0.11 : 0.06), z); m.rotation.y = r() > 0.5 ? Math.PI / 2 : 0; m.userData.t = r();
    group.add(m); parts.push(m);
  }
  // the USB port and the display
  const usb = new THREE.Mesh(new THREE.BoxGeometry(0.7, 0.3, 0.55), new THREE.MeshStandardMaterial({ color: "#b8c0cc", metalness: 1, roughness: 0.25, emissive: "#000000" }));
  usb.position.set(-W / 2 + 0.25, 0.23, 1.6); group.add(usb);
  const sc = document.createElement("canvas"); sc.width = 256; sc.height = 160;
  const screenTex = new THREE.CanvasTexture(sc); screenTex.colorSpace = THREE.SRGBColorSpace;
  const screen = new THREE.Mesh(new THREE.BoxGeometry(2.1, 0.12, 1.35), [null, null, new THREE.MeshBasicMaterial({ map: screenTex }), null, null, null].map(
    (m) => m || new THREE.MeshStandardMaterial({ color: "#111318", metalness: 0.5, roughness: 0.4 })));
  screen.position.set(2.55, 0.17, -1.35); group.add(screen);

  // the traces: right-angled paths out of the chip, as glowing tubes
  const traces = [];
  for (let i = 0; i < (small ? 18 : 30); i++) {
    const side = i % 4, off = -0.66 + ((i * 7) % 12) * 0.12;
    let p = side < 2 ? new THREE.Vector3(off, 0.09, (side ? 1 : -1) * 1.08) : new THREE.Vector3((side === 3 ? 1 : -1) * 1.08, 0.09, off);
    const pts = [p.clone()];
    const dir = side < 2 ? new THREE.Vector3(0, 0, side ? 1 : -1) : new THREE.Vector3(side === 3 ? 1 : -1, 0, 0);
    for (let k = 0; k < 3; k++) {
      const len = 0.4 + r() * 1.4;
      p = p.clone().addScaledVector(dir, len);
      p.x = Math.max(-W / 2 + 0.3, Math.min(W / 2 - 0.3, p.x)); p.z = Math.max(-D / 2 + 0.3, Math.min(D / 2 - 0.3, p.z));
      pts.push(p.clone());
      if (dir.x) { dir.set(0, 0, r() > 0.5 ? 1 : -1); } else { dir.set(r() > 0.5 ? 1 : -1, 0, 0); }
    }
    const path = new THREE.CurvePath();
    for (let k = 0; k < pts.length - 1; k++) path.add(new THREE.LineCurve3(pts[k], pts[k + 1]));
    const col = [CYAN, BLUE, VIOLET][i % 3].clone();
    const mat = new THREE.MeshBasicMaterial({ color: col, transparent: true, opacity: 0.18, blending: THREE.AdditiveBlending, depthWrite: false });
    const tube = new THREE.Mesh(new THREE.TubeGeometry(path, 48, 0.022, 6, false), mat);
    group.add(tube);
    traces.push({ path, mat, col, order: i / 30, len: path.getLength() });
  }
  // the signals running along them
  const pulses = [];
  const tex = { c: glowTexture("rgba(94,234,212,0.9)"), v: glowTexture("rgba(167,139,250,0.9)") };
  for (let i = 0; i < (small ? 22 : 40); i++) {
    const tr = traces[i % traces.length];
    const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: i % 2 ? tex.v : tex.c, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false, opacity: 0.0 }));
    s.scale.setScalar(0.32); group.add(s);
    pulses.push({ s, tr, t: r(), speed: 0.12 + r() * 0.25 });
  }
  return { group, chip, core, parts, traces, pulses, usb, screen, sc, screenTex };
}

function stars(n) {
  const g = new THREE.BufferGeometry(), pos = new Float32Array(n * 3), r = rng(11);
  for (let i = 0; i < n; i++) { pos[i * 3] = (r() - 0.5) * 60; pos[i * 3 + 1] = (r() - 0.3) * 30; pos[i * 3 + 2] = (r() - 0.5) * 60; }
  g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  return new THREE.Points(g, new THREE.PointsMaterial({ color: "#8ea0c4", size: 0.05, transparent: true, opacity: 0.7, depthWrite: false }));
}

function mount(canvas, mode) {
  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: "high-performance" });
  } catch (e) { canvas.parentElement.classList.add("no-webgl"); return null; }
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, small ? 1.5 : 1.75));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  const scene = new THREE.Scene();
  scene.fog = new THREE.Fog("#05060a", 14, 34);
  const camera = new THREE.PerspectiveCamera(34, 1, 0.1, 100);
  scene.add(new THREE.AmbientLight("#9fb4ff", 0.45));
  const key = new THREE.DirectionalLight("#ffffff", 1.6); key.position.set(-5, 9, 6); scene.add(key);
  const pc = new THREE.PointLight(CYAN, 18, 12); pc.position.set(1.5, 2.2, 1); scene.add(pc);
  const pv = new THREE.PointLight(VIOLET, 14, 12); pv.position.set(-2.5, 1.5, -2); scene.add(pv);
  const field = stars(small ? 500 : 1200); scene.add(field);
  const B = makeBoard(mode === "story" ? 5 : 3); scene.add(B.group);

  let w = 0, h = 0, progress = mode === "story" ? 0 : 1, mx = 0, my = 0, visible = true, t0 = performance.now(), first = true;
  const resize = () => {
    const r = canvas.getBoundingClientRect(); w = Math.max(1, r.width); h = Math.max(1, r.height);
    renderer.setSize(w, h, false); camera.aspect = w / h; camera.updateProjectionMatrix();
  };
  new ResizeObserver(resize).observe(canvas); resize();
  window.addEventListener("pointermove", (e) => { mx = e.clientX / window.innerWidth - 0.5; my = e.clientY / window.innerHeight - 0.5; }, { passive: true });
  new IntersectionObserver((es) => { visible = es[0].isIntersecting; }).observe(canvas);
  if (mode === "story") window.addEventListener("story-progress", (e) => { progress = e.detail; });

  const sctx = B.sc.getContext("2d");
  function drawScreen(time, on) {
    sctx.fillStyle = "#04060b"; sctx.fillRect(0, 0, 256, 160);
    if (on <= 0.01) { B.screenTex.needsUpdate = true; return; }
    sctx.globalAlpha = on;
    sctx.strokeStyle = "rgba(94,234,212,0.18)";
    for (let x = 0; x < 256; x += 32) { sctx.beginPath(); sctx.moveTo(x, 0); sctx.lineTo(x, 160); sctx.stroke(); }
    sctx.lineWidth = 3; sctx.strokeStyle = "#5eead4"; sctx.beginPath();
    for (let x = 0; x <= 256; x += 4) { const y = 80 + Math.sin(x / 18 + time * 3) * 26 * Math.sin(time * 0.7 + x / 90); x ? sctx.lineTo(x, y) : sctx.moveTo(x, y); }
    sctx.stroke(); sctx.fillStyle = "#a78bfa"; sctx.font = "bold 22px Consolas, monospace"; sctx.fillText("RUN", 14, 30);
    sctx.globalAlpha = 1; B.screenTex.needsUpdate = true;
  }

  function frame(now) {
    requestAnimationFrame(frame);
    if (!visible && !reduced) return;
    const time = (now - t0) / 1000, p = reduced ? 1 : progress;
    // the five steps of the story (the hero shows the last, alive)
    const sArrive = smooth(0.0, 0.18, p), sFound = smooth(0.18, 0.38, p), sTools = smooth(0.38, 0.58, p), sLit = smooth(0.58, 0.8, p), sRun = smooth(0.8, 0.98, p);
    const hero = mode === "hero" || mode === "art", side = mode === "hero" && !small;      // ("art": the hero board, centred in a panel)
    // the camera: far and low, into the chip, then back out above it
    const camPos = hero ? new THREE.Vector3(side ? -0.4 : 0.6, 7.2, side ? 12.5 : 11.5)
      : new THREE.Vector3(lerp(lerp(7, 0.8, sArrive), 4.2, sRun), lerp(lerp(11, 4.2, sFound), 7.2, sRun), lerp(lerp(14, 4.8, sFound), 9.5, sRun));
    camPos.add(new THREE.Vector3(mx * 1.6, -my * 1.0, 0));
    if (first) { camera.position.copy(camPos); first = false; } else camera.position.lerp(camPos, 0.06);      // (the first frame is already in place: no fly-in from inside the board)
    camera.lookAt(side ? 1.2 : 0, hero ? -0.4 : lerp(0, -0.2, sRun), 0);
    B.group.rotation.y = hero ? time * 0.08 + mx * 0.25 : lerp(-0.9, 0.35, sArrive) + Math.sin(time * 0.3) * 0.04 + sRun * 0.25;
    B.group.rotation.x = hero ? 0.05 + my * 0.08 : lerp(0.5, 0, sArrive);
    B.group.position.y = hero ? Math.sin(time * 0.8) * 0.08 : lerp(-2.5, 0, sArrive);
    B.group.position.x = side ? 3.4 : 0;      // (the hero's board sits to the right of the words)
    // the board is found: the port and the chip light up
    B.usb.material.emissive.setRGB(0.2 * sFound * (1 - sRun * 0.6), 0.6 * sFound * (1 - sRun * 0.6), 0.55 * sFound * (1 - sRun * 0.6));
    B.core.material.opacity = (hero ? 0.35 + Math.sin(time * 2) * 0.15 : 0.08 + sFound * 0.25 + sRun * (0.25 + Math.sin(time * 3) * 0.12));
    // the tools: the parts rise into place one after another
    for (const m of B.parts) { const k = hero ? 1 : smooth(m.userData.t * 0.7, m.userData.t * 0.7 + 0.3, sTools); m.scale.setScalar(Math.max(0.001, k)); }
    // build and flash: the traces light up from the chip outward
    for (const tr of B.traces) {
      const on = hero ? 1 : smooth(tr.order * 0.7, tr.order * 0.7 + 0.3, sLit);
      tr.mat.opacity = 0.12 + on * (0.55 + 0.25 * Math.sin(time * 2 + tr.order * 9));
    }
    // the signals
    const live = hero ? 1 : Math.max(sLit, sRun);
    for (const q of B.pulses) {
      q.t = (q.t + q.speed * (0.004 + 0.012 * live)) % 1;
      q.s.position.copy(q.tr.path.getPointAt(q.t)).add(new THREE.Vector3(0, 0.04, 0));
      q.s.material.opacity = live * (0.55 + 0.45 * Math.sin(q.t * Math.PI));
    }
    // it runs: the chip lifts a little and the display shows its output
    B.chip.position.y = 0.21 + (hero ? 0 : sRun * 0.18);
    drawScreen(time, hero ? 1 : sRun);
    pc.intensity = 10 + 14 * live; pv.intensity = 8 + 10 * live;
    field.rotation.y = time * 0.01 + mx * 0.05; field.rotation.x = my * 0.03;
    renderer.render(scene, camera);
  }
  requestAnimationFrame(frame);
  return { setProgress: (v) => { progress = v; } };
}

document.querySelectorAll("canvas[data-scene]").forEach((c) => mount(c, c.dataset.scene));
