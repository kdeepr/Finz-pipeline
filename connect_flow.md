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

Put these in `backend/.env` (copy from `.env.example`):

```
QBO_CLIENT_ID=your_client_id
QBO_CLIENT_SECRET=your_client_secret
QBO_ENVIRONMENT=sandbox
QBO_REDIRECT_URI=http://localhost:8000/api/qbo/callback
```

## 2. Start the app and connect

```bash
cd backend
uvicorn app.main:app --reload
```

Then, with the server running:

1. `GET http://localhost:8000/api/qbo/connect` → returns
   `{"authorization_url": "https://appcenter.intuit.com/connect/oauth2?..."}`.
2. Open that URL in your browser. Log in and select the **same sandbox
   company** you set up in step 4.1 (the one with the chart of accounts).
3. Intuit redirects you back to
   `http://localhost:8000/api/qbo/callback?code=...&state=...&realmId=...`
   - the backend exchanges the code for tokens and stores them (see
     `app/qbo/connection_store.py`), keyed to that `realmId` (your sandbox
     company's ID).
4. `GET /api/qbo/status` should now show `{"connected": true, "realm_id": "..."}`.

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
