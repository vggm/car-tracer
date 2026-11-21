"""Minimal Telegram Bot API client (long polling) on top of httpx."""
import httpx

API = "https://api.telegram.org"


class TelegramError(Exception):
    """The API answered with ok: false (or something unparseable)."""


class TelegramClient:
    def __init__(self, token: str, http: httpx.Client):
        self._base = f"{API}/bot{token}"
        self._http = http

    def _call(self, method: str, payload: dict, files: dict | None = None):
        # Errors are raised without the URL so the token never reaches logs.
        try:
            if files is None:
                resp = self._http.post(f"{self._base}/{method}", json=payload)
            else:
                resp = self._http.post(f"{self._base}/{method}", data=payload, files=files)
            resp.raise_for_status()
            body = resp.json()
        except httpx.HTTPStatusError as e:
            raise TelegramError(f"{method}: HTTP {e.response.status_code}") from None
        except httpx.HTTPError as e:
            raise TelegramError(f"{method}: {type(e).__name__}") from None
        except ValueError:
            raise TelegramError(f"{method}: invalid JSON") from None
        if not isinstance(body, dict) or not body.get("ok"):
            raise TelegramError(f"{method}: ok=false")
        return body.get("result")

    def get_updates(self, offset: int | None, timeout: int = 50) -> list[dict]:
        payload: dict = {"timeout": timeout}
        if offset is not None:
            payload["offset"] = offset
        return self._call("getUpdates", payload) or []

    def send_message(self, chat_id, text, reply_markup: dict | None = None):
        payload: dict = {"chat_id": chat_id, "text": text}
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        self._call("sendMessage", payload)

    def answer_callback_query(self, callback_query_id: str):
        self._call("answerCallbackQuery", {"callback_query_id": callback_query_id})

    def send_document(self, chat_id, filename: str, content: bytes):
        self._call("sendDocument", {"chat_id": chat_id},
                   files={"document": (filename, content, "application/gpx+xml")})

    def send_location(self, chat_id, lat, lon):
        self._call("sendLocation", {"chat_id": chat_id, "latitude": lat, "longitude": lon})

    def set_my_commands(self, commands: list[tuple[str, str]]):
        self._call("setMyCommands", {
            "commands": [{"command": c, "description": d} for c, d in commands]})
