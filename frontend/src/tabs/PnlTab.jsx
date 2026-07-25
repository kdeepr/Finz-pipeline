import { useEffect, useState } from "react";
import { api } from "../api";
import { money } from "../components/Badge";

function Section({ title, section, period, onDrillDown }) {
  return (
    <div style={{ marginBottom: "1rem" }}>
      <h4 style={{ margin: "0 0 0.4rem" }}>{title}</h4>
      <table>
        <tbody>
          {section.lines.map((line) => (
            <tr key={line.account_code} style={{ cursor: "pointer" }} onClick={() => onDrillDown(period, line)}>
              <td>
                {line.account_code} - {line.account_name}
              </td>
              <td className="num">{money(line.total)}</td>
              <td className="num muted">{line.transaction_count} txn</td>
            </tr>
          ))}
          <tr className="total-row">
            <td>Total {title}</td>
            <td className="num">{money(section.subtotal)}</td>
            <td></td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}

export function PnlTab() {
  const [periods, setPeriods] = useState({ months: [] });
  const [period, setPeriod] = useState("full");
  const [pnl, setPnl] = useState(null);
  const [drillDown, setDrillDown] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.listPeriods().then((p) => {
      setPeriods(p);
      if (p.months.length) setPeriod("full");
    }).catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    if (!period) return;
    api.getPnl(period).then(setPnl).catch((e) => setError(e.message));
    setDrillDown(null);
  }, [period]);

  const onDrillDown = async (p, line) => {
    try {
      const txns = await api.getPnlLineTransactions(p, line.account_code);
      setDrillDown({ line, txns });
    } catch (err) {
      setError(err.message);
    }
  };

  if (!pnl) return <div className="panel">{error ? <div className="error-box">{error}</div> : "Loading..."}</div>;

  return (
    <div>
      <div className="panel">
        <div className="section-title">
          <h3>{pnl.period_label}</h3>
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
        {pnl.excluded_unclassified_count > 0 && (
          <p className="muted">
            {pnl.excluded_unclassified_count} transaction(s) in this period are not yet classified and are not reflected below - see the
            Review tab.
          </p>
        )}

        <div className="kpi-row">
          <div className="kpi">
            <div className="label">Revenue</div>
            <div className="value">{money(pnl.revenue.subtotal)}</div>
          </div>
          <div className="kpi">
            <div className="label">COGS</div>
            <div className="value">{money(pnl.cogs.subtotal)}</div>
          </div>
          <div className="kpi">
            <div className="label">Gross profit</div>
            <div className="value">{money(pnl.gross_profit)}</div>
          </div>
          <div className="kpi">
            <div className="label">Operating expenses</div>
            <div className="value">{money(pnl.operating_expenses.subtotal)}</div>
          </div>
          <div className="kpi">
            <div className="label">Net profit</div>
            <div className="value">{money(pnl.net_profit)}</div>
          </div>
        </div>

        <Section title="Revenue" section={pnl.revenue} period={period} onDrillDown={onDrillDown} />
        <Section title="Cost of Goods Sold" section={pnl.cogs} period={period} onDrillDown={onDrillDown} />
        <Section title="Operating Expenses" section={pnl.operating_expenses} period={period} onDrillDown={onDrillDown} />
      </div>

      {drillDown && (
        <div className="panel">
          <h3>
            {drillDown.line.account_code} - {drillDown.line.account_name}
          </h3>
          <table>
            <thead>
              <tr>
                <th>Date</th>
                <th>Description</th>
                <th className="num">Amount</th>
              </tr>
            </thead>
            <tbody>
              {drillDown.txns.map((t) => (
                <tr key={t.id}>
                  <td>{t.transaction_date}</td>
                  <td>{t.description_normalized}</td>
                  <td className="num">{money(t.amount)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
