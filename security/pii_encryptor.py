"""PII 암호화 및 Masking Token 관리 모듈.

AES-256-GCM으로 PII를 암호화하고, UUID 형태의 Masking_Token으로 참조한다.
동일 PII에 대해 항상 동일한 토큰을 반환하는 1:1 매핑을 사용한다.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import uuid

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from callbot.security.exceptions import DecryptionError, SecretNotFoundError, TokenNotFoundError
from callbot.security.secrets_manager import SecretsManager
from callbot.security.token_mapping_store import TokenMappingStoreBase

_IV_LEN = 12
_TAG_LEN = 16
_KEY_VERSION_LEN = 1  # 1 byte for key version prefix
_MAGIC_BYTE = 0xCB  # 매직 바이트: 새 포맷 식별자 (0xCB = "CallBot")


class PIIEncryptor:
    """AES-256-GCM 기반 PII 암호화 및 Masking Token 관리.

    바이너리 포맷: IV(12B) + Tag(16B) + Ciphertext
    """

    def __init__(
        self,
        secrets_manager: SecretsManager,
        token_mapping_store: TokenMappingStoreBase,
        encryption_key_secret_name: str = "callbot/pii-encryption-key",
        hmac_salt_secret_name: str = "callbot/pii-hmac-salt",
        current_key_version: int = 1,
    ) -> None:
        self._secrets_manager = secrets_manager
        self._token_mapping_store = token_mapping_store
        self._encryption_key_secret_name = encryption_key_secret_name
        self._hmac_salt_secret_name = hmac_salt_secret_name
        if not (0 <= current_key_version <= 255):
            raise ValueError("key_version must be 0-255")
        self._current_key_version = current_key_version

    def _get_key(self, version: int | None = None) -> bytes:
        """SecretsManager에서 암호화 키를 조회하고 32바이트로 변환한다.

        Args:
            version: 키 버전. None이면 현재 버전 사용.
        """
        v = version if version is not None else self._current_key_version
        secret_name = f"{self._encryption_key_secret_name}/v{v}"
        try:
            secret = self._secrets_manager.get_secret(secret_name)
        except SecretNotFoundError:
            # fallback: 버전 없는 레거시 키 이름 (마이그레이션 기간 한정)
            secret = self._secrets_manager.get_secret(self._encryption_key_secret_name)
        # hex 문자열(64자)이면 디코딩, 아니면 UTF-8 인코딩
        if len(secret) == 64:
            try:
                key = bytes.fromhex(secret)
            except ValueError:
                key = secret.encode("utf-8")
        else:
            key = secret.encode("utf-8")
        if len(key) != 32:
            raise ValueError(
                f"Encryption key must be exactly 32 bytes, got {len(key)}"
            )
        return key

    def encrypt(self, plaintext: str, session_id: str | None = None) -> bytes:
        """AES-256-GCM 암호화. 96비트 난수 IV 생성.

        Args:
            plaintext: 암호화할 평문.
            session_id: AAD(Additional Authenticated Data)로 사용할 세션 ID.

        반환값: magic(1B) + key_version(1B) + iv(12B) + tag(16B) + ciphertext.
        """
        key = self._get_key()
        iv = os.urandom(_IV_LEN)
        aesgcm = AESGCM(key)
        aad = session_id.encode("utf-8") if session_id else None
        encrypted = aesgcm.encrypt(iv, plaintext.encode("utf-8"), aad)
        ciphertext_part = encrypted[:-_TAG_LEN]
        tag = encrypted[-_TAG_LEN:]
        header = bytes([_MAGIC_BYTE, self._current_key_version])
        return header + iv + tag + ciphertext_part

    def decrypt(self, ciphertext: bytes, session_id: str | None = None) -> str:
        """AES-256-GCM 복호화. 매직 바이트로 새/레거시 포맷을 구분한다.

        새 포맷: magic(1B) + key_version(1B) + iv(12B) + tag(16B) + ct
        레거시: iv(12B) + tag(16B) + ct (매직 바이트 없음)

        Args:
            ciphertext: 암호화된 바이너리.
            session_id: 암호화 시 사용한 AAD.

        Raises:
            DecryptionError: 인증 태그 검증 실패 시 (AAD 불일치 포함).
        """
        if len(ciphertext) >= 2 and ciphertext[0] == _MAGIC_BYTE:
            # 새 포맷: magic + version + iv + tag + ct
            version = ciphertext[1]
            remainder = ciphertext[2:]
        else:
            # 레거시 포맷: iv + tag + ct (version 헤더 없음)
            version = self._current_key_version
            remainder = ciphertext

        key = self._get_key(version)
        iv = remainder[:_IV_LEN]
        tag = remainder[_IV_LEN : _IV_LEN + _TAG_LEN]
        ct = remainder[_IV_LEN + _TAG_LEN :]
        aad = session_id.encode("utf-8") if session_id else None
        aesgcm = AESGCM(key)
        try:
            plaintext_bytes = aesgcm.decrypt(iv, ct + tag, aad)
        except InvalidTag as exc:
            raise DecryptionError("Authentication tag verification failed") from exc
        return plaintext_bytes.decode("utf-8")

    def _get_hmac_salt(self) -> bytes:
        """SecretsManager에서 HMAC salt를 조회한다."""
        salt_str = self._secrets_manager.get_secret(self._hmac_salt_secret_name)
        return salt_str.encode("utf-8")

    def _hash_pii(self, pii: str) -> str:
        """HMAC-SHA256으로 PII를 해시한다 (salt 적용)."""
        salt = self._get_hmac_salt()
        return hmac.new(salt, pii.encode("utf-8"), hashlib.sha256).hexdigest()

    def tokenize(self, pii: str) -> str:
        """1:1 매핑: 동일 PII는 항상 동일 토큰 반환.

        HMAC-SHA256 + salt로 PII를 해시하여 레인보우 테이블 공격을 방지한다.

        Raises:
            SecretNotFoundError: 암호화 키 또는 HMAC salt 조회 실패 시.
        """
        pii_hash = self._hash_pii(pii)
        existing_token = self._token_mapping_store.get_token_by_pii_hash(pii_hash)
        if existing_token is not None:
            return existing_token

        encrypted = self.encrypt(pii)
        token = str(uuid.uuid4())
        self._token_mapping_store.store_with_pii_hash(token, encrypted, pii_hash)
        return token

    def detokenize(self, token: str) -> str:
        """토큰으로 원본 PII 복호화.

        Raises:
            TokenNotFoundError: 토큰이 존재하지 않을 때.
            DecryptionError: 복호화 실패 시.
        """
        ciphertext = self._token_mapping_store.get_ciphertext(token)
        return self.decrypt(ciphertext)
