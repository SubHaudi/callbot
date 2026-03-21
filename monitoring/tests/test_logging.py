"""Phase D 구조화 로깅 테스트 (FR-013)."""

import json
import logging

from callbot.monitoring.logging import StructuredFormatter, new_correlation_id


class TestStructuredLogging:
    def test_json_format(self):
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="hello world", args=(), exc_info=None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["message"] == "hello world"
        assert parsed["level"] == "INFO"
        assert "timestamp" in parsed

    def test_correlation_id_in_log(self):
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="request", args=(), exc_info=None,
        )
        record.correlation_id = "abc12345"
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["correlation_id"] == "abc12345"

    def test_extra_fields(self):
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="turn", args=(), exc_info=None,
        )
        record.intent = "BILLING_INQUIRY"
        record.session_id = "sess-123"
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["intent"] == "BILLING_INQUIRY"
        assert parsed["session_id"] == "sess-123"

    def test_new_correlation_id(self):
        cid = new_correlation_id()
        assert len(cid) == 8
        # Should be different each time
        assert cid != new_correlation_id()
