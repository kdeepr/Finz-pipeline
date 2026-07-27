# Finz Accounting Data Pipeline

A working pipeline for BrightFix Home Services LLC that ingests raw bank
transactions, normalizes and classifies them, generates a cash-basis P&L,
syncs approved transactions to QuickBooks Online, and reconciles the app's
P&L against QuickBooks' own report - built for the Finz Data Engineering
Challenge.

- `backend/` - FastAPI + MongoDB application (Python)
- `frontend/` - React (Vite) single-page app implementing the required workflow
- `data/` - the challenge dataset, split into per-source bank export fixtures, plus the QBO chart of accounts and company setup as JSON
- `docs/pnl_output/` - generated internal P&L statements (deliverable)
- `docs/AI_USAGE.md` - how this was built and the debugging log from connecting it to a real QuickBooks sandbox
- `connect_flow.md` - one-time manual steps to connect a real QuickBooks sandbox
- `process documentation.md` - a step-by-step account of setting up, running, and debugging the pipeline against a real sandbox, start to finish

## Setup instructions

### Backend
```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate   # optional but recommended
pip install -r requirements.txt
cp .env.example .env                                  # fill in as needed, see below
docker compose -f ../docker-compose.yml up -d          # local MongoDB
uvicorn app.main:app --reload
```
GEMINI_API_KEY and the QBO_* variables are optional until you reach classification's Gemini fallback or the QuickBooks steps. Without a MONGODB_URI set, it defaults to mongodb://localhost:27017, so Option A or B above just needs to be running before you start uvicorn.

One thing worth being direct about: don't set TESTING=true (or MONGODB_URI=mongomock://) for anything other than running the test suite. It swaps in an in-memory database that lives only inside the running process, so every restart - including the automatic ones reload triggers on any file change - wipes everything: uploads, classifications, even your QuickBooks connection, with no warning. I found this out the hard way after a real sync had already posted transactions into my sandbox, the local record of it got wiped by a restart, and a later "clean" re-sync posted the same transactions a second time. That whole incident, and the cleanup script that came out of it.

### Frontend
```
cd frontend
npm install
cp .env.example .env   # points at the backend, defaults to localhost:8000
npm run dev
```
### Tests
```
cd backend
TESTING=true python -m pytest -q
```


This is the one place TESTING=true belongs. 120+ tests run the real HTTP API (FastAPI TestClient) against an in-memory Mongo,  including the full challenge dataset end to end.

Connecting to your QuickBooks Online sandbox See connect_flow.md. This is the one interactive step (OAuth consent) that only a person can complete, using the sandbox company and chart of accounts you already set up.

A heads-up from actually doing this: if you get invalid_scope back from Intuit before you even reach the login screen, it's not a bug in this code. check that your app has the Accounting API enabled under Permissions in the Intuit Developer dashboard. And if POST /api/qbo/accounts/sync reports fewer matches than you expect, it's likely because a real sandbox's chart of accounts includes QuickBooks' own built-in default accounts on top of yours, easily pushing the total past 100 - the account query pages through results now, but it's worth knowing why that mattered.

## Architecture
```
Upload (CSV/Excel)
  -> parser (file format only, format-agnostic)
  -> normalizer (per column-mapping profile: dates, amounts, currency, bank account, description)
  -> duplicate check (against everything already ingested)
  -> raw_transactions + normalized_transactions (Mongo)

Classification
  -> approved-correction lookup (pattern signature) -> rule engine -> Gemini (optional) -> unclassified
  -> updates normalized_transactions in place

P&L (computed live)
  -> queries normalized_transactions by transaction_type + date range
  -> grouped by each account's QBO "Account Type" (Income/COGS/Expenses)

QuickBooks sync
  -> OAuth2 connect -> account-Id resolution (our account_no -> QBO's real Id)
  -> maps each transaction to a Deposit/Purchase/Transfer entity
  -> posts via QBO API, records qbo_txn_id + sync status

Reconciliation
  -> pulls QBO's own cash-basis P&L report via the API
  -> parses + compares against the same P&L the app already generates
```

Each of the five FastAPI routers (uploads, transactions/classification, pnl, qbo, reconciliation) corresponds to one tab in the frontend and one subsection of PDF section 4. The backend has no ORM - pymongo/mongomock documents are read/written directly as dicts, validated at the API boundary by Pydantic models in app/models/.

## Data model
Two collections back every uploaded row, by design:

raw_transactions - the row exactly as the file had it (every original column, string values, untouched). This is what "treat the data as untrusted, preserve original values" (dataset note A) means structurally, not just as a convention to remember.

normalized_transactions - the canonical, typed record derived from a raw row via a column-mapping profile, plus (once classified)
transaction_type / counterparty / qbo_account / a confidence score and explanation / review status, plus (once synced) qbo_txn_id and sync status. Everything downstream reads only from here. 

Supporting collections: upload_batches (one per file uploaded),
column_mapping_profiles (configurable field maps, see below), bank_account_aliases and vendor_directory (configurable lookup tables used by normalization/classification), classification_rules (approved corrections), qbo_connection / qbo_account_ids (QuickBooks OAuth tokens and the account-number -> QBO-Id mapping).

## Ingestion & duplicate prevention
Column mapping is data (a {canonical_field: source_column_name} document in Mongo), not code - the parser and normalizer never reference a specific column name or order, so a different bank's export just needs a new profile registered via POST /api/column-mappings.

Duplicate detection uses the bank's own transaction ID as the primary key when present, falling back to a content hash (date + amount + bank account + cleaned description) when it's absent. Every new row is checked against everything already ingested, not just the current file, which is what catches duplicates from overlapping source files (the dataset includes three "last N days"-style exports that re-send transactions an earlier monthly export already had - the pipeline finds all 5 of those duplicate pairs). Records that can't be safely parsed (bad date, bad amount, unrecognized bank account, missing description) are flagged (needs_review) rather than dropped, and still get a normalized record so a human can fix them.

## Classification approach 
Every "ok" transaction is classified in priority order:

1. Approved corrections - if a reviewer already corrected this exact pattern before, that wins. Patterns are matched on a signature that blanks out job numbers, invoice numbers, and month names, so correcting one month's rent payment teaches the system every future month's rent payment too.
2. Deterministic rules (app/classification/rules.py) - transfers, owner activity, refunds, then a known-vendor directory (vendor_directory.py, analogous to how Plaid/Ramp/Brex enrich raw card descriptors), then revenue sub-typing by keyword (maintenance plan / installation / repair). Every rule match is confidence 1.0 and carries a plain-language explanation tied to a specific Company Setup rule.
3. Gemini (only if GEMINI_API_KEY is set) - a last resort for whatever the rules can't resolve, given the same chart of accounts and accounting rules as context, returning its own confidence score.
4. Otherwise the transaction is left unclassified, visible in the review queue, and excluded from the P&L until resolved (not silently dropped).

The dataset includes several deliberate lookalikes the rules were built and tested to distinguish: WIRE ... EQUIPMENT INSTALL #### (installation revenue - money coming in) vs. MILWAUKEE COMMERCIAL TOOL PACKAGE (the one real fixed-asset purchase - money going out, no customer/job reference); and FLEET AUTO CARE (vehicle repair, account 6100) vs. SHELL OIL/EXXONMOBIL
(fuel, account 6020).

## Internal P&L
Computed live from normalized_transactions on every request - never a stored snapshot - grouped by each account's QBO "Account Type" (Income / Cost of Goods Sold / Expenses), which is the same grouping QuickBooks' own P&L report uses, so the reconciliation compares like for like. Transfers, owner activity, duplicates, and fixed-asset purchases are excluded
structurally (they simply never carry a P&L-eligible transaction_type), not as a special case in the report code. See docs/pnl_output/ for the generated monthly and full-period statements.

## QuickBooks integration and reconciliation
Entity mapping decision: every posted transaction is a QuickBooks Deposit (money in) or Purchase (money out) directly against the classified account - never a SalesReceipt/Invoice/Bill, because those QBO entities require a Product/Service Item, and Company Setup puts AR/AP/ inventory explicitly out of scope. A refund is money out (a debit in the bank feed) posted as a Purchase against the Customer Refunds income account, which is what makes it net against revenue without needing a Credit Memo. Transfers use QuickBooks' native Transfer entity; only the outgoing leg makes an API call, and the paired incoming leg is linked to that same Transfer Id rather than posted a second time, so one bank-to-bank move is represented once on both registers, not as two separate transactions.

Account Id resolution: our chart of accounts uses account numbers (4000, 6010, ...) as human-readable references, but the QBO API needs the sandbox's own internal account Id, assigned when you created each account by hand in 4.1. POST /api/qbo/accounts/sync pulls your sandbox's real account list - paging through it, since a real company's account list, including QuickBooks' own defaults, can easily exceed a single query page - and matches it back to our chart by account number, falling back to name.

Sync eligibility & idempotency: only transactions that are reviewed/corrected by a human, or auto-classified above a confidence threshold (rules and vendor-directory matches are always 1.0; a low-confidence Gemini guess isn't), are eligible to sync. The sync query itself excludes anything already synced/linked, so re-running sync is a no-op for already-posted transactions and only retries genuine failures. Worth being honest about the edge this doesn't cover: idempotency here is tracked locally, not verified against QuickBooks itself - if the local record of a successful sync is ever lost (which is exactly what TESTING=true will do
to you), a re-sync has no way to know those transactions already exist on the QuickBooks side, and will post them again.

Reconciliation: pulls QuickBooks' own cash-basis P&L report via the API for the same period, parses its recursive Row/Section/Data structure, and compares account-by-account against the app's own P&L - matching by the real QBO account Id where known, falling back to name. Each line reports the app amount, the QBO amount, the difference, a status (match / mismatch / app_only / qbo_only), and an explanation. A clean sync is explicitly not treated as sufficient - only exact (to the cent) agreement on every account and on net profit counts as reconciled. Two things worth knowing if you're reading a real report instead of the test fixtures: QuickBooks shows Cost of Goods Sold and Expenses balances as positive numbers, while this app stores every outflow as negative, so the comparison normalizes that; and a parent account with sub-accounts (Utilities, over Gas and Electric/Telephone in this sandbox) reports its own direct postings differently than a plain account does, which the parser accounts for too.

## Assumptions
1. US date format when ambiguous. Dates without an explicit format on the mapping profile are parsed month-before-day; a non-US bank export should set an explicit date_format on its own profile instead of relying on this default.
2. USD only for this challenge (allowed_currencies is configurable, but anything else is flagged for review rather than silently converted).
3. Amounts as float, not arbitrary-precision Decimal. All figures in this dataset are whole dollars or cents; a production system handling
fractional-cent activity would want Decimal/BSON Decimal128 instead.
4. One company/sandbox connection at a time (qbo_connection is a single document) - matches this challenge's scope of one company.
5. Bank account aliasing and the vendor directory are seeded from this dataset (Operating Checking/Tax Reserve; the ~25 recurring vendors found by reading all 195 transactions). Both are stored in Mongo and extendable via the API, not hardcoded branches, but a genuinely different dataset will need its own vendor entries added the same way.
6. Sync-eligibility confidence threshold (0.95) is a judgment call about what counts as "safely classified" per PDF 4.5 - rule/vendor matches always clear it; low-confidence Gemini guesses are meant to require human review first.

## Known limitations
This has genuinely been run end-to-end against a real QuickBooks sandbox - connect, sync, and reconciliation all reach a clean, exact match now. But getting there surfaced real bugs that no amount of testing against a fake QBO client would have caught, because they weren't about the mapping logic at all: a pagination gap in the account query, a sign-convention mismatch between how this app and QuickBooks represent expense amounts, and a parser gap around how QuickBooks reports a parent account's own balance when it has sub-accounts. All three are fixed and covered by tests now. The full debugging account, including a data-loss incident from a local environment misconfiguration and how it was cleaned up, is in docs/AI_USAGE.md - I'd rather document that honestly than pretend the first live run was clean.

Counterparty extraction for customer receipts is a prefix/suffix regex strip that relies on this bank's memo format being regular (which it is, in this dataset); a bank whose memos don't follow "channel prefix + name + job-type keyword + number" would need either a different extraction pattern or to rely more on manual review.

No pagination on /api/transactions beyond skip/limit query params - fine for a few thousand rows, would want cursor-based pagination at scale. Sales tax, inventory, accounts receivable, accounts payable, depreciation, and payroll liabilities are all explicitly out of scope per Company Setup and are not modeled.


See docs/AI_USAGE.md for the AI usage note and the live debugging log, and docs/pnl_output/ for the generated internal P&L statements.
