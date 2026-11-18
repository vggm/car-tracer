import sys

import uvicorn

from app.config import Settings
from app.main import create_app


def main() -> int:
    settings = Settings.from_env()
    if not settings.ingest_token:
        print("error: CAR_TRACE_INGEST_TOKEN is empty; refusing to start", file=sys.stderr)
        return 1
    uvicorn.run(create_app(settings), host="0.0.0.0", port=8000)
    return 0


if __name__ == "__main__":
    sys.exit(main())
