# Connecting the app to your QuickBooks Online sandbox

OAuth2's authorization step is inherently interactive - only you can log into
your own Intuit developer account and click "Authorize" - so this is the one
part of the pipeline that has to be run by hand, once, from your machine.

## 1. Get your app credentials

From your Intuit developer account (developer.intuit.com) → your app → **Keys
& OAuth**:
- Copy the **Client ID** and **Client Secret** for the *Development* keys
  (these work against your sandbox company).
- Under **Redirect URIs**, add `http://localhost:8000/api/qbo/callback`
  (or whatever host/port you're running the backend on).

**The redirect URI you register in Intuit must match `QBO_REDIRECT_URI` in
`.env` byte-for-byte** - scheme, host, port, and path. If they don't match,
Intuit rejects the request before you even see a login screen
(`redirect_uri_mismatch`). If you're running the backend on a different port
than 8000, update both places to match.

Put these in `backend/.env` (copy from `.env.example`):

```
QBO_CLIENT_ID=your_client_id
QBO_CLIENT_SECRET=your_client_secret
QBO_ENVIRONMENT=sandbox
QBO_REDIRECT_URI=http://localhost:8000/api/qbo/callback
FRONTEND_URL=http://localhost:5173   # where the browser lands back after connecting
```

## 2. Start both apps and connect

```bash
cd backend && uvicorn app.main:app --reload      # in one terminal
cd frontend && npm run dev                        # in another
```

Then, from the frontend (`Sync to QuickBooks` tab):

1. Click **Connect to QuickBooks**. This navigates your browser (same tab) to
   Intuit's authorization page.
2. Log in and select the **same sandbox company** you set up in step 4.1 (the
   one with the chart of accounts), then click **Authorize**.
3. Intuit redirects to the backend's `/api/qbo/callback`, which exchanges the
   code for tokens, stores them (`app/qbo/connection_store.py`), and redirects
   you straight back to the frontend with a status banner - you should land
   back on the Sync tab showing "Connected to QuickBooks (realm ...)".

If step 3 instead shows an error banner, the message is specific (expired
OAuth state, or the exact reason the token exchange failed - e.g. a wrong
client secret) rather than a generic failure, so start with what it says.

You can still drive this by hand with `curl`/a REST client if you prefer:
`GET /api/qbo/connect` returns the `authorization_url` directly; after
authorizing, `GET /api/qbo/status` reports `{"connected": true, "realm_id":
"..."}` once the callback has run.

## 3. Map the chart of accounts

Your sandbox assigns its own internal ID to every account you created by hand
in 4.1 - that ID (not the "4000"-style account number) is what the API needs.
Run this once (and again if you rename/add an account later):

```
POST /api/qbo/accounts/sync
```

This pulls your sandbox's real account list and matches each one back to
`data/reference/qbo_chart_of_accounts.json` by account number, falling back to
name. It returns which accounts (if any) it couldn't match - fix those in the
sandbox and re-run before syncing transactions.

## 4. Sync and reconcile

```
POST /api/qbo/sync          # posts approved transactions (4.5)
GET  /api/pnl/full          # your internal P&L
GET  /api/reconciliation/full   # compares it against QBO's own P&L report (4.6)
```

Tokens refresh automatically before they expire; if the refresh token itself
expires (sandbox refresh tokens last 100 days), just repeat step 2.
