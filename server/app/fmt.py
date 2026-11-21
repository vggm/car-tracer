"""Spanish text formatting helpers (no locale dependency)."""
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

WEEKDAYS = ("lun", "mar", "mié", "jue", "vie", "sáb", "dom")
MONTHS = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")


def num(x: float, decimals: int = 0) -> str:
    q = Decimal(1).scaleb(-decimals)
    d = Decimal(str(x)).quantize(q, rounding=ROUND_HALF_UP)
    text = f"{d:,.{decimals}f}"
    return text.replace(",", "\0").replace(".", ",").replace("\0", ".")


def _local(ts_ms: int, tz: str) -> datetime:
    return datetime.fromtimestamp(ts_ms / 1000, ZoneInfo(tz))


def hhmm(ts_ms: int, tz: str) -> str:
    return _local(ts_ms, tz).strftime("%H:%M")


def rel(delta_ms: int) -> str:
    s = max(0, delta_ms) // 1000
    if s < 60:
        return f"{s} s"
    if s < 3600:
        return f"{s // 60} min"
    return f"{s // 3600} h {(s % 3600) // 60} min"


def day_label(ts_ms: int, now_ms: int, tz: str) -> str:
    d = _local(ts_ms, tz)
    days = (_local(now_ms, tz).date() - d.date()).days
    if days == 0:
        return "Hoy"
    if days == 1:
        return "Ayer"
    if 2 <= days <= 6:
        return f"{WEEKDAYS[d.weekday()].capitalize()} {d.day}"
    return f"{d.day} {MONTHS[d.month - 1]}"


def when(ts_ms: int, now_ms: int, tz: str) -> str:
    label = day_label(ts_ms, now_ms, tz)
    return f"{label[0].lower()}{label[1:]} {hhmm(ts_ms, tz)}"


def long_day(ts_ms: int, tz: str) -> str:
    d = _local(ts_ms, tz)
    return f"{WEEKDAYS[d.weekday()]} {d.day} {MONTHS[d.month - 1]}"
