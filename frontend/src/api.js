const BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

async function request(path, options = {}) {
  const resp = await fetch(`${BASE_URL}${path}`, options);
  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const body = await resp.json();
      detail = body.detail || JSON.stringify(body);
    } catch {
      // ignore parse failure, fall back to statusText
    }
    throw new Error(detail);
  }
  if (resp.status === 204) return null;
  return resp.json();
}

function json(method, path, body) {
  return request(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export const api = {
  // column mappings
  listMappingProfiles: () => request("/api/column-mappings"),
  createMappingProfile: (payload) => json("POST", "/api/column-mappings", payload),

  // uploads
  previewUpload: (file) => {
    const form = new FormData();
    form.append("file", file);
    return request("/api/uploads/preview", { method: "POST", body: form });
  },
  createUpload: (file, mappingProfileId, bankAccountOverride) => {
    const form = new FormData();
    form.append("file", file);
    form.append("mapping_profile_id", mappingProfileId);
    if (bankAccountOverride) form.append("bank_account_override", bankAccountOverride);
    return request("/api/uploads", { method: "POST", body: form });
  },
  listUploads: () => request("/api/uploads"),

  // transactions
  listTransactions: (params = {}) => {
    const query = new URLSearchParams(
      Object.fromEntries(Object.entries(params).filter(([, v]) => v !== undefined && v !== ""))
    ).toString();
    return request(`/api/transactions${query ? `?${query}` : ""}`);
  },
  getTransaction: (id) => request(`/api/transactions/${id}`),
  reviewTransaction: (id, payload) => json("POST", `/api/transactions/${id}/review`, payload),

  // classification
  runClassification: (batchId) => json("POST", "/api/classification/run", { batch_id: batchId || null }),
  listClassificationRules: () => request("/api/classification/rules"),

  // chart of accounts
  listChartOfAccounts: () => request("/api/chart-of-accounts"),

  // P&L
  listPeriods: () => request("/api/pnl/periods"),
  getPnl: (period) => request(`/api/pnl/${period}`),
  getPnlLineTransactions: (period, accountCode) => request(`/api/pnl/${period}/accounts/${accountCode}/transactions`),

  // QBO
  getQboStatus: () => request("/api/qbo/status"),
  getQboConnectUrl: () => request("/api/qbo/connect"),
  syncQboAccounts: () => json("POST", "/api/qbo/accounts/sync", {}),
  runQboSync: (batchId) => request(`/api/qbo/sync${batchId ? `?batch_id=${batchId}` : ""}`, { method: "POST" }),

  // reconciliation
  getReconciliation: (period) => request(`/api/reconciliation/${period}`),
};
