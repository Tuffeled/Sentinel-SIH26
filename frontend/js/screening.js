/* New Screening: upload (drag/drop, multi-file) + live analysis */
const STAGE_LABELS = {
  received: "Document Received", classification: "Classification", ocr: "OCR",
  mrz: "MRZ Validation", field_consistency: "Field Consistency", forensic: "Forensic Analysis",
  face: "Face Verification", watchlist: "Watchlist Lookup", identity: "Identity Consistency",
  risk: "Risk Assessment",
};
const STAGE_ICON = { WAITING: "○", PROCESSING: "●", COMPLETED: "✓", WARNING: "!", FAILED: "✕", SKIPPED: "–" };
let _files = [];
let _pollTimer = null;

window.PAGE_INIT = function () {
  const c = document.getElementById("content");
  c.innerHTML = `
    <div class="page-head">
      <div class="titles"><h1>New Screening</h1><p>Upload a synthetic identity document to run the full analysis pipeline.</p></div>
    </div>
    <div class="grid c2" id="screenGrid">
      <div class="card" id="uploadCard">
        <div class="card-title mb-12">Document Upload</div>
        <div class="dropzone" id="dropzone">
          <div class="dz-ico">⭱</div>
          <h3>Drag &amp; drop documents here</h3>
          <p>or click to browse · PNG, JPG, PDF · max 15 MB</p>
          <input type="file" id="fileInput" accept=".png,.jpg,.jpeg,.pdf" multiple hidden>
        </div>
        <div id="fileList" style="margin-top:14px"></div>
        <div class="flex mt-16">
          <label class="hint" style="display:flex;align-items:center;gap:8px"><input type="checkbox" id="crossDoc"> Cross-document (link multiple documents to one identity)</label>
          <div class="spacer"></div>
          <button class="btn primary" id="startBtn" disabled>Start Screening</button>
        </div>
        <div class="disclaimer mt-16">DEMO MODE — synthetic documents only. AI produces an explainable risk assessment; the authorised officer makes the final decision.</div>
      </div>
      <div class="card" id="progressCard">
        <div class="card-title mb-12">Analysis Progress</div>
        <div id="progressBody"><div class="empty"><div class="big">◔</div>Upload a document to begin analysis.</div></div>
      </div>
    </div>`;

  const dz = document.getElementById("dropzone");
  const input = document.getElementById("fileInput");
  dz.onclick = () => input.click();
  dz.ondragover = (e) => { e.preventDefault(); dz.classList.add("drag"); };
  dz.ondragleave = () => dz.classList.remove("drag");
  dz.ondrop = (e) => { e.preventDefault(); dz.classList.remove("drag"); addFiles(e.dataTransfer.files); };
  input.onchange = () => addFiles(input.files);
  document.getElementById("startBtn").onclick = startScreening;
};

const ALLOWED = ["png", "jpg", "jpeg", "pdf"];
function addFiles(fileList) {
  for (const f of fileList) {
    const ext = f.name.split(".").pop().toLowerCase();
    if (!ALLOWED.includes(ext)) { toast("Unsupported file", `${f.name} is not a supported type.`, "error"); continue; }
    if (f.size > 15 * 1024 * 1024) { toast("File too large", `${f.name} exceeds 15 MB.`, "error"); continue; }
    _files.push(f);
  }
  renderFileList();
}

function renderFileList() {
  const wrap = document.getElementById("fileList");
  document.getElementById("startBtn").disabled = _files.length === 0;
  if (!_files.length) { wrap.innerHTML = ""; return; }
  wrap.innerHTML = _files.map((f, i) => `
    <div class="flex" style="padding:8px 10px;border:1px solid var(--border);border-radius:8px;margin-bottom:6px">
      <div id="thumb${i}" style="width:40px;height:40px;border-radius:6px;background:var(--panel-3);flex:none;overflow:hidden;display:grid;place-items:center;font-size:10px" class="muted">${f.name.endsWith("pdf") ? "PDF" : ""}</div>
      <div style="min-width:0"><div style="font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(f.name)}</div><div class="hint">${(f.size / 1024).toFixed(0)} KB</div></div>
      <div class="spacer"></div>
      <button class="btn sm ghost" data-rm="${i}">✕</button>
    </div>`).join("");
  _files.forEach((f, i) => {
    if (!f.name.endsWith("pdf")) {
      const r = new FileReader();
      r.onload = () => { const t = document.getElementById(`thumb${i}`); if (t) t.innerHTML = `<img src="${r.result}" style="width:100%;height:100%;object-fit:cover">`; };
      r.readAsDataURL(f);
    }
  });
  wrap.querySelectorAll("[data-rm]").forEach(b => b.onclick = () => { _files.splice(Number(b.dataset.rm), 1); renderFileList(); });
}

async function startScreening() {
  const btn = document.getElementById("startBtn");
  btn.disabled = true; btn.innerHTML = `<span class="spin"></span> Uploading…`;
  try {
    let investigationId = null;
    for (let i = 0; i < _files.length; i++) {
      const fd = new FormData();
      fd.append("file", _files[i]);
      fd.append("auto_analyze", "false");
      if (investigationId) fd.append("investigation_id", String(investigationId));
      const res = await API.upload(fd);
      investigationId = res.investigation_id;
    }
    // Kick off analysis on the whole investigation.
    await API.reanalyze(investigationId);
    btn.innerHTML = "Start Screening";
    document.getElementById("dropzone").style.opacity = "0.5";
    pollAnalysis(investigationId);
  } catch (e) {
    toast("Upload failed", e.message, "error");
    btn.disabled = false; btn.innerHTML = "Start Screening";
  }
}

function pollAnalysis(id) {
  const body = document.getElementById("progressBody");
  const render = (st) => {
    const stages = st.stages || [];
    const done = st.status === "COMPLETED" || st.status === "FAILED";
    body.innerHTML = `
      <div class="flex mb-12"><span class="mono muted">${esc(st.screening_id || "")}</span><div class="spacer"></div>${badge(st.status)}</div>
      <div class="progress-bar mb-12"><span style="width:${st.progress || 0}%"></span></div>
      <div class="stages">
        ${stages.map(s => `
          <div class="stage ${slug(s.status)}">
            <div class="st-ico">${STAGE_ICON[s.status] || "○"}</div>
            <div class="st-body"><div class="st-label">${esc(s.label)}</div>${s.detail ? `<div class="st-detail">${esc(s.detail)}</div>` : ""}</div>
            <div class="st-status" style="color:${statusColor(s.status)}">${s.status}</div>
          </div>`).join("")}
      </div>
      ${done ? finishBlock(st) : ""}`;
    if (done) { clearInterval(_pollTimer); _pollTimer = null; }
  };
  const tick = async () => { try { render(await API.analysisStatus(id)); } catch (e) { /* keep */ } };
  tick();
  _pollTimer = setInterval(tick, 1000);
}

function statusColor(s) {
  return { COMPLETED: "var(--success)", PROCESSING: "var(--accent)", WARNING: "var(--warning)", FAILED: "var(--danger)", SKIPPED: "var(--muted)", WAITING: "var(--muted-2)" }[s] || "var(--muted)";
}

function finishBlock(st) {
  if (st.status === "FAILED") return `<div class="disclaimer" style="border-color:var(--danger);color:#fca5a5">Analysis failed: ${esc(st.error || "unknown error")}</div>`;
  return `
    <div class="card mt-16" style="background:var(--panel-2);text-align:center">
      <div class="risk-score" style="color:${riskColor(st.risk_level)}">${Math.round(st.risk_score || 0)}<small>/100</small></div>
      <div class="mt-12">${riskBadge(st.risk_level)}</div>
      <div class="hint mt-12">Recommended action: <b>${esc((st.recommended_action || "").replace(/_/g, " "))}</b></div>
      <a class="btn primary mt-16" href="investigation.html?id=${st.investigation_id}">Open Full Investigation →</a>
    </div>`;
}
function riskColor(l) { return { LOW: "var(--low)", MEDIUM: "var(--medium)", HIGH: "var(--high)", CRITICAL: "var(--critical)" }[l] || "var(--text)"; }

window.addEventListener("beforeunload", () => { if (_pollTimer) clearInterval(_pollTimer); });
