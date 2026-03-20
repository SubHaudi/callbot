"""callbot 서버 엔트리포인트: python -m server"""
from __future__ import annotations

import os
import uvicorn


def main() -> None:
    """uvicorn 서버를 시작한다."""
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(
        "server.app:app",
        host=host,
        port=port,
        ws_ping_interval=30,
        ws_ping_timeout=30,
    )


if __name__ == "__main__":
    main()
