"""AnyTelecomHTTPClient — 저수준 HTTP 클라이언트 (api_wrapper.APIWrapperSystemBase 구현)."""

from __future__ import annotations

import logging
import os
import re
import time

import requests

from callbot.business.api_wrapper import APIWrapperSystemBase
from callbot.external.mtls_provider import mTLSCertificateProvider
from callbot.external.operation_mapping import OperationMapping
from callbot.external.pii_masker import PIIMasker
from callbot.security.secrets_manager import SecretsManager

logger = logging.getLogger(__name__)

# 동적 경로 파라미터 마스킹 패턴 (UUID, 숫자 ID 등)
_DYNAMIC_PARAM_RE = re.compile(r"/[0-9a-fA-F-]{8,}|/\d+")


class AnyTelecomHTTPClient(APIWrapperSystemBase):
    """api_wrapper.APIWrapperSystemBase를 구현하는 저수준 HTTP 클라이언트.

    mTLS + API 키 인증으로 AnyTelecom 내부 REST API에 HTTP 요청을 수행한다.
    """

    _API_KEY_SECRET = "callbot/anytelecom-api-key"

    def __init__(
        self,
        secrets_manager: SecretsManager,
        billing_base_url: str,
        customer_db_base_url: str,
        cert_provider: mTLSCertificateProvider | None = None,
        ca_bundle_path: str | None = None,
    ) -> None:
        self._api_key: str = secrets_manager.get_secret(self._API_KEY_SECRET)
        self._billing_base_url = billing_base_url.rstrip("/")
        self._customer_db_base_url = customer_db_base_url.rstrip("/")

        self._session = requests.Session()

        # mTLS 인증서 설정
        if cert_provider is not None:
            self._session.cert = (cert_provider.cert_path, cert_provider.key_path)

        # CA 번들 설정 (None → 시스템 기본 CA 번들 사용)
        self._session.verify = ca_bundle_path if ca_bundle_path else True

    def call(
        self, system: str, operation: str, params: dict, timeout_sec: float
    ) -> dict:
        """HTTP 요청 수행.

        - 200-299: JSON 파싱 → dict 반환
        - 400-499: ValueError 발생 (재시도 불가)
        - 500-599: ConnectionError 발생 (재시도 가능)
        - 타임아웃: TimeoutError 발생
        - 연결 실패: ConnectionError 발생
        """
        endpoint = OperationMapping.resolve(system, operation)

        # base URL 결정
        if system == "billing":
            base_url = self._billing_base_url
        else:
            base_url = self._customer_db_base_url

        # 경로 파라미터 치환 (e.g. {customer_id})
        path = endpoint.path_template
        for key, value in params.items():
            placeholder = "{" + key + "}"
            if placeholder in path:
                path = path.replace(placeholder, str(value))

        url = base_url + path

        # PII 마스킹 후 요청 로깅
        masked_params = PIIMasker.mask(params)
        log_path = _DYNAMIC_PARAM_RE.sub("/***", path)
        logger.info(
            "HTTP request: method=%s path=%s timeout=%s params=%s",
            endpoint.method, log_path, timeout_sec, masked_params,
        )

        headers = {
            "X-API-Key": self._api_key,
            "Content-Type": "application/json",
        }

        try:
            start = time.monotonic()
            resp = self._session.request(
                method=endpoint.method,
                url=url,
                json=params if endpoint.method == "POST" else None,
                params=params if endpoint.method == "GET" else None,
                headers=headers,
                timeout=timeout_sec,
            )
            elapsed_ms = (time.monotonic() - start) * 1000

            # 응답 로깅
            logger.info(
                "HTTP response: status=%d elapsed=%.1fms",
                resp.status_code, elapsed_ms,
            )

            # 상태 코드 처리
            if 200 <= resp.status_code <= 299:
                return resp.json()
            elif 400 <= resp.status_code <= 499:
                logger.error(
                    "Client error: status=%d body=%s",
                    resp.status_code, resp.text,
                )
                raise ValueError(
                    f"HTTP {resp.status_code}: {resp.text}"
                )
            else:
                # 500-599
                logger.error(
                    "Server error: status=%d body=%s",
                    resp.status_code, resp.text,
                )
                raise ConnectionError(
                    f"HTTP {resp.status_code}: {resp.text}"
                )

        except requests.Timeout as exc:
            logger.error("Timeout error: %s", exc)
            raise TimeoutError(str(exc)) from exc
        except requests.ConnectionError as exc:
            logger.error("Connection error: %s", exc)
            raise ConnectionError(str(exc)) from exc

    def health_check(self) -> dict[str, bool]:
        """Billing API, Customer DB API 헬스체크."""
        result: dict[str, bool] = {}
        for name, base_url in [
            ("billing", self._billing_base_url),
            ("customer_db", self._customer_db_base_url),
        ]:
            try:
                resp = self._session.get(f"{base_url}/health", timeout=5)
                result[name] = resp.status_code == 200
            except Exception as e:
                logger.error("Health check failed for %s: %s", name, e)
                raise
        return result

    @classmethod
    def from_env(
        cls, secrets_manager: SecretsManager
    ) -> AnyTelecomHTTPClient:
        """환경변수에서 설정을 읽어 인스턴스 생성."""
        billing_url = os.environ.get("CALLBOT_BILLING_API_BASE_URL")
        if not billing_url:
            raise ValueError("CALLBOT_BILLING_API_BASE_URL is required")
        customer_db_url = os.environ.get("CALLBOT_CUSTOMER_DB_API_BASE_URL")
        if not customer_db_url:
            raise ValueError("CALLBOT_CUSTOMER_DB_API_BASE_URL is required")
        ca_bundle = os.environ.get("CALLBOT_CA_BUNDLE_PATH")
        cert_provider = mTLSCertificateProvider(secrets_manager)
        return cls(
            secrets_manager,
            billing_url,
            customer_db_url,
            cert_provider,
            ca_bundle,
        )
