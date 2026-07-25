import os

os.environ["TESTING"] = "true"

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import reset_client_cache
from app.main import app


@pytest.fixture(autouse=True)
def _fresh_mongomock():
    """Every test gets its own in-memory Mongo, so tests never see each other's data."""
    reset_client_cache()
    get_settings.cache_clear()
    yield


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
