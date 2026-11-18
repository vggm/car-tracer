import contextlib
import json
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import uvicorn

from app.config import Settings
from app.main import create_app

BEARER = "sim-bearer"
SCRIPT = Path(__file__).resolve().parents[2] / "tools" / "simulate_drive.py"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@contextlib.contextmanager
def _running_app(tmp_path):
    settings = Settings(
        ingest_token=BEARER,
        bot_token="",
        chat_id=None,
        db_path=str(tmp_path / "sim.db"),
        tz="Europe/Madrid",
    )
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(create_app(settings), host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        deadline = time.time() + 10
        while not server.started:
            assert time.time() < deadline, "server did not start"
            time.sleep(0.05)
        yield port
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def test_simulator_against_app(tmp_path):
    with _running_app(tmp_path) as port:
        proc = subprocess.run(
            [
                sys.executable, str(SCRIPT),
                "--url", f"http://127.0.0.1:{port}/api/v1/ingest",
                "--token", BEARER,
                "--minutes", "2", "--batch", "30", "--repeat",
            ],
            capture_output=True, text=True, timeout=60,
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr
        responses = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
        assert len(responses) >= 2
        *first, last = responses
        assert sum(r["accepted"] for r in first) == 82
        assert all(r["rejected"] == [] for r in responses)
        assert last["accepted"] == 0
        assert last["duplicates"] > 0


def test_simulator_reads_token_from_environment(tmp_path):
    with _running_app(tmp_path) as port:
        env = {**os.environ, "CAR_TRACE_INGEST_TOKEN": BEARER}
        proc = subprocess.run(
            [
                sys.executable, str(SCRIPT),
                "--url", f"http://127.0.0.1:{port}/api/v1/ingest",
                "--minutes", "1", "--batch", "30",
            ],
            capture_output=True, text=True, timeout=60, env=env,
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr
        responses = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
        assert sum(r["accepted"] for r in responses) > 0


def test_simulator_without_any_token_fails(tmp_path):
    env = {k: v for k, v in os.environ.items() if k != "CAR_TRACE_INGEST_TOKEN"}
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--url", "http://127.0.0.1:1/x"],
        capture_output=True, text=True, timeout=60, env=env,
    )
    assert proc.returncode != 0
    assert "token" in proc.stderr.lower()
