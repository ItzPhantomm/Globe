const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));

let CSRF = "";
let WS = null;
const latHistory = [];
let hourlyActivity = [];
let chartMode = "activity";
let selectedActivityKind = "globe";

// Live spoofer client-side timer smoothing state
let spooferState = {
  running: false,
  current: 0,
  total: 0,
  game: "",
  app_id: "",
  started_client_ms: 0,
  elapsed_s: 0,
  remaining_s: 0,
  completed_total: 0,
};
let spooferTickTimer = 0;

// ── 1. Real Chromium Liquid Glass SDF Displacement Map ────
function makeDisplacementMap(w, h, r, bezel) {
  const cw = Math.max(40, Math.round(w));
  const ch = Math.max(24, Math.round(h));
  const canvas = document.createElement("canvas");
  canvas.width = cw;
  canvas.height = ch;
  const ctx = canvas.getContext("2d");
  const img = ctx.createImageData(cw, ch);

  const rr = Math.min(r, cw / 2, ch / 2);
  const sdf = (x, y) => {
    const qx = Math.abs(x - cw / 2) - (cw / 2 - rr);
    const qy = Math.abs(y - ch / 2) - (ch / 2 - rr);
    return Math.hypot(Math.max(qx, 0), Math.max(qy, 0)) + Math.min(Math.max(qx, qy), 0) - rr;
  };

  for (let y = 0; y < ch; y++) {
    for (let x = 0; x < cw; x++) {
      const inset = -sdf(x, y);
      let dx = 0;
      let dy = 0;
      if (inset > 0 && inset < bezel) {
        const nx = sdf(x + 1, y) - sdf(x - 1, y);
        const ny = sdf(x, y + 1) - sdf(x, y - 1);
        const len = Math.hypot(nx, ny) || 1;
        const t = 1 - inset / bezel;
        const strength = t * t;
        dx = (-nx / len) * strength;
        dy = (-ny / len) * strength;
      }
      const i = (y * cw + x) * 4;
      img.data[i] = 128 + dx * 127;
      img.data[i + 1] = 128 + dy * 127;
      img.data[i + 2] = 128;
      img.data[i + 3] = 255;
    }
  }
  ctx.putImageData(img, 0, 0);
  return canvas.toDataURL();
}

function initLiquidGlassDock() {
  const dock = $("#liquid-dock");
  const mapEl = $("#lg-dock-map");
  if (!dock || !mapEl) return;

  const isChromium =
    navigator.userAgentData?.brands?.some((b) => /chrom/i.test(b.brand)) ||
    /Chrome\//.test(navigator.userAgent);

  let timer = 0;
  function rebuild() {
    const rect = dock.getBoundingClientRect();
    if (rect.width < 40 || rect.height < 20) return;
    if (isChromium) {
      mapEl.setAttribute("width", String(Math.round(rect.width)));
      mapEl.setAttribute("height", String(Math.round(rect.height)));
      mapEl.setAttribute("href", makeDisplacementMap(rect.width, rect.height, rect.height / 2, 18));
      dock.classList.add("is-refracting");
    }
    syncDockIndicator();
  }

  const ro = new ResizeObserver(() => {
    clearTimeout(timer);
    timer = setTimeout(rebuild, 60);
  });
  ro.observe(dock);
  requestAnimationFrame(rebuild);
}

// ── 2. Animated Sliding Pill Indicators ───────────────────
function moveSlider(container, slider, activeBtn) {
  if (!container || !slider) return;
  if (!activeBtn) {
    slider.classList.add("hidden-pill");
    return;
  }
  const left = activeBtn.offsetLeft;
  const width = activeBtn.offsetWidth;
  if (!width) return;
  slider.classList.remove("hidden-pill");
  const padOffset = parseFloat(getComputedStyle(slider).left) || 0;
  slider.style.width = `${width}px`;
  slider.style.transform = `translateX(${left - padOffset}px)`;
}

function syncDockIndicator() {
  const dock = $("#liquid-dock");
  const ind = $("#dock-indicator");
  const active = dock?.querySelector(".dock-item.active");
  moveSlider(dock, ind, active);
}

function setSegActive(segId, attrName, value) {
  const seg = $(segId);
  if (!seg) return;
  const slider = seg.querySelector(".seg-slider");
  const buttons = Array.from(seg.querySelectorAll("button"));
  let targetBtn = null;
  buttons.forEach((btn) => {
    const match = value != null && btn.dataset[attrName] === String(value);
    btn.classList.toggle("active", match);
    if (match) targetBtn = btn;
  });
  moveSlider(seg, slider, targetBtn);
}

function initAllSlidingSegs() {
  $$(".sliding-seg").forEach((seg) => {
    const slider = seg.querySelector(".seg-slider");
    const active = seg.querySelector("button.active");
    moveSlider(seg, slider, active);
    if (seg.dataset.boundSeg) return;
    seg.dataset.boundSeg = "1";
    seg.querySelectorAll("button").forEach((btn) => {
      btn.addEventListener("click", () => {
        seg.querySelectorAll("button").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        moveSlider(seg, slider, btn);
      });
    });
  });
}

// ── 3. Android M3 Expressive Polygon Morph Engine ─────────
const M3_SHAPES = [
  [
    [50, 7], [65, 15], [82, 18], [85, 35],
    [93, 50], [85, 65], [82, 82], [65, 85],
    [50, 93], [35, 85], [18, 82], [15, 65],
    [7, 50], [15, 35], [18, 18], [35, 15],
  ],
  [
    [50, 14], [69, 9], [86, 14], [91, 31],
    [86, 50], [91, 69], [86, 86], [69, 91],
    [50, 86], [31, 91], [14, 86], [9, 69],
    [14, 50], [9, 31], [14, 14], [31, 9],
  ],
  [
    [50, 5], [63, 21], [85, 15], [79, 37],
    [95, 50], [79, 63], [85, 85], [63, 79],
    [50, 95], [37, 79], [15, 85], [21, 63],
    [5, 50], [21, 37], [15, 15], [37, 21],
  ],
  [
    [50, 8], [72, 9], [87, 13], [91, 28],
    [92, 50], [91, 72], [87, 87], [72, 91],
    [50, 92], [28, 91], [13, 87], [9, 72],
    [8, 50], [9, 28], [13, 13], [28, 9],
  ],
];

function ptsToSmoothPath(pts) {
  const n = pts.length;
  let d = "";
  for (let i = 0; i < n; i++) {
    const p0 = pts[(i - 1 + n) % n];
    const p1 = pts[i];
    const p2 = pts[(i + 1) % n];
    const mx = (p1[0] + p2[0]) / 2;
    const my = (p1[1] + p2[1]) / 2;
    if (i === 0) {
      d += `M ${((p0[0] + p1[0]) / 2).toFixed(2)} ${((p0[1] + p1[1]) / 2).toFixed(2)} `;
    }
    d += `Q ${p1[0].toFixed(2)} ${p1[1].toFixed(2)} ${mx.toFixed(2)} ${my.toFixed(2)} `;
  }
  return d + "Z";
}

function initShapeMorph() {
  const authPath = $("#auth-morph-path");
  const navPath = $("#nav-morph-path");
  const initialD = ptsToSmoothPath(M3_SHAPES[0]);
  if (authPath) authPath.setAttribute("d", initialD);
  if (navPath) navPath.setAttribute("d", initialD);
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

  let t = 0;
  function step() {
    t += 0.011;
    const idxA = Math.floor(t) % M3_SHAPES.length;
    const idxB = (idxA + 1) % M3_SHAPES.length;
    const raw = t - Math.floor(t);
    const k = raw < 0.5 ? 2 * raw * raw : 1 - Math.pow(-2 * raw + 2, 2) / 2;
    const A = M3_SHAPES[idxA];
    const B = M3_SHAPES[idxB];
    const pathStr = ptsToSmoothPath(A.map((pt, i) => [pt[0] + (B[i][0] - pt[0]) * k, pt[1] + (B[i][1] - pt[1]) * k]));
    if (authPath && !$("#auth-gate").classList.contains("hidden")) authPath.setAttribute("d", pathStr);
    if (navPath && !$("#workspace").classList.contains("hidden")) navPath.setAttribute("d", pathStr);
    requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
}

function initSpotlightCards() {
  let raf = 0;
  let lastEv = null;
  document.addEventListener("pointermove", (e) => {
    lastEv = e;
    if (raf) return;
    raf = requestAnimationFrame(() => {
      raf = 0;
      if (!lastEv) return;
      $$(".bento-surface").forEach((card) => {
        const r = card.getBoundingClientRect();
        card.style.setProperty("--mx", `${lastEv.clientX - r.left}px`);
        card.style.setProperty("--my", `${lastEv.clientY - r.top}px`);
      });
    });
  }, { passive: true });
}

function animateViewStagger(viewEl) {
  if (!viewEl || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const targets = viewEl.querySelectorAll(".stagger-item");
  if (!targets.length) return;
  if (window.anime) {
    window.anime.remove(targets);
    window.anime({
      targets,
      translateY: [18, 0],
      scale: [0.985, 1],
      opacity: [0, 1],
      duration: 480,
      easing: "cubicBezier(0.28, 1.32, 0.5, 1)",
      delay: window.anime.stagger(48),
    });
  }
}

// ── 4. Helpers & API ──────────────────────────────────────
function toast(msg) {
  const el = document.createElement("div");
  el.className = "toast";
  el.textContent = msg;
  $("#toast-root").appendChild(el);
  setTimeout(() => el.remove(), 3400);
}

function esc(str) {
  return String(str ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function fmtUptime(s) {
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  return h ? `${h}h ${m}m` : `${m}m ${s % 60}s`;
}

function fmtMMSS(sec) {
  const v = Math.max(0, Math.floor(sec || 0));
  const m = Math.floor(v / 60);
  const s = v % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

async function api(path, opts = {}) {
  const headers = { ...(opts.headers || {}) };
  if (opts.body && typeof opts.body === "object") {
    headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(opts.body);
  }
  if (opts.method && opts.method !== "GET" && CSRF) {
    headers["X-Globe-CSRF"] = CSRF;
  }
  const resp = await fetch(path, { ...opts, headers, credentials: "same-origin" });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(data.error || `HTTP ${resp.status}`);
  return data;
}

// ── 5. Sidebar Drawer & Account Popover ───────────────────
function toggleSidebar(open) {
  const drawer = $("#sidebar-drawer");
  const back = $("#sidebar-backdrop");
  const btn = $("#btn-menu-open");
  if (!drawer || !back) return;
  if (open) {
    back.classList.remove("hidden");
    requestAnimationFrame(() => {
      back.classList.add("open");
      drawer.classList.add("open");
    });
    drawer.setAttribute("aria-hidden", "false");
    btn?.setAttribute("aria-expanded", "true");
  } else {
    drawer.classList.remove("open");
    back.classList.remove("open");
    drawer.setAttribute("aria-hidden", "true");
    btn?.setAttribute("aria-expanded", "false");
    setTimeout(() => {
      if (!drawer.classList.contains("open")) back.classList.add("hidden");
    }, 280);
  }
}

$("#btn-menu-open")?.addEventListener("click", () => toggleSidebar(true));
$("#btn-menu-close")?.addEventListener("click", () => toggleSidebar(false));
$("#sidebar-backdrop")?.addEventListener("click", () => toggleSidebar(false));

function toggleAccountPopover(open) {
  const pop = $("#account-popover");
  const btn = $("#account-pill-btn");
  if (!pop || !btn) return;
  const shouldOpen = open !== undefined ? open : pop.classList.contains("hidden");
  pop.classList.toggle("hidden", !shouldOpen);
  btn.setAttribute("aria-expanded", String(shouldOpen));
  if (shouldOpen) loadAccounts();
}

$("#account-pill-btn")?.addEventListener("click", (e) => {
  e.stopPropagation();
  toggleAccountPopover();
});

document.addEventListener("click", (e) => {
  const pop = $("#account-popover");
  if (pop && !pop.classList.contains("hidden") && !e.target.closest(".account-wrap")) {
    toggleAccountPopover(false);
  }
});

$("#btn-pop-show-add")?.addEventListener("click", () => {
  $("#pop-add-form")?.classList.remove("hidden");
  $("#pop-add-token")?.focus();
});
$("#btn-pop-cancel-acct")?.addEventListener("click", () => {
  $("#pop-add-form")?.classList.add("hidden");
  if ($("#pop-add-token")) $("#pop-add-token").value = "";
});
$("#btn-pop-settings")?.addEventListener("click", () => {
  toggleAccountPopover(false);
  switchView("settings");
});

// ── 6. Interactive Smooth Bezier & Histogram Chart ────────
let chartPoints = [];

function catmullRomPath(pts) {
  if (pts.length < 2) return "";
  let d = `M ${pts[0].x.toFixed(1)} ${pts[0].y.toFixed(1)}`;
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[Math.max(i - 1, 0)];
    const p1 = pts[i];
    const p2 = pts[i + 1];
    const p3 = pts[Math.min(i + 2, pts.length - 1)];
    const cp1x = p1.x + (p2.x - p0.x) / 6;
    const cp1y = p1.y + (p2.y - p0.y) / 6;
    const cp2x = p2.x - (p3.x - p1.x) / 6;
    const cp2y = p2.y - (p3.y - p1.y) / 6;
    d += ` C ${cp1x.toFixed(1)} ${cp1y.toFixed(1)}, ${cp2x.toFixed(1)} ${cp2y.toFixed(1)}, ${p2.x.toFixed(1)} ${p2.y.toFixed(1)}`;
  }
  return d;
}

function drawMainChart() {
  const grid = $("#chart-grid");
  const barsG = $("#chart-bars");
  const line = $("#chart-line");
  const area = $("#chart-area");
  if (!grid || !line) return;

  const w = 600;
  const h = 180;
  const padTop = 18;
  const padBot = 24;
  const padX = 28;
  const usableW = w - padX * 2;
  const usableH = h - padTop - padBot;

  let raw = [];
  let unit = "ms";
  if (chartMode === "activity") {
    unit = "msgs";
    raw = hourlyActivity.length
      ? hourlyActivity.map((d) => ({ label: d.label, val: Number(d.count) || 0 }))
      : Array.from({ length: 12 }, (_, i) => ({ label: `${(i * 2).toString().padStart(2, "0")}:00`, val: 0 }));
  } else {
    unit = "ms";
    const src = latHistory.length === 1 ? [latHistory[0], latHistory[0]] : latHistory;
    raw = src.map((v, i) => ({ label: `Sample ${i + 1}`, val: v }));
  }

  if (!raw.length) return;
  const maxVal = Math.max(...raw.map((r) => r.val), chartMode === "activity" ? 10 : 80);
  const yTicks = [0, Math.round(maxVal / 2), maxVal];

  grid.innerHTML = yTicks.map((tv) => {
    const y = padTop + usableH - (tv / maxVal) * usableH;
    return `<line x1="${padX}" y1="${y.toFixed(1)}" x2="${w - 8}" y2="${y.toFixed(1)}" /><text x="2" y="${(y + 3).toFixed(1)}">${tv}</text>`;
  }).join("");

  chartPoints = raw.map((item, idx) => {
    const x = raw.length === 1 ? padX + usableW / 2 : padX + (idx / (raw.length - 1)) * usableW;
    const y = padTop + usableH - (item.val / maxVal) * usableH;
    return { x, y, val: item.val, label: item.label, unit };
  });

  if (chartMode === "activity") {
    const bw = Math.max(6, Math.min(18, usableW / Math.max(8, chartPoints.length * 1.8)));
    barsG.innerHTML = chartPoints.map((p, idx) => {
      const bh = Math.max(2, padTop + usableH - p.y);
      return `<rect class="chart-bar" data-idx="${idx}" x="${(p.x - bw / 2).toFixed(1)}" y="${(padTop + usableH - bh).toFixed(1)}" width="${bw.toFixed(1)}" height="${bh.toFixed(1)}" rx="4" />`;
    }).join("");
  } else {
    barsG.innerHTML = "";
  }

  const d = catmullRomPath(chartPoints);
  line.setAttribute("d", d);
  area.setAttribute("d", `${d} L${chartPoints[chartPoints.length - 1].x.toFixed(1)},${(padTop + usableH).toFixed(1)} L${chartPoints[0].x.toFixed(1)},${(padTop + usableH).toFixed(1)} Z`);
}

function initChartHover() {
  const stage = $("#chart-stage");
  const tip = $("#chart-tooltip");
  const cross = $("#chart-crosshair");
  const dot = $("#chart-hover-dot");
  const ring = $("#chart-hover-ring");
  if (!stage) return;

  function updateHover(clientX) {
    if (!chartPoints.length) return;
    const r = stage.getBoundingClientRect();
    const relX = ((clientX - r.left) / Math.max(1, r.width)) * 600;
    let best = chartPoints[0];
    let bestIdx = 0;
    let minDist = Infinity;
    chartPoints.forEach((p, idx) => {
      const dist = Math.abs(p.x - relX);
      if (dist < minDist) {
        minDist = dist;
        best = p;
        bestIdx = idx;
      }
    });
    cross.setAttribute("x1", best.x.toFixed(1));
    cross.setAttribute("x2", best.x.toFixed(1));
    cross.classList.remove("hidden");
    dot.setAttribute("cx", best.x.toFixed(1));
    dot.setAttribute("cy", best.y.toFixed(1));
    dot.classList.remove("hidden");
    ring.setAttribute("cx", best.x.toFixed(1));
    ring.setAttribute("cy", best.y.toFixed(1));
    ring.classList.remove("hidden");

    $$(".chart-bar").forEach((b, i) => b.classList.toggle("active", i === bestIdx));
    tip.textContent = `${best.label} · ${best.val} ${best.unit}`;
    tip.classList.remove("hidden");
  }

  stage.addEventListener("pointermove", (e) => updateHover(e.clientX));
  stage.addEventListener("pointerleave", () => {
    cross.classList.add("hidden");
    dot.classList.add("hidden");
    ring.classList.add("hidden");
    tip.classList.add("hidden");
    $$(".chart-bar").forEach((b) => b.classList.remove("active"));
  });
}

// ── 7. Auth Orbital Wireframe Canvas ──────────────────────
function initOrbitalCanvas() {
  const canvas = $("#globe-canvas");
  if (!canvas || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const ctx = canvas.getContext("2d");
  let rot = 0;

  function resize() {
    canvas.width = canvas.offsetWidth * devicePixelRatio;
    canvas.height = canvas.offsetHeight * devicePixelRatio;
    ctx.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0);
  }
  resize();
  window.addEventListener("resize", resize);

  function frame() {
    if ($("#auth-gate").classList.contains("hidden")) return;
    const w = canvas.offsetWidth;
    const h = canvas.offsetHeight;
    ctx.clearRect(0, 0, w, h);

    const cx = w * 0.54;
    const cy = h * 0.34;
    const r = Math.min(w, h) * 0.25;
    ctx.strokeStyle = "rgba(212, 168, 83, 0.18)";
    ctx.lineWidth = 1.15;

    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, Math.PI * 2);
    ctx.stroke();

    for (let i = 0; i < 6; i++) {
      const a = rot + (i * Math.PI) / 6;
      const rx = Math.abs(Math.cos(a)) * r;
      ctx.beginPath();
      ctx.ellipse(cx, cy, Math.max(2, rx), r, 0, 0, Math.PI * 2);
      ctx.stroke();
    }
    for (let j = -2; j <= 2; j++) {
      const y = cy + (j * r) / 3;
      const half = Math.sqrt(Math.max(0, r * r - (j * r / 3) ** 2));
      ctx.beginPath();
      ctx.ellipse(cx, y, half, half * 0.16, 0, 0, Math.PI * 2);
      ctx.stroke();
    }
    rot += 0.0028;
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
}

// ── 8. Auth Boot ──────────────────────────────────────────
async function bootWorkspace() {
  $("#auth-gate").classList.add("hidden");
  $("#workspace").classList.remove("hidden");
  initLiquidGlassDock();
  initAllSlidingSegs();
  connectWS();
  await loadOverview();
  requestAnimationFrame(() => {
    syncDockIndicator();
    initAllSlidingSegs();
    animateViewStagger($("#view-overview"));
  });
}

async function checkSession() {
  initShapeMorph();
  initSpotlightCards();
  initChartHover();
  const me = await api("/api/v1/auth/me");
  if (!me.authenticated) {
    $("#auth-gate").classList.remove("hidden");
    $("#workspace").classList.add("hidden");
    initOrbitalCanvas();
    return;
  }
  CSRF = me.csrf;
  await bootWorkspace();
}

$("#toggle-token-vis")?.addEventListener("click", () => {
  const inp = $("#token-input");
  const show = inp.type === "password";
  inp.type = show ? "text" : "password";
  $("#toggle-token-vis").textContent = show ? "Hide" : "Show";
});

$("#login-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const errEl = $("#login-error");
  errEl.classList.add("hidden");
  const btn = $("#login-submit");
  btn.disabled = true;
  try {
    const res = await api("/api/v1/auth/login", {
      method: "POST",
      body: { token: $("#token-input").value, remember: $("#remember-input").checked },
    });
    CSRF = res.csrf;
    $("#token-input").value = "";
    await bootWorkspace();
  } catch (err) {
    errEl.textContent = err.message;
    errEl.classList.remove("hidden");
  } finally {
    btn.disabled = false;
  }
});

$("#btn-logout")?.addEventListener("click", async () => {
  await api("/api/v1/auth/logout", { method: "POST" });
  WS?.close();
  location.reload();
});

// ── 9. Spoofer Live Telemetry Renderer ────────────────────
function renderSpooferTelemetry() {
  const s = spooferState;
  const wrap = $("#spoofer-bar-wrap");
  const statusChip = $("#spoofer-status");
  if (!statusChip) return;

  $("#spoof-stat-total").textContent = `${s.completed_total || 0} titles`;
  const ovTotal = $("#ov-spoof-total");
  if (ovTotal) ovTotal.textContent = `${s.completed_total || 0}`;

  if (s.running) {
    wrap?.classList.remove("hidden");
    const elapsedLive = s.started_client_ms
      ? Math.max(s.elapsed_s, Math.floor((Date.now() - s.started_client_ms) / 1000))
      : s.elapsed_s;
    const pct = Math.min(100, Math.round((s.current / Math.max(1, s.total)) * 100));
    statusChip.textContent = `Running · ${pct}%`;
    $("#spoofer-bar").style.width = `${pct}%`;
    $("#spoof-stat-game").textContent = s.app_id ? `${s.game} (${s.app_id})` : (s.game || "Syncing...");
    $("#spoof-stat-progress").textContent = `${s.current} / ${s.total} (${pct}%)`;
    $("#spoof-stat-time").textContent = `${fmtMMSS(elapsedLive)} / ${fmtMMSS(s.remaining_s)}`;
  } else {
    statusChip.textContent = s.completed_total > 0 ? "Standby · Ready" : "Standby";
    $("#spoof-stat-game").textContent = "—";
    $("#spoof-stat-progress").textContent = "0 / 0 (0%)";
    $("#spoof-stat-time").textContent = "00:00 / 00:00";
    wrap?.classList.add("hidden");
  }
}

function startSpooferTicker() {
  if (spooferTickTimer) return;
  spooferTickTimer = setInterval(() => {
    if (!spooferState.running) {
      clearInterval(spooferTickTimer);
      spooferTickTimer = 0;
      return;
    }
    if (spooferState.remaining_s > 0) spooferState.remaining_s -= 1;
    renderSpooferTelemetry();
  }, 1000);
}

// ── 10. WebSocket Push Hub ────────────────────────────────
function connectWS() {
  if (WS && WS.readyState <= 1) return;
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  WS = new WebSocket(`${proto}//${location.host}/ws`);

  WS.onclose = () => {
    setTimeout(() => {
      if (!$("#workspace").classList.contains("hidden")) connectWS();
    }, 3000);
  };
  WS.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.type === "init") {
      $("#log-stream").innerHTML = "";
      (msg.data.logs || []).forEach(appendLogLine);
    } else if (msg.type === "log") {
      appendLogLine(msg.data);
    } else if (msg.type === "telemetry") {
      updateTelemetry(msg.data);
    } else if (msg.type === "toggles") {
      applyToggles(msg.data);
    } else if (msg.type === "job") {
      handleJobProgress(msg.data);
    } else if (msg.type === "dm_message") {
      handleLiveDMMessage(msg.data);
    }
  };
}

function appendLogLine(entry) {
  const root = $("#log-stream");
  if (!root) return;
  const row = document.createElement("div");
  row.className = "log-line";
  row.innerHTML = `<span class="log-ts">${esc(entry.ts)}</span><span class="log-lvl ${esc(entry.level)}">${esc(entry.level)}</span><span>${esc(entry.message)}</span>`;
  root.appendChild(row);
  while (root.children.length > 90) root.firstChild.remove();
  root.scrollTop = root.scrollHeight;
}

function updateTelemetry(t) {
  $("#m-latency").textContent = `${t.latency_ms} ms`;
  $("#m-uptime").textContent = fmtUptime(t.uptime_s);
  $("#m-reach").textContent = `${t.guilds} / ${t.friends}`;
  latHistory.push(Number(t.latency_ms) || 0);
  if (latHistory.length > 30) latHistory.shift();
  if (chartMode === "ping") drawMainChart();
}

function handleJobProgress(d) {
  if (d.job === "spoofer") {
    if (d.done) {
      spooferState.running = false;
      spooferState.completed_total = d.completed_total ?? spooferState.completed_total;
      $("#spoofer-bar").style.width = "100%";
      $("#spoofer-status").textContent = d.cancelled ? "Cancelled" : "Done";
      toast(d.error ? `Spoofer error: ${d.error}` : (d.cancelled ? "Game spoofer stopped" : `Spoofer finished (${fmtMMSS(d.elapsed_s)})`));
      setTimeout(() => renderSpooferTelemetry(), 1200);
    } else {
      spooferState.running = true;
      spooferState.current = d.current;
      spooferState.total = d.total;
      spooferState.game = d.game;
      spooferState.app_id = d.app_id || "";
      spooferState.elapsed_s = d.elapsed_s || 0;
      spooferState.remaining_s = d.remaining_s || 0;
      spooferState.completed_total = d.completed_total ?? spooferState.completed_total;
      spooferState.started_client_ms = Date.now() - (spooferState.elapsed_s * 1000);
      renderSpooferTelemetry();
      startSpooferTicker();
    }
  } else if (d.job === "deletedm") {
    toast(d.done ? `DM cleanup done (${d.deleted})` : `Deleted ${d.deleted}...`);
  } else if (d.job === "vanity" && d.dropped) {
    toast(`Vanity dropped: ${d.code} — ${d.note}`);
    $("#vanity-badge").textContent = `Dropped: ${d.code}`;
  } else if (d.job === "quests") {
    renderQuestsState(d);
  }
}

function applyToggles(toggles) {
  $$(".m3-switch[data-toggle]").forEach((btn) => {
    btn.setAttribute("aria-pressed", String(Boolean(toggles[btn.dataset.toggle])));
  });
  if (toggles.vanity_target) $("#vanity-badge").textContent = `Watching: ${toggles.vanity_target}`;
}

// ── 11. Config Hydration (Online Mode, RPC, Spoofer, Profile) ──
function hydratePresenceConfig(pc, sp) {
  const mode = pc?.online_status || "online";
  const kind = pc?.activity_kind || "globe";
  const house = pc?.hypesquad_house || "leave";

  setSegActive("#status-mode-seg", "statusMode", mode);
  $("#presence-live-badge").textContent = mode.toUpperCase();

  selectedActivityKind = kind === "clear" ? "globe" : kind;
  setSegActive("#activity-kind-seg", "actKind", kind === "clear" ? null : kind);
  $("#rpc-live-badge").textContent = kind === "clear"
    ? "Cleared"
    : (kind === "globe" ? "GLOBE RPC" : (pc?.activity_title ? `${kind}: ${pc.activity_title}` : kind.toUpperCase()));

  const prevEl = $("#rpc-live-preview");
  if (prevEl) {
    const liveActs = pc?.live_activities || [];
    if (liveActs.length) {
      prevEl.textContent = "Live on Discord: " + liveActs.map((a) => `${a.type}: ${a.name}${a.detail ? ` (${a.detail})` : ""}`).join(" · ");
    } else if (kind === "globe") {
      prevEl.textContent = "Active: Official Globe Rich Presence · Watching Globe (Try Globe! / Add Friend)";
    } else if (kind === "clear") {
      prevEl.textContent = "Active: No Rich Presence set";
    } else {
      prevEl.textContent = `Active: ${kind.toUpperCase()} — ${pc?.activity_title || "—"}`;
    }
  }

  if ($("#ov-presence-summary")) {
    const rpcLabel = kind === "clear" ? "No RPC" : (kind === "globe" ? "Globe RPC" : `${kind}: ${pc.activity_title || "—"}`);
    $("#ov-presence-summary").textContent = `${mode} · ${rpcLabel}`;
  }

  setSegActive("#hypesquad-seg", "house", house);
  if ($("#act-title")) $("#act-title").value = kind === "clear" ? "" : (pc?.activity_title || (kind === "globe" ? "Globe" : ""));
  if ($("#act-extra")) $("#act-extra").value = pc?.activity_extra || "";
  if ($("#cs-input")) $("#cs-input").value = pc?.custom_status_text || "";
  if ($("#bio-input") && pc?.bio_text) $("#bio-input").value = pc.bio_text;
  if ($("#rotate-interval") && pc?.rotate_interval) $("#rotate-interval").value = pc.rotate_interval;
  if ($("#rotate-slides") && Array.isArray(pc?.rotate_slides)) $("#rotate-slides").value = pc.rotate_slides.join("\n");

  if (sp) {
    spooferState = {
      running: Boolean(sp.running),
      current: sp.current || 0,
      total: sp.total || 0,
      game: sp.game || "",
      app_id: sp.app_id || "",
      elapsed_s: sp.elapsed_s || 0,
      remaining_s: sp.running ? Math.max(0, Math.round((sp.total - sp.current) * (sp.interval || 6))) : 0,
      completed_total: sp.completed_total || 0,
      started_client_ms: sp.running ? Date.now() - ((sp.elapsed_s || 0) * 1000) : 0,
    };
    renderSpooferTelemetry();
    if (spooferState.running) startSpooferTicker();
  }
}

// ── 12. Navigation: 4-Button Dock + Slide-Out Sidebar ─────
const VIEW_TITLES = {
  overview: "Overview",
  presence: "Presence & Games",
  analytics: "Insights & Traffic",
  quests: "Orb Quests",
  intel: "Intel & User Lookup",
  servers: "Servers & Voice",
  dms: "DMs & Live Chat",
  settings: "Settings & Accounts",
};

function switchView(name, focusSelector = null) {
  toggleSidebar(false);
  $$(".dock-item").forEach((b) => b.classList.toggle("active", b.dataset.view === name));
  $$(".sidebar-link").forEach((b) => b.classList.toggle("active", b.dataset.view === name && !b.dataset.focus));
  $$(".view").forEach((v) => v.classList.toggle("active", v.id === `view-${name}`));
  $("#view-title").textContent = VIEW_TITLES[name] || name;
  syncDockIndicator();

  const target = $(`#view-${name}`);
  animateViewStagger(target);
  requestAnimationFrame(() => {
    initAllSlidingSegs();
    syncDockIndicator();
  });

  if (name === "analytics") loadAnalyticsView();
  if (name === "quests") loadQuestsView(false);
  if (name === "intel") loadIntel();
  if (name === "servers") loadGuilds();
  if (name === "dms") loadDMs();
  if (name === "settings") {
    loadAccounts();
    loadSchedules();
  }
  if (focusSelector) {
    setTimeout(() => {
      const el = $(focusSelector);
      el?.scrollIntoView({ behavior: "smooth", block: "center" });
      el?.focus?.();
    }, 240);
  }
}

$$(".dock-item").forEach((b) => b.addEventListener("click", () => switchView(b.dataset.view)));
$$(".sidebar-link").forEach((b) => b.addEventListener("click", () => switchView(b.dataset.view, b.dataset.focus || null)));

window.addEventListener("resize", () => {
  syncDockIndicator();
  initAllSlidingSegs();
});

// ── 13. Overview, Analytics & Switches ────────────────────
async function loadOverview() {
  const [data, an] = await Promise.all([
    api("/api/v1/overview"),
    api("/api/v1/analytics").catch(() => ({ hourly: [], stats: {} })),
  ]);

  const dispName = data.account.global_name || data.account.username;
  $("#acct-name").textContent = dispName;
  $("#pop-global").textContent = dispName;
  $("#pop-username").textContent = `@${data.account.username}`;
  if (data.account.avatar) {
    $("#acct-avatar").src = data.account.avatar;
    $("#pop-avatar").src = data.account.avatar;
  }
  if ($("#settings-token-masked")) $("#settings-token-masked").textContent = data.account.token_masked;

  $("#prefix-input").value = data.account.prefix;
  if ($("#ov-prefix-badge")) $("#ov-prefix-badge").textContent = data.account.prefix;
  if ($("#afk-reason-input")) $("#afk-reason-input").value = data.toggles.afk_reason || "";

  if ($("#sidebar-cogs")) {
    $("#sidebar-cogs").innerHTML = (data.runtime.modules || [])
      .map((m) => `<span class="mini-tag">${esc(m)}</span>`)
      .join("");
  }

  const todayMsgs = an.stats?.global_today ?? 0;
  $("#m-db").textContent = `${todayMsgs} / ${data.runtime.db_size_kb} KB`;
  hourlyActivity = an.hourly || [];
  const totalHourly = hourlyActivity.reduce((acc, x) => acc + (Number(x.count) || 0), 0);
  if (totalHourly === 0 && chartMode === "activity") {
    chartMode = "ping";
    setSegActive("#chart-mode-seg", "chartMode", "ping");
  }

  updateTelemetry({
    latency_ms: data.runtime.latency_ms,
    uptime_s: data.runtime.uptime_s,
    guilds: data.runtime.guilds_count,
    friends: data.runtime.friends_count,
  });
  drawMainChart();
  applyToggles(data.toggles);
  hydratePresenceConfig(data.presence_config, data.spoofer);

  $("#log-stream").innerHTML = "";
  (data.logs || []).forEach(appendLogLine);
}

$$("#chart-mode-seg button").forEach((b) => {
  b.addEventListener("click", () => {
    chartMode = b.dataset.chartMode;
    drawMainChart();
  });
});

$$(".m3-switch[data-toggle]").forEach((btn) => {
  btn.addEventListener("click", async () => {
    const key = btn.dataset.toggle;
    const next = btn.getAttribute("aria-pressed") !== "true";
    try {
      const res = await api("/api/v1/toggles", { method: "POST", body: { key, value: next } });
      applyToggles(res.toggles);
      toast(`${key} ${next ? "on" : "off"}`);
    } catch (err) {
      toast(err.message);
    }
  });
});

$("#btn-save-prefix")?.addEventListener("click", async () => {
  const val = $("#prefix-input").value.trim();
  if (!val) return;
  await api("/api/v1/toggles", { method: "POST", body: { key: "prefix", value: val } });
  if ($("#ov-prefix-badge")) $("#ov-prefix-badge").textContent = val;
  toast(`Prefix saved: ${val}`);
});

$("#btn-save-afk-reason")?.addEventListener("click", async () => {
  const reason = $("#afk-reason-input").value.trim();
  const isAfk = $("#switchboard [data-toggle='afk']")?.getAttribute("aria-pressed") === "true";
  const res = await api("/api/v1/toggles", { method: "POST", body: { key: "afk", value: isAfk, reason } });
  applyToggles(res.toggles);
  toast("AFK message updated");
});

// ── 14. Multi-Account Switcher & Settings Token Control ───
async function loadAccounts() {
  try {
    const res = await api("/api/v1/accounts");
    const accounts = res.accounts || [];

    const popList = $("#pop-accounts-list");
    if (popList) {
      popList.innerHTML = accounts.length
        ? accounts.map((a) => `
          <div class="pop-acct-row">
            <div class="pop-acct-info">
              <img class="avatar" src="${esc(a.avatar || "")}" alt="" />
              <div style="min-width:0;">
                <div class="pop-acct-name">${esc(a.global_name || a.username)}</div>
                <div class="muted mono" style="font-size:0.7rem;">${esc(a.masked)}</div>
              </div>
            </div>
            ${a.active
              ? `<span class="gold-chip mono">Active</span>`
              : `<button type="button" class="btn-expressive sm" data-switch-acct="${esc(a.id)}">Switch</button>`}
          </div>`).join("")
        : `<div class="muted">Active session stored. Add another token below.</div>`;
    }

    const setList = $("#settings-accounts-list");
    if (setList) {
      setList.innerHTML = accounts.length
        ? accounts.map((a) => `
          <div class="data-row">
            <div class="pop-acct-info">
              <img class="avatar" src="${esc(a.avatar || "")}" alt="" />
              <div class="data-main">
                <div class="data-title">${esc(a.global_name || a.username)} <span class="muted mono">@${esc(a.username)}</span></div>
                <div class="muted mono">${esc(a.masked)} · ID ${esc(a.id)}</div>
              </div>
            </div>
            <div class="inline-actions">
              ${a.active
                ? `<span class="gold-chip mono">Active</span>`
                : `<button type="button" class="btn-expressive sm" data-switch-acct="${esc(a.id)}">Switch</button>
                   <button type="button" class="btn-danger-tonal sm" data-rm-acct="${esc(a.id)}">Remove</button>`}
            </div>
          </div>`).join("")
        : `<div class="muted">No saved accounts yet.</div>`;
    }

    $$("[data-switch-acct]").forEach((btn) => btn.addEventListener("click", async () => {
      const aid = btn.dataset.switchAcct;
      if (!confirm("Switch active bot session to this account and restart Globe?")) return;
      try {
        await api("/api/v1/accounts/switch", { method: "POST", body: { account_id: aid } });
        toast("Switching account — restarting Globe...");
        setTimeout(() => location.reload(), 3200);
      } catch (err) {
        toast(err.message);
      }
    }));

    $$("[data-rm-acct]").forEach((btn) => btn.addEventListener("click", async () => {
      try {
        await api(`/api/v1/accounts/${btn.dataset.rmAcct}`, { method: "DELETE" });
        toast("Account removed from vault");
        loadAccounts();
      } catch (err) {
        toast(err.message);
      }
    }));
  } catch (err) {
    toast(err.message);
  }
}

async function addAccountToken(rawToken, inputEl, afterCb) {
  const tok = rawToken.trim();
  if (!tok) return toast("Paste a Discord token");
  try {
    await api("/api/v1/accounts", { method: "POST", body: { token: tok } });
    if (inputEl) inputEl.value = "";
    toast("Account verified and added to vault");
    await loadAccounts();
    if (afterCb) afterCb();
  } catch (err) {
    toast(err.message);
  }
}

$("#btn-pop-save-acct")?.addEventListener("click", () => {
  addAccountToken($("#pop-add-token").value, $("#pop-add-token"), () => $("#pop-add-form")?.classList.add("hidden"));
});
$("#btn-settings-add-acct")?.addEventListener("click", () => {
  addAccountToken($("#settings-add-token").value, $("#settings-add-token"));
});
$("#btn-settings-token-save")?.addEventListener("click", async () => {
  const tok = $("#settings-active-token").value.trim();
  if (!tok) return toast("Paste a replacement Discord token");
  if (!confirm("Replace active Discord token and restart Globe onto the new session?")) return;
  try {
    const res = await api("/api/v1/settings/token", { method: "POST", body: { token: tok } });
    toast(`Token updated (${res.username}) — restarting...`);
    $("#settings-active-token").value = "";
    setTimeout(() => location.reload(), 3500);
  } catch (err) {
    toast(err.message);
  }
});

// ── 15. Presence Studio & Spoofer ─────────────────────────
$$("#status-mode-seg button").forEach((b) => {
  b.addEventListener("click", async () => {
    await api("/api/v1/presence/status", { method: "POST", body: { status: b.dataset.statusMode } });
    $("#presence-live-badge").textContent = b.dataset.statusMode.toUpperCase();
    toast(`Status: ${b.dataset.statusMode}`);
  });
});

$$("#activity-kind-seg button").forEach((b) => {
  b.addEventListener("click", () => {
    selectedActivityKind = b.dataset.actKind;
  });
});

$("#btn-act-apply")?.addEventListener("click", async () => {
  const title = $("#act-title").value.trim();
  const extra = $("#act-extra").value.trim();
  const body = { kind: selectedActivityKind, title };
  if (selectedActivityKind === "globe") body.elapsed = extra;
  else if (selectedActivityKind === "streaming") body.url = extra;
  await api("/api/v1/presence/activity", { method: "POST", body });
  $("#rpc-live-badge").textContent = selectedActivityKind === "globe" ? "GLOBE" : `${selectedActivityKind}: ${title}`;
  toast(`Activity updated (${selectedActivityKind})`);
});

$("#btn-act-clear")?.addEventListener("click", async () => {
  await api("/api/v1/presence/activity", { method: "POST", body: { kind: "clear" } });
  setSegActive("#activity-kind-seg", "actKind", null);
  $("#rpc-live-badge").textContent = "Cleared";
  toast("Activity cleared");
});

$("#btn-cs-apply")?.addEventListener("click", async () => {
  await api("/api/v1/presence/custom", { method: "POST", body: { text: $("#cs-input").value } });
  toast("Custom status updated");
});

$("#btn-bio-apply")?.addEventListener("click", async () => {
  await api("/api/v1/presence/bio", { method: "POST", body: { text: $("#bio-input").value } });
  toast("Bio saved");
});

$$("#hypesquad-seg button").forEach((b) => {
  b.addEventListener("click", async () => {
    await api("/api/v1/presence/hypesquad", { method: "POST", body: { house: b.dataset.house } });
    toast(`HypeSquad: ${b.dataset.house}`);
  });
});

$("#btn-rotate-start")?.addEventListener("click", async () => {
  const slides = $("#rotate-slides").value.split("\n").map((s) => s.trim()).filter(Boolean);
  await api("/api/v1/presence/rotate", {
    method: "POST",
    body: { enabled: true, interval: Number($("#rotate-interval").value), slides },
  });
  toast("Rotator started");
});

$("#btn-rotate-stop")?.addEventListener("click", async () => {
  await api("/api/v1/presence/rotate", { method: "POST", body: { enabled: false } });
  toast("Rotator stopped");
});

$("#btn-spoof-start")?.addEventListener("click", async () => {
  const count = Number($("#spoof-count").value);
  const interval = Number($("#spoof-interval").value);
  await api("/api/v1/presence/spoofer", {
    method: "POST",
    body: { action: "start", count, interval },
  });
  spooferState.running = true;
  spooferState.total = count;
  spooferState.current = 0;
  spooferState.game = "Fetching Discord catalog...";
  spooferState.started_client_ms = Date.now();
  spooferState.remaining_s = Math.round(count * interval);
  renderSpooferTelemetry();
  startSpooferTicker();
  toast("Game badge spoofer started");
});

$("#btn-spoof-stop")?.addEventListener("click", async () => {
  await api("/api/v1/presence/spoofer", { method: "POST", body: { action: "stop" } });
  toast("Stopping spoofer");
});

// ── 16. Intel, User Dossier, OSINT, Encoder & Vanity ──────
function renderUserDossier(res) {
  $("#dossier-status-chip").textContent = res.status.toUpperCase();
  const badgesHtml = res.badges?.length
    ? res.badges.map((b) => `<span class="mini-tag gold">${esc(b)}</span>`).join("")
    : `<span class="mini-tag">Standard Account</span>`;
  const connHtml = res.connected_accounts?.length
    ? `<div class="role-chip-row">${res.connected_accounts.map((c) => `<span class="mini-tag">${esc(c.type)}: ${esc(c.name)}</span>`).join("")}</div>`
    : "";
  const actHtml = res.activities?.length
    ? res.activities.map((a) => `<div class="muted">${esc(a.type)}: ${esc(a.name)} ${a.detail ? `(${esc(a.detail)})` : ""}</div>`).join("")
    : `<div class="muted">No active rich activity.</div>`;
  const mutualHtml = res.mutuals?.length
    ? res.mutuals.map((m) => `
      <div class="mutual-row">
        <div class="data-title">${esc(m.guild)}</div>
        <div class="muted mono">Top: ${esc(m.top_role)} · Joined ${esc(m.joined)}${m.nick ? ` · Nick: ${esc(m.nick)}` : ""}${m.boosting ? ` · Boost ${esc(m.boosting)}` : ""}</div>
        ${m.roles?.length ? `<div class="role-chip-row">${m.roles.map((r) => `<span class="mini-tag">${esc(r)}</span>`).join("")}</div>` : ""}
      </div>`).join("")
    : `<div class="muted">No mutual servers found.</div>`;

  $("#profile-output").innerHTML = `
    <div class="dossier-layout">
      <div class="dossier-main">
        ${res.banner ? `<div class="dossier-banner" style="background-image:url('${esc(res.banner)}')"></div>` : ""}
        <div class="dossier-id-row">
          <img class="dossier-avatar" src="${esc(res.avatar)}" alt="" />
          <div class="dossier-names">
            <div class="dossier-global">${esc(res.global_name)} ${res.pronouns ? `<span class="muted">(${esc(res.pronouns)})</span>` : ""}</div>
            <div class="muted mono">@${esc(res.username)} · ${esc(res.user_id)}</div>
            <div class="role-chip-row">${badgesHtml}</div>
          </div>
        </div>
        ${res.bio ? `<div class="dossier-bio">${esc(res.bio)}</div>` : ""}
        <div class="dossier-facts">
          <div class="fact-cell"><div class="fact-label">Account Created</div><div class="fact-val mono">${esc(res.created_at)} (${res.age_days}d)</div></div>
          <div class="fact-cell"><div class="fact-label">Type / Nitro</div><div class="fact-val">${res.is_bot ? "Bot" : "Human"}${res.nitro_since ? ` · Nitro (${esc(res.nitro_since)})` : ""}</div></div>
          <div class="fact-cell"><div class="fact-label">Devices</div><div class="fact-val">${esc(res.platforms?.join(", ") || "Offline")}</div></div>
          <div class="fact-cell"><div class="fact-label">Messages Logged</div><div class="fact-val mono">${res.messages_global ?? 0} total (${res.messages_today ?? 0} today)</div></div>
        </div>
        ${connHtml}
      </div>

      <aside class="dossier-corner">
        <div class="corner-head">
          <span>Presence &amp; Mutuals (${res.mutuals?.length ?? 0})</span>
          <span class="mono">${esc(res.status)}</span>
        </div>
        ${actHtml}
        ${res.voice ? `<div class="mini-tag gold">VC: ${esc(res.voice)}</div>` : ""}
        <div class="divider"></div>
        <div class="data-list" style="max-height:240px;">
          ${mutualHtml}
        </div>
      </aside>
    </div>`;
}

async function runUserLookup(uid) {
  if (!uid) return toast("Enter a Discord User ID");
  $("#dossier-status-chip").textContent = "Loading";
  try {
    const res = await api("/api/v1/intel/user-profile", { method: "POST", body: { user_id: uid } });
    renderUserDossier(res);
  } catch (err) {
    $("#dossier-status-chip").textContent = "Error";
    toast(err.message);
  }
}

async function loadIntel() {
  const [sn, rd, kw, st, vn] = await Promise.all([
    api(`/api/v1/intel/snipes?q=${encodeURIComponent($("#snipe-search").value.trim())}`),
    api("/api/v1/intel/radar"),
    api("/api/v1/intel/keywords"),
    api("/api/v1/intel/stalk"),
    api("/api/v1/intel/vanity"),
  ]);

  $("#snipes-list").innerHTML = sn.snipes.length
    ? sn.snipes.map((s) => `<div class="data-row"><div class="data-main"><div class="data-title">${esc(s.author_name)}</div><div class="muted">${esc(s.content)}</div></div></div>`).join("")
    : `<div class="muted">No deleted messages yet.</div>`;

  $("#radar-list").innerHTML = rd.radar.length
    ? rd.radar.map((r) => `<div class="data-row"><div class="data-main"><div class="data-title">${esc(r.author)} · ${esc(r.where)}</div><div class="muted">${esc(r.content)}</div></div></div>`).join("")
    : `<div class="muted">No ghost-pings yet.</div>`;

  $("#kw-list").innerHTML = kw.keywords.map((k) => `<span class="kw-item">${esc(k)}<button data-rm-kw="${esc(k)}">×</button></span>`).join("");
  $$("[data-rm-kw]").forEach((b) => b.addEventListener("click", async () => {
    await api("/api/v1/intel/keywords", { method: "POST", body: { action: "remove", phrase: b.dataset.rmKw } });
    loadIntel();
  }));

  $("#stalk-logs").innerHTML = st.logs.length
    ? st.logs.map((l) => `<div class="data-row"><div class="data-main"><div class="data-title">${esc(l.user)}</div><div class="muted">${esc(l.detail)}</div></div></div>`).join("")
    : `<div class="muted">Tracking ${st.targets.length} user(s).</div>`;

  $("#vanity-badge").textContent = vn.running ? `Watching: ${vn.target}` : "Standby";
}

$("#btn-profile-user")?.addEventListener("click", () => runUserLookup($("#stalk-uid").value.trim()));
$("#btn-profile-self")?.addEventListener("click", () => {
  $("#stalk-uid").value = "me";
  runUserLookup("me");
});
$("#btn-snipe-search")?.addEventListener("click", loadIntel);
$("#btn-radar-clear")?.addEventListener("click", async () => {
  await api("/api/v1/intel/radar", { method: "DELETE" });
  loadIntel();
});
$("#btn-kw-add")?.addEventListener("click", async () => {
  const phrase = $("#kw-input").value.trim();
  if (!phrase) return;
  await api("/api/v1/intel/keywords", { method: "POST", body: { action: "add", phrase } });
  $("#kw-input").value = "";
  loadIntel();
});
$("#btn-webhook-save")?.addEventListener("click", async () => {
  await api("/api/v1/intel/webhook", { method: "POST", body: { url: $("#webhook-input").value.trim() } });
  toast("Webhook saved");
});
$("#btn-vanity-start")?.addEventListener("click", async () => {
  const code = $("#vanity-code").value.trim();
  if (!code) return toast("Enter invite code");
  await api("/api/v1/intel/vanity", { method: "POST", body: { code, guild_id: $("#vanity-guild").value.trim() } });
  toast(`Watching ${code}`);
  loadIntel();
});
$("#btn-vanity-stop")?.addEventListener("click", async () => {
  await api("/api/v1/intel/vanity", { method: "DELETE" });
  toast("Vanity watch stopped");
  loadIntel();
});
$("#btn-osint-run")?.addEventListener("click", async () => {
  const kind = $("#osint-kind").value;
  const target = $("#osint-target").value.trim();
  if (!target) return toast("Enter target");
  $("#osint-output").textContent = "Looking up...";
  try {
    const res = await api("/api/v1/tools/inspect", { method: "POST", body: { kind, target } });
    $("#osint-output").textContent = JSON.stringify(res.result, null, 2);
  } catch (err) {
    $("#osint-output").textContent = `Error: ${err.message}`;
  }
});
$("#btn-enc-run")?.addEventListener("click", async () => {
  const mode = $("#enc-mode").value;
  const text = $("#enc-input").value;
  if (!text) return toast("Enter text");
  try {
    const res = await api("/api/v1/tools/encode", { method: "POST", body: { mode, text } });
    $("#enc-output").textContent = res.output;
  } catch (err) {
    $("#enc-output").textContent = `Error: ${err.message}`;
  }
});
$("#btn-stalk-add")?.addEventListener("click", async () => {
  await api("/api/v1/intel/stalk", { method: "POST", body: { action: "add", user_id: $("#stalk-uid").value.trim() } });
  toast("User added");
  loadIntel();
});
$("#btn-friends-backup")?.addEventListener("click", async () => {
  const r = await api("/api/v1/intel/friends", { method: "POST", body: { action: "backup" } });
  toast(`Saved snapshot (${r.count})`);
});
$("#btn-friends-diff")?.addEventListener("click", async () => {
  const r = await api("/api/v1/intel/friends/diff");
  if (!r.baseline_exists) {
    $("#friends-diff-out").innerHTML = `<div class="muted">No snapshot saved yet (${r.current_count} friends).</div>`;
    return;
  }
  const rem = r.removed.map((u) => `<div class="data-row"><div class="data-main"><div class="data-title">Removed: ${esc(u.username)}</div><div class="muted mono">${esc(u.id)}</div></div></div>`).join("");
  const add = r.added.map((u) => `<div class="data-row"><div class="data-main"><div class="data-title">Added: ${esc(u.username)}</div><div class="muted mono">${esc(u.id)}</div></div></div>`).join("");
  $("#friends-diff-out").innerHTML = rem || add ? rem + add : `<div class="muted">No changes since snapshot (${r.current_count} friends).</div>`;
});

// ── 17. Servers, Voice & Channel Cleanup ──────────────────
async function loadGuilds() {
  const data = await api("/api/v1/guilds");
  $("#guilds-list").innerHTML = data.guilds.map((g) => `
    <div class="guild-block">
      <div class="data-row" style="padding:0;border:none;">
        <div class="data-main">
          <div class="data-title">${esc(g.name)}</div>
          <div class="muted mono">${esc(g.id)} · ${g.member_count} members · ${g.roles_count} roles</div>
        </div>
        <div class="inline-actions">
          <button class="btn-ghost-sm" data-toggle-chs="${esc(g.id)}">Channels (${(g.voice_channels?.length || 0) + (g.text_channels?.length || 0)})</button>
          <button class="btn-tonal sm" data-audit="${esc(g.id)}">Audit</button>
          <a class="m3-pill-btn" href="/api/v1/guilds/${esc(g.id)}/backup" style="text-decoration:none;">Backup</a>
          <button class="${g.locked ? "btn-expressive sm" : "btn-danger-tonal sm"}" data-lock="${esc(g.id)}" data-state="${g.locked ? "unlock" : "lock"}">${g.locked ? "Unlock" : "Lockdown"}</button>
        </div>
      </div>
      <div id="chs-${esc(g.id)}" class="guild-channels hidden">
        ${(g.voice_channels || []).map((v) => `<button type="button" class="ch-pill" data-pick-vc="${esc(v.id)}">VC: ${esc(v.name)} (${v.members})</button>`).join("")}
        ${(g.text_channels || []).slice(0, 12).map((t) => `<button type="button" class="ch-pill" data-pick-tc="${esc(t.id)}">#${esc(t.name)}</button>`).join("")}
      </div>
    </div>`).join("") || `<div class="muted">No servers loaded.</div>`;

  $$("[data-toggle-chs]").forEach((b) => b.addEventListener("click", () => {
    $(`#chs-${b.dataset.toggleChs}`)?.classList.toggle("hidden");
  }));
  $$("[data-pick-vc]").forEach((b) => b.addEventListener("click", () => {
    $("#vc-channel-id").value = b.dataset.pickVc;
    toast("Selected Voice Channel ID");
  }));
  $$("[data-pick-tc]").forEach((b) => b.addEventListener("click", () => {
    $("#mod-ch-id").value = b.dataset.pickTc;
    $("#dispatch-channel").value = b.dataset.pickTc;
    toast("Copied Channel ID to Cleanup & Dispatch");
  }));

  $$("[data-audit]").forEach((b) => b.addEventListener("click", async () => {
    const res = await api(`/api/v1/guilds/${b.dataset.audit}/audit`);
    $("#audit-title").textContent = res.guild;
    $("#audit-output").innerHTML = `
      <div class="data-row"><div class="data-main"><div class="data-title">@everyone risks</div><div class="muted">${esc(res.everyone_risks.join(", ") || "None")}</div></div></div>
      <div class="data-row"><div class="data-main"><div class="data-title">Admin roles (${res.admin_roles.length})</div><div class="muted">${esc(res.admin_roles.join(", ") || "None")}</div></div></div>
      <div class="data-row"><div class="data-main"><div class="data-title">Open overwrites</div><div class="muted">${esc(res.exposed_channels.join(", ") || "None")}</div></div></div>`;
  }));

  $$("[data-lock]").forEach((b) => b.addEventListener("click", async () => {
    const lock = b.dataset.state === "lock";
    await api("/api/v1/guilds/lockdown", { method: "POST", body: { guild_id: b.dataset.lock, lock } });
    toast(lock ? "Locked down" : "Unlocked");
    loadGuilds();
  }));
}

$("#btn-refresh-guilds")?.addEventListener("click", loadGuilds);
$("#btn-vc-join")?.addEventListener("click", async () => {
  await api("/api/v1/voice", { method: "POST", body: { action: "join", channel_id: $("#vc-channel-id").value.trim(), mode: $("#vc-mode").value } });
  toast("Joined 24/7 voice");
});
$("#btn-vc-leave")?.addEventListener("click", async () => {
  await api("/api/v1/voice", { method: "POST", body: { action: "leave" } });
  toast("Disconnected");
});
$("#btn-vc-follow")?.addEventListener("click", async () => {
  await api("/api/v1/voice", { method: "POST", body: { action: "follow", user_id: $("#vc-follow-uid").value.trim() || "off" } });
  toast("Voice follow updated");
});

$("#btn-mod-run")?.addEventListener("click", async () => {
  const channel_id = $("#mod-ch-id").value.trim();
  const action = $("#mod-action").value;
  if (!channel_id) return toast("Channel ID required");
  try {
    const res = await api("/api/v1/guilds/cleanup", { method: "POST", body: { channel_id, action, seconds: 5 } });
    if (res.top) {
      $("#mod-output").innerHTML = res.top.map((r, i) => `<div class="data-row"><div class="data-main"><div class="data-title">#${i + 1} ${esc(r.user)}</div><div class="muted mono">${r.count} msgs</div></div></div>`).join("") || `<div class="muted">No messages found.</div>`;
    } else {
      $("#mod-output").innerHTML = `<div class="muted">${esc(res.detail)}</div>`;
    }
  } catch (err) {
    toast(err.message);
  }
});

$("#btn-mimic-set")?.addEventListener("click", async () => {
  await api("/api/v1/troll/control", { method: "POST", body: { action: "mimic", channel_id: $("#mimic-cid").value.trim(), user_id: $("#mimic-uid").value.trim() } });
  toast("Mimic updated");
});
$("#btn-treact-set")?.addEventListener("click", async () => {
  await api("/api/v1/troll/control", { method: "POST", body: { action: "react", user_id: $("#treact-uid").value.trim(), emoji: $("#treact-emoji").value.trim() } });
  toast("Auto-react target updated");
});

$("#btn-ov-open-analytics")?.addEventListener("click", () => switchView("analytics"));

// ── 18A. Insights & Traffic (Messages, Invites, Comparisons) ──
let analyticsData = null;
let analyticsMode = "compare24";
let anPoints = [];

function drawAnalyticsChart() {
  const grid = $("#an-chart-grid");
  const barsG = $("#an-chart-bars");
  const line = $("#an-chart-line");
  const yestLine = $("#an-chart-yest");
  const area = $("#an-chart-area");
  if (!grid || !line || !analyticsData) return;

  const w = 640;
  const h = 200;
  const padTop = 20;
  const padBot = 24;
  const padX = 32;
  const usableW = w - padX * 2;
  const usableH = h - padTop - padBot;

  let rows = [];
  const hasYest = analyticsMode === "compare24";
  $("#an-legend-yest-wrap")?.classList.toggle("hidden", !hasYest);

  if (analyticsMode === "compare24") {
    $("#an-legend-primary").textContent = "Today (Msgs)";
    rows = (analyticsData.hourly_comparison || []).map((r) => ({
      label: r.label,
      val: Number(r.today) || 0,
      yest: Number(r.yesterday) || 0,
      unit: "msgs",
    }));
  } else if (analyticsMode === "msgs14") {
    $("#an-legend-primary").textContent = "Daily Messages (14d)";
    rows = (analyticsData.daily_series || []).map((r) => ({
      label: r.label,
      val: Number(r.messages) || 0,
      yest: null,
      unit: "msgs",
    }));
  } else {
    $("#an-legend-primary").textContent = "Daily Invites (14d)";
    rows = (analyticsData.daily_series || []).map((r) => ({
      label: r.label,
      val: Number(r.invites) || 0,
      yest: null,
      unit: "invites",
    }));
  }

  if (!rows.length) return;
  const maxVal = Math.max(
    ...rows.map((r) => Math.max(r.val, r.yest || 0)),
    analyticsMode === "inv14" ? 5 : 10,
  );
  const yTicks = [0, Math.round(maxVal / 2), maxVal];
  grid.innerHTML = yTicks.map((tv) => {
    const y = padTop + usableH - (tv / maxVal) * usableH;
    return `<line x1="${padX}" y1="${y.toFixed(1)}" x2="${w - 8}" y2="${y.toFixed(1)}" /><text x="2" y="${(y + 3).toFixed(1)}">${tv}</text>`;
  }).join("");

  anPoints = rows.map((r, idx) => {
    const x = rows.length === 1 ? padX + usableW / 2 : padX + (idx / (rows.length - 1)) * usableW;
    const y = padTop + usableH - (r.val / maxVal) * usableH;
    const yYest = r.yest !== null ? (padTop + usableH - (r.yest / maxVal) * usableH) : null;
    return { x, y, yYest, ...r };
  });

  if (!hasYest) {
    const bw = Math.max(8, Math.min(22, usableW / Math.max(8, anPoints.length * 1.7)));
    barsG.innerHTML = anPoints.map((p, idx) => {
      const bh = Math.max(2, padTop + usableH - p.y);
      return `<rect class="chart-bar" data-an-idx="${idx}" x="${(p.x - bw / 2).toFixed(1)}" y="${(padTop + usableH - bh).toFixed(1)}" width="${bw.toFixed(1)}" height="${bh.toFixed(1)}" rx="5" />`;
    }).join("");
    yestLine.setAttribute("d", "");
  } else {
    barsG.innerHTML = "";
    const yPts = anPoints.map((p) => ({ x: p.x, y: p.yYest }));
    yestLine.setAttribute("d", catmullRomPath(yPts));
  }

  const d = catmullRomPath(anPoints);
  line.setAttribute("d", d);
  area.setAttribute("d", `${d} L${anPoints[anPoints.length - 1].x.toFixed(1)},${(padTop + usableH).toFixed(1)} L${anPoints[0].x.toFixed(1)},${(padTop + usableH).toFixed(1)} Z`);
}

function initAnalyticsChartHover() {
  const stage = $("#an-chart-stage");
  const tip = $("#an-chart-tooltip");
  const cross = $("#an-chart-cross");
  const dot = $("#an-chart-dot");
  const ring = $("#an-chart-ring");
  if (!stage || stage.dataset.boundHover) return;
  stage.dataset.boundHover = "1";

  stage.addEventListener("pointermove", (e) => {
    if (!anPoints.length) return;
    const r = stage.getBoundingClientRect();
    const relX = ((e.clientX - r.left) / Math.max(1, r.width)) * 640;
    let best = anPoints[0];
    let bestIdx = 0;
    let minD = Infinity;
    anPoints.forEach((p, idx) => {
      const d = Math.abs(p.x - relX);
      if (d < minD) { minD = d; best = p; bestIdx = idx; }
    });
    cross.setAttribute("x1", best.x.toFixed(1));
    cross.setAttribute("x2", best.x.toFixed(1));
    cross.classList.remove("hidden");
    dot.setAttribute("cx", best.x.toFixed(1));
    dot.setAttribute("cy", best.y.toFixed(1));
    dot.classList.remove("hidden");
    ring.setAttribute("cx", best.x.toFixed(1));
    ring.setAttribute("cy", best.y.toFixed(1));
    ring.classList.remove("hidden");
    $$("[data-an-idx]").forEach((b, i) => b.classList.toggle("active", i === bestIdx));
    tip.textContent = best.yest !== null
      ? `${best.label} · Today: ${best.val} | Yest: ${best.yest}`
      : `${best.label} · ${best.val} ${best.unit}`;
    tip.classList.remove("hidden");
  });

  stage.addEventListener("pointerleave", () => {
    cross.classList.add("hidden");
    dot.classList.add("hidden");
    ring.classList.add("hidden");
    tip.classList.add("hidden");
    $$("[data-an-idx]").forEach((b) => b.classList.remove("active"));
  });
}

function setDeltaPill(elId, pct) {
  const el = $(elId);
  if (!el) return;
  const v = Number(pct) || 0;
  el.classList.remove("up", "down");
  if (v > 0) {
    el.classList.add("up");
    el.textContent = `+${v}% vs yest`;
  } else if (v < 0) {
    el.classList.add("down");
    el.textContent = `${v}% vs yest`;
  } else {
    el.textContent = "0% vs yest";
  }
}

async function loadAnalyticsView() {
  initAnalyticsChartHover();
  const res = await api("/api/v1/analytics");
  analyticsData = res;
  const c = res.comparison || {};
  $("#an-msg-today").textContent = String(c.messages_today ?? 0);
  $("#an-msg-yest-sub").textContent = `Yesterday: ${c.messages_yesterday ?? 0}`;
  setDeltaPill("#an-msg-delta", c.messages_delta_pct);
  $("#an-msg-global").textContent = String(c.messages_global ?? 0);
  $("#an-dm-sub").textContent = `DMs today: ${c.dms_today ?? 0} (yest: ${c.dms_yesterday ?? 0}) · All: ${c.dms_global ?? 0}`;

  $("#an-inv-today").textContent = String(c.invites_today ?? 0);
  $("#an-inv-yest-sub").textContent = `Yesterday: ${c.invites_yesterday ?? 0}`;
  setDeltaPill("#an-inv-delta", c.invites_delta_pct);
  $("#an-inv-global").textContent = String(c.invites_global ?? 0);

  drawAnalyticsChart();

  const servers = res.top_servers || [];
  const maxSrv = Math.max(1, ...servers.map((s) => s.count));
  $("#an-top-servers").innerHTML = servers.length
    ? servers.map((s, idx) => `
      <div class="rank-item">
        <div class="rank-top">
          <div class="rank-peer">
            ${s.icon ? `<img class="avatar" src="${esc(s.icon)}" alt="" />` : `<span class="rank-avatar-fallback">${esc((s.name || "S")[0].toUpperCase())}</span>`}
            <div style="min-width:0;">
              <div class="data-title" style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">#${idx + 1} ${esc(s.name)}</div>
              <div class="muted mono">${s.today_count} today · ${s.share_pct}% share</div>
            </div>
          </div>
          <span class="gold-chip mono">${s.count} msgs</span>
        </div>
        <div class="rank-bar-track"><div class="rank-bar-fill" style="width:${Math.max(4, Math.round((s.count / maxSrv) * 100))}%"></div></div>
      </div>`).join("")
    : `<div class="muted">No server message activity logged yet.</div>`;

  const contacts = res.top_contacts || [];
  const maxCtc = Math.max(1, ...contacts.map((u) => u.total));
  $("#an-top-contacts").innerHTML = contacts.length
    ? contacts.map((u, idx) => `
      <div class="rank-item">
        <div class="rank-top">
          <div class="rank-peer">
            ${u.avatar ? `<img class="avatar" src="${esc(u.avatar)}" alt="" />` : `<span class="rank-avatar-fallback">${esc((u.name || "U")[0].toUpperCase())}</span>`}
            <div style="min-width:0;">
              <div class="data-title" style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">#${idx + 1} ${esc(u.name)}</div>
              <div class="muted mono">Sent ${u.sent} · Recv ${u.received} · ${u.today_count} today</div>
            </div>
          </div>
          <div class="inline-actions">
            <span class="mini-tag gold mono">${u.total}</span>
            <button type="button" class="btn-ghost-sm" data-open-dm-id="${esc(u.channel_id)}" data-open-dm-name="${esc(u.name)}" data-open-dm-uid="${esc(u.user_id)}" data-open-dm-av="${esc(u.avatar)}">Chat →</button>
          </div>
        </div>
        <div class="rank-bar-track"><div class="rank-bar-fill" style="width:${Math.max(4, Math.round((u.total / maxCtc) * 100))}%"></div></div>
      </div>`).join("")
    : `<div class="muted">No DM contact stats recorded yet.</div>`;

  $$("[data-open-dm-id]").forEach((btn) => btn.addEventListener("click", () => {
    switchView("dms");
    openDMChat({
      id: btn.dataset.openDmId,
      global_name: btn.dataset.openDmName,
      recipient: btn.dataset.openDmName,
      recipient_id: btn.dataset.openDmUid,
      avatar: btn.dataset.openDmAv,
    });
  }));

  const invs = res.recent_invites || [];
  $("#an-recent-invites").innerHTML = invs.length
    ? invs.map((iv) => `
      <div class="data-row">
        <div class="data-main">
          <div class="data-title"><span class="mini-tag gold mono">${esc(iv.kind)}</span> discord.gg/${esc(iv.code)}</div>
          <div class="muted mono">${esc(iv.guild_name)} · ${new Date(iv.timestamp * 1000).toLocaleString()}</div>
        </div>
      </div>`).join("")
    : `<div class="muted">No shared or created invites tracked yet.</div>`;
}

$$("#an-mode-seg button").forEach((b) => {
  b.addEventListener("click", () => {
    analyticsMode = b.dataset.anMode;
    drawAnalyticsChart();
  });
});
$("#btn-an-refresh")?.addEventListener("click", loadAnalyticsView);

// ── 18B. Discord Orb Quest Completor ─────────────────────
function renderQuestsState(q) {
  if (!q) return;
  $("#q-orb-balance").textContent = `${q.orb_balance ?? 0} Orbs`;
  $("#q-pending-count").textContent = String(q.pending_eligible_count ?? 0);
  $("#q-earned-stat").textContent = `+${q.completed_session_orbs ?? 0} / ${q.completed_total_orbs ?? 0}`;
  $("#q-runner-state").textContent = q.running ? "Running" : "Standby";
  $("#q-status-chip").textContent = q.running ? "Active" : "Standby";
  $("#q-status-line").textContent = q.status_line || "Ready to process pending Orb quests";

  const cfg = q.config || {};
  $("#q-cfg-orbs")?.setAttribute("aria-pressed", String(cfg.orbs_only !== false));
  $("#q-cfg-enroll")?.setAttribute("aria-pressed", String(cfg.auto_enroll !== false));
  setSegActive("#q-pace-seg", "pace", cfg.pace_mode || "stealth");
  const allowed = new Set(cfg.allowed_tasks || []);
  $$("#q-task-chips input[type=checkbox]").forEach((cb) => {
    cb.checked = allowed.size === 0 || allowed.has(cb.value);
  });

  const quests = q.quests || [];
  const orbsOnly = cfg.orbs_only !== false;
  const visible = orbsOnly ? quests.filter((it) => it.is_orbs) : quests;
  $("#quests-list").innerHTML = visible.length
    ? visible.map((it) => {
      const isRun = it.id === q.current_quest_id;
      const cls = isRun ? "quest-card is-running" : (it.completed ? "quest-card is-done" : "quest-card");
      return `
        <div class="${cls}">
          <div class="quest-top">
            <div style="min-width:0;flex:1;">
              <div class="data-title">${esc(it.name)} <span class="muted">(${esc(it.game_name)})</span></div>
              <div class="quest-meta" style="margin-top:0.25rem;">
                <span class="mini-tag gold mono">${esc(it.reward_label)}</span>
                <span class="mini-tag mono">${esc(it.task_type || "TASK")}</span>
                <span class="mini-tag">${it.completed ? "Completed" : (isRun ? "Active" : (it.enrolled ? "Enrolled" : "Pending"))}</span>
              </div>
            </div>
            <span class="mono gold-text" style="font-weight:700;">${it.pct}%</span>
          </div>
          <div class="wavy-track"><div class="wavy-fill" style="width:${it.pct}%;"></div></div>
          <div class="muted mono" style="font-size:0.74rem;">${Math.round(it.seconds_done)}s / ${it.seconds_needed}s</div>
        </div>`;
    }).join("")
    : `<div class="muted">No active ${orbsOnly ? "Orb " : ""}quests available right now.</div>`;
}

async function loadQuestsView(sync = true) {
  try {
    const res = await api(`/api/v1/quests?sync=${sync ? "1" : "0"}`);
    renderQuestsState(res);
  } catch (err) {
    toast(err.message);
  }
}

$("#q-cfg-orbs")?.addEventListener("click", () => {
  const b = $("#q-cfg-orbs");
  b.setAttribute("aria-pressed", String(b.getAttribute("aria-pressed") !== "true"));
});
$("#q-cfg-enroll")?.addEventListener("click", () => {
  const b = $("#q-cfg-enroll");
  b.setAttribute("aria-pressed", String(b.getAttribute("aria-pressed") !== "true"));
});
$("#btn-quest-cfg-save")?.addEventListener("click", async () => {
  const orbs_only = $("#q-cfg-orbs")?.getAttribute("aria-pressed") === "true";
  const auto_enroll = $("#q-cfg-enroll")?.getAttribute("aria-pressed") === "true";
  const pace_mode = $("#q-pace-seg button.active")?.dataset.pace || "stealth";
  const allowed_tasks = $$("#q-task-chips input[type=checkbox]:checked").map((cb) => cb.value);
  const res = await api("/api/v1/quests/config", {
    method: "POST",
    body: { orbs_only, auto_enroll, pace_mode, allowed_tasks },
  });
  renderQuestsState(res);
  toast("Quest configuration saved");
});
$("#btn-quest-sync")?.addEventListener("click", async () => {
  await loadQuestsView(true);
  toast("Synced live quests & Orbs balance");
});
$("#btn-quest-start")?.addEventListener("click", async () => {
  try {
    const res = await api("/api/v1/quests/start", { method: "POST" });
    renderQuestsState(res);
    toast("Orb Quest Completor started");
  } catch (err) {
    toast(err.message);
  }
});
$("#btn-quest-stop")?.addEventListener("click", async () => {
  const res = await api("/api/v1/quests/stop", { method: "POST" });
  renderQuestsState(res);
  toast("Stopping Quest Completor...");
});

// ── 18C. Interactive Side-by-Side DMs Chat, Files, Reply, Mention ──
let dmCache = [];
let activeDM = null;
let dmMessages = [];
let dmHasMore = false;
let dmReplyTarget = null;
let dmPendingFiles = [];

function renderDMConversationList() {
  const q = ($("#dm-search-input")?.value || "").trim().toLowerCase();
  const filtered = q
    ? dmCache.filter((d) => (d.global_name + " " + d.recipient + " " + d.id).toLowerCase().includes(q))
    : dmCache;
  $("#dms-list").innerHTML = filtered.length
    ? filtered.map((d) => {
      const actCls = activeDM && activeDM.id === d.id ? " active" : "";
      const av = d.avatar
        ? `<img class="avatar" src="${esc(d.avatar)}" alt="" />`
        : `<span class="rank-avatar-fallback">${esc((d.global_name || d.recipient || "D")[0].toUpperCase())}</span>`;
      return `
        <button type="button" class="dm-conv-item${actCls}" data-dm-open="${esc(d.id)}">
          ${av}
          <div class="dm-conv-meta">
            <div class="dm-conv-title">${esc(d.global_name || d.recipient)}</div>
            <div class="dm-conv-preview">${esc(d.preview || d.recipient)}</div>
          </div>
        </button>`;
    }).join("")
    : `<div class="muted" style="padding:0.5rem;">No DM conversations found.</div>`;

  $$("[data-dm-open]").forEach((btn) => btn.addEventListener("click", () => {
    const item = dmCache.find((x) => x.id === btn.dataset.dmOpen);
    if (item) openDMChat(item);
  }));
}

function renderDMReplyBanner() {
  const bar = $("#dm-reply-bar");
  if (!dmReplyTarget) {
    bar?.classList.add("hidden");
    return;
  }
  bar?.classList.remove("hidden");
  $("#dm-reply-preview").textContent = `${dmReplyTarget.author}: ${dmReplyTarget.content || "[Attachment]"}`;
}

function renderDMAttachBar() {
  const bar = $("#dm-attach-bar");
  if (!dmPendingFiles.length) {
    bar?.classList.add("hidden");
    bar.innerHTML = "";
    return;
  }
  bar?.classList.remove("hidden");
  bar.innerHTML = dmPendingFiles.map((f, idx) => `
    <span class="kw-item">${esc(f.name)} (${Math.max(1, Math.round(f.size / 1024))} KB)<button type="button" data-rm-file="${idx}">×</button></span>
  `).join("");
  $$("[data-rm-file]").forEach((b) => b.addEventListener("click", () => {
    dmPendingFiles.splice(Number(b.dataset.rmFile), 1);
    renderDMAttachBar();
  }));
}

function renderDMMessageHTML(m) {
  const av = m.avatar
    ? `<img class="avatar" src="${esc(m.avatar)}" alt="" />`
    : `<span class="rank-avatar-fallback">${esc((m.global_name || m.author || "U")[0].toUpperCase())}</span>`;
  const replyHtml = m.reply_to
    ? `<div class="dm-reply-quote">↩ ${esc(m.reply_to.author)}: ${esc(m.reply_to.content)}</div>`
    : "";
  const attHtml = (m.attachments || []).length
    ? `<div class="dm-att-grid">${m.attachments.map((a) => (
      a.is_image
        ? `<a href="${esc(a.url)}" target="_blank" rel="noopener"><img class="dm-att-img" src="${esc(a.url)}" alt="${esc(a.filename)}" /></a>`
        : `<a class="dm-att-file" href="${esc(a.url)}" target="_blank" rel="noopener">📎 ${esc(a.filename)}</a>`
    )).join("")}</div>`
    : "";
  const embHtml = (m.embeds || []).length
    ? m.embeds.map((e) => `<div class="dossier-bio" style="margin-top:0.2rem;">${e.title ? `<strong>${esc(e.title)}</strong>\n` : ""}${esc(e.description)}</div>`).join("")
    : "";

  return `
    <div class="dm-msg${m.is_self ? " self" : ""}" data-msg-id="${esc(m.id)}">
      ${av}
      <div class="dm-msg-body">
        ${replyHtml}
        <div class="dm-msg-top">
          <div>
            <span class="dm-msg-author">${esc(m.global_name || m.author)}</span>
            <span class="muted mono" style="font-size:0.72rem;margin-left:0.4rem;">${esc(m.created_at || "")}</span>
          </div>
          <div class="dm-msg-actions">
            <button type="button" class="dm-msg-act-btn" data-reply-msg="${esc(m.id)}">Reply</button>
            <button type="button" class="dm-msg-act-btn" data-mention-uid="${esc(m.author_id)}">@Mention</button>
          </div>
        </div>
        ${m.content ? `<div class="dm-msg-text">${esc(m.content)}</div>` : ""}
        ${attHtml}
        ${embHtml}
      </div>
    </div>`;
}

function bindDMMessageActions() {
  $$("[data-reply-msg]").forEach((btn) => btn.addEventListener("click", () => {
    const found = dmMessages.find((x) => x.id === btn.dataset.replyMsg);
    if (!found) return;
    dmReplyTarget = { id: found.id, author: found.global_name || found.author, content: found.content };
    renderDMReplyBanner();
    $("#dm-compose-input")?.focus();
  }));
  $$("[data-mention-uid]").forEach((btn) => btn.addEventListener("click", () => {
    const inp = $("#dm-compose-input");
    if (!inp || !btn.dataset.mentionUid) return;
    inp.value = `${inp.value}<@${btn.dataset.mentionUid}> `;
    inp.focus();
  }));
}

function renderDMThread(scrollBottom = true) {
  const container = $("#dm-chat-messages");
  const scroller = $("#dm-chat-scroll");
  if (!container) return;
  $("#dm-load-more-wrap")?.classList.toggle("hidden", !dmHasMore);
  container.innerHTML = dmMessages.length
    ? dmMessages.map(renderDMMessageHTML).join("")
    : `<div class="muted" style="padding:1.2rem 0;text-align:center;">No messages yet in this conversation.</div>`;
  bindDMMessageActions();
  if (scrollBottom && scroller) scroller.scrollTop = scroller.scrollHeight;
}

async function openDMChat(dmItem) {
  activeDM = dmItem;
  dmReplyTarget = null;
  renderDMReplyBanner();
  renderDMConversationList();

  $("#dm-peer-name").textContent = dmItem.global_name || dmItem.recipient;
  $("#dm-peer-sub").textContent = `${dmItem.recipient} · ID ${dmItem.id}`;
  const avEl = $("#dm-peer-avatar");
  if (avEl) {
    if (dmItem.avatar) {
      avEl.src = dmItem.avatar;
      avEl.classList.remove("hidden");
    } else {
      avEl.classList.add("hidden");
    }
  }
  $("#dm-peer-actions")?.classList.remove("hidden");
  $("#btn-dm-export")?.setAttribute("href", `/api/v1/dms/${encodeURIComponent(dmItem.id)}/export`);
  $("#dispatch-channel").value = dmItem.id;

  $("#dm-chat-messages").innerHTML = `<div class="muted" style="padding:1rem;text-align:center;">Loading messages...</div>`;
  try {
    const res = await api(`/api/v1/dms/${encodeURIComponent(dmItem.id)}/messages?limit=40`);
    dmMessages = res.messages || [];
    dmHasMore = Boolean(res.has_more);
    renderDMThread(true);
  } catch (err) {
    $("#dm-chat-messages").innerHTML = `<div class="muted" style="padding:1rem;text-align:center;">Could not load history: ${esc(err.message)}</div>`;
  }
}

function handleLiveDMMessage(m) {
  if (!m || !m.channel_id) return;
  const idx = dmCache.findIndex((x) => x.id === m.channel_id);
  if (idx >= 0) {
    const item = dmCache.splice(idx, 1)[0];
    item.preview = m.content || "[Attachment]";
    item.last_ms = m.ts_ms || Date.now();
    dmCache.unshift(item);
    if ($("#view-dms")?.classList.contains("active")) renderDMConversationList();
  }
  if (activeDM && activeDM.id === m.channel_id) {
    if (!dmMessages.some((x) => x.id === m.id)) {
      dmMessages.push(m);
      renderDMThread(true);
    }
  }
}

async function sendDMChat() {
  if (!activeDM) return toast("Select a DM conversation first");
  const inp = $("#dm-compose-input");
  const text = (inp?.value || "").trim();
  if (!text && !dmPendingFiles.length) return;
  const btn = $("#btn-dm-send");
  if (btn) btn.disabled = true;

  try {
    let data;
    if (dmPendingFiles.length) {
      const fd = new FormData();
      if (text) fd.append("content", text);
      if (dmReplyTarget) {
        fd.append("reply_to", dmReplyTarget.id);
        fd.append("mention_author", $("#dm-reply-ping")?.checked ? "true" : "false");
      }
      dmPendingFiles.forEach((f) => fd.append("file", f));
      const resp = await fetch(`/api/v1/dms/${encodeURIComponent(activeDM.id)}/messages`, {
        method: "POST",
        headers: CSRF ? { "X-Globe-CSRF": CSRF } : {},
        body: fd,
        credentials: "same-origin",
      });
      data = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(data.error || `HTTP ${resp.status}`);
    } else {
      data = await api(`/api/v1/dms/${encodeURIComponent(activeDM.id)}/messages`, {
        method: "POST",
        body: {
          content: text,
          reply_to: dmReplyTarget ? dmReplyTarget.id : "",
          mention_author: $("#dm-reply-ping")?.checked ?? true,
        },
      });
    }
    if (inp) inp.value = "";
    dmPendingFiles = [];
    dmReplyTarget = null;
    renderDMAttachBar();
    renderDMReplyBanner();
    if (data.message && !dmMessages.some((x) => x.id === data.message.id)) {
      dmMessages.push(data.message);
      renderDMThread(true);
    }
  } catch (err) {
    toast(err.message);
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function loadDMs() {
  const [dmRes, bmRes, autoRes] = await Promise.all([
    api("/api/v1/dms"),
    api(`/api/v1/bookmarks?tag=${encodeURIComponent($("#bm-filter").value.trim())}`),
    api("/api/v1/tools/automation"),
  ]);

  dmCache = dmRes.dms || [];
  renderDMConversationList();
  if (!activeDM && dmCache.length) {
    openDMChat(dmCache[0]);
  }

  const arRows = [];
  (autoRes.autoreact || []).forEach((x) => arRows.push(`<div class="data-row"><div class="data-main"><div class="data-title">React #${esc(x.channel_id)}</div><div class="muted">${esc(x.emojis.join(" "))}</div></div><button class="btn-ghost-sm" data-clr-react="${esc(x.channel_id)}">Clear</button></div>`));
  (autoRes.autoreply || []).forEach((x) => arRows.push(`<div class="data-row"><div class="data-main"><div class="data-title">Reply #${esc(x.channel_id)} (${x.rules.length})</div><div class="muted">${x.rules.map((r) => `${esc(r.trigger)} → ${esc(r.response)}`).join(" | ")}</div></div><button class="btn-ghost-sm" data-clr-reply="${esc(x.channel_id)}">Clear</button></div>`));
  $("#ar-rules-list").innerHTML = arRows.join("") || `<div class="muted">No active auto-reply or auto-react rules.</div>`;

  $$("[data-clr-react]").forEach((b) => b.addEventListener("click", async () => {
    await api("/api/v1/tools/automation", { method: "DELETE", body: { kind: "autoreact", channel_id: b.dataset.clrReact } });
    loadDMs();
  }));
  $$("[data-clr-reply]").forEach((b) => b.addEventListener("click", async () => {
    await api("/api/v1/tools/automation", { method: "DELETE", body: { kind: "autoreply", channel_id: b.dataset.clrReply } });
    loadDMs();
  }));

  $("#bookmarks-list").innerHTML = bmRes.bookmarks.length
    ? bmRes.bookmarks.map((bm) => `
      <div class="data-row">
        <div class="data-main">
          <div class="data-title">[${esc(bm.tag)}] ${esc(bm.author_name)}</div>
          <div class="muted">${esc(bm.content)}</div>
        </div>
        <button class="btn-ghost-sm" data-delbm="${bm.id}">Delete</button>
      </div>`).join("")
    : `<div class="muted">No saved bookmarks.</div>`;

  $$("[data-delbm]").forEach((b) => b.addEventListener("click", async () => {
    await api(`/api/v1/bookmarks/${b.dataset.delbm}`, { method: "DELETE" });
    loadDMs();
  }));
}

$("#dm-search-input")?.addEventListener("input", renderDMConversationList);
$("#btn-dm-refresh")?.addEventListener("click", loadDMs);
$("#btn-dm-mention")?.addEventListener("click", () => {
  const inp = $("#dm-compose-input");
  if (!inp || !activeDM) return;
  const tag = activeDM.recipient_id ? `<@${activeDM.recipient_id}> ` : `@${activeDM.global_name || activeDM.recipient} `;
  inp.value = `${inp.value}${tag}`;
  inp.focus();
});
$("#btn-dm-wipe")?.addEventListener("click", async () => {
  if (!activeDM) return;
  if (!confirm(`Delete all your messages in DM with ${activeDM.recipient}?`)) return;
  await api(`/api/v1/dms/${encodeURIComponent(activeDM.id)}/wipe`, { method: "POST" });
  toast("DM cleanup started");
});
$("#btn-dm-load-more")?.addEventListener("click", async () => {
  if (!activeDM || !dmMessages.length) return;
  const oldest = dmMessages[0].id;
  const scroller = $("#dm-chat-scroll");
  const prevHeight = scroller?.scrollHeight || 0;
  const res = await api(`/api/v1/dms/${encodeURIComponent(activeDM.id)}/messages?limit=40&before=${encodeURIComponent(oldest)}`);
  const older = res.messages || [];
  dmHasMore = Boolean(res.has_more);
  dmMessages = [...older, ...dmMessages];
  renderDMThread(false);
  if (scroller) scroller.scrollTop = scroller.scrollHeight - prevHeight;
});
$("#btn-dm-reply-cancel")?.addEventListener("click", () => {
  dmReplyTarget = null;
  renderDMReplyBanner();
});
$("#btn-dm-attach")?.addEventListener("click", () => $("#dm-file-input")?.click());
$("#dm-file-input")?.addEventListener("change", (e) => {
  const files = Array.from(e.target.files || []);
  dmPendingFiles.push(...files);
  e.target.value = "";
  renderDMAttachBar();
});
$("#btn-dm-send")?.addEventListener("click", sendDMChat);
$("#dm-compose-input")?.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendDMChat();
  }
});

$("#btn-ar-react")?.addEventListener("click", async () => {
  const channel_id = $("#ar-ch-id").value.trim();
  const emojis = $("#ar-emojis").value.trim().split(/\s+/).filter(Boolean);
  await api("/api/v1/tools/automation", { method: "POST", body: { kind: "autoreact", channel_id, emojis } });
  toast("Auto-react saved");
  loadDMs();
});
$("#btn-ar-add")?.addEventListener("click", async () => {
  const channel_id = $("#ar-ch-id").value.trim();
  const trigger = $("#ar-trigger").value.trim();
  const response = $("#ar-response").value.trim();
  await api("/api/v1/tools/automation", { method: "POST", body: { kind: "autoreply", channel_id, trigger, response } });
  toast("Auto-reply rule added");
  loadDMs();
});
$("#btn-dispatch-send")?.addEventListener("click", async () => {
  const channel_id = $("#dispatch-channel").value.trim();
  const content = $("#dispatch-content").value.trim();
  if (!channel_id || !content) return toast("Channel ID and message required");
  await api("/api/v1/dispatch/send", { method: "POST", body: { channel_id, content } });
  $("#dispatch-content").value = "";
  toast("Sent");
});
$("#btn-wh-send")?.addEventListener("click", async () => {
  const url = $("#wh-send-url").value.trim();
  const content = $("#wh-send-content").value.trim();
  const username = $("#wh-send-name").value.trim();
  if (!url || !content) return toast("Webhook URL and message required");
  await api("/api/v1/dispatch/webhook", { method: "POST", body: { url, content, username } });
  $("#wh-send-content").value = "";
  toast("Webhook sent");
});
$("#btn-bm-filter")?.addEventListener("click", loadDMs);
$("#btn-accept-friends")?.addEventListener("click", async () => {
  const r = await api("/api/v1/intel/friends", { method: "POST", body: { action: "accept" } });
  toast(`Accepted ${r.processed}`);
});
$("#btn-clear-outgoing")?.addEventListener("click", async () => {
  const r = await api("/api/v1/intel/friends", { method: "POST", body: { action: "clear" } });
  toast(`Cleared ${r.processed}`);
});

// ── 19. Settings: System & Schedules ──────────────────────
async function loadSchedules() {
  const r = await api("/api/v1/schedules");
  $("#schedules-list").innerHTML = r.schedules.length
    ? r.schedules.map((s) => `
      <div class="data-row">
        <div class="data-main"><div class="data-title">#${s.id} · every ${esc(s.interval)}</div><div class="muted">${esc(s.channel)}: ${esc(s.text)}</div></div>
        <button class="btn-danger-tonal sm" data-delsch="${s.id}">Cancel</button>
      </div>`).join("")
    : `<div class="muted">No active schedules.</div>`;
  $$("[data-delsch]").forEach((b) => b.addEventListener("click", async () => {
    await api(`/api/v1/schedules/${b.dataset.delsch}`, { method: "DELETE" });
    loadSchedules();
  }));
}

$("#btn-refresh-sched")?.addEventListener("click", loadSchedules);
$("#btn-sys-reload")?.addEventListener("click", async () => {
  const mod = $("#reload-mod").value;
  await api("/api/v1/system", { method: "POST", body: { action: "reload", module: mod } });
  toast(`Reloaded ${mod}`);
});
$("#btn-sys-update")?.addEventListener("click", async () => {
  const r = await api("/api/v1/system", { method: "POST", body: { action: "update" } });
  toast(`Updated (${r.reloaded.length} cogs)`);
});
$("#btn-sys-restart")?.addEventListener("click", async () => {
  if (!confirm("Restart Globe?")) return;
  await api("/api/v1/system", { method: "POST", body: { action: "restart" } });
  toast("Restarting...");
});
$("#btn-revoke-all")?.addEventListener("click", async () => {
  await api("/api/v1/auth/revoke", { method: "POST" });
  location.reload();
});

checkSession();
