/* Screening History + genuine/altered compare */
let _selected = [];

window.PAGE_INIT = function () {
  document.getElementById("content").innerHTML = `
    <div class="page-head">
      <div class="titles"><h1>Screening History</h1><p>All document screenings with filters, search and comparison.</p></div>
      <div class="actions"><button class="btn ghost" id="compareBtn" disabled>Compare selected (0)</button><a class="btn primary" href="screening.html">+ New Screening</a></div>
    </div>
    <div class="card mb-12">
      <div class="filters">
        <input class="input" id="fSearch" placeholder="Search ID, filename, document number…">
        <select class="input" id="fRisk"><option value="">All risk</option><option>LOW</option><option>MEDIUM</option><option>HIGH</option><option>CRITICAL</option></select>
        <select class="input" id="fStatus"><option value="">All status</option><option>VERIFIED</option><option>REVIEW</option><option>FLAGGED</option><option>REVIEWED</option></select>
        <select class="input" id="fType"><option value="">All types</option><option value="PASSPORT">Passport</option><option value="NATIONAL_ID">National ID</option><option value="VISA">Visa</option></select>
        <input class="input" id="fFrom" type="date" title="From date">
        <button class="btn ghost" id="clearF">Clear</button>
      </div>
    </div>
    <div class="card pad-0">
      <div class="table-wrap">
        <table class="tbl" id="histTbl">
          <thead><tr><th style="width:32px"></th><th>Screening ID</th><th>Date</th><th>Type</th><th>Document No.</th><th>Risk</th><th>Status</th><th>Watchlist</th><th>Officer</th><th></th></tr></thead>
          <tbody><tr><td colspan="10"><div class="spinner-lg"></div></td></tr></tbody>
        </table>
      </div>
    </div>`;

  const run = debounce(load, 250);
  ["fSearch", "fRisk", "fStatus", "fType", "fFrom"].forEach(id => document.getElementById(id).addEventListener("input", run));
  document.getElementById("clearF").onclick = () => { ["fSearch", "fRisk", "fStatus", "fType", "fFrom"].forEach(id => document.getElementById(id).value = ""); load(); };
  document.getElementById("compareBtn").onclick = doCompare;
  load();
};

async function load() {
  const params = new URLSearchParams();
  const v = (id) => document.getElementById(id).value;
  if (v("fSearch")) params.set("search", v("fSearch"));
  if (v("fRisk")) params.set("risk", v("fRisk"));
  if (v("fStatus")) params.set("status", v("fStatus"));
  if (v("fType")) params.set("document_type", v("fType"));
  if (v("fFrom")) params.set("date_from", v("fFrom"));
  params.set("limit", "200");
  const tb = document.querySelector("#histTbl tbody");
  try {
    const data = await API.listInvestigations(params.toString());
    if (!data.investigations.length) { tb.innerHTML = `<tr><td colspan="10"><div class="empty">No screenings match your filters.</div></td></tr>`; return; }
    tb.innerHTML = data.investigations.map(i => `
      <tr>
        <td><input type="checkbox" data-sel="${i.id}" ${_selected.includes(i.id) ? "checked" : ""}></td>
        <td class="mono">${esc(i.screening_id)}</td>
        <td class="nowrap">${fmtDateTime(i.created_at)}</td>
        <td>${badge(i.document_type || "UNKNOWN", "accent")}</td>
        <td class="mono">${esc(i.document_number || "—")}</td>
        <td>${riskBadge(i.risk_level)}</td>
        <td>${badge(i.screening_status)}</td>
        <td>${i.watchlist_hit ? badge("MATCH", "critical") : `<span class="muted">—</span>`}</td>
        <td>${esc(i.assigned_officer || "—")}</td>
        <td><a class="link" href="investigation.html?id=${i.id}">View</a></td>
      </tr>`).join("");
    tb.querySelectorAll("[data-sel]").forEach(cb => cb.onchange = () => toggleSel(Number(cb.dataset.sel), cb.checked));
  } catch (e) { tb.innerHTML = `<tr><td colspan="10"><div class="empty">${esc(e.message)}</div></td></tr>`; }
}

function toggleSel(id, on) {
  if (on) { if (_selected.length >= 2) { _selected.shift(); document.querySelectorAll(`[data-sel]`).forEach(cb => { if (!_selected.includes(Number(cb.dataset.sel))) cb.checked = false; }); } _selected.push(id); }
  else _selected = _selected.filter(x => x !== id);
  const btn = document.getElementById("compareBtn");
  btn.textContent = `Compare selected (${_selected.length})`;
  btn.disabled = _selected.length !== 2;
}

async function doCompare() {
  try {
    const [a, b] = await Promise.all(_selected.map(id => API.getInvestigation(id)));
    const docA = a.documents[0], docB = b.documents[0];
    const cmp = await API.compare(docA.id, docB.id);
    renderCompare(cmp);
  } catch (e) { toast("Compare failed", e.message, "error"); }
}

function renderCompare(cmp) {
  const side = (s, label) => `
    <div style="flex:1;min-width:0">
      <div class="section-title">${label}</div>
      <div class="forensic-img-wrap" style="max-height:220px"><img src="/api/documents/${s.document.id}/image"></div>
      <div class="flex mt-12" style="justify-content:space-between"><span class="mono">${esc(s.risk.screening_id || "")}</span>${riskBadge(s.risk.risk_level)}</div>
      <div class="hint">Risk ${Math.round(s.risk.risk_score || 0)}/100 · MRZ ${s.mrz.valid ? "valid" : (s.mrz.detected ? "FAILED" : "none")} · forensic ${(s.forensic.overall_score || 0).toFixed(2)}</div>
    </div>`;
  const diffs = cmp.field_diffs.map(d => `<tr><td>${esc(d.label)}</td><td class="mono">${esc(d.a || "—")}</td><td class="mono">${esc(d.b || "—")}</td><td>${badge(d.same ? "SAME" : "DIFFERENT", d.same ? "match" : "mismatch")}</td></tr>`).join("");
  openModal(`
    <div class="modal-head"><h3>Document Comparison</h3><button class="btn sm ghost" style="margin-left:auto" onclick="closeModal()">✕</button></div>
    <div class="modal-body">
      <div class="flex" style="gap:20px;align-items:flex-start">${side(cmp.a, "Document A")}${side(cmp.b, "Document B")}</div>
      <div class="section-title mt-16">Field Comparison</div>
      <div class="table-wrap"><table class="tbl"><thead><tr><th>Field</th><th>A</th><th>B</th><th>Result</th></tr></thead><tbody>${diffs}</tbody></table></div>
      ${cmp.differences.length ? `<div class="disclaimer mt-12">${cmp.differences.length} field difference(s) detected between the documents.</div>` : `<div class="disclaimer mt-12">Documents are field-consistent.</div>`}
    </div>`, { wide: true });
}
