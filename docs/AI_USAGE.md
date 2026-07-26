# AI usage note

This entire application (backend, tests, frontend) was built with **Claude
Code** (Anthropic), working directly in this repository across the 4.2-4.6
build. This note is a factual account of what the tool generated and what was
independently checked, per the challenge's requirement.

## What Claude Code generated

- The full FastAPI backend: ingestion/normalization pipeline, classification
  engine (rules + vendor directory + Gemini fallback + learned corrections),
  P&L generation, QuickBooks OAuth/sync, and reconciliation.
- The pytest suite (100+ tests) exercising all of the above through the real
  HTTP API.
- The React frontend (five tabs matching the required workflow).
- This documentation.

## What was independently validated, and how

Claude Code is capable of writing code that runs and even code whose tests
pass while still being wrong about the underlying accounting - a rule that
misclassifies a transaction can still produce a P&L that adds up correctly.
So validation here specifically targeted *correctness of the numbers*, not
just *code that executes*:

- **The dataset was read and manually cross-checked line by line.** All 195
  unique transactions in the challenge dataset were listed out and reviewed
  by hand (not just sampled) to build the classification rules, specifically
  to catch the dataset's deliberate lookalikes - e.g. `WIRE ... EQUIPMENT
  INSTALL ####` (installation revenue) vs. `MILWAUKEE COMMERCIAL TOOL
  PACKAGE` (the one real fixed-asset purchase), and `FLEET AUTO CARE` (vehicle
  repair, account 6100) vs. `SHELL OIL` (fuel, account 6020).
- **Expected P&L totals were computed independently of the app's own
  classification code** - a separate script summed every transaction's signed
  amount directly from the source dataset, excluding only transfers, owner
  activity, and the fixed-asset purchase (exactly what PDF 4.4 says to
  exclude), with no reference to which QBO account each transaction landed
  on. The app's generated P&L was then checked against those numbers and
  matches exactly for all three months and the full period (see
  `docs/pnl_output/`).
- **The full stack was run live**, not just unit-tested: both the FastAPI
  backend and the Vite dev server were started, and a real Chromium browser
  (via Playwright) drove the actual UI - uploading all 9 sample bank exports,
  running classification, and viewing/drilling into the P&L - to confirm the
  frontend and backend agree, not just that each passes its own tests.
- **Duplicate detection was checked against the actual dataset structure**:
  the 5 known cross-file duplicates (transactions repeated across
  overlapping "last 30 days"-style bank exports) were identified by hand
  first, then verified that the pipeline catches exactly those 5 and no
  others.

## What could not be validated in this environment

- **The live QuickBooks Online integration** (OAuth connect, account-Id
  resolution, transaction sync, and pulling the real P&L report) requires the
  developer's own Intuit sandbox credentials and an interactive browser
  consent step - neither exists in this build environment. That code is
  written to Intuit's documented API/OAuth2 spec and is covered by tests
  against a fake QBO client (verifying payload shape, sync eligibility,
  idempotency, and transfer pairing), but the actual HTTP calls to
  `sandbox-quickbooks.api.intuit.com` have not been exercised against a real
  company. `connect_flow.md` documents the one-time manual steps to connect
  and verify this yourself.
- **The QBO Profit & Loss report parser** is written against Intuit's
  documented report JSON shape and unit-tested against a report fixture
  matching that shape - it has not been run against an actual report response,
  since that also requires the live connection above.

Whoever runs this against a real sandbox should treat the QBO
sync/reconciliation step as the one piece still needing a first live
smoke-test, even though the code and its logic have been reviewed and tested
as thoroughly as possible without that connection.

## A live debugging session, and its outcome

After the initial build, the developer ran the app locally and reported the
QuickBooks connect flow failing partway through - getting past Intuit's login
and Authorize screen, then breaking. This was worked through interactively,
attempt by attempt, and surfaced three separate real bugs in the OAuth
callback handler that no amount of testing against a fake QBO client could
have caught, because they were about what happens on the *local machine
actually running the app*, not about the QBO API contract:

1. The callback returned raw JSON directly in the browser instead of
   redirecting back into the app - a real UX bug, indistinguishable from a
   crash even on success.
2. `code`/`realmId` were required query parameters, so when Intuit itself
   redirected back with an `error` (e.g. access denied) instead of a code,
   FastAPI's validation rejected the request with a generic "field required"
   error that hid Intuit's actual, specific reason.
3. OAuth `state` was verified against a database record - which turned out to
   be fragile against exactly the kind of interruption a local dev workflow
   produces (a `--reload`-triggered restart from an unrelated file change,
   or a manual restart), producing "unrecognized or expired state" on
   completely valid, fresh attempts.

Each fix was verified concretely, not just asserted: bug 3's fix was proven
by reproducing the exact failure - generating a state, killing the backend
process, starting a brand-new one with a fully wiped database, and
confirming the old state still verified correctly - rather than trusting that
switching to a signed-token approach would obviously work. Test coverage for
the callback endpoint (previously nonexistent) was added alongside each fix.

This is worth recording plainly: the fake-client test suite gave high
confidence in the *logic* (payload shapes, sync eligibility, idempotency,
transfer pairing) but had a blind spot around *runtime environment behavior*
(process restarts, browser redirect UX) that only surfaced by actually
running the app and hitting a real failure. Both kinds of validation turned
out to matter.
