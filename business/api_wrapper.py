"""callbot.business.api_wrapper — 외부 API 래퍼 (재시도, 서킷브레이커, 타임아웃)"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any, Callable, Optional

from callbot.business.enums import (
    APIErrorType,
    BillingOperation,
    CircuitStatus,
    CustomerDBOperation,
)
from callbot.business.models import APIError, APIResult, RollbackResult

# ---------------------------------------------------------------------------
# 재시도 설정
# ---------------------------------------------------------------------------
_RETRY_DELAYS_MS = [100, 200]          # 일반 재시도 백오프 (ms)
_ROLLBACK_DELAYS_MS = [500, 1000, 2000]  # 롤백 재시도 백오프 (ms)
_MAX_RETRIES = 2
_MAX_ROLLBACK_RETRIES = 3


# ---------------------------------------------------------------------------
# 외부 시스템 추상 인터페이스
# ---------------------------------------------------------------------------

class APIWrapperSystemBase(ABC):
    """외부 시스템 호출 추상 인터페이스 (테스트 mock 대상)."""

    @abstractmethod
    def call(self, system: str, operation: str, params: dict, timeout_sec: float) -> dict:
        """외부 시스템 호출. 성공 시 dict 반환, 실패 시 예외 발생."""
        ...


# ---------------------------------------------------------------------------
# 알림 서비스 추상 인터페이스
# ---------------------------------------------------------------------------

class AlertServiceBase(ABC):
    @abstractmethod
    def send_critical(self, message: str) -> None:
        """운영팀 critical 알림 발송."""
        ...


# ---------------------------------------------------------------------------
# 서킷브레이커
# ---------------------------------------------------------------------------

class CircuitBreaker:
    """단순 슬라이딩 윈도우 서킷브레이커.

    - CLOSED → OPEN: 1분 내 실패율 50% 초과 (최소 10건)
    - OPEN → HALF_OPEN: 30초 후
    - HALF_OPEN → CLOSED/OPEN: 테스트 요청 성공/실패
    """

    _WINDOW_SEC = 60
    _FAILURE_THRESHOLD = 0.5
    _MIN_CALLS = 10
    _HALF_OPEN_TIMEOUT_SEC = 30

    def __init__(self) -> None:
        self._status = CircuitStatus.CLOSED
        self._call_times: list[float] = []   # epoch seconds
        self._failure_times: list[float] = []
        self._opened_at: Optional[float] = None

    @property
    def status(self) -> CircuitStatus:
        self._maybe_transition_to_half_open()
        return self._status

    def record_success(self) -> None:
        now = time.monotonic()
        self._call_times.append(now)
        self._prune(now)
        if self._status == CircuitStatus.HALF_OPEN:
            self._status = CircuitStatus.CLOSED
            self._opened_at = None

    def record_failure(self) -> None:
        now = time.monotonic()
        self._call_times.append(now)
        self._failure_times.append(now)
        self._prune(now)
        if self._status in (CircuitStatus.CLOSED, CircuitStatus.HALF_OPEN):
            self._evaluate()

    def is_open(self) -> bool:
        return self.status == CircuitStatus.OPEN

    def allow_request(self) -> bool:
        """요청 허용 여부. OPEN이면 False, CLOSED/HALF_OPEN이면 True."""
        s = self.status
        return s != CircuitStatus.OPEN

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _prune(self, now: float) -> None:
        cutoff = now - self._WINDOW_SEC
        self._call_times = [t for t in self._call_times if t > cutoff]
        self._failure_times = [t for t in self._failure_times if t > cutoff]

    def _evaluate(self) -> None:
        total = len(self._call_times)
        failures = len(self._failure_times)
        if total >= self._MIN_CALLS and failures / total > self._FAILURE_THRESHOLD:
            self._status = CircuitStatus.OPEN
            self._opened_at = time.monotonic()

    def _maybe_transition_to_half_open(self) -> None:
        if (
            self._status == CircuitStatus.OPEN
            and self._opened_at is not None
            and time.monotonic() - self._opened_at >= self._HALF_OPEN_TIMEOUT_SEC
        ):
            self._status = CircuitStatus.HALF_OPEN


# ---------------------------------------------------------------------------
# ExternalAPIWrapper
# ---------------------------------------------------------------------------

class ExternalAPIWrapper:
    """과금_시스템, 고객_DB 연동 래퍼 — 재시도, 서킷브레이커, 타임아웃 포함."""

    def __init__(
        self,
        external_system: APIWrapperSystemBase,
        alert_service: Optional[AlertServiceBase] = None,
    ) -> None:
        self._sys = external_system
        self._alert = alert_service
        self._circuit_breakers: dict[str, CircuitBreaker] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def call_billing_api(
        self,
        operation: BillingOperation,
        params: dict,
        timeout_sec: float = 5.0,
    ) -> APIResult:
        """과금_시스템 API 호출 — 재시도, 서킷브레이커, 타임아웃 포함."""
        return self._call_with_retry("billing", operation.value, params, timeout_sec)

    def call_customer_db(
        self,
        operation: CustomerDBOperation,
        params: dict,
        timeout_sec: float = 1.0,
    ) -> APIResult:
        """고객_DB API 호출 — 재시도, 서킷브레이커 포함 (타임아웃 1초)."""
        return self._call_with_retry("customer_db", operation.value, params, timeout_sec)

    def rollback_transaction(self, transaction_id: str, system: str) -> RollbackResult:
        """트랜잭션 롤백 — 최대 3회 재시도, 지수 백오프 (500ms, 1000ms, 2000ms)."""
        last_error: Optional[str] = None
        for attempt, delay_ms in enumerate(_ROLLBACK_DELAYS_MS):
            try:
                self._sys.call(
                    system,
                    "rollback",
                    {"transaction_id": transaction_id},
                    timeout_sec=5.0,
                )
                return RollbackResult(
                    is_success=True,
                    requires_manual=False,
                    retry_count=attempt,
                    error_message=None,
                )
            except Exception as exc:
                last_error = str(exc)
                if attempt < len(_ROLLBACK_DELAYS_MS) - 1:
                    time.sleep(delay_ms / 1000)

        # 3회 모두 실패
        if self._alert:
            self._alert.send_critical(
                f"롤백 3회 실패: transaction_id={transaction_id}, system={system}"
            )
        return RollbackResult(
            is_success=False,
            requires_manual=True,
            retry_count=3,
            error_message=last_error,
        )

    def get_circuit_status(self, system: str) -> CircuitStatus:
        """서킷브레이커 상태 조회."""
        return self._get_breaker(system).status

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_breaker(self, system: str) -> CircuitBreaker:
        if system not in self._circuit_breakers:
            self._circuit_breakers[system] = CircuitBreaker()
        return self._circuit_breakers[system]

    def _call_with_retry(
        self, system: str, operation: str, params: dict, timeout_sec: float
    ) -> APIResult:
        breaker = self._get_breaker(system)

        if not breaker.allow_request():
            return APIResult(
                is_success=False,
                data=None,
                error=APIError(
                    error_type=APIErrorType.PARTIAL_FAILURE,
                    message="서킷브레이커 OPEN — 요청 차단",
                    is_retryable=False,
                ),
                response_time_ms=0,
                retry_count=0,
            )

        start = time.monotonic()
        last_exc: Optional[Exception] = None

        for attempt in range(_MAX_RETRIES + 1):
            try:
                data = self._sys.call(system, operation, params, timeout_sec)
                elapsed_ms = int((time.monotonic() - start) * 1000)
                breaker.record_success()
                return APIResult(
                    is_success=True,
                    data=data,
                    error=None,
                    response_time_ms=elapsed_ms,
                    retry_count=attempt,
                )
            except TimeoutError as exc:
                last_exc = exc
                breaker.record_failure()
                if attempt < _MAX_RETRIES:
                    time.sleep(_RETRY_DELAYS_MS[attempt] / 1000)
            except ValueError as exc:
                # 4xx 클라이언트 오류 — 재시도 불가, 즉시 실패 반환
                elapsed_ms = int((time.monotonic() - start) * 1000)
                return APIResult(
                    is_success=False,
                    data=None,
                    error=APIError(
                        error_type=APIErrorType.CLIENT_ERROR,
                        message=str(exc),
                        is_retryable=False,
                    ),
                    response_time_ms=elapsed_ms,
                    retry_count=attempt,
                )
            except Exception as exc:
                last_exc = exc
                breaker.record_failure()
                if attempt < _MAX_RETRIES:
                    time.sleep(_RETRY_DELAYS_MS[attempt] / 1000)

        elapsed_ms = int((time.monotonic() - start) * 1000)
        error_type = (
            APIErrorType.TIMEOUT
            if isinstance(last_exc, TimeoutError)
            else APIErrorType.SERVER_ERROR
        )
        return APIResult(
            is_success=False,
            data=None,
            error=APIError(
                error_type=error_type,
                message=str(last_exc),
                is_retryable=True,
            ),
            response_time_ms=elapsed_ms,
            retry_count=_MAX_RETRIES,
        )
