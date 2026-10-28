import os
import tempfile

import pytest

import database.db as db

# app.py runs init_db()/seed_db() at import time — point it at a throwaway
# file first so the test run never touches expense_tracker.db.
db.DB_PATH = os.path.join(tempfile.mkdtemp(), "import.db")

from app import app as flask_app  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    db.init_db()
    db.seed_db()


@pytest.fixture
def app():
    flask_app.config.update(TESTING=True)
    return flask_app
