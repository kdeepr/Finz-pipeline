import { useState } from "react";
import { UploadTab } from "./tabs/UploadTab";
import { ReviewTab } from "./tabs/ReviewTab";
import { PnlTab } from "./tabs/PnlTab";
import { SyncTab } from "./tabs/SyncTab";
import { ReconciliationTab } from "./tabs/ReconciliationTab";

const TABS = [
  { id: "upload", label: "1. Upload & Map", Component: UploadTab },
  { id: "review", label: "2. Review & Classify", Component: ReviewTab },
  { id: "pnl", label: "3. Internal P&L", Component: PnlTab },
  { id: "sync", label: "4. Sync to QuickBooks", Component: SyncTab },
  { id: "reconciliation", label: "5. Reconciliation", Component: ReconciliationTab },
];

// The QBO OAuth callback (backend, not this app) redirects the browser back
// here with the outcome in the query string - see app/api/qbo.py's
// `callback` handler. This is what turns that redirect into something
// visible instead of the user just landing back on whatever tab was open.
function readQboRedirectNotice() {
  const params = new URLSearchParams(window.location.search);
  const status = params.get("qbo_status");
  if (!status) return null;
  const notice =
    status === "connected"
      ? { kind: "ok", text: `Connected to QuickBooks (realm ${params.get("realm_id")}).` }
      : { kind: "error", text: params.get("qbo_message") || "QuickBooks connection failed." };
  window.history.replaceState({}, "", window.location.pathname);
  return notice;
}

function App() {
  const [notice] = useState(readQboRedirectNotice);
  const [activeTab, setActiveTab] = useState(notice ? "sync" : "upload");
  const Active = TABS.find((t) => t.id === activeTab).Component;

  return (
    <>
      <h1>Finz Accounting Pipeline</h1>
      <p className="subtitle">BrightFix Home Services LLC - bank transaction ingestion, classification, P&amp;L, and QuickBooks reconciliation</p>

      {notice && <div className={notice.kind === "ok" ? "success-box" : "error-box"}>{notice.text}</div>}

      <nav className="tabs">
        {TABS.map((t) => (
          <button key={t.id} className={activeTab === t.id ? "active" : ""} onClick={() => setActiveTab(t.id)}>
            {t.label}
          </button>
        ))}
      </nav>

      <Active />
    </>
  );
}

export default App;
