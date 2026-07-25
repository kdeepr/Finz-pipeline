import secrets

from fastapi import APIRouter, Depends, HTTPException
from pymongo.database import Database

from app.classification.coa import load_chart_of_accounts
from app.config import get_settings
from app.deps import db_dep
from app.qbo import connection_store, oauth
from app.qbo.accounts_sync import sync_account_ids
from app.qbo.client import QBOClient, QBONotConnectedError
from app.qbo.sync_service import sync_pending

router = APIRouter(prefix="/api/qbo", tags=["qbo"])

_STATE_COLLECTION = "qbo_oauth_state"


@router.get("/connect")
def connect(db: Database = Depends(db_dep)):
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
def callback(code: str, state: str, realmId: str, db: Database = Depends(db_dep)):
    if not db[_STATE_COLLECTION].find_one({"state": state}):
        raise HTTPException(status_code=400, detail="Unrecognized or expired OAuth state.")
    settings = get_settings()
    tokens = oauth.exchange_code_for_tokens(settings, code)
    connection_store.save_tokens(db, realmId, tokens["access_token"], tokens["refresh_token"], tokens["expires_in"])
    db[_STATE_COLLECTION].delete_one({"state": state})
    return {"connected": True, "realm_id": realmId}


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
