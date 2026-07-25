"""
MongoDB access point.

Real deployments point MONGODB_URI at an actual MongoDB instance (Atlas or local).
When TESTING=true (set automatically by the pytest fixtures), we swap in mongomock's
in-memory MongoClient, which implements the same pymongo API surface. This lets the
whole ingestion/classification/P&L pipeline be exercised in tests without any
external service, while production code never has an if-testing branch in it.
"""
from functools import lru_cache

from pymongo.database import Database

from app.config import get_settings


@lru_cache
def get_client():
    settings = get_settings()
    if settings.testing or settings.mongodb_uri.startswith("mongomock://"):
        import mongomock

        return mongomock.MongoClient()
    from pymongo import MongoClient

    return MongoClient(settings.mongodb_uri)


def get_db() -> Database:
    settings = get_settings()
    return get_client()[settings.mongodb_db_name]


def reset_client_cache() -> None:
    """Used by tests to force a fresh mongomock instance between test modules."""
    get_client.cache_clear()
