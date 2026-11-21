import subprocess
import sys
from pathlib import Path

from app.__main__ import main

FWD = {"X-Forwarded-Host": "car.example.ts.net"}


def test_forwarded_request_to_healthz_is_404(client):
    assert client.get("/healthz", headers=FWD).status_code == 404


def test_forwarded_request_to_ingest_reaches_app(client):
    r = client.post("/api/v1/ingest", headers=FWD, json={})
    assert r.status_code == 401


def test_direct_request_to_healthz_is_200(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_forwarded_trailing_slash_is_404(client):
    assert client.post("/api/v1/ingest/", headers=FWD, json={}).status_code == 404


def test_forwarded_get_ingest_is_405_or_404(client):
    assert client.get("/api/v1/ingest", headers=FWD).status_code in (404, 405)


def test_docs_and_openapi_are_404(client):
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404
        assert client.get(path, headers=FWD).status_code == 404


def test_main_exits_1_without_ingest_token(monkeypatch, capsys):
    monkeypatch.delenv("CAR_TRACE_INGEST_TOKEN", raising=False)
    assert main() == 1
    assert "CAR_TRACE_INGEST_TOKEN" in capsys.readouterr().err


def test_python_m_app_exits_1_without_token(tmp_path):
    import os

    env = {k: v for k, v in os.environ.items() if k != "CAR_TRACE_INGEST_TOKEN"}
    env["CAR_TRACE_DB"] = str(tmp_path / "x.db")
    server_dir = Path(__file__).resolve().parents[1]
    p = subprocess.run([sys.executable, "-m", "app"], cwd=server_dir, env=env,
                       capture_output=True, text=True, timeout=30)
    assert p.returncode == 1
    assert "CAR_TRACE_INGEST_TOKEN" in p.stderr


def test_forwarded_panel_routes_are_404(client):
    for path in ["/", "/static/index.html", "/api/panel/overview", "/tiles/1/0/0.png"]:
        assert client.get(path, headers=FWD).status_code == 404, path
