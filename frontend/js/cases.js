/* Cases */
window.PAGE_INIT = function () {
  document.getElementById("content").innerHTML = `
    <div class="page-head">
      <div class="titles"><h1>Cases</h1><p>Investigations grouped for review, escalation and resolution.</p></div>
      <div class="actions"><select class="input" id="fStatus" style="width:auto"><option value="">All status</option><option>OPEN</option><option>UNDER_REVIEW</option><option>ESCALATED</option><option>RESOLVED</option></select></div>
    </div>
    <div class="grid stats" id="caseStats"></div>
    <div class="card pad-0 mt-16">
      <div class="table-wrap"><table class="tbl" id="caseTbl">
        <thead><tr><th>Case ID</th><th>Title</th><th>Status</th><th>Risk</th><th>Documents</th><th>Officer</th><th>Updated</th><th></th></tr></thead>
        <tbody><tr><td colspan="8"><div class="spinner-lg"></div></td></tr></tbody>
      </table></div>
    </div>`;
  document.getElementById("fStatus").onchange = load;
  load();
};

async function load() {
  const status = document.getElementById("fStatus").value;
  const data = await API.listCases(status ? `status=${status}` : "");
  const s = data.stats;
  document.getElementById("caseStats").innerHTML = [
    ["Total Cases", s.total, "var(--text)"], ["Open", s.open, "var(--accent)"],
    ["Escalated", s.escalated, "var(--danger)"], ["Resolved", s.resolved, "var(--success)"],
  ].map(([l, v, c]) => `<div class="stat"><div class="label">${l}</div><div class="value" style="color:${c}">${v}</div></div>`).join("");
  const tb = document.querySelector("#caseTbl tbody");
  if (!data.cases.length) { tb.innerHTML = `<tr><td colspan="8"><div class="empty">No cases. Open one from an investigation's Officer Review.</div></td></tr>`; return; }
  tb.innerHTML = data.cases.map(c => `
    <tr>
      <td class="mono">${esc(c.case_id)}</td>
      <td>${esc(c.title)}</td>
      <td>${badge(c.status, slug(c.status))}</td>
      <td>${riskBadge(c.risk_level)}</td>
      <td>${c.document_count || 0}</td>
      <td>${esc(c.assigned_officer || "—")}</td>
      <td class="nowrap">${fmtDateTime(c.updated_at)}</td>
      <td><a class="link" data-case="${c.id}">Manage</a></td>
    </tr>`).join("");
  tb.querySelectorAll("[data-case]").forEach(a => a.onclick = () => openCase(Number(a.dataset.case)));
}

async function openCase(id) {
  const c = await API.getCase(id);
  const invs = c.investigations || [];
  openModal(`
    <div class="modal-head"><h3 class="mono">${esc(c.case_id)}</h3><button class="btn sm ghost" style="margin-left:auto" onclick="closeModal()">✕</button></div>
    <div class="modal-body">
      <div class="field"><label>Title</label><input class="input" id="cTitle" value="${esc(c.title)}"></div>
      <div class="grid c2">
        <div class="field"><label>Status</label><select class="input" id="cStatus">${["OPEN","UNDER_REVIEW","ESCALATED","RESOLVED"].map(s => `<option ${s === c.status ? "selected" : ""}>${s}</option>`).join("")}</select></div>
        <div class="field"><label>Assigned Officer</label><input class="input" id="cOfficer" value="${esc(c.assigned_officer || "")}"></div>
      </div>
      <div class="field"><label>Summary</label><textarea class="input" id="cSummary">${esc(c.summary || "")}</textarea></div>
      <div class="section-title">Linked Investigations</div>
      ${invs.length ? invs.map(i => `<div class="flex" style="padding:6px 0;border-bottom:1px solid var(--border-soft)"><a class="link mono" href="investigation.html?id=${i.id}">${esc(i.screening_id)}</a>${riskBadge(i.risk_level)}<span class="spacer"></span>${badge(i.screening_status)}</div>`).join("") : `<div class="hint">No linked investigations.</div>`}
    </div>
    <div class="modal-foot"><button class="btn ghost" onclick="closeModal()">Cancel</button><button class="btn primary" id="cSave">Save Changes</button></div>`, { wide: true });
  document.getElementById("cSave").onclick = async () => {
    await API.updateCase(id, {
      title: document.getElementById("cTitle").value, status: document.getElementById("cStatus").value,
      assigned_officer: document.getElementById("cOfficer").value, summary: document.getElementById("cSummary").value,
    });
    closeModal(); toast("Case updated", "", "success"); load();
  };
}
