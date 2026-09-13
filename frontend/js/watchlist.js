/* Watchlist (synthetic demo) */
window.PAGE_INIT = function () {
  document.getElementById("content").innerHTML = `
    <div class="page-head">
      <div class="titles"><h1>Watchlist <span class="badge accent" style="vertical-align:middle">Synthetic Demo</span></h1><p>Local synthetic watchlist — not connected to any real database.</p></div>
      <div class="actions"><button class="btn ghost" id="seedBtn">Seed Demo</button><button class="btn primary" id="addBtn">+ Add Record</button></div>
    </div>
    <div class="grid stats" id="wlStats"></div>
    <div class="card mt-16 mb-12">
      <div class="filters">
        <input class="input" id="fSearch" placeholder="Search document number, reason…">
        <select class="input" id="fStatus"><option value="">All status</option><option>FLAGGED</option><option>STOLEN</option><option>LOST</option><option>SUSPICIOUS</option><option>DUPLICATE</option><option>REVOKED</option><option>UNDER_REVIEW</option></select>
      </div>
    </div>
    <div class="card pad-0">
      <div class="table-wrap"><table class="tbl" id="wlTbl">
        <thead><tr><th>Document Number</th><th>Type</th><th>Status</th><th>Reason</th><th>Source</th><th>Added</th><th>Active</th><th></th></tr></thead>
        <tbody><tr><td colspan="8"><div class="spinner-lg"></div></td></tr></tbody>
      </table></div>
    </div>`;
  const run = debounce(load, 250);
  document.getElementById("fSearch").addEventListener("input", run);
  document.getElementById("fStatus").addEventListener("change", load);
  document.getElementById("addBtn").onclick = () => openForm();
  document.getElementById("seedBtn").onclick = async () => { await API.seedWatchlist(); toast("Watchlist seeded", "", "success"); load(); };
  load();
};

async function load() {
  const p = new URLSearchParams();
  if (document.getElementById("fSearch").value) p.set("search", document.getElementById("fSearch").value);
  if (document.getElementById("fStatus").value) p.set("status", document.getElementById("fStatus").value);
  const data = await API.listWatchlist(p.toString());
  const s = data.stats;
  document.getElementById("wlStats").innerHTML = [
    ["Total Records", s.total, "var(--text)"], ["Active", s.active, "var(--success)"],
    ["Flagged", s.flagged, "var(--warning)"], ["Stolen / Lost", s.stolen_lost, "var(--danger)"],
  ].map(([l, v, c]) => `<div class="stat"><div class="label">${l}</div><div class="value" style="color:${c}">${v}</div></div>`).join("");
  const tb = document.querySelector("#wlTbl tbody");
  if (!data.records.length) { tb.innerHTML = `<tr><td colspan="8"><div class="empty">No records. Click "Seed Demo" to load synthetic records.</div></td></tr>`; return; }
  tb.innerHTML = data.records.map(r => `
    <tr style="${r.active ? "" : "opacity:.5"}">
      <td class="mono">${esc(r.document_number)}</td>
      <td>${badge(r.document_type, "accent")}</td>
      <td>${badge(r.status, slug(r.status))}</td>
      <td style="max-width:280px">${esc(r.reason || "—")}</td>
      <td class="hint">${esc(r.source)}</td>
      <td class="nowrap">${fmtDateTime(r.created_at)}</td>
      <td>${r.active ? badge("ACTIVE", "low") : badge("INACTIVE", "na")}</td>
      <td class="nowrap"><a class="link" data-edit='${encodeURIComponent(JSON.stringify(r))}'>Edit</a> ${r.active ? `· <a class="link" data-off="${r.id}">Deactivate</a>` : ""}</td>
    </tr>`).join("");
  tb.querySelectorAll("[data-edit]").forEach(a => a.onclick = () => openForm(JSON.parse(decodeURIComponent(a.dataset.edit))));
  tb.querySelectorAll("[data-off]").forEach(a => a.onclick = async () => {
    if (await confirmDialog("Deactivate record", "The record is preserved for audit but will no longer match. Continue?", "Deactivate")) {
      await API.deactivateWatchlist(Number(a.dataset.off)); toast("Deactivated", "", "success"); load();
    }
  });
}

function openForm(rec) {
  const r = rec || {};
  openModal(`
    <div class="modal-head"><h3>${rec ? "Edit" : "Add"} Watchlist Record</h3></div>
    <div class="modal-body">
      <div class="field"><label>Document Number</label><input class="input" id="wNum" value="${esc(r.document_number || "")}"></div>
      <div class="grid c2">
        <div class="field"><label>Type</label><select class="input" id="wType">${["PASSPORT","NATIONAL_ID","VISA"].map(t => `<option ${t === r.document_type ? "selected" : ""}>${t}</option>`).join("")}</select></div>
        <div class="field"><label>Status</label><select class="input" id="wStatus">${["FLAGGED","STOLEN","LOST","SUSPICIOUS","DUPLICATE","REVOKED","UNDER_REVIEW"].map(s => `<option ${s === r.status ? "selected" : ""}>${s}</option>`).join("")}</select></div>
      </div>
      <div class="field"><label>Reason</label><textarea class="input" id="wReason">${esc(r.reason || "")}</textarea></div>
      <div class="disclaimer">All records are synthetic demonstration records only.</div>
    </div>
    <div class="modal-foot"><button class="btn ghost" onclick="closeModal()">Cancel</button><button class="btn primary" id="wSave">Save</button></div>`);
  document.getElementById("wSave").onclick = async () => {
    const body = { document_number: document.getElementById("wNum").value, document_type: document.getElementById("wType").value, status: document.getElementById("wStatus").value, reason: document.getElementById("wReason").value };
    try {
      if (rec) await API.updateWatchlist(r.id, body); else await API.createWatchlist(body);
      closeModal(); toast("Saved", "", "success"); load();
    } catch (e) { toast("Failed", e.message, "error"); }
  };
}
