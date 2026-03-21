"""Phase D 입력 validation 테스트 (FR-012, NFR-005)."""

from callbot.server.schemas import TurnRequest


class TestTurnRequestValidation:
    def test_empty_text_returns_error(self):
        req = TurnRequest(text="")
        errors = req.validate()
        assert len(errors) >= 1
        assert errors[0]["loc"] == ["body", "text"]

    def test_text_over_2000_returns_error(self):
        req = TurnRequest(text="a" * 2001)
        errors = req.validate()
        assert len(errors) >= 1
        assert "2000" in errors[0]["msg"]

    def test_invalid_session_id_returns_error(self):
        req = TurnRequest(text="hello", session_id="not-a-uuid")
        errors = req.validate()
        assert len(errors) >= 1
        assert errors[0]["loc"] == ["body", "session_id"]

    def test_caller_id_too_long_returns_error(self):
        req = TurnRequest(text="hello", caller_id="a" * 21)
        errors = req.validate()
        assert len(errors) >= 1
        assert errors[0]["loc"] == ["body", "caller_id"]

    def test_valid_request_passes(self):
        req = TurnRequest(
            text="요금 조회해줘",
            session_id="550e8400-e29b-41d4-a716-446655440000",
            caller_id="010-1234-5678",
        )
        errors = req.validate()
        assert errors == []

    def test_valid_request_minimal(self):
        req = TurnRequest(text="hi")
        errors = req.validate()
        assert errors == []

    def test_text_exactly_2000_passes(self):
        req = TurnRequest(text="a" * 2000)
        errors = req.validate()
        assert errors == []
