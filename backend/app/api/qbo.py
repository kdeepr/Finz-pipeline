import secrets
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import RedirectResponse
from pymongo.database import Database

from app.classification.coa import load_chart_of_accounts
from app.config import get_settings
from app.deps import db_dep
from app.qbo import connection_store, oauth
from app.qbo.accounts_sync import sync_account_ids
from app.qbo.client import QBOClient, QBONotConnectedError
from app.qbo.oauth import QBOOAuthError
from app.qbo.sync_service import sync_pending

router = APIRouter(prefix="/api/qbo", tags=["qbo"])

_STATE_COLLECTION = "qbo_oauth_state"


@router.get("/connect")
def connect(response: Response, db: Database = Depends(db_dep)):
    # A cached response here would hand back a stale authorization_url (and
    # therefore a stale, already-invalid `state`) on a re-click - this must
    # always issue a fresh state.
    response.headers["Cache-Control"] = "no-store"
    settings = get_settings()
    if not settings.qbo_client_id or not settings.qbo_client_secret:
        raise HTTPException(
            status_code=400,
            detail="QBO_CLIENT_ID / QBO_CLIENT_SECRET are not configured. Add them to .env from your Intuit developer app.",
        )
    state = secrets.token_urlsafe(24)
    db[_STATE_COLLECTION].insert_one({"state": state})
    return {"authorization_url": oauth.build_authorization_url(settings, state)}


@router.get("/callback")
def callback(
    state: str,
    code: str | None = None,
    realmId: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
    db: Database = Depends(db_dep),
):
    """
    Intuit lands the browser here directly (a full-page redirect, not a fetch
    call from the frontend), so this must never just return raw JSON - that
    reads as "it broke" even on success, since the user is staring at a bare
    API response with no indication of what to do next. Every path below ends
    in a redirect back to the frontend, with the outcome encoded in the query
    string, so the SPA can show it and the tab closes the loop visibly.

    `code`/`realmId` are optional, not required, because a failure on
    Intuit's side (access denied, a misconfigured app) redirects here with
    `error`/`error_description` instead of a code - making them required
    turned every such failure into an opaque generic 422 ("field required")
    that hid Intuit's actual reason instead of showing it.
    """
    settings = get_settings()

    if not db[_STATE_COLLECTION].find_one({"state": state}):
        return _redirect_with_error(
            settings, "Unrecognized or expired OAuth state - the connect link may be stale. Click Connect to QuickBooks again."
        )

    if error or not code or not realmId:
        message = error_description or error or "QuickBooks did not return an authorization code."
        return _redirect_with_error(settings, message)

    try:
        tokens = oauth.exchange_code_for_tokens(settings, code)
    except QBOOAuthError as exc:
        return _redirect_with_error(settings, str(exc))

    connection_store.save_tokens(db, realmId, tokens["access_token"], tokens["refresh_token"], tokens["expires_in"])
    db[_STATE_COLLECTION].delete_one({"state": state})
    return RedirectResponse(f"{settings.frontend_url}/?{urlencode({'qbo_status': 'connected', 'realm_id': realmId})}")


def _redirect_with_error(settings, message: str) -> RedirectResponse:
    return RedirectResponse(f"{settings.frontend_url}/?{urlencode({'qbo_status': 'error', 'qbo_message': message})}")


@router.get("/status")
def status(db: Database = Depends(db_dep)):
    connection = connection_store.get_connection(db)
    if connection is None:
        return {"connected": False}
    return {"connected": True, "realm_id": connection["realm_id"]}


@router.post("/accounts/sync")
def accounts_sync(db: Database = Depends(db_dep)):
    settings = get_settings()
    client = QBOClient(db, settings)
    try:
        unmatched = sync_account_ids(db, client)
    except QBONotConnectedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    total = len(load_chart_of_accounts())
    return {"matched": total - len(unmatched), "total": total, "unmatched_account_numbers": unmatched}


@router.post("/sync")
def run_sync(batch_id: str | None = None, db: Database = Depends(db_dep)):
    if connection_store.get_connection(db) is None:
        raise HTTPException(status_code=400, detail="Not connected to QuickBooks Online. Visit GET /api/qbo/connect first.")
    settings = get_settings()
    try:
        return sync_pending(db, settings, batch_id=batch_id)
    except QBONotConnectedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
