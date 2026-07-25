"""Stores the current QBO OAuth connection (one sandbox company at a time, matching this app's scope)."""
from datetime import datetime, timedelta, timezone

from pymongo.database import Database

COLLECTION = "qbo_connection"
_DOC_ID = "current"


def save_tokens(db: Database, realm_id: str, access_token: str, refresh_token: str, expires_in: int) -> None:
    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat()
    db[COLLECTION].update_one(
        {"_id": _DOC_ID},
        {
            "$set": {
                "_id": _DOC_ID,
                "realm_id": realm_id,
                "access_token": access_token,
                "refresh_token": refresh_token,
                "access_token_expires_at": expires_at,
            }
        },
        upsert=True,
    )


def update_access_token(db: Database, access_token: str, refresh_token: str, expires_in: int) -> None:
    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat()
    db[COLLECTION].update_one(
        {"_id": _DOC_ID},
        {"$set": {"access_token": access_token, "refresh_token": refresh_token, "access_token_expires_at": expires_at}},
    )


def get_connection(db: Database) -> dict | None:
    return db[COLLECTION].find_one({"_id": _DOC_ID})


def is_access_token_expired(connection: dict, skew_seconds: int = 60) -> bool:
    expires_at = datetime.fromisoformat(connection["access_token_expires_at"])
    return datetime.now(timezone.utc) >= expires_at - timedelta(seconds=skew_seconds)
