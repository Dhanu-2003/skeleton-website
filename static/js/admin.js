// The admin dashboard: the counts, a chart of every day (drawn on a canvas, no library) and the top lists, from /api/admin/stats.
(function () {
  "use strict";
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const COLORS = ["#5eead4", "#a78bfa", "#f5a524"];
  let data = null, anim = 1;

  function load(days) {
    fetch("/api/admin/stats?days=" + days, { credentials: "same-origin" }).then((r) => r.json()).then((j) => {
      data = j; fill(); anim = 0; grow();
    }).catch(() => window.siteToast && window.siteToast("The statistics could not be loaded."));
  }

  function fill() {
    Object.entries(data.totals).forEach(([k, v]) => { const el = $(`[data-kpi="${k}"]`); if (el) el.textContent = Number(v).toLocaleString(); });
    $$("[data-table]").forEach((t) => {
      const rows = data[t.dataset.table] || [];
      const max = Math.max(1, ...rows.map((r) => r.n));
      t.textContent = "";
      if (!rows.length) { const tr = t.insertRow(); tr.insertCell().textContent = "Nothing yet"; tr.cells[0].className = "muted"; return; }
      rows.forEach((r) => {
        const tr = t.insertRow(), a = tr.insertCell(), b = tr.insertCell();
        a.className = "bar-cell";
        const bar = document.createElement("i"); bar.style.width = (r.n / max) * 100 + "%";
        const s = document.createElement("span"); s.textContent = r.key;
        a.append(bar, s); b.className = "n"; b.textContent = r.n.toLocaleString();
      });
    });
  }

  function grow() {
    anim = Math.min(1, anim + 0.04);
    draw();
    if (anim < 1) requestAnimationFrame(grow);
  }

  function draw() {
    const c = $("#chart-traffic"); if (!c || !data) return;
    const dpr = window.devicePixelRatio || 1, w = c.clientWidth, h = c.clientHeight;
    c.width = w * dpr; c.height = h * dpr;
    const g = c.getContext("2d"); g.scale(dpr, dpr); g.clearRect(0, 0, w, h);
    const series = [data.views, data.visitors, data.downloads];
    const max = Math.max(4, ...series.flat());
    const L = 36, R = 10, T = 10, B = 26, n = data.days.length;
    const X = (i) => L + (n === 1 ? 0 : (i / (n - 1)) * (w - L - R)), Y = (v) => T + (1 - (v * anim) / max) * (h - T - B);
    g.font = "12px Segoe UI, system-ui"; g.fillStyle = "#6b7385"; g.strokeStyle = "rgba(255,255,255,0.06)";
    for (let k = 0; k <= 4; k++) {
      const v = Math.round((max * k) / 4), y = T + (1 - k / 4) * (h - T - B);
      g.beginPath(); g.moveTo(L, y); g.lineTo(w - R, y); g.stroke(); g.fillText(String(v), 4, y + 4);
    }
    const step = Math.ceil(n / 7);
    data.days.forEach((d, i) => { if (i % step === 0 || i === n - 1) g.fillText(d.slice(5), X(i) - 14, h - 6); });
    series.forEach((s, k) => {
      const grad = g.createLinearGradient(0, T, 0, h - B);
      grad.addColorStop(0, COLORS[k] + "55"); grad.addColorStop(1, COLORS[k] + "00");
      g.beginPath(); s.forEach((v, i) => (i ? g.lineTo(X(i), Y(v)) : g.moveTo(X(i), Y(v))));
      g.lineWidth = 2.2; g.strokeStyle = COLORS[k]; g.stroke();
      g.lineTo(X(n - 1), h - B); g.lineTo(X(0), h - B); g.closePath(); g.fillStyle = grad; g.globalAlpha = k === 2 ? 0.6 : 0.35; g.fill(); g.globalAlpha = 1;
    });
  }

  $$(".seg [data-days]").forEach((b) => b.addEventListener("click", () => {
    $$(".seg [data-days]").forEach((x) => x.classList.toggle("on", x === b)); load(b.dataset.days);
  }));
  window.addEventListener("resize", draw);
  load(30);
})();
