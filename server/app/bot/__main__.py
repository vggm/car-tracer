"""Entry point: python -m app.bot (long polling loop)."""
import logging
import sys
import time

import httpx

from app.bot.commands import handle_update
from app.bot.telegram import TelegramClient, TelegramError
from app.config import Settings
from app.db import connect

log = logging.getLogger("car-trace.bot")
MAX_BACKOFF_S = 60
POLL_TIMEOUT_S = 50
HTTP_READ_TIMEOUT_S = 60.0


def poll_loop(client, handler, sleep=time.sleep) -> None:
    offset = None
    backoff = 0
    while True:
        try:
            updates = client.get_updates(offset, timeout=POLL_TIMEOUT_S)
        except (httpx.HTTPError, TelegramError) as e:
            backoff = min(backoff * 2, MAX_BACKOFF_S) if backoff else 1
            # type name only: httpx messages may include the URL (with the token)
            log.warning("getUpdates failed (%s); retrying in %ss", type(e).__name__, backoff)
            sleep(backoff)
            continue
        backoff = 0
        for update in updates:
            uid = update.get("update_id") if isinstance(update, dict) else None
            if isinstance(uid, int):
                offset = uid + 1
            try:
                handler(update)
            except Exception:
                log.exception("error handling update %s", uid)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = Settings.from_env()
    missing = [n for n, v in (("CAR_TRACE_BOT_TOKEN", settings.bot_token),
                              ("CHAT_ID", settings.chat_id)) if not v]
    if missing:
        print(f"error: missing required environment: {', '.join(missing)}", file=sys.stderr)
        return 1
    http = httpx.Client(timeout=httpx.Timeout(10.0, read=HTTP_READ_TIMEOUT_S))
    client = TelegramClient(settings.bot_token, http)
    conn = connect(settings.db_path)
    try:
        client.set_my_commands([("donde", "Dónde está el coche")])
    except (httpx.HTTPError, TelegramError) as e:
        log.warning("setMyCommands failed (%s)", type(e).__name__)

    def handler(update):
        handle_update(update, chat_id=settings.chat_id, client=client, conn=conn,
                      now_ms=int(time.time() * 1000), tz=settings.tz)

    log.info("bot started")
    try:
        poll_loop(client, handler)
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
