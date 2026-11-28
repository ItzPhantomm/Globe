const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));

let CSRF = "";
let WS = null;
const latHistory = [];
let selectedActivityKind = "globe";

// ── Motion & M3 Expressive Polygon Morph Engine ───────────
const M3_SHAPES = [
  // Organic rounded 8-petal cookie
  [
    [50, 7], [65, 15], [82, 18], [85, 35],
    [93, 50], [85, 65], [82, 82], [65, 85],
    [50, 93], [35, 85], [18, 82], [15, 65],
    [7, 50], [15, 35], [18, 18], [35, 15],
  ],
  // Android 4-leaf rounded clover
  [
    [50, 14], [69, 9], [86, 14], [91, 31],
    [86, 50], [91, 69], [86, 86], [69, 91],
    [50, 86], [31, 91], [14, 86], [9, 69],
    [14, 50], [9, 31], [14, 14], [31, 9],
  ],
  // Soft burst star-squircle
  [
    [50, 5], [63, 21], [85, 15], [79, 37],
    [95, 50], [79, 63], [85, 85], [63, 79],
    [50, 95], [37, 79], [15, 85], [21, 63],
    [5, 50], [21, 37], [15, 15], [37, 21],
  ],
  // Expressive squircle
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
      const pmx = (p0[0] + p1[0]) / 2;
      const pmy = (p0[1] + p1[1]) / 2;
      d += `M ${pmx.toFixed(2)} ${pmy.toFixed(2)} `;
    }
    d += `Q ${p1[0].toFixed(2)} ${p1[1].toFixed(2)} ${mx.toFixed(2)} ${my.toFixed(2)} `;
  }
  return d + "Z";
}

function initShapeMorph() {
  const authPath = $("#auth-morph-path");
  const navPath = $("#nav-morph-path");
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const initialD = ptsToSmoothPath(M3_SHAPES[0]);
  if (authPath) authPath.setAttribute("d", initialD);
  if (navPath) navPath.setAttribute("d", initialD);
  if (reduced) return;

  let t = 0;
  function step() {
    t += 0.011;
    const total = M3_SHAPES.length;
    const idxA = Math.floor(t) % total;
    const idxB = (idxA + 1) % total;
    const raw = t - Math.floor(t);
    // Smooth M3 expressive ease
    const k = raw < 0.5 ? 2 * raw * raw : 1 - Math.pow(-2 * raw + 2, 2) / 2;
    const A = M3_SHAPES[idxA];
    const B = M3_SHAPES[idxB];
    const blended = A.map((pt, i) => [
      pt[0] + (B[i][0] - pt[0]) * k,
      pt[1] + (B[i][1] - pt[1]) * k,
    ]);
    const pathStr = ptsToSmoothPath(blended);
    if (authPath && !$("#auth-gate").classList.contains("hidden")) authPath.setAttribute("d", pathStr);
    if (navPath && !$("#workspace").classList.contains("hidden")) navPath.setAttribute("d", pathStr);
    requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
}

// Pointer-tracked spotlight borders on desktop
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
      duration: 520,
      easing: "cubicBezier(0.34, 1.48, 0.64, 1)",
      delay: window.anime.stagger(55),
    });
  } else {
    targets.forEach((el, idx) => {
      el.animate(
        [{ opacity: 0, transform: "translateY(14px) scale(0.985)" }, { opacity: 1, transform: "translateY(0) scale(1)" }],
        { duration: 420, delay: idx * 45, easing: "cubic-bezier(0.34, 1.48, 0.64, 1)", fill: "both" }
      );
    });
  }
}

// ── Helpers ───────────────────────────────────────────────
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

// ── Orbital Wireframe Canvas (Auth Screen) ────────────────
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
    const cy = h * 0.33;
    const r = Math.min(w, h) * 0.25;
    ctx.strokeStyle = "rgba(94, 234, 212, 0.14)";
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

// ── Auth Boot ─────────────────────────────────────────────
async function checkSession() {
  initShapeMorph();
  initSpotlightCards();
  const me = await api("/api/v1/auth/me");
  if (!me.authenticated) {
    $("#auth-gate").classList.remove("hidden");
    $("#workspace").classList.add("hidden");
    initOrbitalCanvas();
    return;
  }
  CSRF = me.csrf;
  $("#auth-gate").classList.add("hidden");
  $("#workspace").classList.remove("hidden");
  connectWS();
  await loadOverview();
  animateViewStagger($("#view-overview"));
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
    $("#auth-gate").classList.add("hidden");
    $("#workspace").classList.remove("hidden");
    connectWS();
    await loadOverview();
    animateViewStagger($("#view-overview"));
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

// ── WebSocket Live Telemetry ──────────────────────────────
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
  drawSparkline();
}

function drawSparkline() {
  if (latHistory.length === 0) return;
  const series = latHistory.length === 1 ? [latHistory[0], latHistory[0]] : latHistory;
  const w = 420, h = 130, pad = 12;
  const max = Math.max(...series, 60);
  const min = Math.min(...series, 0);
  const span = Math.max(1, max - min);
  const pts = series.map((v, i) => {
    const x = (i / (series.length - 1)) * w;
    const y = h - pad - ((v - min) / span) * (h - pad * 2);
    return [x.toFixed(1), y.toFixed(1)];
  });
  const d = pts.map((p, i) => `${i === 0 ? "M" : "L"}${p[0]},${p[1]}`).join(" ");
  $("#spark-line").setAttribute("d", d);
  $("#spark-area").setAttribute("d", `${d} L${w},${h} L0,${h} Z`);
  const last = pts[pts.length - 1];
  if (last) {
    $("#spark-dot")?.setAttribute("cx", last[0]);
    $("#spark-dot")?.setAttribute("cy", last[1]);
    $("#spark-dot-halo")?.setAttribute("cx", last[0]);
    $("#spark-dot-halo")?.setAttribute("cy", last[1]);
  }
}

function handleJobProgress(d) {
  const pill = $("#dynamic-pill");
  if (d.job === "spoofer") {
    const wrap = $("#spoofer-bar-wrap");
    if (d.done) {
      $("#spoofer-status").textContent = "Completed";
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
    toast(d.done ? `DM wipe finished: ${d.deleted} deleted` : `DM wipe progress: ${d.deleted} deleted`);
  } else if (d.job === "vanity" && d.dropped) {
    toast(`VANITY DROPPED: ${d.code} — ${d.note}`);
    $("#vanity-badge").textContent = `Dropped: ${d.code}`;
  }
}

function applyToggles(toggles) {
  $$("#switchboard .m3-switch").forEach((btn) => {
    const key = btn.dataset.toggle;
    btn.setAttribute("aria-pressed", String(Boolean(toggles[key])));
  });
  if (toggles.vanity_target) {
    $("#vanity-badge").textContent = `Armed: ${toggles.vanity_target}`;
  }
}

// ── Navigation ────────────────────────────────────────────
const VIEW_TITLES = {
  overview: "Overview",
  presence: "Presence Studio",
  intel: "Intelligence & OSINT",
  servers: "Servers & Voice",
  dms: "DMs & Dispatch",
  system: "System & Jobs",
};

function switchView(name) {
  $$(".nav-item").forEach((b) => b.classList.toggle("active", b.dataset.view === name));
  $$(".rail-btn").forEach((b) => b.classList.toggle("active", b.dataset.view === name));
  $$(".view").forEach((v) => v.classList.toggle("active", v.id === `view-${name}`));
  $("#view-title").textContent = VIEW_TITLES[name] || name;
  $("#sidebar").classList.remove("open");
  animateViewStagger($(`#view-${name}`));
  if (name === "intel") loadIntel();
  if (name === "servers") loadGuilds();
  if (name === "dms") loadDMs();
  if (name === "system") loadSchedules();
}

$$(".nav-item, .rail-btn").forEach((b) => b.addEventListener("click", () => switchView(b.dataset.view)));
$("#open-drawer")?.addEventListener("click", () => $("#sidebar").classList.add("open"));
$("#close-drawer")?.addEventListener("click", () => $("#sidebar").classList.remove("open"));

// ── Overview Load & Switchboard ───────────────────────────
async function loadOverview() {
  const data = await api("/api/v1/overview");
  $("#acct-name").textContent = data.account.global_name || data.account.username;
  $("#acct-mask").textContent = data.account.token_masked;
  if (data.account.avatar) $("#acct-avatar").src = data.account.avatar;
  $("#prefix-input").value = data.account.prefix;
  $("#m-db").textContent = `${data.runtime.db_size_kb} KB`;
  updateTelemetry({
    latency_ms: data.runtime.latency_ms,
    uptime_s: data.runtime.uptime_s,
    guilds: data.runtime.guilds_count,
    friends: data.runtime.friends_count,
  });
  applyToggles(data.toggles);
  $("#log-stream").innerHTML = "";
  (data.logs || []).forEach(appendLogLine);
}

$$("#switchboard .m3-switch").forEach((btn) => {
  btn.addEventListener("click", async () => {
    const key = btn.dataset.toggle;
    const next = btn.getAttribute("aria-pressed") !== "true";
    try {
      const res = await api("/api/v1/toggles", { method: "POST", body: { key, value: next } });
      applyToggles(res.toggles);
      toast(`${key} ${next ? "enabled" : "disabled"}`);
    } catch (err) {
      toast(err.message);
    }
  });
});

$("#btn-save-prefix")?.addEventListener("click", async () => {
  const val = $("#prefix-input").value.trim();
  if (!val) return;
  await api("/api/v1/toggles", { method: "POST", body: { key: "prefix", value: val } });
  toast(`Prefix updated to ${val}`);
});

// ── Presence Studio & Spoofer ─────────────────────────────
$$("#status-mode-seg button").forEach((b) => {
  b.addEventListener("click", async () => {
    $$("#status-mode-seg button").forEach((x) => x.classList.remove("active"));
    b.classList.add("active");
    await api("/api/v1/presence/status", { method: "POST", body: { status: b.dataset.statusMode } });
    toast(`Status set to ${b.dataset.statusMode}`);
  });
});

$$("#activity-kind-seg button").forEach((b) => {
  b.addEventListener("click", () => {
    $$("#activity-kind-seg button").forEach((x) => x.classList.remove("active"));
    b.classList.add("active");
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
  toast("Rich presence cleared");
});

$("#btn-cs-apply")?.addEventListener("click", async () => {
  await api("/api/v1/presence/custom", { method: "POST", body: { text: $("#cs-input").value } });
  toast("Custom status updated");
});

$("#btn-bio-apply")?.addEventListener("click", async () => {
  await api("/api/v1/presence/bio", { method: "POST", body: { text: $("#bio-input").value } });
  toast("Profile bio updated");
});

$$("#hypesquad-seg button").forEach((b) => {
  b.addEventListener("click", async () => {
    $$("#hypesquad-seg button").forEach((x) => x.classList.remove("active"));
    b.classList.add("active");
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
  toast("Status rotator started");
});

$("#btn-rotate-stop")?.addEventListener("click", async () => {
  await api("/api/v1/presence/rotate", { method: "POST", body: { enabled: false } });
  toast("Status rotator stopped");
});

$("#btn-spoof-start")?.addEventListener("click", async () => {
  await api("/api/v1/presence/spoofer", {
    method: "POST",
    body: { action: "start", count: Number($("#spoof-count").value), interval: Number($("#spoof-interval").value) },
  });
  toast("Badge spoofer started");
});

$("#btn-spoof-stop")?.addEventListener("click", async () => {
  await api("/api/v1/presence/spoofer", { method: "POST", body: { action: "stop" } });
  toast("Stopping spoofer");
});

// ── Intelligence, Vanity & OSINT ──────────────────────────
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
    : `<div class="muted">No deleted messages recorded.</div>`;

  $("#radar-list").innerHTML = rd.radar.length
    ? rd.radar.map((r) => `<div class="data-row"><div class="data-main"><div class="data-title">${esc(r.author)} · ${esc(r.where)}</div><div class="muted">${esc(r.content)}</div></div></div>`).join("")
    : `<div class="muted">No ghost-pings caught yet.</div>`;

  $("#kw-list").innerHTML = kw.keywords.map((k) => `<span class="kw-item">${esc(k)}<button data-rm-kw="${esc(k)}">×</button></span>`).join("");
  $$("[data-rm-kw]").forEach((b) => b.addEventListener("click", async () => {
    await api("/api/v1/intel/keywords", { method: "POST", body: { action: "remove", phrase: b.dataset.rmKw } });
    loadIntel();
  }));

  $("#stalk-logs").innerHTML = st.logs.length
    ? st.logs.map((l) => `<div class="data-row"><div class="data-main"><div class="data-title">${esc(l.user)}</div><div class="muted">${esc(l.detail)}</div></div></div>`).join("")
    : `<div class="muted">Tracking ${st.targets.length} target(s).</div>`;

  $("#vanity-badge").textContent = vn.running ? `Armed: ${vn.target}` : "Standby";
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
  toast("Alert webhook updated");
});
$("#btn-vanity-start")?.addEventListener("click", async () => {
  const code = $("#vanity-code").value.trim();
  if (!code) return toast("Enter invite code");
  await api("/api/v1/intel/vanity", { method: "POST", body: { code, guild_id: $("#vanity-guild").value.trim() } });
  toast(`Vanity watch armed: ${code}`);
  loadIntel();
});
$("#btn-vanity-stop")?.addEventListener("click", async () => {
  await api("/api/v1/intel/vanity", { method: "DELETE" });
  toast("Vanity watch disarmed");
  loadIntel();
});
$("#btn-osint-run")?.addEventListener("click", async () => {
  const kind = $("#osint-kind").value;
  const target = $("#osint-target").value.trim();
  if (!target) return toast("Enter target");
  $("#osint-output").textContent = "Querying...";
  try {
    const res = await api("/api/v1/tools/inspect", { method: "POST", body: { kind, target } });
    $("#osint-output").textContent = JSON.stringify(res.result, null, 2);
  } catch (err) {
    $("#osint-output").textContent = `Error: ${err.message}`;
  }
});
$("#btn-stalk-add")?.addEventListener("click", async () => {
  await api("/api/v1/intel/stalk", { method: "POST", body: { action: "add", user_id: $("#stalk-uid").value.trim() } });
  toast("User added to stalker");
  loadIntel();
});
$("#btn-profile-user")?.addEventListener("click", async () => {
  const res = await api("/api/v1/intel/user-profile", { method: "POST", body: { user_id: $("#stalk-uid").value.trim() } });
  $("#profile-output").innerHTML = `
    <div class="data-row"><div class="data-main">
      <div class="data-title">${esc(res.username)} · ${esc(res.status)}</div>
      <div class="muted">Platforms: ${esc(res.platforms.join(", ") || "None")} · Mutual servers: ${res.mutuals.length}</div>
      ${res.voice ? `<div class="muted">Voice: ${esc(res.voice)}</div>` : ""}
    </div></div>`;
});
$("#btn-friends-backup")?.addEventListener("click", async () => {
  const r = await api("/api/v1/intel/friends", { method: "POST", body: { action: "backup" } });
  toast(`Saved snapshot (${r.count} friends)`);
});
$("#btn-friends-diff")?.addEventListener("click", async () => {
  const r = await api("/api/v1/intel/friends/diff");
  if (!r.baseline_exists) {
    $("#friends-diff-out").innerHTML = `<div class="muted">No baseline snapshot saved yet (${r.current_count} friends).</div>`;
    return;
  }
  const rem = r.removed.map((u) => `<div class="data-row"><div class="data-main"><div class="data-title">Removed: ${esc(u.username)}</div><div class="muted mono">${esc(u.id)}</div></div></div>`).join("");
  const add = r.added.map((u) => `<div class="data-row"><div class="data-main"><div class="data-title">Added: ${esc(u.username)}</div><div class="muted mono">${esc(u.id)}</div></div></div>`).join("");
  $("#friends-diff-out").innerHTML = rem || add ? rem + add : `<div class="muted">No relationship changes since last snapshot (${r.current_count} friends).</div>`;
});

// ── Servers & Voice ───────────────────────────────────────
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
    </div>`).join("");

  $$("[data-audit]").forEach((b) => b.addEventListener("click", async () => {
    const res = await api(`/api/v1/guilds/${b.dataset.audit}/audit`);
    $("#audit-title").textContent = res.guild;
    $("#audit-output").innerHTML = `
      <div class="data-row"><div class="data-main"><div class="data-title">@everyone risks</div><div class="muted">${esc(res.everyone_risks.join(", ") || "None")}</div></div></div>
      <div class="data-row"><div class="data-main"><div class="data-title">Admin roles (${res.admin_roles.length})</div><div class="muted">${esc(res.admin_roles.join(", ") || "None")}</div></div></div>
      <div class="data-row"><div class="data-main"><div class="data-title">Exposed channel overwrites</div><div class="muted">${esc(res.exposed_channels.join(", ") || "None")}</div></div></div>`;
  }));

  $$("[data-lock]").forEach((b) => b.addEventListener("click", async () => {
    const lock = b.dataset.state === "lock";
    await api("/api/v1/guilds/lockdown", { method: "POST", body: { guild_id: b.dataset.lock, lock } });
    toast(lock ? "Server locked down" : "Lockdown lifted");
    loadGuilds();
  }));
}

$("#btn-refresh-guilds")?.addEventListener("click", loadGuilds);
$("#btn-vc-join")?.addEventListener("click", async () => {
  await api("/api/v1/voice", { method: "POST", body: { action: "join", channel_id: $("#vc-channel-id").value.trim(), mode: $("#vc-mode").value } });
  toast("Joined 24/7 voice channel");
});
$("#btn-vc-leave")?.addEventListener("click", async () => {
  await api("/api/v1/voice", { method: "POST", body: { action: "leave" } });
  toast("Disconnected from voice");
});
$("#btn-vc-follow")?.addEventListener("click", async () => {
  await api("/api/v1/voice", { method: "POST", body: { action: "follow", user_id: $("#vc-follow-uid").value.trim() || "off" } });
  toast("Voice follow updated");
});

// ── DMs, Dispatch & Bookmarks ─────────────────────────────
async function loadDMs() {
  const [dmRes, bmRes] = await Promise.all([
    api("/api/v1/dms"),
    api(`/api/v1/bookmarks?tag=${encodeURIComponent($("#bm-filter").value.trim())}`),
  ]);
  $("#dms-list").innerHTML = dmRes.dms.length
    ? dmRes.dms.map((d) => `
    <div class="data-row">
      <div class="data-main">
        <div class="data-title">${esc(d.recipient)}</div>
        <div class="muted mono">${esc(d.id)}</div>
      </div>
      <div class="inline-actions">
        <button class="btn-ghost-sm" data-use-dm="${esc(d.id)}">Dispatch</button>
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
    if (!confirm(`Delete all self-authored messages in DM with ${b.dataset.name}?`)) return;
    await api(`/api/v1/dms/${b.dataset.wipedm}/wipe`, { method: "POST" });
    toast("DM wipe started");
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

$("#btn-dispatch-send")?.addEventListener("click", async () => {
  const channel_id = $("#dispatch-channel").value.trim();
  const content = $("#dispatch-content").value.trim();
  if (!channel_id || !content) return toast("Channel ID and content required");
  await api("/api/v1/dispatch/send", { method: "POST", body: { channel_id, content } });
  $("#dispatch-content").value = "";
  toast("Message dispatched");
});
$("#btn-bm-filter")?.addEventListener("click", loadDMs);
$("#btn-accept-friends")?.addEventListener("click", async () => {
  const r = await api("/api/v1/intel/friends", { method: "POST", body: { action: "accept" } });
  toast(`Accepted ${r.processed} friend requests`);
});
$("#btn-clear-outgoing")?.addEventListener("click", async () => {
  const r = await api("/api/v1/intel/friends", { method: "POST", body: { action: "clear" } });
  toast(`Cancelled ${r.processed} outgoing requests`);
});

// ── System & Schedules ────────────────────────────────────
async function loadSchedules() {
  const r = await api("/api/v1/schedules");
  $("#schedules-list").innerHTML = r.schedules.length
    ? r.schedules.map((s) => `
      <div class="data-row">
        <div class="data-main"><div class="data-title">#${s.id} · every ${esc(s.interval)}</div><div class="muted">${esc(s.channel)}: ${esc(s.text)}</div></div>
        <button class="btn-danger-tonal" data-delsch="${s.id}">Cancel</button>
      </div>`).join("")
    : `<div class="muted">No active recurring schedules.</div>`;
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
  toast(`Hot-updated (${r.reloaded.length} modules)`);
});
$("#btn-sys-restart")?.addEventListener("click", async () => {
  if (!confirm("Restart the Globe bot process?")) return;
  await api("/api/v1/system", { method: "POST", body: { action: "restart" } });
  toast("Process restarting...");
});
$("#btn-revoke-all")?.addEventListener("click", async () => {
  await api("/api/v1/auth/revoke", { method: "POST" });
  location.reload();
});

// ── Cmd+K Command Palette ─────────────────────────────────
const PALETTE_ACTIONS = [
  { label: "Go to Overview", run: () => switchView("overview") },
  { label: "Go to Presence Studio", run: () => switchView("presence") },
  { label: "Go to Intelligence & OSINT", run: () => switchView("intel") },
  { label: "Go to Servers & Voice", run: () => switchView("servers") },
  { label: "Go to DMs & Dispatch", run: () => switchView("dms") },
  { label: "Go to System & Jobs", run: () => switchView("system") },
  { label: "Set Online Mode: DND", run: () => api("/api/v1/presence/status", { method: "POST", body: { status: "dnd" } }).then(() => toast("Status: DND")) },
  { label: "Set Online Mode: Online", run: () => api("/api/v1/presence/status", { method: "POST", body: { status: "online" } }).then(() => toast("Status: Online")) },
  { label: "Set Online Mode: Invisible", run: () => api("/api/v1/presence/status", { method: "POST", body: { status: "invisible" } }).then(() => toast("Status: Invisible")) },
  { label: "Hot-update from GitHub", run: () => $("#btn-sys-update").click() },
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
