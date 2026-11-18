import hmac
import json
import threading

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.contract import Batch, RecordError, parse_record
from app.db import insert_records

MAX_BODY = 262144

router = APIRouter()
_write_lock = threading.Lock()


def _err(status: int, msg: str) -> JSONResponse:
    return JSONResponse({"error": msg}, status_code=status)


def _authorized(request: Request) -> bool:
    expected = request.app.state.settings.ingest_token
    header = request.headers.get("authorization", "")
    prefix = "Bearer "
    if not expected or not header.startswith(prefix):
        return False
    return hmac.compare_digest(header[len(prefix):].encode(), expected.encode())


@router.post("/api/v1/ingest")
async def ingest(request: Request):
    if not _authorized(request):
        return _err(401, "unauthorized")

    cl = request.headers.get("content-length")
    if cl is not None:
        try:
            if int(cl) > MAX_BODY:
                return _err(413, "payload too large")
        except ValueError:
            return _err(400, "invalid content-length")

    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > MAX_BODY:
            return _err(413, "payload too large")

    try:
        data = json.loads(bytes(body))
    except (ValueError, UnicodeDecodeError, RecursionError):
        return _err(400, "body is not valid JSON")
    if not isinstance(data, dict):
        return _err(400, "body must be a JSON object")
    try:
        batch = Batch.model_validate(data)
    except ValidationError:
        return _err(400, "invalid batch")

    now = request.app.state.clock()
    valid = []
    rejected = []
    for i, raw in enumerate(batch.records):
        try:
            valid.append(parse_record(raw, now))
        except RecordError as e:
            rejected.append({"index": i, "id": raw.get("id") if isinstance(raw, dict) else None, "error": str(e)})

    with _write_lock:
        accepted, duplicates = insert_records(
            request.app.state.db, batch.device_id, valid, now
        )
    return {"accepted": accepted, "duplicates": duplicates, "rejected": rejected}
