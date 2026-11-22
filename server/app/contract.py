"""Pydantic models of ingest contract v1 (docs/contract/ingest-v1.md)."""
import re
from typing import Annotated, Any, Literal, Union
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictFloat,
    StrictInt,
    TypeAdapter,
    ValidationError,
    field_validator,
    model_validator,
)

TS_MIN_MS = 1704067200000  # 2024-01-01 UTC
TS_MAX_AHEAD_MS = 300_000  # now + 5 min
MAX_RECORDS = 500

DETAIL_DEFAULT_MAX = 200
DETAIL_LIMITS = {"obd_trace": 4000, "diag": 500}

_OBD_KEY = re.compile(r"^[a-z0-9_]{1,32}$")

Num = Annotated[StrictInt | StrictFloat, Field(allow_inf_nan=False)]
Float = Annotated[float, Field(strict=True, allow_inf_nan=False)]
DtcCode = Annotated[str, Field(pattern=r"^[PCBU][0-9A-F]{4}$")]
_COMMON = {"id", "session_id", "seq", "ts", "type"}


class RecordError(Exception):
    """A single record violates the contract."""


class Batch(BaseModel):
    device_id: str = Field(pattern=r"^[a-z0-9-]{1,64}$")
    app_version: str = Field(max_length=32)
    records: list[Any] = Field(max_length=MAX_RECORDS)


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    session_id: UUID
    seq: Annotated[int, Field(strict=True, ge=0, le=2**63 - 1)]
    ts: Annotated[int, Field(strict=True)]

    def payload(self) -> dict:
        return self.model_dump(mode="json", exclude=_COMMON)


class GpsRecord(_Base):
    type: Literal["gps"]
    lat: Annotated[Float, Field(ge=-90, le=90)]
    lon: Annotated[Float, Field(ge=-180, le=180)]
    acc_m: Annotated[Float, Field(ge=0)]
    speed_mps: Annotated[Float, Field(ge=0)] | None = None
    bearing: Annotated[Float, Field(ge=0, lt=360)] | None = None
    alt_m: Float | None = None


class _ValuesRecord(_Base):
    values: dict[str, Num] = Field(min_length=1)

    @field_validator("values")
    @classmethod
    def _keys(cls, v: dict) -> dict:
        for k in v:
            if not _OBD_KEY.match(k):
                raise ValueError(f"invalid obd key: {k!r}")
        return v


class ObdRecord(_ValuesRecord):
    type: Literal["obd"]


class HealthRecord(_ValuesRecord):
    type: Literal["health"]


class DtcRecord(_Base):
    type: Literal["dtc"]
    active: list[DtcCode]
    pending: list[DtcCode]


class EventRecord(_Base):
    type: Literal["event"]
    event: Literal["session_start", "resumed", "obd_connected", "obd_lost", "obd_error",
                   "dtc_scan", "dtc_scan_failed", "dtc_clear", "dtc_clear_failed", "obd_attempt_failed", "obd_trace", "diag"]
    detail: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def _detail_limit(self) -> "EventRecord":
        limit = DETAIL_LIMITS.get(self.event, DETAIL_DEFAULT_MAX)
        if self.detail is not None and len(self.detail) > limit:
            raise ValueError(f"detail: too long for {self.event} (max {limit})")
        return self


Record = Union[GpsRecord, ObdRecord, DtcRecord, EventRecord, HealthRecord]
_adapter: TypeAdapter[Record] = TypeAdapter(
    Annotated[Record, Field(discriminator="type")]
)


def parse_record(raw: Any, now_ms: int) -> Record:
    try:
        rec = _adapter.validate_python(raw)
    except ValidationError as e:
        err = e.errors()[0]
        loc = ".".join(str(x) for x in err["loc"])
        raise RecordError(f"{loc}: {err['msg']}" if loc else err["msg"]) from e
    if not TS_MIN_MS <= rec.ts <= now_ms + TS_MAX_AHEAD_MS:
        raise RecordError("ts: out of valid range")
    return rec
