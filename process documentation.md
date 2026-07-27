# creating and troubleshooting the whole pipeline

## 1. Before this session (prerequisite)
Created the QuickBooks Online sandbox company in the Intuit Developer dashboard. Manually created the 21-account chart of 
accounts in that sandbox (Operating Checking, Tax Reserve, Tools & Equipment, Owner's Equity, and all Income/COGS/Expense 
accounts),matching data/reference/qbo_chart_of_accounts.json.

##2. Local environment setup
Created and activated a Python virtual environment (```python3 -m venv .venv && source .venv/bin/activate```) and installed 
backend dependencies (```pip install -r requirements.txt```). Ran the backend (```uvicorn app.main:app --reload```) and 
frontend (```npm run dev```) locally. Filled in ```backend/.env``` with real credentials (QBO_CLIENT_ID, QBO_CLIENT_SECRET, GEMINI_API_KEY).
Installed and started a real, persistent local MongoDB:

```
brew tap mongodb/brew
brew install mongodb-community
brew services start mongodb-community
```

Changed .env's TESTING=true → TESTING=false so data would persist across backend restarts (the earlier value was silently using 
an in-memory database).

Installed and configured GitHub CLI to fix a git authentication failure:

```
brew install gh
gh auth login
gh auth setup-git
```
## 3. Git/GitHub troubleshooting resolved
Resolved a git pull merge conflict on ```.env.example/requirements.txt``` by discarding local uncommitted changes 
(git checkout -- .env.example requirements.txt) after confirming your real secrets were safely still in your untouched .env file, not lost.
Noticed and flagged that backend/.venv had been accidentally git add-ed (thousands of files) — cleared with git restore --staged .venv before anything got committed.

## 4. QuickBooks OAuth connect — debugging and fix
Repeatedly tested the "Connect to QuickBooks" flow, reporting exact error messages and terminal output at each attempt so the underlying 
bugs could be diagnosed. Ran a clean test in a fresh incognito browser window to rule out stale-tab causes.
Enabled debug logging, reproduced the failure, and shared the exact backend log lines showing the real cause: Intuit was rejecting the 
request with invalid_scope. Went into the Intuit Developer Dashboard myself and checked:
Redirect URIs (confirmed http://localhost:8000/api/qbo/callback was already correct)
Permissions tab — found the Accounting API wasn't enabled for the app, which was the actual root cause
Successfully completed the OAuth consent flow and connected to the sandbox (realm 9341457593180838).


## 5. Running the pipeline live, end-to-end
Uploaded all 9 bank export CSVs from data/sample_bank_exports/ through the frontend's Upload & Map tab (twice total — once before, 
once after the data-loss bug below required a redo).
Ran classification and confirmed the result (195 classified, 7 correctly-detected duplicates, 0 needing manual review) each time.
Ran "Sync chart-of-accounts IDs" and "Sync approved transactions" repeatedly, reporting exact results at each step (including the 
account-mapping pagination bug: 19/21 → 21/21 after the fix).


## 6. Diagnosing and recovering from the data-loss bug
Ran diagnostic commands to check transaction/sync status when things unexpectedly reset (curl .../api/transactions, piped into Python 
one-liners to summarize confidence/sync-status breakdowns).
Checked .env and confirmed TESTING=true was the cause.
After switching to real MongoDB, redid the entire pipeline from scratch: reconnect → re-upload all 9 files → re-classify → re-map accounts → re-sync.


## 7. Finding and cleaning up duplicate sandbox entities
Ran the cleanup script for duplicate entities created by the data-loss incident:
python3 scripts/cleanup_duplicate_qbo_syncs.py            # dry run - reviewed the list
python3 scripts/cleanup_duplicate_qbo_syncs.py --confirm  # 171 deleted, 0 failed
Reviewed the dry-run output and confirmed the dates/amounts looked legitimate before approving the real deletion.


## 8. Manually cleaning QuickBooks' pre-loaded sample data
This was the most labor-intensive part — going through QuickBooks' own UI to remove sample "Craig's Design and Landscaping" demo data that 
came pre-seeded in the sandbox, account by account:

Found and deleted sample transactions under Cost of Goods Sold (Invoices for Mark Cho, Sonnenschein Family Store, Freeman Sporting Goods).
Found and deleted sample transactions under Job Expenses (Tania's Nursery), Fountains and Garden Lighting / Plants and Soil.
and continued this process for all the QOB only transactions and this helped me to understand the quickbooks UI and got very familiar to the UI.

Worked through a QBO-enforced dependency chain: a Norton Lumber and Building Materials Bill couldn't be deleted because it was linked to an 
Invoice (#1032, Travis Waldron) — found and deleted that invoice first, then the bill.
Worked through a second dependency: a Dukes Basketball Camp customer Payment couldn't be deleted because it had been bundled into a bank 
Deposit — used QBO's direct link to jump to the Deposit, removed it, then deleted the payment.

Repeated this same process across the full remaining list of unrelated sample accounts: Accounting, Advertising, Automobile, Bookkeeper, 
Decks and Patios, Design income, Discounts given, Equipment Rental, Fuel (deleted), Gas and Electric, Landscaping Services, Lawyer, 
Legal & Professional Fees, Maintenance and Repair, Meals and Entertainment, Miscellaneous, Office Expenses, Pest Control Services, 
Rent or Lease, Sales of Product Income, Services, Sprinklers and Drip Systems, Telephone.
Corrected manual QBO report cross-check twice: fixed the date range (was cutting off at June 1 instead of June 30) and the accounting 
method (was set to Accrual instead of Cash) to make it a fair comparison against the app's own reconciliation.

## 9. Final validation
Re-ran reconciliation repeatedly through each round of cleanup, reporting the exact numbers each time, until reaching:
App Net Profit: $68,180.00
QBO Net Profit: $68,180.00
Difference: $0.00
Status: RECONCILED, every one of the 17 real P&L accounts showing MATCH.
