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
START_TEXT_EXPECTED = (
    "Comandos:\n/donde · dónde está el coche\n/trayectos · últimos trayectos\n"
    "/estado · motor y batería\n/averias · averías guardadas\n"
    "/escanear · leer averías ahora\n"
    "/borrar_averias · borrar averías de la centralita")
NOW = 1_700_000_000_000


class FakeClient:
    def __init__(self):
        self.calls = []
        self.parse_modes = []

    def send_message(self, chat_id, text, reply_markup=None, parse_mode=None):
        self.calls.append(("message", chat_id, text))
        self.parse_modes.append(parse_mode)
        if reply_markup is not None:
            self.calls.append(("markup", reply_markup))

    def send_photo(self, chat_id, photo, caption, parse_mode=None):
        if getattr(self, "photo_error", None):
            raise self.photo_error
        self.calls.append(("photo", chat_id, photo, caption))
        self.parse_modes.append(parse_mode)

    def answer_callback_query(self, callback_query_id):
        self.calls.append(("answer", callback_query_id))

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


def run(update, conn, client, fetch_tile=None):
    handle_update(update, chat_id=CHAT, client=client, conn=conn, now_ms=NOW, tz="Europe/Madrid",
                  fetch_tile=fetch_tile)


def grey_tile(z, x, y):
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (256, 256), (200, 200, 200)).save(buf, "PNG")
    return buf.getvalue()


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
    {"update_id": 1, "callback_query": "garbage"},
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
    assert c.calls == [("message", CHAT, START_TEXT_EXPECTED)]


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


def test_logging_setup_keeps_token_out_of_logs():
    import logging

    class Collect(logging.Handler):
        def __init__(self):
            super().__init__(level=logging.NOTSET)
            self.messages = []

        def emit(self, record):
            self.messages.append(record.getMessage())

    marker = "TEST:FAKE-MARKER"
    t = httpx.MockTransport(lambda r: httpx.Response(200, json={"ok": True, "result": []}))
    root = logging.getLogger()
    names = ("httpx", "httpcore")
    saved = (root.level, [logging.getLogger(n).level for n in names])
    collect = Collect()
    root.addHandler(collect)
    try:
        root.setLevel(logging.INFO)  # what basicConfig(level=INFO) gives in production
        botmain.setup_logging()
        TelegramClient(marker, httpx.Client(transport=t)).get_updates(None)
        levels = [logging.getLogger(n).level for n in names]
    finally:
        root.removeHandler(collect)
        root.setLevel(saved[0])
        for n, lvl in zip(names, saved[1]):
            logging.getLogger(n).setLevel(lvl)
    assert levels == [logging.WARNING, logging.WARNING]
    assert not any(marker in m for m in collect.messages)


def test_transport_error_is_wrapped_without_token():
    marker = "TEST:FAKE-MARKER"

    def boom(request):
        raise httpx.ConnectError("failed", request=request)

    c = TelegramClient(marker, httpx.Client(transport=httpx.MockTransport(boom)))
    with pytest.raises(botmain.TelegramError) as ei:
        c.send_message(CHAT, "hi")
    assert marker not in str(ei.value)
    assert ei.value.__cause__ is None and ei.value.__suppress_context__


# ---- trips, estado, averias ----

def cb(data, chat=CHAT, cid="q1"):
    return {"update_id": 1, "callback_query": {
        "id": cid, "data": data, "message": {"chat": {"id": chat}}}}


def drive(conn, start_ts, seconds=300, session="s1", north0=0.0):
    for i in range(0, seconds + 1, 10):
        ts = start_ts + i * 1000
        conn.execute(
            "INSERT INTO records(id, device_id, session_id, seq, ts, type, data, received_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (f"{session}-{ts}", "d", session, i, ts, "gps",
             json.dumps({"lat": 40.0 + (north0 + i * 10) / 111_195.0, "lon": -3.0,
                         "acc_m": 5.0, "speed_mps": 10.0}), ts))


def test_trayectos_sends_list_and_keyboard(conn):
    drive(conn, NOW - 3_600_000)
    c = FakeClient()
    run(msg("/trayectos"), conn, c)
    assert c.calls[0][0] == "message" and "Últimos trayectos" in c.calls[0][2]
    assert c.calls[1][0] == "markup"
    assert c.calls[1][1]["inline_keyboard"][0][0]["callback_data"].startswith("trip:")
    assert c.parse_modes == ["HTML"]


def test_trayectos_empty(conn):
    c = FakeClient()
    run(msg("/trayectos"), conn, c)
    assert c.calls == [("message", CHAT, "Todavía no hay trayectos.")]


def trip_callback(conn):
    drive(conn, NOW - 3_600_000)
    c = FakeClient()
    run(msg("/trayectos"), conn, c)
    return c.calls[1][1]["inline_keyboard"][0][0]["callback_data"]


def test_callback_trip_sends_route_photo_with_detail_caption(conn):
    data = trip_callback(conn)
    c2 = FakeClient()
    run(cb(data), conn, c2, fetch_tile=grey_tile)
    assert [x[0] for x in c2.calls] == ["answer", "photo"]
    _, chat, photo, caption = c2.calls[1]
    assert chat == CHAT and photo[:8] == b"\x89PNG\r\n\x1a\n"
    assert "🕒" in caption and "Sin posiciones GPS" not in caption
    assert c2.parse_modes == ["HTML"]
    assert not [x for x in c2.calls if x[0] in ("message", "markup")]


def test_callback_trip_render_failure_falls_back_to_message(conn, caplog):
    data = trip_callback(conn)
    c2 = FakeClient()
    c3 = FakeClient()

    def boom(z, x, y):
        raise RuntimeError("tiles down")

    run(cb(data), conn, c2, fetch_tile=grey_tile)
    run(cb(data), conn, c3, fetch_tile=boom)
    assert [x[0] for x in c3.calls] == ["answer", "message"]
    assert c3.calls[1][2] == c2.calls[1][3]
    assert c3.parse_modes == ["HTML"]


def test_callback_trip_photo_send_failure_falls_back_to_message(conn):
    data = trip_callback(conn)
    ok = FakeClient()
    run(cb(data), conn, ok, fetch_tile=grey_tile)
    c = FakeClient()
    c.photo_error = RuntimeError("boom")
    run(cb(data), conn, c, fetch_tile=grey_tile)
    assert [x[0] for x in c.calls] == ["answer", "message"]
    assert c.calls[1][2] == ok.calls[1][3]


def test_callback_trip_long_text_sends_photo_then_message(conn, monkeypatch):
    from app.bot import commands

    data = trip_callback(conn)
    monkeypatch.setattr(commands, "format_trip_detail", lambda *a: "x" * 1500)
    c = FakeClient()
    run(cb(data), conn, c, fetch_tile=grey_tile)
    assert [x[0] for x in c.calls] == ["answer", "photo", "message"]
    assert c.calls[1][3] == ""
    assert c.calls[2][2] == "x" * 1500


def test_callback_trip_without_points_sends_text_only(conn, monkeypatch):
    from dataclasses import replace

    from app.bot import commands

    data = trip_callback(conn)
    real = commands.get_trip
    monkeypatch.setattr(commands, "get_trip", lambda conn, tid: replace(real(conn, tid), points=[]))
    c2 = FakeClient()
    run(cb(data), conn, c2, fetch_tile=grey_tile)
    assert [x[0] for x in c2.calls] == ["answer", "message"]
    assert c2.calls[1][2].endswith("📎 Sin posiciones GPS válidas para la ruta")


def test_callback_unknown_trip(conn):
    c = FakeClient()
    run(cb("trip:nope:123"), conn, c)
    assert c.calls == [("answer", "q1"),
                       ("message", CHAT, "Ese trayecto ya no está disponible.")]


@pytest.mark.parametrize("data", ["trip:", "trip:garbage", "xyz", "trips:abc", "trips:", None, 5])
def test_callback_malformed_only_answers(conn, data):
    c = FakeClient()
    run(cb(data), conn, c)
    assert c.calls == [("answer", "q1")]


def test_callback_trips_nothing_older(conn):
    drive(conn, NOW - 3_600_000)
    c = FakeClient()
    run(cb("trips:1"), conn, c)
    assert c.calls == [("answer", "q1"), ("message", CHAT, "No hay trayectos anteriores.")]


def test_callback_trips_older_page(conn):
    drive(conn, NOW - 7_200_000, session="a")
    drive(conn, NOW - 3_600_000, session="b")
    c = FakeClient()
    run(cb(f"trips:{NOW - 3_600_000}"), conn, c)
    assert c.calls[0] == ("answer", "q1")
    assert c.calls[1][0] == "message" and "Últimos trayectos" in c.calls[1][2]
    assert c.parse_modes == ["HTML"]


def test_callback_other_chat_ignored(conn):
    c = FakeClient()
    run(cb("trip:s1:1", chat=999), conn, c)
    assert c.calls == []


def test_callback_without_message_ignored(conn):
    c = FakeClient()
    run({"update_id": 1, "callback_query": {"id": "x", "data": "trip:a:1"}}, conn, c)
    assert c.calls == []


def test_estado_and_averias_route_to_formatters(conn):
    from app.dtc import format_averias
    from app.vehicle import format_estado
    c = FakeClient()
    run(msg("/estado"), conn, c)
    run(msg("/averias"), conn, c)
    assert c.calls == [
        ("message", CHAT, format_estado(conn, NOW, "Europe/Madrid")),
        ("message", CHAT, format_averias(conn, NOW, "Europe/Madrid"))]


def test_client_new_methods():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"ok": True, "result": True})

    client = TelegramClient("TEST:FAKE", httpx.Client(transport=httpx.MockTransport(handler)))
    kb = {"inline_keyboard": [[{"text": "1", "callback_data": "trip:a:1"}]]}
    client.send_message(CHAT, "hi", reply_markup=kb)
    client.answer_callback_query("q9")
    assert [r.url.path for r in seen] == [
        "/botTEST:FAKE/sendMessage", "/botTEST:FAKE/answerCallbackQuery"]
    assert json.loads(seen[0].content) == {"chat_id": CHAT, "text": "hi", "reply_markup": kb}
    assert json.loads(seen[1].content) == {"callback_query_id": "q9"}


def test_send_message_parse_mode_only_when_given():
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"ok": True, "result": True})

    client = TelegramClient("TEST:FAKE", httpx.Client(transport=httpx.MockTransport(handler)))
    client.send_message(CHAT, "plain")
    client.send_message(CHAT, "<b>x</b>", parse_mode="HTML")
    assert seen[0] == {"chat_id": CHAT, "text": "plain"}
    assert seen[1] == {"chat_id": CHAT, "text": "<b>x</b>", "parse_mode": "HTML"}


def test_send_message_error_hides_token():
    marker = "TEST:FAKE-MARKER"
    t = httpx.MockTransport(lambda r: httpx.Response(500))
    c = TelegramClient(marker, httpx.Client(transport=t))
    with pytest.raises(botmain.TelegramError) as ei:
        c.send_message(CHAT, "x")
    assert marker not in str(ei.value)


def test_callback_still_handled_when_answer_fails(conn, caplog):
    from app.bot.telegram import TelegramError

    class FailingAnswer(FakeClient):
        def answer_callback_query(self, callback_query_id):
            raise TelegramError("answerCallbackQuery: HTTP 400")

    drive(conn, NOW - 3_600_000)
    c = FakeClient()
    run(msg("/trayectos"), conn, c)
    data = c.calls[1][1]["inline_keyboard"][0][0]["callback_data"]
    c2 = FailingAnswer()
    run(cb(data), conn, c2)
    assert c2.calls[0][0] == "message" and "🕒" in c2.calls[0][2]
    assert len(c2.calls) == 1
    assert "HTTP 400" not in caplog.text


def test_escanear_parked_replies_apagado_and_saves_nothing(conn):
    c = FakeClient()
    run(msg("/escanear"), conn, c)
    assert c.calls == [("message", CHAT,
        "🅿️ El coche está apagado. Las averías se leen solas cada vez que arranca; "
        "/averias muestra la última lectura.")]
    assert conn.execute("SELECT COUNT(*) FROM scan_requests").fetchone()[0] == 0


def test_escanear_moving_creates_scan(conn):
    add_gps(conn, NOW - 5_000)
    add_gps(conn, NOW - 2_000, lat=40.001)
    conn.execute(
        "INSERT INTO records(id, device_id, session_id, seq, ts, type, data, received_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        ("o1", "d", "s", 2, NOW - 1_000, "obd", json.dumps({"rpm": 2000, "speed_kmh": 50}), NOW),
    )
    from app.location import car_status
    assert car_status(conn, NOW).state not in {"parked", "no_signal", "no_data"}
    c = FakeClient()
    run(msg("/escanear"), conn, c)
    assert c.calls == [("message", CHAT, "🔍 Leyendo averías… (tarda menos de un minuto)")]
    assert conn.execute("SELECT COUNT(*) FROM scan_requests").fetchone()[0] == 1


# ---- /borrar_averias ----

ENGINE_RUNNING = "🔑 Para borrar, pon el contacto con el motor apagado y vuelve a mandar /borrar_averias."
CAR_OFF = "🅿️ El coche está apagado. Pon el contacto (sin arrancar) y manda /borrar_averias."
NO_ELM = "⚠️ La tablet no está conectada al ELM327 ahora mismo."
WARNING = "No arregla nada: si el fallo sigue, volverá a aparecer. También se reinician las pruebas de emisiones."
CANCELLED = "Borrado cancelado."


def add_obd(conn, ts, rpm):
    conn.execute(
        "INSERT INTO records(id, device_id, session_id, seq, ts, type, data, received_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (f"o{ts}", "d", "s", 2, ts, "obd", json.dumps({"values": {"rpm": rpm, "speed_kmh": 0}}), ts),
    )


def engine_off(conn):
    add_gps(conn, NOW - 3_000)
    add_obd(conn, NOW - 1_000, 0)


def add_dtc_rec(conn, ts, active, pending=()):
    conn.execute(
        "INSERT INTO records(id, device_id, session_id, seq, ts, type, data, received_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (f"d{ts}", "d", "s", 3, ts, "dtc",
         json.dumps({"active": list(active), "pending": list(pending)}), ts),
    )


def clear_rows(conn):
    return conn.execute("SELECT COUNT(*) FROM scan_requests WHERE kind='clear_dtc'").fetchone()[0]


def confirm_id(c):
    markup = [x for x in c.calls if x[0] == "markup"][0][1]
    return markup["inline_keyboard"][0][0]["callback_data"].split(":", 1)[1]


def test_borrar_parked_no_data(conn):
    c = FakeClient()
    run(msg("/borrar_averias"), conn, c)  # no_data
    assert c.calls == [("message", CHAT, CAR_OFF)]
    c = FakeClient()
    add_gps(conn, NOW - 400_000)
    run(msg("/borrar_averias"), conn, c)  # parked
    assert c.calls == [("message", CHAT, CAR_OFF)]
    assert conn.execute("SELECT COUNT(*) FROM clear_confirmations").fetchone()[0] == 0


def test_borrar_engine_running(conn):
    add_gps(conn, NOW - 3_000)
    add_obd(conn, NOW - 1_000, 800)  # idle
    c = FakeClient()
    run(msg("/borrar_averias"), conn, c)
    assert c.calls == [("message", CHAT, ENGINE_RUNNING)]
    assert conn.execute("SELECT COUNT(*) FROM clear_confirmations").fetchone()[0] == 0


def test_borrar_moving(conn):
    add_gps(conn, NOW - 5_000)
    add_gps(conn, NOW - 2_000, lat=40.001)
    conn.execute(
        "INSERT INTO records(id, device_id, session_id, seq, ts, type, data, received_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        ("om", "d", "s", 2, NOW - 1_000, "obd",
         json.dumps({"values": {"rpm": 2000, "speed_kmh": 50}}), NOW))
    c = FakeClient()
    run(msg("/borrar_averias"), conn, c)
    assert c.calls == [("message", CHAT, ENGINE_RUNNING)]


def test_borrar_stopped_no_elm(conn):
    add_gps(conn, NOW - 1_000)
    c = FakeClient()
    run(msg("/borrar_averias"), conn, c)
    assert c.calls == [("message", CHAT, NO_ELM)]


def test_borrar_confirmation_with_codes(conn):
    engine_off(conn)
    add_dtc_rec(conn, NOW - 50_000, ["P0401"], ["P0409", "P0401"])
    c = FakeClient()
    run(msg("/borrar_averias"), conn, c)
    cid = confirm_id(c)
    assert c.calls[0] == ("message", CHAT,
        "🗑️ Vas a borrar las averías guardadas en la centralita:\n"
        "• P0401 · Flujo insuficiente de recirculación de gases (EGR)\n"
        "• P0409 · Circuito del sensor de la EGR\n\n" + WARNING)
    assert c.calls[1] == ("markup", {"inline_keyboard": [[
        {"text": "🗑️ Sí, borrar", "callback_data": f"clear:{cid}"},
        {"text": "Cancelar", "callback_data": f"clearno:{cid}"}]]})


@pytest.mark.parametrize("seed", [False, True])
def test_borrar_confirmation_without_codes(conn, seed):
    engine_off(conn)
    if seed:
        add_dtc_rec(conn, NOW - 50_000, [])
    c = FakeClient()
    run(msg("/borrar_averias"), conn, c)
    assert c.calls[0] == ("message", CHAT,
        "🗑️ Vas a borrar las averías guardadas en la centralita "
        "(la última lectura no tenía ninguna).\n\n" + WARNING)


def test_borrar_confirm_creates_scan_once(conn):
    engine_off(conn)
    c = FakeClient()
    run(msg("/borrar_averias"), conn, c)
    cid = confirm_id(c)
    c2 = FakeClient()
    run(cb(f"clear:{cid}"), conn, c2)
    assert c2.calls == [("answer", "q1"), ("message", CHAT, "🗑️ Borrando…")]
    assert clear_rows(conn) == 1
    c3 = FakeClient()
    run(cb(f"clear:{cid}", cid="q2"), conn, c3)
    assert c3.calls == [("answer", "q2"), ("message", CHAT, CANCELLED)]
    assert clear_rows(conn) == 1


def test_borrar_confirm_expired(conn):
    engine_off(conn)
    from app.confirmations import CLEAR_CONFIRM_MS, create_confirmation
    cid = create_confirmation(conn, NOW - CLEAR_CONFIRM_MS - 1)
    c = FakeClient()
    run(cb(f"clear:{cid}"), conn, c)
    assert c.calls == [("answer", "q1"), ("message", CHAT, CANCELLED)]
    assert clear_rows(conn) == 0


def test_borrar_confirm_unknown_id(conn):
    engine_off(conn)
    c = FakeClient()
    run(cb("clear:nope"), conn, c)
    assert c.calls == [("answer", "q1"), ("message", CHAT, CANCELLED)]


def test_borrar_cancel(conn):
    engine_off(conn)
    c = FakeClient()
    run(msg("/borrar_averias"), conn, c)
    cid = confirm_id(c)
    c2 = FakeClient()
    run(cb(f"clearno:{cid}"), conn, c2)
    assert c2.calls == [("answer", "q1"), ("message", CHAT, CANCELLED)]
    c3 = FakeClient()
    run(cb(f"clear:{cid}", cid="q2"), conn, c3)
    assert c3.calls == [("answer", "q2"), ("message", CHAT, CANCELLED)]
    assert clear_rows(conn) == 0


def test_borrar_engine_started_between(conn):
    engine_off(conn)
    c = FakeClient()
    run(msg("/borrar_averias"), conn, c)
    cid = confirm_id(c)
    add_obd(conn, NOW - 500, 900)
    c2 = FakeClient()
    run(cb(f"clear:{cid}"), conn, c2)
    assert c2.calls == [("answer", "q1"), ("message", CHAT, ENGINE_RUNNING)]
    assert clear_rows(conn) == 0


def test_borrar_other_chat_ignored(conn):
    engine_off(conn)
    c = FakeClient()
    run(msg("/borrar_averias", chat=99), conn, c)
    assert c.calls == []
    from app.confirmations import create_confirmation
    cid = create_confirmation(conn, NOW)
    run(cb(f"clear:{cid}", chat=99), conn, c)
    assert c.calls == [] and clear_rows(conn) == 0


def test_set_my_commands_includes_borrar():
    import inspect
    assert '("borrar_averias", "Borrar averías de la centralita")' in inspect.getsource(botmain.main)


def test_send_photo_is_multipart():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"ok": True, "result": True})

    client = TelegramClient("TEST:FAKE", httpx.Client(transport=httpx.MockTransport(handler)))
    client.send_photo(CHAT, b"\x89PNGdata", "<b>hi</b>", parse_mode="HTML")
    r = seen[0]
    assert r.url.path == "/botTEST:FAKE/sendPhoto"
    assert r.headers["content-type"].startswith("multipart/form-data")
    body = r.content
    assert b'name="photo"; filename="route.png"' in body
    assert b"Content-Type: image/png" in body and b"\x89PNGdata" in body
    for field, value in (("chat_id", str(CHAT)), ("caption", "<b>hi</b>"), ("parse_mode", "HTML")):
        assert f'name="{field}"\r\n\r\n{value}'.encode() in body


def test_send_photo_error_hides_token():
    marker = "TEST:FAKE-MARKER"
    t = httpx.MockTransport(lambda r: httpx.Response(500))
    c = TelegramClient(marker, httpx.Client(transport=t))
    with pytest.raises(botmain.TelegramError) as ei:
        c.send_photo(CHAT, b"x", "cap")
    assert marker not in str(ei.value)
