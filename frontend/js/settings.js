/* Settings + demo data controls */
window.PAGE_INIT = async function () {
  document.getElementById("content").innerHTML = `
    <div class="page-head"><div class="titles"><h1>Settings</h1><p>System status, analysis configuration and demo data controls.</p></div></div>
    <div id="settingsBody"><div class="spinner-lg"></div></div>`;
  load();
};

async function load() {
  let s;
  try { s = await API.getSettings(); } catch (e) { document.getElementById("settingsBody").innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }
  const cfg = s.config;
  const engineRow = (label, active, extra) => `<div class="flex" style="padding:8px 0;border-bottom:1px solid var(--border-soft)"><span>${label}</span><span class="spacer"></span>${active && active !== "none" ? badge(active, "low") : badge("unavailable", "na")}${extra ? `<span class="hint" style="margin-left:8px">${extra}</span>` : ""}</div>`;
  document.getElementById("settingsBody").innerHTML = `
    <div class="grid c2">
      <div class="card">
        <div class="card-title mb-12">System Status</div>
        ${engineRow("Demo mode", cfg.demo_mode ? "enabled" : "off")}
        ${engineRow("Database", "connected", `${num(s.database.counts.investigations)} screenings · ${num(s.database.counts.watchlist)} watchlist`)}
        ${engineRow("OCR engine", s.ocr.active, `Tesseract ${s.ocr.tesseract_available ? "✓" : "✕"}`)}
        ${engineRow("Face engine", s.face.active, `threshold ${s.face.threshold}`)}
        ${engineRow("Synthetic dataset", s.dataset.count ? "loaded" : "missing", `${s.dataset.genuine} genuine · ${s.dataset.altered} altered`)}
      </div>
      <div class="card">
        <div class="card-title mb-12">Risk Engine Weights</div>
        <div class="kv">${Object.entries(cfg.risk_weights).map(([k, v]) => `<div class="k">${esc(k.replace(/_/g, " "))}</div><div class="v mono">+${v}</div>`).join("")}</div>
        <div class="disclaimer mt-12">Weights are deterministic and configurable via .env. The risk engine de-duplicates related evidence to prevent double-counting.</div>
      </div>
    </div>

    <div class="card mt-16">
      <div class="card-title mb-12">Analysis Configuration</div>
      <div class="kv">
        <div class="k">Supported file types</div><div class="v mono">${cfg.allowed_extensions.join(", ")}</div>
        <div class="k">Max upload size</div><div class="v">${cfg.max_upload_mb} MB</div>
        <div class="k">Face match threshold</div><div class="v mono">${cfg.face_match_threshold} (SFace cosine)</div>
        <div class="k">Implemented modules</div><div class="v">OCR · MRZ validation · Field consistency · Forensics (reference-diff) · Face verification · Watchlist · Cross-document · Evidence · Risk engine</div>
        <div class="k">ML tampering model</div><div class="v">${badge("Not configured", "na")} <span class="hint">pluggable via TamperingDetector interface</span></div>
      </div>
    </div>

    <div class="card mt-16" style="border-color:var(--warning)">
      <div class="card-title mb-12">Demo Data Controls</div>
      <p class="hint">Seeding runs the real pipeline over the synthetic dataset — every dashboard number originates from genuine analysis. Destructive actions require confirmation.</p>
      <div class="flex wrap mt-12">
        <button class="btn primary" id="seedBtn">Seed Demo Data</button>
        <button class="btn danger" id="clearBtn">Clear Demo Data</button>
        <button class="btn danger" id="resetBtn">Reset Database</button>
      </div>
    </div>
    <div class="disclaimer mt-16">DEMO MODE — SYNTHETIC DOCUMENTS ONLY. This system never connects to real government or stolen-document databases. AI assists the officer; the authorised officer makes the final decision.</div>`;

  document.getElementById("seedBtn").onclick = async (e) => {
    const b = e.target; b.disabled = true; b.innerHTML = `<span class="spin"></span> Seeding…`;
    try { const r = await API.seedDemo(); toast("Demo data seeded", `${r.screenings || 0} screenings created`, "success"); }
    catch (err) { toast("Seed failed", err.message, "error"); }
    b.disabled = false; b.innerHTML = "Seed Demo Data"; load();
  };
  document.getElementById("clearBtn").onclick = async () => {
    if (await confirmDialog("Clear demo data", "This deletes all screenings, cases, evidence and reviews (watchlist is kept). Continue?", "Clear")) {
      await API.clearDemo(); toast("Demo data cleared", "", "success"); load();
    }
  };
  document.getElementById("resetBtn").onclick = async () => {
    if (await confirmDialog("Reset database", "This deletes ALL data including the watchlist, then re-seeds the synthetic watchlist. Continue?", "Reset")) {
      await API.resetDemo(); toast("Database reset", "", "success"); load();
    }
  };
}
