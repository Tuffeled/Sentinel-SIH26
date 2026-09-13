/* SENTINEL API client */
const API_BASE = "/api";

async function apiFetch(path, opts = {}) {
  const res = await fetch(API_BASE + path, opts);
  const ct = res.headers.get("content-type") || "";
  const data = ct.includes("application/json") ? await res.json() : await res.text();
  if (!res.ok) {
    const msg = (data && data.detail) ? data.detail : `Request failed (${res.status})`;
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return data;
}

const API = {
  health: () => apiFetch("/health"),

  // Documents / screening
  upload: (formData) => apiFetch("/documents/upload", { method: "POST", body: formData }),
  getDocument: (id) => apiFetch(`/documents/${id}`),
  analyzeDocument: (id) => apiFetch(`/documents/${id}/analyze`, { method: "POST" }),

  // Analysis
  analysisStatus: (id) => apiFetch(`/analysis/${id}/status`),
  analysisResult: (id) => apiFetch(`/analysis/${id}`),

  // Investigations
  createInvestigation: (body) => apiFetch("/investigations", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  listInvestigations: (q = "") => apiFetch("/investigations" + (q ? `?${q}` : "")),
  getInvestigation: (id) => apiFetch(`/investigations/${id}`),
  reanalyze: (id) => apiFetch(`/investigations/${id}/analyze`, { method: "POST" }),

  // Compare
  compare: (a, b) => apiFetch(`/compare?a=${a}&b=${b}`),

  // Reviews
  createReview: (body) => apiFetch("/reviews", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  listReviews: (invId) => apiFetch("/reviews" + (invId ? `?investigation_id=${invId}` : "")),

  // Cases
  listCases: (q = "") => apiFetch("/cases" + (q ? `?${q}` : "")),
  createCase: (body) => apiFetch("/cases", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  getCase: (id) => apiFetch(`/cases/${id}`),
  updateCase: (id, body) => apiFetch(`/cases/${id}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),

  // Watchlist
  listWatchlist: (q = "") => apiFetch("/watchlist" + (q ? `?${q}` : "")),
  searchWatchlist: (num) => apiFetch(`/watchlist/search?document_number=${encodeURIComponent(num)}`),
  createWatchlist: (body) => apiFetch("/watchlist", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  updateWatchlist: (id, body) => apiFetch(`/watchlist/${id}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  deactivateWatchlist: (id) => apiFetch(`/watchlist/${id}`, { method: "DELETE" }),
  seedWatchlist: () => apiFetch("/watchlist/seed-demo", { method: "POST" }),

  // Dashboard
  dashboardOverview: () => apiFetch("/dashboard/overview"),
  dashboardStats: () => apiFetch("/dashboard/stats"),

  // Evaluation
  runEvaluation: () => apiFetch("/evaluation/run", { method: "POST" }),
  latestEvaluation: () => apiFetch("/evaluation/latest"),
  evaluationDataset: () => apiFetch("/evaluation/dataset"),

  // Reports
  generateReport: (invId) => apiFetch(`/reports/${invId}`, { method: "POST" }),

  // Notifications
  listNotifications: () => apiFetch("/notifications"),
  markNotificationRead: (id) => apiFetch(`/notifications/${id}/read`, { method: "POST" }),
  markAllNotificationsRead: () => apiFetch("/notifications/read-all", { method: "POST" }),

  // Search
  search: (q) => apiFetch(`/search?q=${encodeURIComponent(q)}`),

  // Settings
  getSettings: () => apiFetch("/settings"),
  seedDemo: () => apiFetch("/settings/seed-demo", { method: "POST" }),
  clearDemo: () => apiFetch("/settings/clear-demo?confirm=true", { method: "POST" }),
  resetDemo: () => apiFetch("/settings/reset?confirm=true", { method: "POST" }),
};

window.API = API;
