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

from callbot.security.exceptions import DecryptionError, TokenNotFoundError
from callbot.security.secrets_manager import SecretsManager
from callbot.security.token_mapping_store import TokenMappingStoreBase

_IV_LEN = 12
_TAG_LEN = 16


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
    ) -> None:
        self._secrets_manager = secrets_manager
        self._token_mapping_store = token_mapping_store
        self._encryption_key_secret_name = encryption_key_secret_name
        self._hmac_salt_secret_name = hmac_salt_secret_name

    def _get_key(self) -> bytes:
        """SecretsManager에서 암호화 키를 조회하고 32바이트로 변환한다."""
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

    def encrypt(self, plaintext: str) -> bytes:
        """AES-256-GCM 암호화. 96비트 난수 IV 생성.

        반환값: iv(12B) + tag(16B) + ciphertext.
        """
        key = self._get_key()
        iv = os.urandom(_IV_LEN)
        aesgcm = AESGCM(key)
        # AESGCM.encrypt returns ciphertext + tag(16B)
        encrypted = aesgcm.encrypt(iv, plaintext.encode("utf-8"), None)
        ciphertext_part = encrypted[:-_TAG_LEN]
        tag = encrypted[-_TAG_LEN:]
        return iv + tag + ciphertext_part

    def decrypt(self, ciphertext: bytes) -> str:
        """AES-256-GCM 복호화. 인증 태그 검증 실패 시 DecryptionError.

        Raises:
            DecryptionError: 인증 태그 검증 실패 시.
        """
        key = self._get_key()
        iv = ciphertext[:_IV_LEN]
        tag = ciphertext[_IV_LEN : _IV_LEN + _TAG_LEN]
        ct = ciphertext[_IV_LEN + _TAG_LEN :]
        # AESGCM.decrypt expects ciphertext + tag
        aesgcm = AESGCM(key)
        try:
            plaintext_bytes = aesgcm.decrypt(iv, ct + tag, None)
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
