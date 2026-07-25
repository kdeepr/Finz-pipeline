from pymongo.database import Database

from app.db import get_db


def db_dep() -> Database:
    return get_db()
