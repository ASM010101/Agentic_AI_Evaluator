from __future__ import annotations

import os

os.environ.setdefault("AUTOGRADER_DATABASE_URL", "sqlite:///./data/test_autograder.db")
os.environ.setdefault("AUTOGRADER_ARTIFACT_DIR", "./data/test-artifacts")
os.environ.setdefault("AUTOGRADER_RUNNER", "fake")
os.environ.setdefault("AUTOGRADER_USE_LLM", "false")

import pytest

from app.core.db import Base, engine, init_db
from app.main import app


@pytest.fixture(autouse=True)
def clean_database():
    init_db()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def fastapi_app():
    return app
