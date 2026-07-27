# AI usage note

This entire application (backend, tests, frontend) was built with using **Claude Code**, working directly in this repository across
build tasks as specified. This note is a factual account of what the tool generated and what was independently checked, per the challenge's requirement.

## How I used Claude Code

- claude code is used to develop The full FastAPI backend: ingestion/normalization pipeline, classification engine (rules + vendor directory + Gemini fallback + learned corrections),P&L generation, QuickBooks OAuth/sync, and reconciliation.
- The pytest suite exercising all of the above through the real HTTP API.
- The React frontend (five tabs matching the required workflow).

## What was independently validated, and how

- **The dataset was read and manually cross-checked line by line.** All 195 unique transactions in the challenge dataset were listed out and reviewed by hand (not just sampled) to build the classification rules, specifically to catch the dataset's deliberate lookalikes - e.g. `WIRE ... EQUIPMENT INSTALL ####` (installation revenue) vs. `MILWAUKEE COMMERCIAL TOOL PACKAGE` (the one real fixed-asset purchase), and `FLEET AUTO CARE` (vehicle repair, account 6100) vs. `SHELL OIL` (fuel, account 6020).
- **Expected P&L totals were computed independently of the app's own classification code** - a separate script summed every transaction's signed amount directly from the source dataset, excluding only transfers, owner activity, and the fixed-asset purchase (exactly what instructions from the task 4.4 says to exclude), with no reference to which QBO account each transaction landed on. The app's generated P&L was then checked against those numbers and matches exactly for all three months and the full period (see`docs/pnl_output/`).
- **The full stack was run live**, not just unit-tested: both the FastAPI backend and the Vite dev server were started, and a real Chromium browser (via Playwright) drove the actual UI - uploading all 9 sample bank exports,running classification, and viewing/drilling into the P&L - to confirm the frontend and backend agree, not just that each passes its own tests.
- **Duplicate detection was checked against the actual dataset structure**: the 5 known cross-file duplicates (transactions repeated across overlapping "last 30 days"-style bank exports) were identified by hand first, then verified that the pipeline catches exactly those 5 and no
others.
