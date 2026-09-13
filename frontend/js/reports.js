/* Reports — generate investigation report PDFs */
window.PAGE_INIT = function () {
  document.getElementById("content").innerHTML = `
    <div class="page-head"><div class="titles"><h1>Reports</h1><p>Generate a full investigation report (PDF) for any screening.</p></div></div>
    <div class="card pad-0">
      <div class="table-wrap"><table class="tbl" id="repTbl">
        <thead><tr><th>Screening ID</th><th>Date</th><th>Type</th><th>Risk</th><th>Status</th><th>Report</th></tr></thead>
        <tbody><tr><td colspan="6"><div class="spinner-lg"></div></td></tr></tbody>
      </table></div>
    </div>`;
  load();
};

async function load() {
  const data = await API.listInvestigations("limit=200");
  const tb = document.querySelector("#repTbl tbody");
  if (!data.investigations.length) { tb.innerHTML = `<tr><td colspan="6"><div class="empty">No screenings yet.</div></td></tr>`; return; }
  tb.innerHTML = data.investigations.map(i => `
    <tr>
      <td class="mono"><a class="link" href="investigation.html?id=${i.id}">${esc(i.screening_id)}</a></td>
      <td class="nowrap">${fmtDateTime(i.created_at)}</td>
      <td>${badge(i.document_type || "UNKNOWN", "accent")}</td>
      <td>${riskBadge(i.risk_level)}</td>
      <td>${badge(i.screening_status)}</td>
      <td><button class="btn sm primary" data-rep="${i.id}">Generate PDF</button></td>
    </tr>`).join("");
  tb.querySelectorAll("[data-rep]").forEach(b => b.onclick = async () => {
    b.disabled = true; b.innerHTML = `<span class="spin"></span>`;
    try { const r = await API.generateReport(Number(b.dataset.rep)); toast("Report ready", r.filename, "success"); window.open(r.url, "_blank"); b.innerHTML = "Open PDF"; b.onclick = () => window.open(r.url, "_blank"); b.disabled = false; }
    catch (e) { toast("Failed", e.message, "error"); b.innerHTML = "Generate PDF"; b.disabled = false; }
  });
}
