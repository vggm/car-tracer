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
