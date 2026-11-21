"""Command handling for the car's Telegram bot."""
import logging

import httpx

from app.confirmations import consume_confirmation, create_confirmation
from app.dtc import format_averias, format_codes, latest_dtc
from app.bot.telegram import TelegramError
from app.location import car_status, format_status
from app.scans import create_scan
from app.route_map import render_route_png
from app.trip_text import format_trip_detail, format_trip_list, has_route, trip_list_keyboard
from app.trips import get_trip, list_trips
from app.vehicle import format_estado

log = logging.getLogger(__name__)

START_TEXT = (
    "Comandos:\n"
    "/donde · dónde está el coche\n"
    "/trayectos · últimos trayectos\n"
    "/estado · motor y batería\n"
    "/averias · averías guardadas\n"
    "/escanear · leer averías ahora\n"
    "/borrar_averias · borrar averías de la centralita"
)

CLEAR_GATE_TEXTS = {
    "moving": "🔑 Para borrar, pon el contacto con el motor apagado y vuelve a mandar /borrar_averias.",
    "idle": "🔑 Para borrar, pon el contacto con el motor apagado y vuelve a mandar /borrar_averias.",
    "parked": "🅿️ El coche está apagado. Pon el contacto (sin arrancar) y manda /borrar_averias.",
    "no_signal": "🅿️ El coche está apagado. Pon el contacto (sin arrancar) y manda /borrar_averias.",
    "no_data": "🅿️ El coche está apagado. Pon el contacto (sin arrancar) y manda /borrar_averias.",
    "stopped": "⚠️ La tablet no está conectada al ELM327 ahora mismo.",
}
CLEAR_WARNING = (
    "No arregla nada: si el fallo sigue, volverá a aparecer. "
    "También se reinician las pruebas de emisiones."
)
CLEAR_CANCELLED = "Borrado cancelado."

APAGADO_TEXT = (
    "🅿️ El coche está apagado. Las averías se leen solas cada vez que arranca; "
    "/averias muestra la última lectura."
)


def _command(text: str) -> str:
    word = text.strip().split(maxsplit=1)[0] if text.strip() else ""
    return word.split("@", 1)[0].lower()


def _send_trip_list(client, chat_id, conn, now_ms, tz, before_ts, empty_text) -> None:
    trips, has_more = list_trips(conn, before_ts=before_ts)
    if not trips:
        client.send_message(chat_id, empty_text)
        return
    client.send_message(chat_id, format_trip_list(trips, now_ms, tz),
                        reply_markup=trip_list_keyboard(trips, has_more), parse_mode="HTML")


CAPTION_LIMIT = 1024


def _send_trip_text(client, chat_id, text: str) -> None:
    client.send_message(chat_id, text, parse_mode="HTML")


def _send_trip(client, chat_id, conn, tz, trip_id: str, fetch_tile=None) -> None:
    _, sep, start = trip_id.rpartition(":")
    if not sep or not start.isdigit():
        return  # malformed
    trip = get_trip(conn, trip_id)
    if trip is None:
        client.send_message(chat_id, "Ese trayecto ya no está disponible.")
        return
    route = has_route(trip.points)
    text = format_trip_detail(trip, tz, route)
    if not route or fetch_tile is None:
        _send_trip_text(client, chat_id, text)
        return
    try:
        png = render_route_png(trip.points, fetch_tile)
        short = len(text) <= CAPTION_LIMIT
        client.send_photo(chat_id, png, caption=text if short else "", parse_mode="HTML")
    except Exception as e:
        # type name only: the message or URL may carry the bot credential
        log.warning("trip route image failed: %s", type(e).__name__)
        _send_trip_text(client, chat_id, text)
        return
    if not short:
        _send_trip_text(client, chat_id, text)


def _clear_gate(conn, now_ms) -> str | None:
    """Spanish refusal text unless the car is ready (engine_off)."""
    state = car_status(conn, now_ms).state
    return None if state == "engine_off" else CLEAR_GATE_TEXTS.get(state, CLEAR_GATE_TEXTS["stopped"])


def _confirmation_text(conn) -> str:
    latest = latest_dtc(conn)
    codes: list[str] = []
    if latest is not None:
        for c in latest[1] + latest[2]:
            if c not in codes:
                codes.append(c)
    if codes:
        head = "🗑️ Vas a borrar las averías guardadas en la centralita:\n" + "\n".join(format_codes(codes))
    else:
        head = ("🗑️ Vas a borrar las averías guardadas en la centralita "
                "(la última lectura no tenía ninguna).")
    return f"{head}\n\n{CLEAR_WARNING}"


def _start_clear(client, chat_id, conn, now_ms) -> None:
    refusal = _clear_gate(conn, now_ms)
    if refusal is not None:
        client.send_message(chat_id, refusal)
        return
    cid = create_confirmation(conn, now_ms)
    client.send_message(chat_id, _confirmation_text(conn), reply_markup={"inline_keyboard": [[
        {"text": "🗑️ Sí, borrar", "callback_data": f"clear:{cid}"},
        {"text": "Cancelar", "callback_data": f"clearno:{cid}"},
    ]]})


def _confirm_clear(client, chat_id, conn, now_ms, cid: str) -> None:
    if not consume_confirmation(conn, cid, now_ms):
        client.send_message(chat_id, CLEAR_CANCELLED)
        return
    refusal = _clear_gate(conn, now_ms)
    if refusal is not None:
        client.send_message(chat_id, refusal)
        return
    create_scan(conn, now_ms, kind="clear_dtc")
    client.send_message(chat_id, "🗑️ Borrando…")


def _handle_callback(query: dict, *, chat_id, client, conn, now_ms, tz, fetch_tile=None) -> None:
    message = query.get("message")
    chat = message.get("chat") if isinstance(message, dict) else None
    if not isinstance(chat, dict) or chat.get("id") != chat_id:
        return
    query_id = query.get("id")
    if not isinstance(query_id, str):
        return
    try:
        client.answer_callback_query(query_id)
    except (TelegramError, httpx.HTTPError) as e:
        # type name only: the message or URL may carry the bot credential
        log.warning("answer_callback_query failed: %s", type(e).__name__)
    data = query.get("data")
    if not isinstance(data, str):
        return
    kind, _, arg = data.partition(":")
    if kind == "trip" and arg:
        _send_trip(client, chat_id, conn, tz, arg, fetch_tile)
    elif kind == "trips" and arg.isdigit():
        _send_trip_list(client, chat_id, conn, now_ms, tz, int(arg),
                        "No hay trayectos anteriores.")
    elif kind == "clear" and arg:
        _confirm_clear(client, chat_id, conn, now_ms, arg)
    elif kind == "clearno" and arg:
        consume_confirmation(conn, arg, now_ms)
        client.send_message(chat_id, CLEAR_CANCELLED)


def handle_update(update: dict, *, chat_id: int, client, conn, now_ms: int, tz: str,
                  fetch_tile=None) -> None:
    if isinstance(update, dict) and isinstance(update.get("callback_query"), dict):
        _handle_callback(update["callback_query"], chat_id=chat_id, client=client,
                         conn=conn, now_ms=now_ms, tz=tz, fetch_tile=fetch_tile)
        return
    message = update.get("message") if isinstance(update, dict) else None
    if not isinstance(message, dict):
        return
    text = message.get("text")
    chat = message.get("chat")
    if not isinstance(text, str) or not isinstance(chat, dict) or chat.get("id") != chat_id:
        return
    cmd = _command(text)
    if cmd == "/donde":
        status = car_status(conn, now_ms)
        client.send_message(chat_id, format_status(status, now_ms, tz))
        if status.point is not None:
            client.send_location(chat_id, status.point.lat, status.point.lon)
    elif cmd == "/trayectos":
        _send_trip_list(client, chat_id, conn, now_ms, tz, None, "Todavía no hay trayectos.")
    elif cmd == "/estado":
        client.send_message(chat_id, format_estado(conn, now_ms, tz))
    elif cmd == "/averias":
        client.send_message(chat_id, format_averias(conn, now_ms, tz))
    elif cmd == "/escanear":
        if car_status(conn, now_ms).state in {"parked", "no_signal", "no_data"}:
            client.send_message(chat_id, APAGADO_TEXT)
        else:
            create_scan(conn, now_ms)
            client.send_message(chat_id, "🔍 Leyendo averías… (tarda menos de un minuto)")
    elif cmd == "/borrar_averias":
        _start_clear(client, chat_id, conn, now_ms)
    elif cmd == "/start":
        client.send_message(chat_id, START_TEXT)
