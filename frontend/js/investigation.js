/* Investigation workspace */
let INV = null;
let _invPoll = null;
const qp = new URLSearchParams(location.search);
const INV_ID = qp.get("id");

window.PAGE_INIT = async function () {
  if (!INV_ID) { document.getElementById("content").innerHTML = `<div class="empty">No investigation specified.</div>`; return; }
  await loadInvestigation();
};

async function loadInvestigation() {
  try {
    INV = await API.getInvestigation(INV_ID);
  } catch (e) {
    document.getElementById("content").innerHTML = `<div class="empty">${esc(e.message)}</div>`;
    return;
  }
  if (INV.status === "RUNNING" || INV.status === "QUEUED") { renderRunning(); return; }
  if (_invPoll) { clearInterval(_invPoll); _invPoll = null; }
  render();
}

function renderRunning() {
  const c = document.getElementById("content");
  const st = INV;
  c.innerHTML = `
    <div class="page-head"><div class="titles"><h1 class="mono">${esc(st.screening_id)}</h1><p>Analysis in progress…</p></div></div>
    <div class="card">
      <div class="progress-bar mb-12"><span style="width:${st.progress || 0}%"></span></div>
      <div class="stages">${(st.stages || []).map(s => `
        <div class="stage ${slug(s.status)}"><div class="st-ico">${{WAITING:"○",PROCESSING:"●",COMPLETED:"✓",WARNING:"!",FAILED:"✕",SKIPPED:"–"}[s.status]||"○"}</div>
        <div class="st-body"><div class="st-label">${esc(s.label)}</div>${s.detail?`<div class="st-detail">${esc(s.detail)}</div>`:""}</div></div>`).join("")}</div>
    </div>`;
  if (!_invPoll) _invPoll = setInterval(loadInvestigation, 1200);
}

function mergedFields(doc) {
  const mrz = (doc.mrz && doc.mrz.fields) || {};
  const ocr = (doc.ocr && doc.ocr.fields) || {};
  const pick = (k) => mrz[k] || ocr[k] || "";
  return {
    full_name: pick("full_name") || `${ocr.given_names || ""} ${ocr.surname || ""}`.trim(),
    surname: pick("surname"), given_names: pick("given_names"),
    document_number: doc.document_number || pick("document_number"),
    nationality: pick("nationality"), dob: pick("dob"), sex: pick("sex"),
    expiry_date: pick("expiry_date"), issuing_country: pick("issuing_country"),
  };
}

function render() {
  const c = document.getElementById("content");
  const primary = INV.documents[0] || {};
  const f = mergedFields(primary);
  const risk = INV.risk || {};
  const reviewed = INV.reviews && INV.reviews.length;

  c.innerHTML = `
    <div class="page-head">
      <div class="titles">
        <h1 class="mono">${esc(INV.screening_id)}</h1>
        <p>${esc(primary.document_type || "Document")} screening · ${fmtDateTime(INV.created_at)} · ${INV.document_count} document(s)</p>
      </div>
      <div class="actions">
        ${badge(INV.screening_status)}
        <button class="btn ghost" id="reanalyzeBtn">Re-run</button>
        <button class="btn ghost" id="reportBtn">Generate Report</button>
        <button class="btn primary" id="reviewBtn">${reviewed ? "Update Review" : "Officer Review"}</button>
      </div>
    </div>

    <div class="grid" style="grid-template-columns: 1fr 1fr 340px; align-items:start">
      ${docPreviewCard(primary)}
      ${identityCard(f, primary)}
      ${riskCard(risk)}
    </div>

    <div class="card mt-16 pad-0">
      <div class="tabs" id="tabs" style="padding:0 16px">
        <div class="tab active" data-tab="evidence">Evidence</div>
        <div class="tab" data-tab="validation">Validation</div>
        <div class="tab" data-tab="forensics">Forensics</div>
        <div class="tab" data-tab="face">Face</div>
        <div class="tab" data-tab="watchlist">Watchlist</div>
        <div class="tab" data-tab="cross">Cross-Document</div>
        <div class="tab" data-tab="review">Officer Review</div>
        <div class="tab" data-tab="audit">Audit Trail</div>
      </div>
      <div style="padding:18px">
        <div class="tab-panel active" data-panel="evidence">${evidencePanel()}</div>
        <div class="tab-panel" data-panel="validation">${validationPanel(primary)}</div>
        <div class="tab-panel" data-panel="forensics">${forensicsPanel(primary)}</div>
        <div class="tab-panel" data-panel="face">${facePanel(primary)}</div>
        <div class="tab-panel" data-panel="watchlist">${watchlistPanel()}</div>
        <div class="tab-panel" data-panel="cross">${crossPanel()}</div>
        <div class="tab-panel" data-panel="review">${reviewPanel()}</div>
        <div class="tab-panel" data-panel="audit">${auditPanel()}</div>
      </div>
    </div>`;

  wireTabs();
  wireEvidence();
  wireForensicViewer(primary);
  document.getElementById("reviewBtn").onclick = openReviewModal;
  document.getElementById("reportBtn").onclick = generateReport;
  document.getElementById("reanalyzeBtn").onclick = async () => {
    await API.reanalyze(INV.id); toast("Re-analysis started", "", "success"); loadInvestigation();
  };
}

/* ---------- Top cards ---------- */
function docPreviewCard(doc) {
  const forensic = doc.forensic || {};
  return `
    <div class="card">
      <div class="card-head"><div class="card-title">Document Preview</div>
        <div class="actions"><span class="pill">${esc(doc.original_filename || "")}</span></div></div>
      <div class="forensic-toggle" id="imgToggle">
        <button class="btn sm primary" data-img="original">Original</button>
        ${forensic.visualization_url ? `<button class="btn sm ghost" data-img="overlay">Tamper Overlay</button>` : ""}
        ${forensic.ela_url ? `<button class="btn sm ghost" data-img="ela">ELA View</button>` : ""}
      </div>
      <div class="forensic-img-wrap"><img id="docImg" src="/api/documents/${doc.id}/image" alt="document"></div>
      <div class="hint mt-12">Type: <b>${esc(doc.document_type)}</b> · Classifier confidence ${Math.round((doc.classification_confidence || 0) * 100)}%</div>
    </div>`;
}

function identityCard(f, doc) {
  const rows = [
    ["Full Name", f.full_name], ["Surname", f.surname], ["Given Names", f.given_names],
    ["Document No.", f.document_number, true], ["Nationality", f.nationality],
    ["Date of Birth", f.dob, true], ["Sex", f.sex], ["Date of Expiry", f.expiry_date, true],
    ["Issuing Country", f.issuing_country],
  ].filter(r => r[1]);
  return `
    <div class="card">
      <div class="card-title mb-12">Extracted Identity Information</div>
      <div class="kv">
        ${rows.map(r => `<div class="k">${esc(r[0])}</div><div class="v ${r[2] ? "mono" : ""}">${esc(r[1] || "—")}</div>`).join("")}
      </div>
      <div class="section-title mt-16">Sources</div>
      <div class="flex wrap" style="gap:6px">
        ${doc.ocr ? badge(`OCR ${Math.round((doc.ocr.confidence || 0) * 100)}%`, "accent") : badge("OCR N/A", "na")}
        ${doc.mrz && doc.mrz.detected ? badge(`MRZ ${doc.mrz.mrz_type}`, doc.mrz.valid ? "pass" : "fail") : badge("No MRZ", "na")}
      </div>
    </div>`;
}

function riskCard(risk) {
  const score = risk.score || 0;
  const contributors = (risk.contributors || []).slice(0, 6);
  return `
    <div class="card">
      <div class="card-title mb-12">Risk Assessment</div>
      <div class="risk-hero">
        <div class="risk-score" style="color:${riskColor(risk.level)}">${Math.round(score)}<small>/100</small></div>
        <div class="risk-level-badge">${riskBadge(risk.level)}</div>
      </div>
      <div class="risk-meter"><div class="needle" style="left:${Math.min(100, score)}%"></div></div>
      <div class="flex" style="justify-content:space-between;font-size:10px" class="muted"><span class="muted">0</span><span class="muted">100</span></div>
      <div class="hint mt-12">Recommended action</div>
      <div style="font-weight:700;font-size:15px">${esc((risk.recommended_action || INV.recommended_action || "—").replace(/_/g, " "))}</div>
      <div class="section-title mt-16">Top Contributing Signals</div>
      ${contributors.length ? contributors.map(c => `
        <div class="flex" style="padding:5px 0;border-bottom:1px solid var(--border-soft)">
          <span class="mono" style="color:var(--warning);font-weight:700;min-width:40px">+${c.points}</span>
          <span style="font-size:13px">${esc(c.label)}</span>
          <span class="spacer"></span>${badge(c.severity || "", slug(c.severity || "na"))}
        </div>`).join("") : `<div class="hint">No risk-contributing signals — document appears clean.</div>`}
      <div class="disclaimer mt-12">${esc(risk.disclaimer || "Risk assessment is an analytical aid and does not constitute a final determination.")}</div>
    </div>`;
}

/* ---------- Panels ---------- */
function evidencePanel() {
  const ev = INV.evidence || [];
  if (!ev.length) return `<div class="empty">No evidence items were generated — the document appears consistent and clean.</div>`;
  return `<div>${ev.map((e, i) => `
    <div class="evidence-item ${i === 0 ? "open" : ""}" data-ev="${i}">
      <div class="evidence-head">
        <span class="evidence-pts" style="color:${e.risk_contribution > 0 ? "var(--warning)" : "var(--muted)"}">${e.risk_contribution > 0 ? "+" + e.risk_contribution : "0"}</span>
        <div><div class="evidence-title">${esc(e.title)}</div><div class="evidence-src">${esc(e.source)} · ${esc(e.type)}</div></div>
        <span class="spacer"></span>
        ${badge(e.severity, slug(e.severity))}
        <span class="chev">›</span>
      </div>
      <div class="evidence-body">
        <p style="margin:0 0 8px">${esc(e.description)}</p>
        <div class="hint">Confidence: ${(e.confidence * 100).toFixed(0)}% · Risk contribution: ${e.risk_contribution} pts</div>
      </div>
    </div>`).join("")}</div>`;
}

function validationPanel(doc) {
  const ocr = doc.ocr, mrz = doc.mrz;
  const cons = (INV.cross_document, null);
  let mrzChecks = "";
  if (mrz && mrz.detected) {
    mrzChecks = `<table class="tbl" style="max-width:420px"><thead><tr><th>Check</th><th>Result</th></tr></thead><tbody>
      ${Object.entries(mrz.checks || {}).map(([k, v]) => `<tr><td>${esc(k.replace(/_/g, " "))}</td><td>${badge(v, slug(v))}</td></tr>`).join("")}
    </tbody></table>`;
  }
  return `
    <div class="grid c2">
      <div>
        <div class="section-title">OCR</div>
        ${ocr ? `<div class="kv">
          <div class="k">Engine</div><div class="v">${esc(ocr.engine || "—")}</div>
          <div class="k">Confidence</div><div class="v">${Math.round((ocr.confidence || 0) * 100)}%</div>
        </div>
        <details style="margin-top:10px"><summary class="link">View raw OCR text</summary><pre style="white-space:pre-wrap;font-size:11px;background:var(--panel-2);padding:10px;border-radius:8px;max-height:200px;overflow:auto;margin-top:8px">${esc(ocr.raw_text || "")}</pre></details>`
        : `<div class="hint">OCR unavailable.</div>`}
      </div>
      <div>
        <div class="section-title">MRZ Validation</div>
        ${mrz && mrz.detected ? `
          <div class="hint mb-12">Type ${esc(mrz.mrz_type)} · ${mrz.valid ? badge("ALL CHECKS PASSED", "pass") : badge("CHECKSUM FAILURE", "fail")}</div>
          ${mrzChecks}
          <details style="margin-top:10px"><summary class="link">View MRZ lines</summary><pre class="mono" style="font-size:12px;background:var(--panel-2);padding:10px;border-radius:8px;margin-top:8px;overflow:auto">${esc((mrz.raw_lines || []).join("\n"))}</pre></details>`
        : `<div class="hint">MRZ not detected — MRZ validation skipped.</div>`}
      </div>
    </div>
    <div class="section-title mt-16">Field Consistency (Visual Zone vs MRZ)</div>
    ${consistencyTable(doc)}`;
}

function consistencyTable(doc) {
  // Compute a display comparison from OCR + MRZ fields.
  const ocr = (doc.ocr && doc.ocr.fields) || {}, mrz = (doc.mrz && doc.mrz.fields) || {};
  const fields = [["surname", "Surname"], ["given_names", "Given Names"], ["document_number", "Document No."], ["dob", "Date of Birth"], ["nationality", "Nationality"]];
  const rows = fields.map(([k, label]) => {
    const a = ocr[k], b = mrz[k];
    if (!a || !b) return `<tr><td>${label}</td><td class="mono">${esc(a || "—")}</td><td class="mono">${esc(b || "—")}</td><td>${badge("N/A", "na")}</td></tr>`;
    const match = String(a).toUpperCase().replace(/[^A-Z0-9]/g, "") === String(b).toUpperCase().replace(/[^A-Z0-9]/g, "") ||
      (k.includes("name") && String(a).toUpperCase().slice(0, 5) === String(b).toUpperCase().slice(0, 5));
    return `<tr><td>${label}</td><td class="mono">${esc(a)}</td><td class="mono">${esc(b)}</td><td>${badge(match ? "MATCH" : "MISMATCH", match ? "match" : "mismatch")}</td></tr>`;
  });
  return `<div class="table-wrap"><table class="tbl"><thead><tr><th>Field</th><th>OCR (Visual Zone)</th><th>MRZ</th><th>Result</th></tr></thead><tbody>${rows.join("")}</tbody></table></div>`;
}

function forensicsPanel(doc) {
  const forensic = doc.forensic;
  if (!forensic) return `<div class="empty">Forensic analysis not available.</div>`;
  return `
    <div class="forensic-view">
      <div>
        <div class="forensic-toggle" id="fvToggle">
          <button class="btn sm primary" data-fv="original">Original</button>
          ${forensic.visualization_url ? `<button class="btn sm ghost" data-fv="overlay">Suspicious Regions</button>` : ""}
          ${forensic.ela_url ? `<button class="btn sm ghost" data-fv="ela">ELA</button>` : ""}
        </div>
        <div class="forensic-img-wrap"><img id="fvImg" src="/api/documents/${doc.id}/image"></div>
        <div class="hint mt-12">Overall anomaly score: <b>${(forensic.overall_score || 0).toFixed(2)}</b> · ${forensic.suspicious ? badge("SUSPICIOUS", "critical") : badge("NO STRONG ANOMALY", "low")}${forensic.has_reference ? " · reference-based" : " · blind (no reference)"}</div>
      </div>
      <div>
        <div class="section-title">Why was this flagged?</div>
        ${(forensic.signals || []).map(s => `
          <div class="card" style="padding:12px;margin-bottom:8px;background:var(--panel-2)">
            <div class="flex"><b style="font-size:13px">${esc(s.label)}</b><span class="spacer"></span><span class="mono" style="color:${s.score >= 0.5 ? "var(--warning)" : "var(--muted)"}">${(s.score * 100).toFixed(0)}%</span></div>
            <div class="hint" style="margin-top:4px">${esc(s.description)}</div>
            ${(s.regions && s.regions.length) ? `<div class="hint" style="margin-top:4px">${s.regions.length} region(s) · confidence ${(s.confidence * 100).toFixed(0)}%</div>` : ""}
          </div>`).join("")}
        <div class="disclaimer">Forensic signals indicate <i>potential</i> anomalies; they do not by themselves prove manipulation. A trained ML tampering model is not configured.</div>
      </div>
    </div>`;
}

function facePanel(doc) {
  const face = doc.face;
  if (!face) return `<div class="empty">Face verification not available.</div>`;
  return `
    <div class="grid c2">
      <div>
        <div class="section-title">Detected Face</div>
        ${face.crop_url ? `<div class="forensic-img-wrap" style="max-width:220px"><img src="${face.crop_url}"></div>` : `<div class="empty" style="max-width:220px">No face crop</div>`}
      </div>
      <div>
        <div class="section-title">Verification</div>
        <div class="kv">
          <div class="k">Engine</div><div class="v">${esc(face.engine || "—")}</div>
          <div class="k">Face detected</div><div class="v">${face.face_detected ? badge("YES", "match") : badge("NO", "no_match")}</div>
          <div class="k">Status</div><div class="v">${badge(face.status, slug(face.status))}</div>
          <div class="k">Similarity</div><div class="v mono">${face.similarity !== null && face.similarity !== undefined ? face.similarity.toFixed(3) : "—"}</div>
          <div class="k">Match</div><div class="v">${face.match === null || face.match === undefined ? "—" : (face.match ? badge("MATCH", "match") : badge("NO MATCH", "no_match"))}</div>
        </div>
        <div class="hint mt-12">${esc(face.detail || "")}</div>
        <div class="disclaimer mt-12">Face verification compares the document photo against the enrolled reference on file for this identifier. Similarity values are never fabricated.</div>
      </div>
    </div>`;
}

function watchlistPanel() {
  const wl = (INV.evidence || []).find(e => e.type === "WATCHLIST_MATCH");
  if (!wl) return `<div class="empty"><div class="big">✓</div>No match in the local synthetic watchlist.<div class="hint mt-12">Note: "no watchlist match" does not mean the document is genuine — it only means no matching record exists in the local synthetic watchlist.</div></div>`;
  const d = wl.details || {};
  return `
    <div class="card" style="background:var(--panel-2);border-color:var(--danger)">
      <div class="flex mb-12"><b style="font-size:15px;color:var(--danger)">⚠ Synthetic Watchlist Match</b><span class="spacer"></span>${badge(d.status || "FLAGGED", slug(d.status || "flagged"))}</div>
      <div class="kv">
        <div class="k">Document Number</div><div class="v mono">${esc(d.document_number || "")}</div>
        <div class="k">Status</div><div class="v">${esc(d.status || "")}</div>
        <div class="k">Reason</div><div class="v">${esc(d.reason || "")}</div>
        <div class="k">Source</div><div class="v">${esc(d.source || "SYNTHETIC_DEMO")}</div>
      </div>
      <div class="disclaimer mt-12">Contributes +${wl.risk_contribution} to the risk score. This is a synthetic demonstration record and does not determine the final decision.</div>
    </div>`;
}

function crossPanel() {
  const cross = INV.cross_document || {};
  if (!cross.applicable) return `<div class="empty">Cross-document consistency requires at least two linked documents in one investigation.</div>`;
  const matrix = cross.matrix || [];
  return `
    <div class="section-title">Identity Consistency Matrix</div>
    <div class="table-wrap"><table class="tbl"><thead><tr><th>Attribute</th><th>Result</th><th>Values</th></tr></thead><tbody>
      ${matrix.map(row => `<tr>
        <td><b>${esc(row.label || row.attribute)}</b></td>
        <td>${badge(row.result, slug(row.result))}</td>
        <td class="mono" style="font-size:12px">${(row.values || []).map(v => esc(v.value || "")).filter(Boolean).join(" · ") || "—"}</td>
      </tr>`).join("")}
    </tbody></table></div>`;
}

function reviewPanel() {
  const reviews = INV.reviews || [];
  const aiRec = (INV.recommended_action || "").replace(/_/g, " ");
  return `
    <div class="grid c2">
      <div>
        <div class="section-title">AI Recommendation</div>
        <div class="card" style="background:var(--panel-2)">
          <div class="flex"><span>Risk level</span><span class="spacer"></span>${riskBadge(INV.risk_level)}</div>
          <div class="flex mt-12"><span>Recommended action</span><span class="spacer"></span><b>${esc(aiRec || "—")}</b></div>
          <div class="disclaimer mt-12">AI assists the officer by combining document, forensic, biometric, watchlist and consistency signals. The officer makes the final decision.</div>
        </div>
        <button class="btn primary mt-16" onclick="openReviewModal()">${reviews.length ? "Submit Another Decision" : "Record Officer Decision"}</button>
      </div>
      <div>
        <div class="section-title">Review History</div>
        ${reviews.length ? reviews.map(r => `
          <div class="card" style="background:var(--panel-2);margin-bottom:8px">
            <div class="flex"><b>${esc(r.decision.replace(/_/g, " "))}</b><span class="spacer"></span>${r.overridden ? badge("OVERRIDE", "critical") : badge("ACCEPTED", "low")}</div>
            <div class="hint mt-12">By ${esc(r.reviewer)} · ${fmtDateTime(r.created_at)}</div>
            <div class="hint">AI recommended: ${esc(r.ai_recommendation || "—")} (${esc(r.ai_risk_level || "—")})</div>
            ${r.notes ? `<div style="margin-top:8px;font-size:13px">"${esc(r.notes)}"</div>` : ""}
          </div>`).join("") : `<div class="empty">No officer review recorded yet.</div>`}
      </div>
    </div>`;
}

function auditPanel() {
  const audit = INV.audit || [];
  if (!audit.length) return `<div class="empty">No audit events.</div>`;
  return `<div class="timeline">${audit.map(a => `
    <div class="tl-item">
      <div class="tl-time">${fmtDateTime(a.ts)}</div>
      <div class="tl-event">${esc(a.event.replace(/_/g, " "))}</div>
      <div class="tl-actor">${esc(a.actor)}${a.details && Object.keys(a.details).length ? " · " + esc(JSON.stringify(a.details).slice(0, 80)) : ""}</div>
    </div>`).join("")}</div>`;
}

/* ---------- Wiring ---------- */
function wireTabs() {
  $$("#tabs .tab").forEach(t => t.onclick = () => {
    $$("#tabs .tab").forEach(x => x.classList.remove("active"));
    $$(".tab-panel").forEach(x => x.classList.remove("active"));
    t.classList.add("active");
    $(`.tab-panel[data-panel="${t.dataset.tab}"]`).classList.add("active");
  });
}
function wireEvidence() {
  $$(".evidence-item").forEach(item => { item.querySelector(".evidence-head").onclick = () => item.classList.toggle("open"); });
}
function wireForensicViewer(doc) {
  const forensic = doc.forensic || {};
  const map = { original: `/api/documents/${doc.id}/image`, overlay: forensic.visualization_url, ela: forensic.ela_url };
  const bind = (toggleId, imgId) => {
    const tg = document.getElementById(toggleId); if (!tg) return;
    tg.querySelectorAll("[data-img],[data-fv]").forEach(b => b.onclick = () => {
      tg.querySelectorAll("button").forEach(x => { x.classList.remove("primary"); x.classList.add("ghost"); });
      b.classList.add("primary"); b.classList.remove("ghost");
      const key = b.dataset.img || b.dataset.fv;
      const img = document.getElementById(imgId); if (img && map[key]) img.src = map[key];
    });
  };
  bind("imgToggle", "docImg");
  bind("fvToggle", "fvImg");
}

/* ---------- Actions ---------- */
window.openReviewModal = function () {
  const decisions = ["CLEAR", "SECONDARY_INSPECTION", "SUSPICIOUS", "INCONCLUSIVE"];
  const m = openModal(`
    <div class="modal-head"><h3>Officer Review — ${esc(INV.screening_id)}</h3></div>
    <div class="modal-body">
      <div class="card" style="background:var(--panel-2);margin-bottom:16px">
        <div class="flex"><span class="muted">AI recommendation</span><span class="spacer"></span>${riskBadge(INV.risk_level)} <b style="margin-left:8px">${esc((INV.recommended_action || "").replace(/_/g, " "))}</b></div>
      </div>
      <div class="field"><label>Officer Decision</label>
        <select class="input" id="rDecision">${decisions.map(d => `<option value="${d}">${d.replace(/_/g, " ")}</option>`).join("")}</select></div>
      <div class="field"><label>Reviewer</label><input class="input" id="rReviewer" value="Officer"></div>
      <div class="field"><label>Notes / Justification</label><textarea class="input" id="rNotes" placeholder="e.g. Insufficient image quality for reliable face verification."></textarea></div>
      <label class="hint" style="display:flex;align-items:center;gap:8px"><input type="checkbox" id="rCase"> Open a case for this screening</label>
    </div>
    <div class="modal-foot"><button class="btn ghost" onclick="closeModal()">Cancel</button><button class="btn primary" id="rSubmit">Submit Decision</button></div>`);
  m.querySelector("#rSubmit").onclick = async () => {
    try {
      await API.createReview({
        investigation_id: Number(INV.id), decision: m.querySelector("#rDecision").value,
        reviewer: m.querySelector("#rReviewer").value, notes: m.querySelector("#rNotes").value,
        create_case: m.querySelector("#rCase").checked,
      });
      closeModal(); toast("Decision recorded", "Officer review saved.", "success"); loadInvestigation(); refreshBadges();
    } catch (e) { toast("Failed", e.message, "error"); }
  };
};

async function generateReport() {
  const btn = document.getElementById("reportBtn"); btn.disabled = true; btn.innerHTML = `<span class="spin"></span> Generating…`;
  try {
    const r = await API.generateReport(INV.id);
    toast("Report generated", r.filename, "success");
    window.open(r.url, "_blank");
  } catch (e) { toast("Report failed", e.message, "error"); }
  btn.disabled = false; btn.innerHTML = "Generate Report";
}

function riskColor(l) { return { LOW: "var(--low)", MEDIUM: "var(--medium)", HIGH: "var(--high)", CRITICAL: "var(--critical)" }[l] || "var(--text)"; }
window.addEventListener("beforeunload", () => { if (_invPoll) clearInterval(_invPoll); });
