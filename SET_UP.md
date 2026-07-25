# 4.1 QuickBooks Online setup notes

This step (Intuit developer account, sandbox company, chart of accounts) is
manual and interactive - it was completed directly in the QuickBooks Online
sandbox UI, not through this codebase. This file is where that setup gets
documented, per the PDF's "Document any setup choices or QBO detail-type
differences."

Fill in the checklist below with what actually happened during setup - the
prompts are pulled directly from `data/reference/company_setup.json` and
`data/reference/qbo_chart_of_accounts.json` (the same files the app reads),
so anywhere your sandbox ended up different from those is worth a line here.

## Company setup

- [ ] Company name: BrightFix Home Services LLC
- [ ] Industry / accounting basis: Cash basis, USD, fiscal year Jan-Dec
- [ ] Bank accounts created: Operating Checking, Tax Reserve (opening balance $0)
- [ ] Sandbox realm ID: `___________` (visible once connected - see `connect_flow.md`)

## Chart of accounts (21 accounts required)

For each account in `data/reference/qbo_chart_of_accounts.json`, note whether
the sandbox's actual detail type matched the "Suggested Detail Type" column,
or whether a substitute was picked because QBO didn't offer that exact option
(the dataset itself anticipates this: "If a detail-type label differs, select
the closest available option under the specified account type").

| Account No. | Account Name | Suggested Detail Type | Actual detail type used (fill in) | Notes |
|---|---|---|---|---|
| 1000 | Operating Checking | Checking | | |
| 1010 | Tax Reserve | Savings | | |
| 1500 | Tools & Equipment | Machinery and Equipment | | |
| 3000 | Owner's Equity | Owner's Equity | | |
| 4000 | Repair Service Revenue | Service/Fee Income | | |
| 4010 | Installation Revenue | Service/Fee Income | | |
| 4020 | Maintenance Plan Revenue | Service/Fee Income | | |
| 4100 | Customer Refunds | Discounts/Refunds Given | | |
| 5000 | Materials & Supplies | Supplies & Materials - COGS | | |
| 5010 | Subcontractor Costs | Cost of Labor | | |
| 6000 | Payroll Expense | Payroll Expenses | | |
| 6010 | Rent Expense | Rent or Lease of Buildings | | |
| 6020 | Vehicle & Fuel | Auto | | |
| 6030 | Software & Subscriptions | Dues & Subscriptions | | |
| 6040 | Marketing & Advertising | Advertising/Promotional | | |
| 6050 | Insurance Expense | Insurance | | |
| 6060 | Utilities | Utilities | | |
| 6070 | Professional Fees | Legal & Professional Fees | | |
| 6080 | Bank Fees | Bank Charges | | |
| 6090 | Office & General | Office/General Administrative Expenses | | |
| 6100 | Repairs & Maintenance | Repair & Maintenance | | |

## Other setup choices worth recording

- Whether "Show account numbers" was enabled in report preferences (this
  affects how account names are labeled in the QBO P&L report the
  reconciliation step parses - see `app/reconciliation/qbo_report_parser.py`,
  which strips a leading account-number prefix if present).
- Anything QBO required beyond the dataset's instructions (e.g. a mandatory
  field on account creation not listed in the chart of accounts tab).
- The Intuit developer app's Client ID is in `backend/.env` (never commit real
  secrets) - `connect_flow.md` covers generating one if you haven't yet.
