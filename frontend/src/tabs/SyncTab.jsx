import { useEffect, useState } from "react";
import { api } from "../api";

export function SyncTab() {
  const [status, setStatus] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [accountsResult, setAccountsResult] = useState(null);
  const [syncResult, setSyncResult] = useState(null);

  const refreshStatus = () => api.getQboStatus().then(setStatus).catch((e) => setError(e.message));

  useEffect(() => {
    refreshStatus();
  }, []);

  const connect = async () => {
    setError(null);
    try {
      const { authorization_url } = await api.getQboConnectUrl();
      window.open(authorization_url, "_blank", "noopener");
    } catch (err) {
      setError(err.message);
    }
  };

  const syncAccounts = async () => {
    setBusy(true);
    setError(null);
    try {
      setAccountsResult(await api.syncQboAccounts());
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const runSync = async () => {
    setBusy(true);
    setError(null);
    try {
      setSyncResult(await api.runQboSync());
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="panel">
      <h3>QuickBooks Online sync</h3>
      {error && <div className="error-box">{error}</div>}

      <p>
        Connection status:{" "}
        {status?.connected ? <span className="badge synced">connected (realm {status.realm_id})</span> : <span className="badge needs_review">not connected</span>}
      </p>

      <div className="row" style={{ marginBottom: "1rem" }}>
        <button className="btn" onClick={connect}>
          Connect to QuickBooks
        </button>
        <button className="btn secondary" disabled={busy} onClick={syncAccounts}>
          1. Sync chart-of-accounts IDs
        </button>
        <button className="btn secondary" disabled={busy} onClick={runSync}>
          2. Sync approved transactions
        </button>
        <button className="btn secondary" onClick={refreshStatus}>
          Refresh status
        </button>
      </div>

      <p className="muted">
        Connecting opens Intuit's authorization page in a new tab - log into your sandbox company and approve access, then come back
        and refresh status. See <code>connect_flow.md</code> for the full one-time setup. Only reviewed/corrected transactions, or
        auto-classified ones above the confidence threshold, are eligible to sync; already-synced transactions are never re-posted.
      </p>

      {accountsResult && (
        <div className="panel" style={{ marginTop: "0.75rem" }}>
          <strong>Account mapping:</strong> matched {accountsResult.matched}/{accountsResult.total}.
          {accountsResult.unmatched_account_numbers.length > 0 && (
            <p className="muted">Unmatched: {accountsResult.unmatched_account_numbers.join(", ")} - check these accounts exist in the sandbox.</p>
          )}
        </div>
      )}

      {syncResult && (
        <div className="panel" style={{ marginTop: "0.75rem" }}>
          <div className="kpi-row">
            <div className="kpi">
              <div className="label">Synced</div>
              <div className="value">{syncResult.synced}</div>
            </div>
            <div className="kpi">
              <div className="label">Linked (transfer pairs)</div>
              <div className="value">{syncResult.linked}</div>
            </div>
            <div className="kpi">
              <div className="label">Failed</div>
              <div className="value">{syncResult.failed}</div>
            </div>
          </div>
          {syncResult.failures.length > 0 && (
            <table>
              <thead>
                <tr>
                  <th>Transaction</th>
                  <th>Error</th>
                </tr>
              </thead>
              <tbody>
                {syncResult.failures.map((f) => (
                  <tr key={f.transaction_id}>
                    <td>{f.transaction_id}</td>
                    <td className="explain">{f.error}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}
