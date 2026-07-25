import { useEffect, useState } from "react";
import { api } from "../api";
import { Badge, money } from "../components/Badge";

export function ReconciliationTab() {
  const [periods, setPeriods] = useState({ months: [] });
  const [period, setPeriod] = useState("full");
  const [report, setReport] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.listPeriods().then(setPeriods).catch((e) => setError(e.message));
  }, []);

  const load = async (p) => {
    setBusy(true);
    setError(null);
    setReport(null);
    try {
      setReport(await api.getReconciliation(p));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    if (period) load(period);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [period]);

  return (
    <div className="panel">
      <div className="section-title">
        <h3>Reconciliation vs. QuickBooks</h3>
        <select value={period} onChange={(e) => setPeriod(e.target.value)}>
          {periods.months.map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
          <option value="full">Full period</option>
        </select>
      </div>
      {error && <div className="error-box">{error}</div>}
      {busy && <p className="muted">Pulling QuickBooks' P&amp;L report and comparing...</p>}

      {report && (
        <>
          <div className="kpi-row">
            <div className="kpi">
              <div className="label">App net profit</div>
              <div className="value">{money(report.app_net_profit)}</div>
            </div>
            <div className="kpi">
              <div className="label">QBO net profit</div>
              <div className="value">{money(report.qbo_net_profit)}</div>
            </div>
            <div className="kpi">
              <div className="label">Difference</div>
              <div className="value">{money(report.net_profit_difference)}</div>
            </div>
            <div className="kpi">
              <div className="label">Status</div>
              <div className="value">
                <Badge value={report.overall_status} />
              </div>
            </div>
          </div>

          <table>
            <thead>
              <tr>
                <th>Account</th>
                <th className="num">App amount</th>
                <th className="num">QBO amount</th>
                <th className="num">Difference</th>
                <th>Status</th>
                <th>Explanation</th>
              </tr>
            </thead>
            <tbody>
              {report.lines.map((line) => (
                <tr key={line.account_code || line.account_name}>
                  <td>
                    {line.account_code ? `${line.account_code} - ` : ""}
                    {line.account_name}
                  </td>
                  <td className="num">{money(line.app_amount)}</td>
                  <td className="num">{money(line.qbo_amount)}</td>
                  <td className="num">{money(line.difference)}</td>
                  <td>
                    <Badge value={line.status} />
                  </td>
                  <td className="explain">{line.explanation}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}
