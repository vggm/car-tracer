import os
import subprocess
import sys
import json

import httpx
import pytest

from app.bot import __main__ as botmain
from app.bot.commands import handle_update
from app.bot.telegram import TelegramClient
from app.db import connect

CHAT = 42
NOW = 1_700_000_000_000


class FakeClient:
    def __init__(self):
        self.calls = []

    def send_message(self, chat_id, text):
        self.calls.append(("message", chat_id, text))

    def send_location(self, chat_id, lat, lon):
        self.calls.append(("location", chat_id, lat, lon))


def msg(text, chat=CHAT):
    return {"update_id": 1, "message": {"text": text, "chat": {"id": chat}}}


def add_gps(conn, ts, lat=40.0, lon=-3.0):
    conn.execute(
        "INSERT INTO records(id, device_id, session_id, seq, ts, type, data, received_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (f"id{ts}", "d", "s", 1, ts, "gps",
         json.dumps({"lat": lat, "lon": lon, "acc_m": 5.0}), ts),
    )


@pytest.fixture
def conn(tmp_path):
    return connect(str(tmp_path / "t.db"))


def run(update, conn, client):
    handle_update(update, chat_id=CHAT, client=client, conn=conn, now_ms=NOW, tz="Europe/Madrid")


def test_donde_sends_text_then_location(conn):
    add_gps(conn, NOW - 1000, 40.5, -3.5)
    c = FakeClient()
    run(msg("/donde"), conn, c)
    assert [x[0] for x in c.calls] == ["message", "location"]
    assert c.calls[1] == ("location", CHAT, 40.5, -3.5)


def test_donde_with_botname_suffix(conn):
    c = FakeClient()
    run(msg("/donde@car_bot"), conn, c)
    assert len(c.calls) == 1


def test_donde_without_point_sends_only_text(conn):
    c = FakeClient()
    run(msg("/donde"), conn, c)
    assert c.calls == [("message", CHAT, "Todavía no hay datos del coche.")]


def test_other_chat_is_ignored(conn):
    c = FakeClient()
    run(msg("/donde", chat=999), conn, c)
    assert c.calls == []


@pytest.mark.parametrize("update", [
    {"update_id": 1, "edited_message": {"text": "/donde", "chat": {"id": CHAT}}},
    {"update_id": 1, "callback_query": {"id": "x", "data": "/donde"}},
    {"update_id": 1, "message": {"photo": [{}], "chat": {"id": CHAT}}},
    {"update_id": 1, "message": {"text": "/donde"}},
    {"update_id": 1, "message": {"text": "hola", "chat": {"id": CHAT}}},
    {"update_id": 1, "message": "garbage"},
    {"update_id": 1, "message": {"text": 5, "chat": None}},
])
def test_non_text_updates_are_ignored(conn, update):
    c = FakeClient()
    run(update, conn, c)
    assert c.calls == []


def test_start_lists_commands(conn):
    c = FakeClient()
    run(msg("/start"), conn, c)
    assert c.calls == [("message", CHAT, "Comandos:\n/donde · dónde está el coche")]


def test_client_builds_urls():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"ok": True, "result": [{"update_id": 7}]})

    client = TelegramClient("TEST:FAKE", httpx.Client(transport=httpx.MockTransport(handler)))
    assert client.get_updates(5, timeout=30) == [{"update_id": 7}]
    client.send_location(CHAT, 1.5, 2.5)
    client.send_message(CHAT, "hi")
    client.set_my_commands([("donde", "Dónde está el coche")])
    assert [r.url.path for r in seen] == [
        "/botTEST:FAKE/getUpdates", "/botTEST:FAKE/sendLocation",
        "/botTEST:FAKE/sendMessage", "/botTEST:FAKE/setMyCommands"]
    q = json.loads(seen[0].content)
    assert q == {"offset": 5, "timeout": 30}
    loc = json.loads(seen[1].content)
    assert loc == {"chat_id": CHAT, "latitude": 1.5, "longitude": 2.5}
    cmds = json.loads(seen[3].content)
    assert cmds == {"commands": [{"command": "donde", "description": "Dónde está el coche"}]}


def test_client_ok_false_raises():
    t = httpx.MockTransport(lambda r: httpx.Response(200, json={"ok": False}))
    with pytest.raises(botmain.TelegramError):
        TelegramClient("TEST:FAKE", httpx.Client(transport=t)).get_updates(None)


class LoopClient:
    """get_updates plays a script of results/exceptions, then stops the loop."""

    def __init__(self, script):
        self.script = list(script)
        self.offsets = []

    def get_updates(self, offset, timeout=50):
        self.offsets.append(offset)
        if not self.script:
            raise KeyboardInterrupt
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def test_loop_advances_offset_and_survives_handler_failure():
    handled = []

    def handler(update):
        handled.append(update["update_id"])
        if update["update_id"] == 10:
            raise RuntimeError("boom")

    client = LoopClient([[{"update_id": 10}, {"update_id": 11}], []])
    with pytest.raises(KeyboardInterrupt):
        botmain.poll_loop(client, handler, sleep=lambda s: None)
    assert handled == [10, 11]
    assert client.offsets == [None, 12, 12]


def test_loop_backoff_doubles_caps_and_resets():
    sleeps = []
    errs = [httpx.ConnectError("x")] * 8
    client = LoopClient(errs + [[], httpx.ConnectError("x")])
    with pytest.raises(KeyboardInterrupt):
        botmain.poll_loop(client, lambda u: None, sleep=sleeps.append)
    assert sleeps == [1, 2, 4, 8, 16, 32, 60, 60, 1]


def test_main_exits_1_without_token_or_chat():
    env = {k: v for k, v in os.environ.items()
           if k not in ("CAR_TRACE_BOT_TOKEN", "CHAT_ID")}
    p = subprocess.run([sys.executable, "-m", "app.bot"], env=env,
                       capture_output=True, text=True, timeout=30)
    assert p.returncode == 1
    assert "CAR_TRACE_BOT_TOKEN" in p.stderr and "CHAT_ID" in p.stderr


def test_logging_setup_keeps_token_out_of_logs(caplog):
    import logging
    marker = "TEST:FAKE-MARKER"
    t = httpx.MockTransport(lambda r: httpx.Response(200, json={"ok": True, "result": []}))
    root = logging.getLogger()
    saved = (root.level, list(root.handlers), logging.getLogger("httpx").level,
             logging.getLogger("httpcore").level)
    try:
        root.handlers.clear()
        botmain.setup_logging()
        caplog.set_level(logging.INFO)
        TelegramClient(marker, httpx.Client(transport=t)).get_updates(None)
        levels = (logging.getLogger("httpx").level, logging.getLogger("httpcore").level)
    finally:
        root.setLevel(saved[0])
        root.handlers[:] = saved[1]
        logging.getLogger("httpx").setLevel(saved[2])
        logging.getLogger("httpcore").setLevel(saved[3])
    assert levels == (logging.WARNING, logging.WARNING)
    assert marker not in caplog.text


def test_transport_error_is_wrapped_without_token():
    marker = "TEST:FAKE-MARKER"

    def boom(request):
        raise httpx.ConnectError("failed", request=request)

    c = TelegramClient(marker, httpx.Client(transport=httpx.MockTransport(boom)))
    with pytest.raises(botmain.TelegramError) as ei:
        c.send_message(CHAT, "hi")
    assert marker not in str(ei.value)
    assert ei.value.__cause__ is None and ei.value.__suppress_context__
