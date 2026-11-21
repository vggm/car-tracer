"""Command handling for the car's Telegram bot."""
import logging

import httpx

from app.dtc import format_averias
from app.gpx import to_gpx
from app.bot.telegram import TelegramError
from app.location import car_status, format_status
from app.scans import create_scan
from app.trip_text import format_trip_detail, format_trip_list, trip_list_keyboard
from app.trips import get_trip, list_trips
from app.vehicle import format_estado

log = logging.getLogger(__name__)

START_TEXT = (
    "Comandos:\n"
    "/donde · dónde está el coche\n"
    "/trayectos · últimos trayectos\n"
    "/estado · motor y batería\n"
    "/averias · averías guardadas\n"
    "/escanear · leer averías ahora"
)

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
                        reply_markup=trip_list_keyboard(trips, has_more))


def _send_trip(client, chat_id, conn, tz, trip_id: str) -> None:
    _, sep, start = trip_id.rpartition(":")
    if not sep or not start.isdigit():
        return  # malformed
    trip = get_trip(conn, trip_id)
    if trip is None:
        client.send_message(chat_id, "Ese trayecto ya no está disponible.")
        return
    client.send_message(chat_id, format_trip_detail(trip, tz, bool(trip.points)))
    if trip.points:
        filename, content = to_gpx(trip.points, trip.start_ts, tz)
        client.send_document(chat_id, filename, content)


def _handle_callback(query: dict, *, chat_id, client, conn, now_ms, tz) -> None:
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
        _send_trip(client, chat_id, conn, tz, arg)
    elif kind == "trips" and arg.isdigit():
        _send_trip_list(client, chat_id, conn, now_ms, tz, int(arg),
                        "No hay trayectos anteriores.")


def handle_update(update: dict, *, chat_id: int, client, conn, now_ms: int, tz: str) -> None:
    if isinstance(update, dict) and isinstance(update.get("callback_query"), dict):
        _handle_callback(update["callback_query"], chat_id=chat_id, client=client,
                         conn=conn, now_ms=now_ms, tz=tz)
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
    elif cmd == "/start":
        client.send_message(chat_id, START_TEXT)
