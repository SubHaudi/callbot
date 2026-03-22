from __future__ import annotations
"""VendorConnectionError 단위 테스트."""

from datetime import datetime

from callbot.voice_io.exceptions import VendorConnectionError


class TestVendorConnectionError:
    def test_attributes_set_correctly(self):
        err = VendorConnectionError("aws-transcribe", "timeout")
        assert err.vendor == "aws-transcribe"
        assert err.original_message == "timeout"
        assert isinstance(err.occurred_at, datetime)

    def test_occurred_at_defaults_to_utcnow(self):
        before = datetime.utcnow()
        err = VendorConnectionError("aws-polly", "connection refused")
        after = datetime.utcnow()
        assert before <= err.occurred_at <= after

    def test_custom_occurred_at(self):
        ts = datetime(2025, 1, 1, 12, 0, 0)
        err = VendorConnectionError("aws-transcribe", "fail", occurred_at=ts)
        assert err.occurred_at is ts

    def test_str_contains_vendor_and_message(self):
        err = VendorConnectionError("aws-polly", "network error")
        msg = str(err)
        assert "[aws-polly]" in msg
        assert "network error" in msg
        assert "Connection error" in msg

    def test_is_exception_subclass(self):
        err = VendorConnectionError("v", "m")
        assert isinstance(err, Exception)


# Feature: callbot-voice-io, Property 6: VendorConnectionError 속성 완전성
from hypothesis import given, settings
from hypothesis import strategies as st


@given(
    vendor=st.text(min_size=1),
    message=st.text(min_size=1),
)
@settings(max_examples=100)
def test_vendor_connection_error_attribute_completeness(vendor: str, message: str):
    """For any vendor/message strings, VendorConnectionError must expose
    vendor, original_message, and a valid datetime occurred_at.

    **Validates: Requirements 5.5**
    """
    err = VendorConnectionError(vendor, message)

    assert err.vendor == vendor
    assert err.original_message == message
    assert isinstance(err.occurred_at, datetime)
