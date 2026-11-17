// The website's motion and its small behaviours. Everything works without it (the content is in the HTML); with it: smooth scrolling (Lenis), the pinned
// story and the sideways rail (GSAP ScrollTrigger), parallax, reveals, magnetic and rippling buttons, 3D tilt, counters, the animated popups, the FAQ,
// the password helpers, and the first-party statistics beacon (it honours Do Not Track and Global Privacy Control).
(function () {
  "use strict";
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const desktop = () => window.matchMedia("(min-width: 881px)").matches;
  const fine = window.matchMedia("(pointer: fine)").matches;
  const csrf = ($('meta[name="csrf-token"]') || {}).content || "";
  const ghRepo = ($('meta[name="gh-repo"]') || {}).content || "";
  const isStatic = !csrf;      // (the static site: no server to tell; the download count is GitHub's)
  function refreshDownloads() {
    const put = (n) => $$("[data-downloads]").forEach((el) => { el.textContent = Number(n).toLocaleString(); });
    if (ghRepo) {
      fetch(`https://api.github.com/repos/${ghRepo}/releases?per_page=100`, { headers: { Accept: "application/vnd.github+json" } })
        .then((r) => r.ok ? r.json() : Promise.reject(r.status))
        .then((rels) => put(rels.reduce((s, rel) => s + (rel.assets || []).filter((a) => /\.(exe|msi|zip)$/i.test(a.name)).reduce((t, a) => t + (a.download_count || 0), 0), 0)))
        .catch(() => {});
    } else if (!isStatic) {
      fetch("/api/downloads", { credentials: "same-origin" }).then((r) => r.json()).then((j) => put(j.total)).catch(() => {});
    }
  }
  refreshDownloads();
  const G = window.gsap, ST = window.ScrollTrigger;

  // ---------------------------------------------------------------- statistics (first party: this server only)
  const dnt = navigator.doNotTrack === "1" || window.doNotTrack === "1" || navigator.globalPrivacyControl === true;
  function track(name, value) {
    if (dnt || isStatic) return;
    try {
      fetch("/api/event", { method: "POST", keepalive: true, credentials: "same-origin", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, value: value || "", path: location.pathname }) });
    } catch (e) { /* statistics never get in the way */ }
  }
  window.siteTrack = track;
  document.addEventListener("click", (e) => {
    const t = e.target.closest("[data-track]");
    if (t) track(t.dataset.track, t.dataset.trackValue || t.textContent.trim().slice(0, 60));
    const n = e.target.closest("[data-track-nav]");
    if (n) track("nav", n.dataset.trackNav);
  });
  const seenDepth = new Set();
  window.addEventListener("scroll", () => {
    const max = document.documentElement.scrollHeight - innerHeight;
    if (max <= 0) return;
    const pct = (scrollY / max) * 100;
    [25, 50, 75, 100].forEach((d) => { if (pct >= d - 1 && !seenDepth.has(d)) { seenDepth.add(d); track("scroll_" + d); } });
  }, { passive: true });
  setTimeout(() => track("time_30s"), 30000);
  setTimeout(() => track("time_120s"), 120000);

  // ---------------------------------------------------------------- toasts
  function toast(text) {
    const box = $(".toasts"); if (!box) return;
    const t = document.createElement("div"); t.className = "toast"; t.textContent = text; box.appendChild(t);
    if (G) { G.fromTo(t, { y: 20, opacity: 0 }, { y: 0, opacity: 1, duration: 0.4, ease: "power3.out" }); G.to(t, { opacity: 0, y: 10, delay: 3.2, duration: 0.4, onComplete: () => t.remove() }); }
    else setTimeout(() => t.remove(), 3600);
  }
  window.siteToast = toast;

  // ---------------------------------------------------------------- the popups: open with a blur behind and a rising panel; Esc and the backdrop close
  let lastFocus = null;
  function openModal(m) {
    if (!m) return;
    lastFocus = document.activeElement;
    m.hidden = false; m.classList.add("is-open");
    const bd = $(".backdrop", m), panel = $(".panel", m);
    if (G && !reduced) {
      G.fromTo(bd, { opacity: 0 }, { opacity: 1, duration: 0.45, ease: "power2.out", onUpdate() { const v = 14 * G.getProperty(bd, "opacity"); bd.style.backdropFilter = `blur(${v}px)`; bd.style.webkitBackdropFilter = `blur(${v}px)`; } });
      G.fromTo(panel, { opacity: 0, y: 40, scale: 0.92, rotateX: 8 }, { opacity: 1, y: 0, scale: 1, rotateX: 0, duration: 0.7, ease: "back.out(1.6)" });
    } else { bd.style.opacity = 1; panel.style.opacity = 1; panel.style.transform = "none"; }
    setTimeout(() => { const f = $("button:not([data-close]), a, input", panel) || $("[data-close].btn", panel) || panel; f.focus && f.focus(); }, 60);
    window.lenis && window.lenis.stop();
  }
  function closeModal(m) {
    if (!m || !m.classList.contains("is-open")) return;
    const bd = $(".backdrop", m), panel = $(".panel", m);
    const done = () => { m.classList.remove("is-open"); m.hidden = true; lastFocus && lastFocus.focus && lastFocus.focus(); window.lenis && window.lenis.start(); };
    if (G && !reduced) { G.to(panel, { opacity: 0, y: 24, scale: 0.96, duration: 0.3, ease: "power2.in" }); G.to(bd, { opacity: 0, duration: 0.35, onComplete: done }); }
    else done();
  }
  window.siteModal = { open: openModal, close: closeModal };
  document.addEventListener("click", (e) => {
    const c = e.target.closest("[data-close]");
    if (c) { const m = c.closest(".modal"); if (m) { if (c.tagName === "A") { closeModal(m); return; } e.preventDefault(); closeModal(m); } }
    const o = e.target.closest("[data-modal-open]");
    if (o) { e.preventDefault(); openModal(document.getElementById(o.dataset.modalOpen)); }
  });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") $$(".modal.is-open").forEach(closeModal); });

  // ---------------------------------------------------------------- the download: the file starts, a popup says what is next, the counter moves
  document.addEventListener("click", (e) => {
    const a = e.target.closest("a[data-download]");
    if (!a) return;
    const m = document.getElementById("modal-download");
    if (m) { $(".md-file", m).textContent = a.dataset.file || "the installer"; setTimeout(() => openModal(m), 250); }
    $$("[data-downloads]").forEach((el) => { el.textContent = String((parseInt(el.textContent, 10) || 0) + 1); });
    setTimeout(refreshDownloads, 4000);
  });

  // ---------------------------------------------------------------- copy (the installer's hash)
  document.addEventListener("click", (e) => {
    const b = e.target.closest("[data-copy]");
    if (!b) return;
    navigator.clipboard && navigator.clipboard.writeText(b.dataset.copy).then(() => { toast("Copied."); track("copy_hash"); });
  });

  // ---------------------------------------------------------------- the header and the mobile menu
  const head = $(".site-head");
  let lastY = 0;
  window.addEventListener("scroll", () => {
    const y = scrollY;
    head && head.classList.toggle("is-scrolled", y > 20);
    head && head.classList.toggle("is-hidden", y > 400 && y > lastY && !document.body.classList.contains("menu-open"));
    lastY = y;
  }, { passive: true });
  const mb = $(".menu-btn");
  mb && mb.addEventListener("click", () => {
    const on = !document.body.classList.contains("menu-open");
    document.body.classList.toggle("menu-open", on); mb.setAttribute("aria-expanded", String(on));
  });

  // ---------------------------------------------------------------- password helpers
  $$("[data-eye]").forEach((b) => b.addEventListener("click", () => {
    const i = document.getElementById(b.dataset.eye); if (!i) return;
    i.type = i.type === "password" ? "text" : "password"; b.setAttribute("aria-label", i.type === "password" ? "Show the password" : "Hide the password");
  }));
  $$("[data-meter]").forEach((input) => {
    const bar = $("#" + input.dataset.meter + " i"); if (!bar) return;
    input.addEventListener("input", () => {
      const v = input.value; let s = 0;
      if (v.length >= 10) s++; if (v.length >= 14) s++; if (/[A-Z]/.test(v) && /[a-z]/.test(v)) s++; if (/\d/.test(v)) s++; if (/[^A-Za-z0-9]/.test(v)) s++;
      bar.style.width = Math.min(100, s * 20) + "%"; bar.style.background = s <= 1 ? "#f87171" : s <= 3 ? "#f5a524" : "#34d399";
    });
  });

  // ---------------------------------------------------------------- the FAQ
  $$(".faq-item button").forEach((b) => b.addEventListener("click", () => {
    const item = b.closest(".faq-item"), a = $(".a", item), open = !item.classList.contains("is-open");
    item.classList.toggle("is-open", open); b.setAttribute("aria-expanded", String(open));
    if (G && !reduced) G.to(a, { height: open ? "auto" : 0, duration: 0.55, ease: "power3.inOut" }); else a.style.height = open ? "auto" : "0";
    if (open) track("faq_open", b.textContent.trim().slice(0, 60));
  }));

  // ---------------------------------------------------------------- without GSAP (or with reduced motion): everything is simply shown
  if (!G || !ST || reduced) {
    $$("[data-reveal]").forEach((el) => { el.style.opacity = 1; });
    $(".loader") && $(".loader").remove();
    return;
  }
  G.registerPlugin(ST);

  // ---------------------------------------------------------------- smooth scrolling
  if (window.Lenis) {
    const lenis = new window.Lenis({ lerp: 0.09, smoothWheel: true });
    window.lenis = lenis;
    lenis.on("scroll", ST.update);
    G.ticker.add((t) => lenis.raf(t * 1000));
    G.ticker.lagSmoothing(0);
    document.addEventListener("click", (e) => {
      const a = e.target.closest('a[href^="#"]'); if (!a || a.getAttribute("href").length < 2) return;
      const t = document.querySelector(a.getAttribute("href")); if (!t) return;
      e.preventDefault(); lenis.scrollTo(t, { offset: -10, duration: 1.4 });
    });
  }

  // ---------------------------------------------------------------- the intro: the loader fills, then the hero comes in
  const intro = G.timeline();
  const loader = $(".loader");
  if (loader && getComputedStyle(loader).display !== "none") {
    intro.to(".loader .bar i", { width: "100%", duration: 0.9, ease: "power2.inOut" })
      .to(".loader .mark", { scale: 0.6, opacity: 0, duration: 0.4, ease: "power2.in" }, "-=0.1")
      .to(loader, { yPercent: -100, duration: 0.8, ease: "expo.inOut", onComplete: () => loader.remove() }, "-=0.15");
  } else if (loader) loader.remove();
  if ($("[data-split]")) {
    intro.from("[data-split] .line > span", { yPercent: 110, rotate: 3, duration: 1.1, ease: "expo.out", stagger: 0.09 }, loader ? "-=0.45" : 0)
      .from("[data-hero]", { y: 30, opacity: 0, duration: 0.9, ease: "power3.out", stagger: 0.08 }, "-=0.8")
      .from(".hero canvas.scene", { opacity: 0, duration: 1.6, ease: "power2.out" }, 0.2);
  }

  // ---------------------------------------------------------------- reveals and parallax
  ST.batch("[data-reveal]", {
    start: "top 88%", once: true,
    onEnter: (els) => G.fromTo(els, { y: 46, opacity: 0, filter: "blur(6px)" }, { y: 0, opacity: 1, filter: "blur(0px)", duration: 1.1, ease: "expo.out", stagger: 0.09 }),
  });
  $$("[data-speed]").forEach((el) => {
    const s = parseFloat(el.dataset.speed) || 1;
    G.to(el, { y: () => (1 - s) * 260, ease: "none", scrollTrigger: { trigger: el.closest("section") || el, start: "top bottom", end: "bottom top", scrub: true, invalidateOnRefresh: true } });
  });
  if ($(".hero .wrap")) G.to(".hero .wrap", { yPercent: -18, opacity: 0.2, ease: "none", scrollTrigger: { trigger: ".hero", start: "top top", end: "bottom top", scrub: true } });

  // ---------------------------------------------------------------- the pinned story: the page holds still, the board and the words move
  const story = $("#story");
  const mm = G.matchMedia();
  mm.add("(min-width: 881px)", () => {
    if (!story) return;
    const steps = $$(".step", story), bars = $$(".rail i b", story), hud = $$("[data-hud]", story);
    let cur = 0;
    const show = (i) => {
      if (i === cur) return;
      const dir = i > cur ? 1 : -1;
      G.to(steps[cur], { opacity: 0, y: -40 * dir, duration: 0.45, ease: "power2.in" });
      G.fromTo(steps[i], { opacity: 0, y: 50 * dir }, { opacity: 1, y: 0, duration: 0.7, ease: "expo.out", delay: 0.15 });
      steps.forEach((s, k) => s.classList.toggle("is-on", k === i));
      cur = i;
    };
    G.set(steps, { opacity: 0 }); G.set(steps[0], { opacity: 1, y: 0 });
    ST.create({
      trigger: story, start: "top top", end: "bottom bottom", scrub: true,
      onUpdate(self) {
        const p = self.progress;
        window.dispatchEvent(new CustomEvent("story-progress", { detail: p }));
        show(Math.min(steps.length - 1, Math.floor(p * steps.length * 0.999)));
        bars.forEach((b, k) => { b.style.width = Math.max(0, Math.min(1, p * steps.length - k)) * 100 + "%"; });
        hud.forEach((h) => { const on = p >= (+h.dataset.hud) / 5; if (on !== h._on) { h._on = on; G.to(h, { opacity: on ? 1 : 0, x: on ? 0 : 20, duration: 0.5, ease: "power3.out" }); } });
      },
    });
  });
  mm.add("(max-width: 880px)", () => { window.dispatchEvent(new CustomEvent("story-progress", { detail: 1 })); });

  // ---------------------------------------------------------------- the chat showcase: the messages arrive as you scroll
  const chats = $$("[data-chat]");
  if (chats.length) {
    G.set(chats, { opacity: 0, y: 20 });
    ST.create({ trigger: chats[0].closest(".window"), start: "top 70%", once: true,
      onEnter: () => G.to(chats, { opacity: 1, y: 0, duration: 0.7, ease: "power3.out", stagger: 0.55 }) });
  }

  // ---------------------------------------------------------------- the sideways rail (pinned)
  mm.add("(min-width: 881px)", () => {
    const track = $("[data-hscroll]"); if (!track) return;
    const dist = () => Math.max(0, track.scrollWidth - innerWidth);
    const slide = G.to(track, { x: () => -dist(), ease: "none",
      scrollTrigger: { trigger: track.closest("section"), start: "top top", end: () => "+=" + dist(), pin: true, scrub: 0.8, invalidateOnRefresh: true, anticipatePin: 1 } });
    $$(".fcard", track).forEach((c) => G.from(c, { rotateY: -14, opacity: 0.4, scale: 0.94, transformPerspective: 1000, ease: "none",
      scrollTrigger: { trigger: c, containerAnimation: slide, start: "left 95%", end: "left 55%", scrub: true } }));
  });

  // ---------------------------------------------------------------- counters
  $$("[data-count]").forEach((el) => {
    const end = parseInt(el.dataset.count, 10) || 0, o = { v: 0 };
    ST.create({ trigger: el, start: "top 90%", once: true,
      onEnter: () => G.to(o, { v: end, duration: 1.8, ease: "power3.out", onUpdate: () => { el.textContent = Math.round(o.v).toLocaleString(); } }) });
  });

  // ---------------------------------------------------------------- the timeline (How it works): the line draws itself, each step lights up
  const tl = $(".timeline path");
  if (tl) {
    const len = tl.getTotalLength();
    G.set(tl, { strokeDasharray: len, strokeDashoffset: len });
    G.to(tl, { strokeDashoffset: 0, ease: "none", scrollTrigger: { trigger: ".timeline", start: "top 70%", end: "bottom 70%", scrub: true } });
    $$(".tl-step").forEach((s) => ST.create({ trigger: s, start: "top 65%", onToggle: (self) => s.classList.toggle("is-on", self.isActive || self.progress > 0) , end: "bottom top" }));
  }

  // ---------------------------------------------------------------- feature visuals drift as they pass
  $$(".feature .visual .inner").forEach((el) => G.fromTo(el, { y: 40 }, { y: -40, ease: "none", scrollTrigger: { trigger: el.closest(".feature"), start: "top bottom", end: "bottom top", scrub: true } }));

  // ---------------------------------------------------------------- the cursor, magnetic buttons, ripples, tilt
  if (fine) {
    const dot = $(".cursor"), ring = $(".cursor-ring");
    window.addEventListener("pointermove", () => document.body.classList.add("has-cursor"), { once: true, passive: true });      // (shown from the first move: never parked in a corner)
    const dx = G.quickTo(dot, "x", { duration: 0.08 }), dy = G.quickTo(dot, "y", { duration: 0.08 });
    const rx = G.quickTo(ring, "x", { duration: 0.45, ease: "power3" }), ry = G.quickTo(ring, "y", { duration: 0.45, ease: "power3" });
    window.addEventListener("pointermove", (e) => { dx(e.clientX); dy(e.clientY); rx(e.clientX); ry(e.clientY); }, { passive: true });
    document.addEventListener("pointerover", (e) => ring.classList.toggle("is-hover", !!e.target.closest("a, button, [data-magnetic], input, textarea")));
    $$("[data-magnetic]").forEach((el) => {
      const xTo = G.quickTo(el, "x", { duration: 0.6, ease: "elastic.out(1, 0.4)" }), yTo = G.quickTo(el, "y", { duration: 0.6, ease: "elastic.out(1, 0.4)" });
      el.addEventListener("pointermove", (e) => { const r = el.getBoundingClientRect(); xTo((e.clientX - r.left - r.width / 2) * 0.28); yTo((e.clientY - r.top - r.height / 2) * 0.35); });
      el.addEventListener("pointerleave", () => { xTo(0); yTo(0); });
    });
    $$("[data-tilt]").forEach((el) => {
      el.addEventListener("pointermove", (e) => { const r = el.getBoundingClientRect(); const px = (e.clientX - r.left) / r.width - 0.5, py = (e.clientY - r.top) / r.height - 0.5;
        G.to(el, { rotateY: px * 10, rotateX: -py * 8, transformPerspective: 900, duration: 0.6, ease: "power3.out" }); });
      el.addEventListener("pointerleave", () => G.to(el, { rotateY: 0, rotateX: 0, duration: 0.9, ease: "elastic.out(1, 0.5)" }));
    });
  }
  document.addEventListener("pointerdown", (e) => {
    const b = e.target.closest(".btn"); if (!b) return;
    const r = b.getBoundingClientRect(), s = Math.max(r.width, r.height), i = document.createElement("span");
    i.className = "ripple"; i.style.width = i.style.height = s + "px"; i.style.left = e.clientX - r.left - s / 2 + "px"; i.style.top = e.clientY - r.top - s / 2 + "px";
    b.appendChild(i); setTimeout(() => i.remove(), 700);
  });

  // page enter: the page head comes in like the hero
  if ($(".page-head")) G.from(".page-head > .wrap > *", { y: 40, opacity: 0, duration: 1, ease: "expo.out", stagger: 0.08, delay: loader ? 1.2 : 0.05 });
  window.addEventListener("load", () => ST.refresh());
})();
