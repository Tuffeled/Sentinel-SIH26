/* SENTINEL — shared shell + helpers (vanilla JS) */

/* ---------------- Icons (inline SVG, stroke) ---------------- */
const ICON = (p) => `<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">${p}</svg>`;
const ICONS = {
  dashboard: ICON('<rect x="3" y="3" width="7" height="9"/><rect x="14" y="3" width="7" height="5"/><rect x="14" y="12" width="7" height="9"/><rect x="3" y="16" width="7" height="5"/>'),
  scan: ICON('<path d="M3 7V5a2 2 0 0 1 2-2h2M17 3h2a2 2 0 0 1 2 2v2M21 17v2a2 2 0 0 1-2 2h-2M7 21H5a2 2 0 0 1-2-2v-2"/><path d="M3 12h18"/>'),
  history: ICON('<path d="M3 3v5h5"/><path d="M3.05 13A9 9 0 1 0 6 5.3L3 8"/><path d="M12 7v5l3 2"/>'),
  cases: ICON('<rect x="3" y="7" width="18" height="13" rx="2"/><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>'),
  watchlist: ICON('<path d="M12 2 4 6v6c0 5 3.5 8 8 10 4.5-2 8-5 8-10V6z"/><path d="M9 12l2 2 4-4"/>'),
  eval: ICON('<path d="M3 3v18h18"/><path d="M7 14l3-3 3 3 5-6"/>'),
  reports: ICON('<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M8 13h8M8 17h6"/>'),
  settings: ICON('<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-2.7 1.1V21a2 2 0 0 1-4 0v-.1A1.6 1.6 0 0 0 7 19.4a1.6 1.6 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.6 1.6 0 0 0-1.1-2.7H1a2 2 0 0 1 0-4h.1A1.6 1.6 0 0 0 2.6 7a1.6 1.6 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1A1.6 1.6 0 0 0 7 2.6 1.6 1.6 0 0 0 8 1.1V1a2 2 0 0 1 4 0v.1A1.6 1.6 0 0 0 15 2.6a1.6 1.6 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.6 1.6 0 0 0-.3 1.8V7a1.6 1.6 0 0 0 1.5 1H21a2 2 0 0 1 0 4h-.1a1.6 1.6 0 0 0-1.5 1z"/>'),
  bell: ICON('<path d="M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.7 21a2 2 0 0 1-3.4 0"/>'),
  search: ICON('<circle cx="11" cy="11" r="7"/><path d="M21 21l-4-4"/>'),
};

const NAV = [
  { group: "Security Screening", items: [
    { id: "index", label: "Dashboard", href: "index.html", icon: "dashboard" },
    { id: "screening", label: "New Screening", href: "screening.html", icon: "scan" },
    { id: "history", label: "Screening History", href: "history.html", icon: "history" },
    { id: "cases", label: "Cases", href: "cases.html", icon: "cases", badge: "cases" },
  ]},
  { group: "Analysis", items: [
    { id: "watchlist", label: "Watchlist", href: "watchlist.html", icon: "watchlist" },
    { id: "evaluation", label: "Evaluation", href: "evaluation.html", icon: "eval" },
  ]},
  { group: "System", items: [
    { id: "reports", label: "Reports", href: "reports.html", icon: "reports" },
    { id: "settings", label: "Settings", href: "settings.html", icon: "settings" },
  ]},
];

const PAGE_META = {
  index: "Dashboard", screening: "New Screening", investigation: "Investigation",
  history: "Screening History", cases: "Cases", watchlist: "Watchlist",
  evaluation: "Evaluation", reports: "Reports", settings: "Settings",
};

/* ---------------- Small helpers ---------------- */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
function el(html) { const t = document.createElement("template"); t.innerHTML = html.trim(); return t.content.firstElementChild; }
function esc(s) { if (s === null || s === undefined) return ""; return String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); }
function num(n) { if (n === null || n === undefined || isNaN(n)) return "0"; return Number(n).toLocaleString("en-US"); }
function slug(s) { return String(s || "").toLowerCase().replace(/[^a-z0-9]+/g, "_"); }
function debounce(fn, ms = 300) { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; }

function badge(text, cls) {
  const c = cls !== undefined ? cls : slug(text);
  return `<span class="badge ${c}"><span class="b-dot"></span>${esc(text)}</span>`;
}
function riskBadge(level) { return level ? badge(level) : `<span class="muted">—</span>`; }

function fmtDateTime(iso) { if (!iso) return "—"; const d = new Date(iso); return d.toLocaleString("en-GB", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", hour12: false }); }
function fmtTime(iso) { if (!iso) return "—"; return new Date(iso).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hour12: true }); }
function timeAgo(iso) {
  if (!iso) return "—";
  const s = Math.max(1, Math.floor((Date.now() - new Date(iso)) / 1000));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

function countUp(elm, target, opts = {}) {
  const dur = opts.dur || 700, dec = opts.dec || 0;
  const start = 0, t0 = performance.now();
  function step(t) {
    const p = Math.min(1, (t - t0) / dur);
    const val = start + (target - start) * (1 - Math.pow(1 - p, 3));
    elm.textContent = (opts.prefix || "") + val.toLocaleString("en-US", { minimumFractionDigits: dec, maximumFractionDigits: dec }) + (opts.suffix || "");
    if (p < 1) requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
}

/* ---------------- Toasts ---------------- */
function toast(title, msg = "", type = "") {
  let wrap = $(".toasts"); if (!wrap) { wrap = el('<div class="toasts"></div>'); document.body.appendChild(wrap); }
  const t = el(`<div class="toast ${type}"><div class="t-title">${esc(title)}</div>${msg ? `<div class="t-msg">${esc(msg)}</div>` : ""}</div>`);
  wrap.appendChild(t);
  setTimeout(() => { t.style.opacity = "0"; t.style.transition = "opacity .3s"; setTimeout(() => t.remove(), 300); }, 4200);
}

/* ---------------- Modal ---------------- */
function openModal(innerHtml, opts = {}) {
  closeModal();
  const overlay = el(`<div class="modal-overlay"><div class="modal ${opts.wide ? "wide" : ""}">${innerHtml}</div></div>`);
  overlay.addEventListener("click", (e) => { if (e.target === overlay && !opts.persist) closeModal(); });
  document.body.appendChild(overlay);
  return overlay;
}
function closeModal() { const m = $(".modal-overlay"); if (m) m.remove(); }
function confirmDialog(title, message, confirmLabel = "Confirm", danger = true) {
  return new Promise((resolve) => {
    const m = openModal(`
      <div class="modal-head"><h3>${esc(title)}</h3></div>
      <div class="modal-body"><p style="margin:0;color:var(--muted)">${esc(message)}</p></div>
      <div class="modal-foot">
        <button class="btn ghost" data-x>Cancel</button>
        <button class="btn ${danger ? "danger" : "primary"}" data-ok>${esc(confirmLabel)}</button>
      </div>`);
    m.querySelector("[data-x]").onclick = () => { closeModal(); resolve(false); };
    m.querySelector("[data-ok]").onclick = () => { closeModal(); resolve(true); };
  });
}

/* ---------------- Shell ---------------- */
function renderShell() {
  const page = document.body.dataset.page || "index";
  const navHtml = NAV.map(g => `
    <div class="nav-group">
      <div class="nav-group-title">${g.group}</div>
      ${g.items.map(it => `
        <a class="nav-item ${it.id === page ? "active" : ""}" href="${it.href}">
          ${ICONS[it.icon] || ""}<span>${it.label}</span>
          ${it.badge ? `<span class="badge-count" data-badge="${it.badge}">0</span>` : ""}
        </a>`).join("")}
    </div>`).join("");

  const officer = "OFFICER";
  const shell = el(`
    <div class="app">
      <aside class="sidebar">
        <div class="brand">
          <div class="logo"><div class="mark">S</div><div class="name">SENTINEL</div></div>
          <div class="subtitle">Document Screening</div>
        </div>
        <nav class="nav">${navHtml}</nav>
        <div class="sidebar-foot">
          <div class="officer">
            <div class="avatar">O</div>
            <div><div class="who" data-officer>Officer</div><div class="status"><span class="b-dot" style="width:6px;height:6px;border-radius:50%;background:var(--success);display:inline-block"></span> Online</div></div>
          </div>
        </div>
      </aside>
      <div class="main">
        <header class="topbar">
          <div class="breadcrumb">Screening <b>/ ${esc(PAGE_META[page] || "")}</b></div>
          <div class="topbar-right">
            <div class="topbar-search">
              <button class="icon-btn" id="searchBtn" title="Global search">${ICONS.search}</button>
            </div>
            <div class="sys-indicator" id="sysIndicator"><span class="dot" id="sysDot"></span><span id="sysText">Connecting…</span></div>
            <span class="demo-flag" id="demoFlag" hidden>Demo — Synthetic Only</span>
            <div class="clock" id="clock">--:--:--</div>
            <button class="icon-btn" id="notifBtn" title="Notifications">${ICONS.bell}<span class="notif-dot" id="notifDot" hidden>0</span></button>
            <div class="officer" style="gap:8px"><div class="avatar" style="width:30px;height:30px;font-size:12px">O</div></div>
          </div>
        </header>
        <main class="content" id="content"></main>
      </div>
    </div>`);
  document.body.prepend(shell);

  startClock();
  pollHealth();
  setInterval(pollHealth, 8000);
  refreshBadges();
  setInterval(refreshBadges, 15000);
  wireTopbar();
}

function startClock() {
  const c = $("#clock");
  const tick = () => { c.textContent = new Date().toLocaleTimeString("en-GB", { hour12: false }); };
  tick(); setInterval(tick, 1000);
}

async function pollHealth() {
  const dot = $("#sysDot"), txt = $("#sysText"), flag = $("#demoFlag");
  try {
    const h = await API.health();
    if (h.state === "ANALYSIS_BUSY") { dot.className = "dot busy"; txt.textContent = "Analysis Busy"; }
    else { dot.className = "dot ok"; txt.textContent = "System Operational"; }
    if (h.demo_mode) flag.hidden = false;
    const off = $("[data-officer]"); if (off && h.app_name) { /* keep */ }
    window.__health = h;
  } catch (e) {
    dot.className = "dot off"; txt.textContent = "Backend Offline";
  }
}

async function refreshBadges() {
  try {
    const s = await API.dashboardStats();
    $$('[data-badge="cases"]').forEach(b => b.textContent = num(s.open_cases || 0));
    const dot = $("#notifDot");
    if (s.unread_notifications > 0) { dot.hidden = false; dot.textContent = s.unread_notifications > 99 ? "99+" : s.unread_notifications; }
    else dot.hidden = true;
  } catch (e) { /* offline */ }
}

function wireTopbar() {
  $("#notifBtn").onclick = toggleNotifications;
  $("#searchBtn").onclick = openSearch;
  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "k") { e.preventDefault(); openSearch(); }
    if (e.key === "Escape") { const p = $(".notif-panel"); if (p) p.remove(); }
  });
}

async function toggleNotifications() {
  const existing = $(".notif-panel"); if (existing) { existing.remove(); return; }
  const panel = el(`<div class="notif-panel"><div style="padding:12px 14px;display:flex;align-items:center;border-bottom:1px solid var(--border)"><b>Notifications</b><button class="btn sm ghost" id="markAll" style="margin-left:auto">Mark all read</button></div><div id="notifList"><div class="spinner-lg"></div></div></div>`);
  document.body.appendChild(panel);
  panel.querySelector("#markAll").onclick = async () => { await API.markAllNotificationsRead(); toggleNotifications(); refreshBadges(); toggleNotifications(); };
  try {
    const data = await API.listNotifications();
    const list = panel.querySelector("#notifList");
    if (!data.notifications.length) { list.innerHTML = `<div class="empty">No notifications</div>`; return; }
    list.innerHTML = data.notifications.map(n => `
      <div class="notif-item ${n.read ? "" : "unread"}">
        <div style="flex:1">
          <div class="n-title">${esc(n.title)}</div>
          <div class="n-msg">${esc(n.message)}</div>
          <div class="n-time">${timeAgo(n.created_at)}</div>
        </div>
        ${n.investigation_id ? `<a class="link" href="investigation.html?id=${n.investigation_id}">View</a>` : ""}
      </div>`).join("");
  } catch (e) { panel.querySelector("#notifList").innerHTML = `<div class="empty">Failed to load</div>`; }
}

function openSearch() {
  const m = openModal(`
    <div class="modal-head"><h3>Global Search</h3></div>
    <div class="modal-body">
      <input class="input" id="gSearch" placeholder="Screening ID, document number, case ID…" autocomplete="off"/>
      <div id="gResults" style="margin-top:14px"></div>
    </div>`);
  const input = m.querySelector("#gSearch"); input.focus();
  const results = m.querySelector("#gResults");
  const run = debounce(async () => {
    const q = input.value.trim(); if (q.length < 2) { results.innerHTML = ""; return; }
    try {
      const r = await API.search(q);
      const inv = r.investigations.map(i => `<a class="notif-item" style="display:block" href="investigation.html?id=${i.id}"><div class="n-title mono">${esc(i.screening_id)} ${riskBadge(i.risk_level)}</div><div class="n-msg">${esc(i.document_type || "")} · ${esc(i.document_number || "")}</div></a>`).join("");
      const cs = r.cases.map(c => `<a class="notif-item" style="display:block" href="cases.html"><div class="n-title mono">${esc(c.case_id)}</div><div class="n-msg">${esc(c.title)}</div></a>`).join("");
      results.innerHTML = (inv + cs) || `<div class="empty">No results</div>`;
    } catch (e) { results.innerHTML = `<div class="empty">${esc(e.message)}</div>`; }
  }, 250);
  input.oninput = run;
}

/* Auto-render shell when DOM ready */
document.addEventListener("DOMContentLoaded", () => { renderShell(); if (window.PAGE_INIT) window.PAGE_INIT(); });
