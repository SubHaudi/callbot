from __future__ import annotations
from datetime import datetime


class VendorConnectionError(Exception):
    """벤더 SDK 연결 오류 시 발생하는 예외.

    Attributes:
        vendor: 벤더 식별자 (예: "aws-transcribe", "aws-polly")
        original_message: 원본 예외 메시지
        occurred_at: 발생 시각 (UTC)
    """

    def __init__(
        self,
        vendor: str,
        original_message: str,
        occurred_at: datetime | None = None,
    ) -> None:
        self.vendor = vendor
        self.original_message = original_message
        self.occurred_at = occurred_at or datetime.utcnow()
        super().__init__(
            f"[{self.vendor}] Connection error at {self.occurred_at.isoformat()}: "
            f"{self.original_message}"
        )
