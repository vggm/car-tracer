from datetime import datetime
from zoneinfo import ZoneInfo

from app import fmt

TZ = "Europe/Madrid"


def ms(y, mo, d, h=0, mi=0):
    return int(datetime(y, mo, d, h, mi, tzinfo=ZoneInfo(TZ)).timestamp() * 1000)


DAY = 86_400_000
NOW = ms(2026, 11, 21, 18, 26)  # Saturday


def test_num():
    assert fmt.num(1450) == "1.450"
    assert fmt.num(6.25, 1) == "6,3"
    assert fmt.num(14.1, 1) == "14,1"
    assert fmt.num(741) == "741"


def test_hhmm():
    assert fmt.hhmm(ms(2026, 11, 21, 18, 12), TZ) == "18:12"


def test_rel_keeps_existing_outputs():
    assert fmt.rel(20_000) == "20 s"
    assert fmt.rel(7 * 60_000) == "7 min"
    assert fmt.rel(125 * 60_000) == "2 h 5 min"
    assert fmt.rel(-5) == "0 s"


def test_day_label():
    assert fmt.day_label(NOW, NOW, TZ) == "Hoy"
    assert fmt.day_label(NOW - DAY, NOW, TZ) == "Ayer"
    assert fmt.day_label(ms(2026, 11, 18, 18, 26), NOW, TZ) == "Mié 18"
    assert fmt.day_label(ms(2026, 11, 11, 18, 26), NOW, TZ) == "11 nov"


def test_day_label_calendar_days_not_24h():
    ts = ms(2026, 11, 20, 23, 50)
    now = ms(2026, 11, 21, 0, 10)
    assert fmt.day_label(ts, now, TZ) == "Ayer"


def test_when():
    assert fmt.when(NOW, NOW, TZ) == "hoy 18:26"
    assert fmt.when(NOW - DAY, NOW, TZ) == "ayer 18:26"
    assert fmt.when(ms(2026, 11, 17, 18, 26), NOW, TZ) == "mar 17 18:26"
    assert fmt.when(ms(2026, 11, 10, 18, 26), NOW, TZ) == "10 nov 18:26"


def test_full_day():
    assert fmt.full_day(ms(2026, 11, 20, 18, 12), TZ) == "Viernes 20 de noviembre"
    assert fmt.full_day(ms(2026, 3, 4, 9, 0), TZ) == "Miércoles 4 de marzo"
