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

function App() {
  const [activeTab, setActiveTab] = useState("upload");
  const Active = TABS.find((t) => t.id === activeTab).Component;

  return (
    <>
      <h1>Finz Accounting Pipeline</h1>
      <p className="subtitle">BrightFix Home Services LLC - bank transaction ingestion, classification, P&amp;L, and QuickBooks reconciliation</p>

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
