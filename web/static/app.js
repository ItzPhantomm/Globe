const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));

let CSRF = "";
let WS = null;
const latHistory = [];
let hourlyActivity = [];
let chartMode = "activity";
let selectedActivityKind = "globe";

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

// ── 2. Sliding Active Pill Indicators (Dock + Segmented Controls) ──
function moveSlider(container, slider, activeBtn) {
  if (!container || !slider || !activeBtn) return;
  const left = activeBtn.offsetLeft;
  const width = activeBtn.offsetWidth;
  if (!width) return;
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

function initAllSlidingSegs() {
  $$(".sliding-seg").forEach((seg) => {
    const slider = seg.querySelector(".seg-slider");
    const active = seg.querySelector("button.active") || seg.querySelector("button");
    if (active) moveSlider(seg, slider, active);
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
      translateY: [16, 0],
      scale: [0.985, 1],
      opacity: [0, 1],
      duration: 460,
      easing: "cubicBezier(0.32, 1.38, 0.54, 1)",
      delay: window.anime.stagger(45),
    });
  }
}

// ── 4. Helpers & API ──────────────────────────────────────
function toast(msg) {
  const el = document.createElement("div");
  el.className = "toast";
  el.textContent = msg;
  $("#toast-root").appendChild(el);
  setTimeout(() => el.remove(), 3200);
}

function esc(str) {
  return String(str ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function fmtUptime(s) {
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  return h ? `${h}h ${m}m` : `${m}m ${s % 60}s`;
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

// ── 5. Interactive Smooth Bezier & Histogram Chart ────────
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

// ── 6. Auth Orbital Wireframe Canvas ──────────────────────
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
    ctx.strokeStyle = "rgba(200, 255, 76, 0.16)";
    ctx.lineWidth = 1.1;

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
    rot += 0.003;
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
}

// ── 7. Auth Boot ──────────────────────────────────────────
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

// ── 8. WebSocket Push Hub ─────────────────────────────────
function connectWS() {
  if (WS && WS.readyState <= 1) return;
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  WS = new WebSocket(`${proto}//${location.host}/ws`);

  WS.onopen = () => {
    $("#ws-dot").classList.add("online");
    $("#ws-label").textContent = "Live";
  };
  WS.onclose = () => {
    $("#ws-dot").classList.remove("online");
    $("#ws-label").textContent = "Reconnecting";
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
  $("#spark-latest").textContent = `${t.latency_ms} ms`;
  $("#pill-extra").textContent = `· ${t.latency_ms}ms`;
  latHistory.push(Number(t.latency_ms) || 0);
  if (latHistory.length > 30) latHistory.shift();
  if (chartMode === "ping") drawMainChart();
}

function handleJobProgress(d) {
  const pill = $("#dynamic-pill");
  if (d.job === "spoofer") {
    const wrap = $("#spoofer-bar-wrap");
    if (d.done) {
      $("#spoofer-status").textContent = "Done";
      $("#spoofer-bar").style.width = "100%";
      pill?.classList.remove("active-job");
      setTimeout(() => wrap.classList.add("hidden"), 1500);
    } else {
      wrap.classList.remove("hidden");
      pill?.classList.add("active-job");
      const pct = Math.round((d.current / Math.max(1, d.total)) * 100);
      $("#spoofer-bar").style.width = `${pct}%`;
      $("#spoofer-status").textContent = `[${d.current}/${d.total}] ${d.game}`;
      $("#pill-extra").textContent = `· Spoofing ${d.current}/${d.total}`;
    }
  } else if (d.job === "deletedm") {
    toast(d.done ? `DM cleanup done (${d.deleted})` : `Deleted ${d.deleted}...`);
  } else if (d.job === "vanity" && d.dropped) {
    toast(`Vanity dropped: ${d.code} — ${d.note}`);
    $("#vanity-badge").textContent = `Dropped: ${d.code}`;
  }
}

function applyToggles(toggles) {
  $$("#switchboard .m3-switch").forEach((btn) => {
    btn.setAttribute("aria-pressed", String(Boolean(toggles[btn.dataset.toggle])));
  });
  if (toggles.vanity_target) $("#vanity-badge").textContent = `Watching: ${toggles.vanity_target}`;
}

// ── 9. Navigation via Single Liquid Glass Dock ────────────
const VIEW_TITLES = {
  overview: "Overview",
  presence: "Presence",
  intel: "Intel & Tools",
  servers: "Servers & Voice",
  dms: "DMs & Rules",
  system: "System",
};

function switchView(name) {
  $$(".dock-item").forEach((b) => b.classList.toggle("active", b.dataset.view === name));
  $$(".view").forEach((v) => v.classList.toggle("active", v.id === `view-${name}`));
  $("#view-title").textContent = VIEW_TITLES[name] || name;
  syncDockIndicator();
  const target = $(`#view-${name}`);
  animateViewStagger(target);
  requestAnimationFrame(initAllSlidingSegs);
  if (name === "intel") loadIntel();
  if (name === "servers") loadGuilds();
  if (name === "dms") loadDMs();
  if (name === "system") loadSchedules();
}

$$(".dock-item").forEach((b) => b.addEventListener("click", () => switchView(b.dataset.view)));
window.addEventListener("resize", () => {
  syncDockIndicator();
  initAllSlidingSegs();
});

// ── 10. Overview & Chart Mode Switch ──────────────────────
async function loadOverview() {
  const [data, an] = await Promise.all([
    api("/api/v1/overview"),
    api("/api/v1/analytics").catch(() => ({ hourly: [], stats: {} })),
  ]);
  $("#acct-name").textContent = data.account.global_name || data.account.username;
  $("#acct-mask").textContent = data.account.token_masked;
  if (data.account.avatar) $("#acct-avatar").src = data.account.avatar;
  $("#prefix-input").value = data.account.prefix;
  const todayMsgs = an.stats?.global_today ?? 0;
  $("#m-db").textContent = `${todayMsgs} / ${data.runtime.db_size_kb} KB`;
  hourlyActivity = an.hourly || [];
  const totalHourly = hourlyActivity.reduce((acc, x) => acc + (Number(x.count) || 0), 0);
  if (totalHourly === 0 && chartMode === "activity") {
    chartMode = "ping";
    const seg = $("#chart-mode-seg");
    const pingBtn = seg?.querySelector('[data-chart-mode="ping"]');
    if (pingBtn) {
      seg.querySelectorAll("button").forEach((b) => b.classList.remove("active"));
      pingBtn.classList.add("active");
      moveSlider(seg, seg.querySelector(".seg-slider"), pingBtn);
    }
  }
  updateTelemetry({
    latency_ms: data.runtime.latency_ms,
    uptime_s: data.runtime.uptime_s,
    guilds: data.runtime.guilds_count,
    friends: data.runtime.friends_count,
  });
  drawMainChart();
  applyToggles(data.toggles);
  $("#log-stream").innerHTML = "";
  (data.logs || []).forEach(appendLogLine);
}

$$("#chart-mode-seg button").forEach((b) => {
  b.addEventListener("click", () => {
    chartMode = b.dataset.chartMode;
    drawMainChart();
  });
});

$$("#switchboard .m3-switch").forEach((btn) => {
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
  toast(`Prefix saved: ${val}`);
});

// ── 11. Presence Studio ───────────────────────────────────
$$("#status-mode-seg button").forEach((b) => {
  b.addEventListener("click", async () => {
    await api("/api/v1/presence/status", { method: "POST", body: { status: b.dataset.statusMode } });
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
  toast(`Activity updated (${selectedActivityKind})`);
});

$("#btn-act-clear")?.addEventListener("click", async () => {
  await api("/api/v1/presence/activity", { method: "POST", body: { kind: "clear" } });
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
  await api("/api/v1/presence/spoofer", {
    method: "POST",
    body: { action: "start", count: Number($("#spoof-count").value), interval: Number($("#spoof-interval").value) },
  });
  toast("Spoofer started");
});

$("#btn-spoof-stop")?.addEventListener("click", async () => {
  await api("/api/v1/presence/spoofer", { method: "POST", body: { action: "stop" } });
  toast("Stopping spoofer");
});

// ── 12. Intel, OSINT, Encoder & Vanity ────────────────────
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
$("#btn-profile-user")?.addEventListener("click", async () => {
  const res = await api("/api/v1/intel/user-profile", { method: "POST", body: { user_id: $("#stalk-uid").value.trim() } });
  $("#profile-output").innerHTML = `
    <div class="data-row"><div class="data-main">
      <div class="data-title">${esc(res.username)} · ${esc(res.status)}</div>
      <div class="muted">Platforms: ${esc(res.platforms.join(", ") || "None")} · Mutuals: ${res.mutuals.length}</div>
      ${res.voice ? `<div class="muted">Voice: ${esc(res.voice)}</div>` : ""}
    </div></div>`;
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

// ── 13. Servers, Voice & Channel Cleanup ──────────────────
async function loadGuilds() {
  const data = await api("/api/v1/guilds");
  $("#guilds-list").innerHTML = data.guilds.map((g) => `
    <div class="data-row">
      <div class="data-main">
        <div class="data-title">${esc(g.name)}</div>
        <div class="muted mono">${esc(g.id)} · ${g.member_count} members · ${g.roles_count} roles</div>
      </div>
      <div class="inline-actions">
        <button class="btn-tonal" data-audit="${esc(g.id)}">Audit</button>
        <a class="m3-pill-btn" href="/api/v1/guilds/${esc(g.id)}/backup" style="text-decoration:none;">Backup</a>
        <button class="${g.locked ? "btn-expressive" : "btn-danger-tonal"}" data-lock="${esc(g.id)}" data-state="${g.locked ? "unlock" : "lock"}">${g.locked ? "Unlock" : "Lockdown"}</button>
      </div>
    </div>`).join("") || `<div class="muted">No servers loaded.</div>`;

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

// ── 14. DMs, Automation Rules & Bookmarks ─────────────────
async function loadDMs() {
  const [dmRes, bmRes, autoRes] = await Promise.all([
    api("/api/v1/dms"),
    api(`/api/v1/bookmarks?tag=${encodeURIComponent($("#bm-filter").value.trim())}`),
    api("/api/v1/tools/automation"),
  ]);

  $("#dms-list").innerHTML = dmRes.dms.length
    ? dmRes.dms.map((d) => `
    <div class="data-row">
      <div class="data-main">
        <div class="data-title">${esc(d.recipient)}</div>
        <div class="muted mono">${esc(d.id)}</div>
      </div>
      <div class="inline-actions">
        <button class="btn-ghost-sm" data-use-dm="${esc(d.id)}">Use</button>
        <a class="m3-pill-btn" href="/api/v1/dms/${esc(d.id)}/export" style="text-decoration:none;">Export</a>
        <button class="btn-danger-tonal" data-wipedm="${esc(d.id)}" data-name="${esc(d.recipient)}">Wipe</button>
      </div>
    </div>`).join("")
    : `<div class="muted">No open DM channels cached.</div>`;

  $$("[data-use-dm]").forEach((b) => b.addEventListener("click", () => {
    $("#dispatch-channel").value = b.dataset.useDm;
    $("#dispatch-content").focus();
  }));

  $$("[data-wipedm]").forEach((b) => b.addEventListener("click", async () => {
    if (!confirm(`Delete all your messages in DM with ${b.dataset.name}?`)) return;
    await api(`/api/v1/dms/${b.dataset.wipedm}/wipe`, { method: "POST" });
    toast("DM cleanup started");
  }));

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
$("#btn-bm-filter")?.addEventListener("click", loadDMs);
$("#btn-accept-friends")?.addEventListener("click", async () => {
  const r = await api("/api/v1/intel/friends", { method: "POST", body: { action: "accept" } });
  toast(`Accepted ${r.processed}`);
});
$("#btn-clear-outgoing")?.addEventListener("click", async () => {
  const r = await api("/api/v1/intel/friends", { method: "POST", body: { action: "clear" } });
  toast(`Cleared ${r.processed}`);
});

// ── 15. System & Schedules ────────────────────────────────
async function loadSchedules() {
  const r = await api("/api/v1/schedules");
  $("#schedules-list").innerHTML = r.schedules.length
    ? r.schedules.map((s) => `
      <div class="data-row">
        <div class="data-main"><div class="data-title">#${s.id} · every ${esc(s.interval)}</div><div class="muted">${esc(s.channel)}: ${esc(s.text)}</div></div>
        <button class="btn-danger-tonal" data-delsch="${s.id}">Cancel</button>
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

// ── 16. Cmd+K Quick Bar ───────────────────────────────────
const PALETTE_ACTIONS = [
  { label: "Go to Overview", run: () => switchView("overview") },
  { label: "Go to Presence", run: () => switchView("presence") },
  { label: "Go to Intel & Tools", run: () => switchView("intel") },
  { label: "Go to Servers & Voice", run: () => switchView("servers") },
  { label: "Go to DMs & Rules", run: () => switchView("dms") },
  { label: "Go to System", run: () => switchView("system") },
  { label: "Set Status: DND", run: () => api("/api/v1/presence/status", { method: "POST", body: { status: "dnd" } }).then(() => toast("Status: DND")) },
  { label: "Set Status: Online", run: () => api("/api/v1/presence/status", { method: "POST", body: { status: "online" } }).then(() => toast("Status: Online")) },
  { label: "Set Status: Invisible", run: () => api("/api/v1/presence/status", { method: "POST", body: { status: "invisible" } }).then(() => toast("Status: Invisible")) },
  { label: "Pull Git & Reload Cogs", run: () => $("#btn-sys-update").click() },
  { label: "Disconnect Voice", run: () => $("#btn-vc-leave").click() },
];

function openCmdk() {
  const dlg = $("#cmdk-dialog");
  $("#cmdk-input").value = "";
  renderCmdk("");
  dlg.showModal();
}
function renderCmdk(q) {
  const matches = PALETTE_ACTIONS.filter((a) => a.label.toLowerCase().includes(q.toLowerCase()));
  $("#cmdk-results").innerHTML = matches.map((a, i) => `<button class="cmdk-row" data-cmdk-idx="${i}">${esc(a.label)}</button>`).join("");
  $$("[data-cmdk-idx]").forEach((b) => b.addEventListener("click", () => {
    $("#cmdk-dialog").close();
    matches[Number(b.dataset.cmdkIdx)].run();
  }));
}

$("#btn-cmdk")?.addEventListener("click", openCmdk);
$("#cmdk-input")?.addEventListener("input", (e) => renderCmdk(e.target.value));
$("#cmdk-dialog")?.addEventListener("click", (e) => {
  if (e.target === $("#cmdk-dialog")) $("#cmdk-dialog").close();
});
window.addEventListener("keydown", (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
    e.preventDefault();
    openCmdk();
  }
});

checkSession();
