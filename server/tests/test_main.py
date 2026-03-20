"""server.__main__ 테스트"""
from __future__ import annotations

from unittest.mock import patch
import pytest


def test_main_calls_uvicorn_run(monkeypatch):
    """main() 실행 시 uvicorn.run() 호출."""
    monkeypatch.setenv("HOST", "127.0.0.1")
    monkeypatch.setenv("PORT", "9000")

    with patch("uvicorn.run") as mock_run:
        from server.__main__ import main
        main()
        mock_run.assert_called_once()
        kwargs = mock_run.call_args.kwargs
        assert kwargs["port"] == 9000
        assert kwargs["host"] == "127.0.0.1"
        assert kwargs["ws_ping_interval"] == 30


def test_main_default_port(monkeypatch):
    """PORT 미설정 시 기본 8000."""
    monkeypatch.delenv("PORT", raising=False)
    monkeypatch.delenv("HOST", raising=False)

    with patch("uvicorn.run") as mock_run:
        from server.__main__ import main
        main()
        kwargs = mock_run.call_args.kwargs
        assert kwargs["port"] == 8000
        assert kwargs["host"] == "0.0.0.0"
