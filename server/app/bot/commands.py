"""Command handling for the car's Telegram bot."""
from app.location import car_status, format_status

START_TEXT = "Comandos:\n/donde · dónde está el coche"


def _command(text: str) -> str:
    word = text.strip().split(maxsplit=1)[0] if text.strip() else ""
    return word.split("@", 1)[0].lower()


def handle_update(update: dict, *, chat_id: int, client, conn, now_ms: int, tz: str) -> None:
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
    elif cmd == "/start":
        client.send_message(chat_id, START_TEXT)
