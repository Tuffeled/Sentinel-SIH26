/* Dashboard page */
let _riskChart, _trendChart;

const RISK_COLORS = { LOW: "#22C55E", MEDIUM: "#F59E0B", HIGH: "#F97316", CRITICAL: "#EF4444" };

function chartTheme() {
  if (window.Chart) {
    Chart.defaults.color = "#94A3B8";
    Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
    Chart.defaults.borderColor = "rgba(38,54,77,0.6)";
  }
}

window.PAGE_INIT = async function () {
  chartTheme();
  const c = document.getElementById("content");
  c.innerHTML = `
    <div class="page-head">
      <div class="titles">
        <h1>Screening Operations</h1>
        <p>Monitor document verification activity and detected anomalies.</p>
      </div>
      <div class="actions">
        <button class="btn ghost" id="refreshBtn">Refresh</button>
        <a class="btn primary" href="screening.html">+ New Screening</a>
      </div>
    </div>

    <div class="grid stats" id="statCards"></div>

    <div class="grid c2 mt-16">
      <div class="card">
        <div class="card-head"><div><div class="card-title">Risk Distribution</div><div class="card-sub">Across completed screenings</div></div></div>
        <div style="position:relative;height:240px"><canvas id="riskChart"></canvas></div>
        <div id="riskLegend" class="flex wrap" style="justify-content:center;margin-top:8px;font-size:12px"></div>
      </div>
      <div class="card">
        <div class="card-head"><div><div class="card-title">7-Day Screening Trend</div><div class="card-sub">Documents screened vs flagged</div></div></div>
        <div style="position:relative;height:240px"><canvas id="trendChart"></canvas></div>
      </div>
    </div>

    <div class="card mt-16 pad-0">
      <div class="card-head" style="padding:16px 18px 0"><div><div class="card-title">Live Screening Activity</div><div class="card-sub">Most recent screenings</div></div>
        <div class="actions"><a class="link" href="history.html">View all →</a></div></div>
      <div class="table-wrap" style="margin-top:12px">
        <table class="tbl" id="activityTbl">
          <thead><tr><th>Time</th><th>Screening ID</th><th>Document</th><th>Type</th><th>Status</th><th>Risk</th><th></th></tr></thead>
          <tbody><tr><td colspan="7"><div class="spinner-lg"></div></td></tr></tbody>
        </table>
      </div>
    </div>`;

  document.getElementById("refreshBtn").onclick = load;
  await load();
  window.__dashTimer = setInterval(load, 5000);
};

async function load() {
  let data;
  try { data = await API.dashboardOverview(); }
  catch (e) { return; }
  renderStats(data.stats);
  renderRisk(data.risk_distribution);
  renderTrend(data.trends);
  renderActivity(data.activity);
}

function statCard(label, value, foot, color, dec, suffix) {
  return `<div class="stat">
    <div class="label">${esc(label)}</div>
    <div class="value" data-val="${value}" data-dec="${dec || 0}" data-suffix="${suffix || ""}" style="color:${color || "var(--text)"}">0</div>
    <div class="foot">${esc(foot || "")}</div>
  </div>`;
}

let _statsRendered = false;
function renderStats(s) {
  const cards = [
    statCard("Documents Screened", s.documents_screened, `${num(s.total_screenings)} screenings total`, "var(--text)"),
    statCard("Flagged for Review", s.flagged_for_review, "Awaiting officer action", "var(--warning)"),
    statCard("High Risk Cases", s.high_risk_cases, "High / Critical risk", "var(--danger)"),
    statCard("Avg Screening Time", s.avg_screening_time_sec, "Per document", "var(--accent)", 1, " sec"),
  ];
  const wrap = document.getElementById("statCards");
  if (!_statsRendered) {
    wrap.innerHTML = cards.join("");
    wrap.querySelectorAll(".value").forEach(v => countUp(v, Number(v.dataset.val), { dec: Number(v.dataset.dec), suffix: v.dataset.suffix }));
    _statsRendered = true;
  } else {
    const vals = [s.documents_screened, s.flagged_for_review, s.high_risk_cases, s.avg_screening_time_sec];
    wrap.querySelectorAll(".value").forEach((v, i) => {
      const cur = parseFloat(v.textContent.replace(/[^0-9.]/g, "")) || 0;
      if (cur !== vals[i]) countUp(v, vals[i], { dec: Number(v.dataset.dec), suffix: v.dataset.suffix });
    });
  }
}

function renderRisk(dist) {
  const labels = ["LOW", "MEDIUM", "HIGH", "CRITICAL"];
  const values = labels.map(l => dist[l] || 0);
  const total = values.reduce((a, b) => a + b, 0);
  const legend = document.getElementById("riskLegend");
  legend.innerHTML = labels.map((l, i) => `<span style="display:inline-flex;align-items:center;gap:6px;margin:0 6px"><span style="width:9px;height:9px;border-radius:50%;background:${RISK_COLORS[l]}"></span>${l} <b>${values[i]}</b></span>`).join("");
  const ctx = document.getElementById("riskChart");
  const cfg = {
    type: "doughnut",
    data: { labels, datasets: [{ data: total ? values : [1, 1, 1, 1], backgroundColor: labels.map(l => RISK_COLORS[l]), borderColor: "#111B2B", borderWidth: 3, hoverOffset: 6 }] },
    options: { cutout: "68%", plugins: { legend: { display: false }, tooltip: { enabled: total > 0 } }, animation: { duration: 500 } },
  };
  if (_riskChart) { _riskChart.data.datasets[0].data = total ? values : [1, 1, 1, 1]; _riskChart.update(); }
  else _riskChart = new Chart(ctx, cfg);
  drawCenter(total);
}
function drawCenter(total) {
  const wrap = document.getElementById("riskChart").parentElement;
  let c = wrap.querySelector(".donut-center");
  if (!c) { c = el(`<div class="donut-center" style="position:absolute;inset:0;display:grid;place-items:center;pointer-events:none"></div>`); wrap.appendChild(c); }
  c.innerHTML = `<div style="text-align:center"><div style="font-size:30px;font-weight:750">${total}</div><div class="muted" style="font-size:11px;text-transform:uppercase;letter-spacing:.05em">Screenings</div></div>`;
}

function renderTrend(series) {
  const labels = series.map(d => new Date(d.date).toLocaleDateString("en-US", { weekday: "short" }));
  const screened = series.map(d => d.screened);
  const flagged = series.map(d => d.flagged);
  const ctx = document.getElementById("trendChart");
  if (_trendChart) {
    _trendChart.data.labels = labels;
    _trendChart.data.datasets[0].data = screened;
    _trendChart.data.datasets[1].data = flagged;
    _trendChart.update();
    return;
  }
  _trendChart = new Chart(ctx, {
    type: "line",
    data: { labels, datasets: [
      { label: "Screened", data: screened, borderColor: "#3B82F6", backgroundColor: "rgba(59,130,246,0.12)", fill: true, tension: 0.35, pointRadius: 3 },
      { label: "Flagged", data: flagged, borderColor: "#EF4444", backgroundColor: "rgba(239,68,68,0.10)", fill: true, tension: 0.35, pointRadius: 3 },
    ]},
    options: { plugins: { legend: { position: "bottom", labels: { boxWidth: 10, usePointStyle: true } } },
      scales: { y: { beginAtZero: true, ticks: { precision: 0 }, grid: { color: "rgba(38,54,77,0.4)" } }, x: { grid: { display: false } } } },
  });
}

function renderActivity(rows) {
  const tb = document.querySelector("#activityTbl tbody");
  if (!rows.length) { tb.innerHTML = `<tr><td colspan="7"><div class="empty"><div class="big">◎</div>No screenings yet. Start a <a class="link" href="screening.html">new screening</a> or seed demo data in Settings.</div></td></tr>`; return; }
  tb.innerHTML = rows.map(r => `
    <tr>
      <td class="mono nowrap">${fmtTime(r.time)}</td>
      <td class="mono">${esc(r.screening_id)}</td>
      <td>${esc(r.document)}</td>
      <td>${badge(r.type || "UNKNOWN", "accent")}</td>
      <td>${badge(r.status)}${r.watchlist_hit ? " " + badge("WL", "critical") : ""}</td>
      <td>${riskBadge(r.risk)}</td>
      <td><a class="link" href="investigation.html?id=${r.investigation_id}">View</a></td>
    </tr>`).join("");
}

window.addEventListener("beforeunload", () => { if (window.__dashTimer) clearInterval(window.__dashTimer); });
