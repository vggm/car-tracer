import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.contract import Batch, RecordError, parse_record

NOW = 1763481600000
EX = Path(__file__).resolve().parents[2] / "docs/contract/examples"
U1 = "4347dc96-113b-4b4e-aba8-bdcff7f6eda2"
U2 = "5d3eb6a5-e4ec-4dad-85a8-7fb5ebfc5375"


def base(**kw):
    d = {"id": U1, "session_id": U2, "seq": 0, "ts": NOW - 1000}
    d.update(kw)
    return d


def gps(**kw):
    return base(type="gps", lat=40.47, lon=-3.77, acc_m=6.0, **kw)


def test_valid_mixed_example_parses():
    recs = json.loads((EX / "valid-mixed.json").read_text())["request"]["records"]
    assert len(recs) == 6
    parsed = [parse_record(r, NOW) for r in recs]
    assert parsed[5].payload()["values"]["boost_extra"] == 1.7
    assert parsed[0].payload() == {"event": "session_start", "detail": None}


@pytest.mark.parametrize("rec", [
    base(type="event", event="session_start", ts=946684800000),
    base(type="event", event="session_start", ts=NOW + 300001),
    gps() | {"lat": 91},
    gps() | {"bearing": 360},
    gps() | {"acc_m": -1},
    base(type="dtc", active=["X1234"], pending=[]),
    base(type="event", event="reboot"),
    base(type="event", event="obd_lost", detail="x" * 201),
    base(type="obd", values={}),
    base(type="obd", values={"RPM": 1}),
    base(type="obd", values={"rpm": "850"}),
    base(type="obd", values={"rpm": True}),
])
def test_rejects_out_of_range(rec):
    with pytest.raises(RecordError):
        parse_record(rec, NOW)


def test_ts_upper_bound_inclusive():
    parse_record(base(type="event", event="resumed", ts=NOW + 300000), NOW)


def test_batch_rejects_501_records():
    with pytest.raises(ValidationError):
        Batch(device_id="junsun-307", app_version="0.1.0", records=[{}] * 501)


def test_batch_rejects_bad_device_id():
    with pytest.raises(ValidationError):
        Batch(device_id="Junsun 307", app_version="0.1.0", records=[])


@pytest.mark.parametrize("event,detail", [
    ("dtc_scan", "abc"),
    ("dtc_scan_failed", "abc obd_not_connected"),
    ("dtc_clear", "abc"),
    ("dtc_clear_failed", "abc rejected"),
])
def test_scan_events_accepted(event, detail):
    parse_record(base(type="event", event=event, detail=detail), NOW)


def test_obd_attempt_failed_event_accepted():
    detail = "n=2 t=54s v=12.4V | 5: BUS INIT ERROR | 0: UNABLE TO CONNECT"
    parsed = parse_record(base(type="event", event="obd_attempt_failed", detail=detail), NOW)
    assert parsed.payload() == {"event": "obd_attempt_failed", "detail": detail}


def _event(event, detail):
    return base(type="event", event=event, detail=detail)


def test_obd_trace_detail_limits():
    assert parse_record(_event("obd_trace", "x" * 4000), NOW).detail == "x" * 4000
    with pytest.raises(RecordError):
        parse_record(_event("obd_trace", "x" * 4001), NOW)


def test_diag_detail_limits():
    assert parse_record(_event("diag", "x" * 500), NOW).detail == "x" * 500
    with pytest.raises(RecordError):
        parse_record(_event("diag", "x" * 501), NOW)


def test_other_events_still_200():
    assert parse_record(_event("obd_lost", "x" * 200), NOW).detail == "x" * 200
    with pytest.raises(RecordError):
        parse_record(_event("obd_lost", "x" * 201), NOW)
    with pytest.raises(RecordError):
        parse_record(_event("obd_attempt_failed", "x" * 201), NOW)


def test_health_record_valid_and_invalid():
    rec = parse_record(base(type="health", values={"battery_pct": 80, "gps_age_s": 1.5}), NOW)
    assert rec.payload() == {"values": {"battery_pct": 80, "gps_age_s": 1.5}}
    for values in ({}, {"": 1}, {"BAD": 1}, {"a" * 33: 1}, {"x": "1"}, {"x": True}):
        with pytest.raises(RecordError):
            parse_record(base(type="health", values=values), NOW)
