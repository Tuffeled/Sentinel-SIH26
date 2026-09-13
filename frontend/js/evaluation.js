/* Evaluation — real metrics from the synthetic dataset */
let _cmChart;

window.PAGE_INIT = async function () {
  if (window.Chart) { Chart.defaults.color = "#94A3B8"; }
  document.getElementById("content").innerHTML = `
    <div class="page-head">
      <div class="titles"><h1>Dataset Evaluation</h1><p>Detection metrics computed by running the real pipeline over the synthetic genuine/altered dataset.</p></div>
      <div class="actions"><button class="btn primary" id="runBtn">Run Evaluation</button></div>
    </div>
    <div id="evalBody"><div class="empty"><div class="big">▤</div>Loading latest evaluation…</div></div>`;
  document.getElementById("runBtn").onclick = run;
  try {
    const latest = await API.latestEvaluation();
    if (latest.available) render(latest); else showDataset();
  } catch (e) { showDataset(); }
};

async function showDataset() {
  try {
    const ds = await API.evaluationDataset();
    document.getElementById("evalBody").innerHTML = `
      <div class="card"><div class="card-title mb-12">Synthetic Dataset</div>
        <div class="grid stats">
          <div class="stat"><div class="label">Documents</div><div class="value">${ds.count}</div></div>
          <div class="stat"><div class="label">Genuine</div><div class="value" style="color:var(--success)">${ds.genuine}</div></div>
          <div class="stat"><div class="label">Altered</div><div class="value" style="color:var(--danger)">${ds.altered}</div></div>
        </div>
        <div class="hint mt-16">${ds.count ? "Click <b>Run Evaluation</b> to compute metrics." : "No labelled dataset found — generate it with generate_synthetic_docs.py."}</div>
      </div>`;
  } catch (e) { document.getElementById("evalBody").innerHTML = `<div class="empty">${esc(e.message)}</div>`; }
}

async function run() {
  const btn = document.getElementById("runBtn"); btn.disabled = true; btn.innerHTML = `<span class="spin"></span> Running…`;
  try { const r = await API.runEvaluation(); render(r); toast("Evaluation complete", `${r.documents_tested} documents tested`, "success"); }
  catch (e) { toast("Evaluation failed", e.message, "error"); }
  btn.disabled = false; btn.innerHTML = "Run Evaluation";
}

function pct(x) { return (x * 100).toFixed(1) + "%"; }

function render(r) {
  if (r.error) { document.getElementById("evalBody").innerHTML = `<div class="card"><div class="empty">${esc(r.error)}</div></div>`; return; }
  const m = r.metrics, cm = r.confusion_matrix;
  document.getElementById("evalBody").innerHTML = `
    <div class="grid stats">
      <div class="stat"><div class="label">Documents Tested</div><div class="value">${r.documents_tested}</div><div class="foot">${r.genuine} genuine · ${r.altered} altered</div></div>
      <div class="stat"><div class="label">Accuracy</div><div class="value" style="color:var(--accent)">${pct(m.accuracy)}</div></div>
      <div class="stat"><div class="label">Precision</div><div class="value">${pct(m.precision)}</div></div>
      <div class="stat"><div class="label">Recall</div><div class="value">${pct(m.recall)}</div></div>
    </div>
    <div class="grid c2 mt-16">
      <div class="card">
        <div class="card-title mb-12">Confusion Matrix</div>
        <table class="tbl" style="text-align:center">
          <thead><tr><th></th><th>Pred. Altered</th><th>Pred. Genuine</th></tr></thead>
          <tbody>
            <tr><th>Actual Altered</th><td style="background:rgba(34,197,94,0.12);font-size:20px;font-weight:700">${cm.tp}<div class="hint">TP</div></td><td style="background:rgba(239,68,68,0.12);font-size:20px;font-weight:700">${cm.fn}<div class="hint">FN</div></td></tr>
            <tr><th>Actual Genuine</th><td style="background:rgba(239,68,68,0.12);font-size:20px;font-weight:700">${cm.fp}<div class="hint">FP</div></td><td style="background:rgba(34,197,94,0.12);font-size:20px;font-weight:700">${cm.tn}<div class="hint">TN</div></td></tr>
          </tbody>
        </table>
        <div class="grid c2 mt-16">
          <div><div class="hint">F1 Score</div><b style="font-size:18px">${pct(m.f1)}</b></div>
          <div><div class="hint">False Positive Rate</div><b style="font-size:18px">${pct(m.false_positive_rate)}</b></div>
          <div><div class="hint">False Negative Rate</div><b style="font-size:18px">${pct(m.false_negative_rate)}</b></div>
          <div><div class="hint">Decision Threshold</div><b style="font-size:18px">≥ ${r.decision_threshold}</b></div>
        </div>
      </div>
      <div class="card">
        <div class="card-title mb-12">Detector Breakdown</div>
        <div class="table-wrap"><table class="tbl">
          <thead><tr><th>Detector</th><th>Recall</th><th>FP</th><th>Precision</th></tr></thead>
          <tbody>${r.detector_breakdown.map(d => `<tr><td>${esc(d.detector)}</td><td>${pct(d.recall)}</td><td>${d.fp}</td><td>${pct(d.precision)}</td></tr>`).join("")}</tbody>
        </table></div>
        <div class="disclaimer mt-12">Metrics are computed live by executing the detection pipeline over the labelled synthetic dataset — never hard-coded.</div>
      </div>
    </div>
    <div class="card mt-16 pad-0">
      <div class="card-head" style="padding:16px 18px 0"><div class="card-title">Per-Document Results</div></div>
      <div class="table-wrap" style="margin-top:12px"><table class="tbl">
        <thead><tr><th>File</th><th>Ground Truth</th><th>Predicted</th><th>Outcome</th><th>Risk</th><th>Detectors Fired</th></tr></thead>
        <tbody>${r.samples.map(s => `<tr>
          <td class="mono">${esc(s.file)}</td>
          <td>${badge(s.ground_truth, slug(s.ground_truth))}</td>
          <td>${badge(s.predicted, slug(s.predicted))}</td>
          <td>${badge(s.outcome, outcomeCls(s.outcome))}</td>
          <td>${Math.round(s.risk_score)} ${riskBadge(s.risk_level)}</td>
          <td class="hint">${s.detectors.join(", ") || "—"}</td>
        </tr>`).join("")}</tbody>
      </table></div>
    </div>
    <div class="hint mt-12">Run ID: <span class="mono">${esc(r.id)}</span> · ${fmtDateTime(r.created_at)}</div>`;
}

function outcomeCls(o) { return { TP: "low", TN: "low", FP: "critical", FN: "critical" }[o] || "na"; }
