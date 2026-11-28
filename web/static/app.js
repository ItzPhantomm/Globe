const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));

let CSRF = "";
let WS = null;
const latHistory = [];

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

// ── Orbital Wireframe Globe Canvas (Auth Screen) ──────────
function initOrbitalCanvas() {
  const canvas = $("#globe-canvas");
  if (!canvas || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const ctx = canvas.getContext("2d");
  let rot = 0;
  let raf = 0;

  function resize() {
    canvas.width = canvas.offsetWidth * devicePixelRatio;
    canvas.height = canvas.offsetHeight * devicePixelRatio;
    ctx.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0);
  }
  resize();
  window.addEventListener("resize", resize);

  function frame() {
    if ($("#auth-gate").classList.contains("hidden")) {
      cancelAnimationFrame(raf);
      return;
    }
    const w = canvas.offsetWidth;
    const h = canvas.offsetHeight;
    ctx.clearRect(0, 0, w, h);

    const cx = w * 0.50;
    const cy = h * 0.27;
    const r = Math.min(w, h) * 0.26;
    ctx.strokeStyle = "rgba(255, 255, 255, 0.08)";
    ctx.lineWidth = 1;

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

    rot += 0.0025;
    raf = requestAnimationFrame(frame);
  }
  raf = requestAnimationFrame(frame);
}

// ── Auth Boot ─────────────────────────────────────────────
async function checkSession() {
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
  latHistory.push(Number(t.latency_ms) || 0);
  if (latHistory.length > 30) latHistory.shift();
  drawSparkline();
}

function drawSparkline() {
  if (latHistory.length === 0) return;
  const series = latHistory.length === 1 ? [latHistory[0], latHistory[0]] : latHistory;
  const w = 420, h = 120, pad = 10;
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
  const dot = $("#spark-dot");
  if (dot && last) {
    dot.setAttribute("cx", last[0]);
    dot.setAttribute("cy", last[1]);
  }
}

function handleJobProgress(d) {
  if (d.job === "spoofer") {
    const wrap = $("#spoofer-bar-wrap");
    if (d.done) {
      $("#spoofer-status").textContent = "Completed";
      $("#spoofer-bar").style.width = "100%";
      setTimeout(() => wrap.classList.add("hidden"), 1500);
    } else {
      wrap.classList.remove("hidden");
      const pct = Math.round((d.current / Math.max(1, d.total)) * 100);
      $("#spoofer-bar").style.width = `${pct}%`;
      $("#spoofer-status").textContent = `[${d.current}/${d.total}] ${d.game}`;
    }
  } else if (d.job === "deletedm") {
    toast(d.done ? `DM wipe finished: ${d.deleted} deleted` : `DM wipe progress: ${d.deleted} deleted`);
  }
}

function applyToggles(toggles) {
  $$("#switchboard .toggle").forEach((btn) => {
    const key = btn.dataset.toggle;
    btn.setAttribute("aria-pressed", String(Boolean(toggles[key])));
  });
}

// ── Navigation ────────────────────────────────────────────
const VIEW_TITLES = {
  overview: "Overview",
  presence: "Presence & Spoofer",
  intel: "Intelligence",
  servers: "Servers & Voice",
  dms: "DMs & Vault",
  system: "System & Jobs",
};

function switchView(name) {
  $$(".nav-item").forEach((b) => b.classList.toggle("active", b.dataset.view === name));
  $$(".view").forEach((v) => v.classList.toggle("active", v.id === `view-${name}`));
  $("#view-title").textContent = VIEW_TITLES[name] || name;
  $("#sidebar").classList.remove("open");
  if (name === "intel") loadIntel();
  if (name === "servers") loadGuilds();
  if (name === "dms") loadDMs();
  if (name === "system") loadSchedules();
}

$$(".nav-item").forEach((b) => b.addEventListener("click", () => switchView(b.dataset.view)));
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

$$("#switchboard .toggle").forEach((btn) => {
  btn.addEventListener("click", async () => {
    const key = btn.dataset.toggle;
    const next = btn.getAttribute("aria-pressed") !== "true";
    const res = await api("/api/v1/toggles", { method: "POST", body: { key, value: next } });
    applyToggles(res.toggles);
    toast(`${key} ${next ? "enabled" : "disabled"}`);
  });
});

$("#btn-save-prefix")?.addEventListener("click", async () => {
  const val = $("#prefix-input").value.trim();
  if (!val) return;
  await api("/api/v1/toggles", { method: "POST", body: { key: "prefix", value: val } });
  toast(`Prefix updated to ${val}`);
});

// ── Presence & Spoofer ────────────────────────────────────
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

// ── Intelligence ──────────────────────────────────────────
async function loadIntel() {
  const [sn, rd, kw, st] = await Promise.all([
    api(`/api/v1/intel/snipes?q=${encodeURIComponent($("#snipe-search").value.trim())}`),
    api("/api/v1/intel/radar"),
    api("/api/v1/intel/keywords"),
    api("/api/v1/intel/stalk"),
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
        <button class="btn-secondary" data-audit="${esc(g.id)}">Audit</button>
        <a class="btn-ghost" href="/api/v1/guilds/${esc(g.id)}/backup" style="text-decoration:none;padding:0.45rem 0.75rem;border:1px solid var(--border);border-radius:8px;font-size:var(--text-sm);">Backup</a>
        <button class="${g.locked ? "btn-primary" : "btn-danger"}" data-lock="${esc(g.id)}" data-state="${g.locked ? "unlock" : "lock"}">${g.locked ? "Unlock" : "Lockdown"}</button>
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

// ── DMs & Bookmarks ───────────────────────────────────────
async function loadDMs() {
  const [dmRes, bmRes] = await Promise.all([
    api("/api/v1/dms"),
    api(`/api/v1/bookmarks?tag=${encodeURIComponent($("#bm-filter").value.trim())}`),
  ]);
  $("#dms-list").innerHTML = dmRes.dms.map((d) => `
    <div class="data-row">
      <div class="data-main">
        <div class="data-title">${esc(d.recipient)}</div>
        <div class="muted mono">${esc(d.id)}</div>
      </div>
      <div class="inline-actions">
        <a class="btn-secondary" href="/api/v1/dms/${esc(d.id)}/export" style="text-decoration:none;padding:0.45rem 0.75rem;border:1px solid var(--border);border-radius:8px;font-size:var(--text-sm);">Export</a>
        <button class="btn-danger" data-wipedm="${esc(d.id)}" data-name="${esc(d.recipient)}">Wipe mine</button>
      </div>
    </div>`).join("");

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
        <button class="btn-ghost" data-delbm="${bm.id}">Delete</button>
      </div>`).join("")
    : `<div class="muted">No saved bookmarks.</div>`;

  $$("[data-delbm]").forEach((b) => b.addEventListener("click", async () => {
    await api(`/api/v1/bookmarks/${b.dataset.delbm}`, { method: "DELETE" });
    loadDMs();
  }));
}

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
        <button class="btn-danger" data-delsch="${s.id}">Cancel</button>
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
  { label: "Go to Presence & Spoofer", run: () => switchView("presence") },
  { label: "Go to Intelligence", run: () => switchView("intel") },
  { label: "Go to Servers & Voice", run: () => switchView("servers") },
  { label: "Go to DMs & Vault", run: () => switchView("dms") },
  { label: "Go to System & Jobs", run: () => switchView("system") },
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
    if (!$("#workspace").classList.contains("hidden")) openCmdk();
  }
});

checkSession();
