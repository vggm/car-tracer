import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    ingest_token: str
    bot_token: str
    chat_id: int | None
    db_path: str
    tz: str

    @classmethod
    def from_env(cls) -> "Settings":
        chat = os.environ.get("CHAT_ID", "").strip()
        return cls(
            ingest_token=os.environ.get("CAR_TRACE_INGEST_TOKEN", ""),
            bot_token=os.environ.get("CAR_TRACE_BOT_TOKEN", ""),
            chat_id=int(chat) if chat else None,
            db_path=os.environ.get("CAR_TRACE_DB") or "/data/car-trace.db",
            tz=os.environ.get("CAR_TRACE_TZ") or "Europe/Madrid",
        )
