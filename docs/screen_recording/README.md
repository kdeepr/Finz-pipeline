# Screen recording

`local_workflow_demo.webm` (~39s) - a real browser (Playwright-driven
Chromium) against the actual running backend + frontend, covering:

1. Uploading all 9 sample bank exports (raw-data upload).
2. Running classification (195/195 transactions classified with explanations
   shown per row).
3. Opening the review/correct UI for a transaction.
4. Viewing the April 2026 monthly P&L and drilling into the Rent Expense line
   down to its underlying transaction.
5. Viewing the full 3-month P&L ($68,180.00 net profit).
6. The Sync-to-QuickBooks and Reconciliation tabs, showing their clear
   "not connected" states.

**What this recording does not cover:** the actual QuickBooks OAuth connect,
live sync, and live reconciliation - those require your own Intuit sandbox
credentials and an interactive browser consent step that only you can
complete (see `../../connect_flow.md`). Once connected, re-running this same
flow through tabs 4 and 5 would complete the recording end to end.
