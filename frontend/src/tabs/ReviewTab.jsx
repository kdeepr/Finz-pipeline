import { Fragment, useEffect, useState } from "react";
import { api } from "../api";
import { Badge, money } from "../components/Badge";

const TRANSACTION_TYPES = ["revenue", "refund", "cogs", "operating_expense", "transfer", "owner_activity", "fixed_asset", "uncategorized"];

function EditRow({ txn, accounts, onSaved }) {
  const [transactionType, setTransactionType] = useState(txn.transaction_type || "uncategorized");
  const [qboAccount, setQboAccount] = useState(txn.qbo_account || "");
  const [counterparty, setCounterparty] = useState(txn.counterparty || "");
  const [applyToSimilar, setApplyToSimilar] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      await api.reviewTransaction(txn.id, {
        transaction_type: transactionType,
        qbo_account: transactionType === "transfer" ? null : qboAccount || null,
        counterparty: counterparty || null,
        apply_to_similar: applyToSimilar,
      });
      onSaved();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <tr>
      <td colSpan={7}>
        {error && <div className="error-box">{error}</div>}
        <div className="row">
          <select value={transactionType} onChange={(e) => setTransactionType(e.target.value)}>
            {TRANSACTION_TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
          {transactionType !== "transfer" && (
            <select value={qboAccount} onChange={(e) => setQboAccount(e.target.value)}>
              <option value="">(no account)</option>
              {accounts.map((a) => (
                <option key={a["Account No."]} value={a["Account No."]}>
                  {a["Account No."]} - {a["Account Name"]}
                </option>
              ))}
            </select>
          )}
          <input type="text" placeholder="Counterparty" value={counterparty} onChange={(e) => setCounterparty(e.target.value)} />
          <label className="muted">
            <input type="checkbox" checked={applyToSimilar} onChange={(e) => setApplyToSimilar(e.target.checked)} /> Apply to similar
            transactions going forward
          </label>
          <button className="btn" disabled={saving} onClick={save}>
            {saving ? "Saving..." : "Save"}
          </button>
        </div>
      </td>
    </tr>
  );
}

export function ReviewTab() {
  const [status, setStatus] = useState("ok");
  const [query, setQuery] = useState("");
  const [transactions, setTransactions] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [editingId, setEditingId] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [runSummary, setRunSummary] = useState(null);

  const refresh = () => {
    api
      .listTransactions({ status, q: query, limit: 200 })
      .then(setTransactions)
      .catch((e) => setError(e.message));
  };

  useEffect(() => {
    api.listChartOfAccounts().then(setAccounts).catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status]);

  const runClassification = async () => {
    setBusy(true);
    setError(null);
    try {
      setRunSummary(await api.runClassification());
      refresh();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <div className="panel">
        <div className="section-title">
          <h3>Review &amp; classify transactions</h3>
          <button className="btn" disabled={busy} onClick={runClassification}>
            {busy ? "Classifying..." : "Run classification"}
          </button>
        </div>
        {error && <div className="error-box">{error}</div>}
        {runSummary && (
          <p className="muted">
            Classified {runSummary.classified} transaction(s): {Object.entries(runSummary.by_transaction_type).map(([k, v]) => `${k}=${v}`).join(", ")}
          </p>
        )}
        <div className="row" style={{ marginBottom: "0.75rem" }}>
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="ok">ok</option>
            <option value="needs_review">needs_review</option>
            <option value="duplicate">duplicate</option>
          </select>
          <input type="text" placeholder="Search description..." value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => e.key === "Enter" && refresh()} />
          <button className="btn secondary" onClick={refresh}>
            Search
          </button>
          <span className="muted">{transactions.length} transaction(s)</span>
        </div>

        <table>
          <thead>
            <tr>
              <th>Date</th>
              <th>Description</th>
              <th className="num">Amount</th>
              <th>Bank account</th>
              <th>Classification</th>
              <th>Confidence / why</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {transactions.map((t) => (
              <Fragment key={t.id}>
                <tr>
                  <td>{t.transaction_date}</td>
                  <td>{t.description_normalized}</td>
                  <td className="num">{money(t.amount)}</td>
                  <td>{t.bank_account}</td>
                  <td>
                    <Badge value={t.transaction_type} /> <Badge value={t.classification_status} />
                    <div className="muted">{t.qbo_account_name || t.qbo_account}</div>
                  </td>
                  <td className="explain">
                    {t.classification_confidence != null ? `${Math.round(t.classification_confidence * 100)}%` : "-"} - {t.classification_explanation}
                  </td>
                  <td>
                    {t.status === "ok" && (
                      <button className="btn secondary" onClick={() => setEditingId(editingId === t.id ? null : t.id)}>
                        {editingId === t.id ? "Cancel" : "Review"}
                      </button>
                    )}
                  </td>
                </tr>
                {editingId === t.id && (
                  <EditRow
                    txn={t}
                    accounts={accounts}
                    onSaved={() => {
                      setEditingId(null);
                      refresh();
                    }}
                  />
                )}
              </Fragment>
            ))}
            {transactions.length === 0 && (
              <tr>
                <td colSpan={7} className="muted">
                  No transactions match this filter.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
