import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

FIXED_NOW = 1763481600000
BEARER_FOR_TESTS = "test-token"


@pytest.fixture
def client(tmp_path):
    settings = Settings(
        ingest_token=BEARER_FOR_TESTS,
        bot_token="",
        chat_id=None,
        db_path=str(tmp_path / "t.db"),
        tz="Europe/Madrid",
    )
    app = create_app(settings, clock=lambda: FIXED_NOW)
    with TestClient(app) as c:
        yield c
