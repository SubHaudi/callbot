"""callbot.voice_io.vendor_factory — 벤더 팩토리 (레지스트리 패턴)

설정값(VendorConfig)에 따라 적절한 STT/TTS 벤더 어댑터 인스턴스를 생성한다.
어댑터 모듈은 import 시 자동으로 레지스트리에 등록된다 (Task 8.1).
"""
from __future__ import annotations

import logging
from typing import Any

from callbot.voice_io.stt_engine import STTEngine
from callbot.voice_io.tts_engine import TTSEngine
from callbot.voice_io.vendor_config import VendorConfig
from callbot.voice_io.fallback_stt import FallbackSTTEngine

logger = logging.getLogger(__name__)

# 지원 벤더 레지스트리 (벤더 식별자 → 어댑터 클래스)
_STT_VENDORS: dict[str, type] = {}
_TTS_VENDORS: dict[str, type] = {}


def register_stt_vendor(vendor_id: str, adapter_cls: type) -> None:
    """STT 벤더 어댑터를 레지스트리에 등록한다."""
    _STT_VENDORS[vendor_id] = adapter_cls


def register_tts_vendor(vendor_id: str, adapter_cls: type) -> None:
    """TTS 벤더 어댑터를 레지스트리에 등록한다."""
    _TTS_VENDORS[vendor_id] = adapter_cls


def create_stt_engine(
    config: VendorConfig, **kwargs: Any
) -> STTEngine:
    """config.stt_vendor에 따라 STT 벤더 어댑터 인스턴스를 생성한다.

    항상 STTEngine을 반환한다. FallbackSTTEngine으로 래핑하여
    주 엔진 실패 시 STTFallbackError가 발생한다.

    Returns:
        STTEngine: FallbackSTTEngine 래퍼로 감싼 단일 엔진

    Raises:
        ValueError: 지원되지 않는 벤더 식별자
    """
    adapter_cls = _STT_VENDORS.get(config.stt_vendor)
    if adapter_cls is None:
        supported = sorted(_STT_VENDORS.keys())
        raise ValueError(
            f"Unsupported STT vendor '{config.stt_vendor}'. "
            f"Supported: {supported}"
        )
    primary = adapter_cls(config=config, **kwargs)

    if config.stt_fallback_vendor:
        fallback_cls = _STT_VENDORS.get(config.stt_fallback_vendor)
        if fallback_cls is None:
            supported = sorted(_STT_VENDORS.keys())
            raise ValueError(
                f"Unsupported STT fallback vendor '{config.stt_fallback_vendor}'. "
                f"Supported: {supported}"
            )
        # Phase F: 폴백 벤더가 있어도 FallbackSTTEngine으로 주 엔진만 래핑
        # 실패 시 STTFallbackError → VoiceServer가 텍스트 모드 전환
        return FallbackSTTEngine(primary)

    return FallbackSTTEngine(primary)


def create_tts_engine(
    config: VendorConfig, **kwargs: Any
) -> TTSEngine | tuple[TTSEngine, TTSEngine]:
    """config.tts_vendor에 따라 TTS 벤더 어댑터 인스턴스를 생성한다.

    폴백 벤더(config.tts_fallback_vendor)가 설정된 경우,
    (주 어댑터, 폴백 어댑터) 튜플을 반환한다.

    Returns:
        TTSEngine: 폴백 미설정 시 단일 어댑터
        tuple[TTSEngine, TTSEngine]: 폴백 설정 시 (primary, fallback)

    Raises:
        ValueError: 지원되지 않는 벤더 식별자
    """
    adapter_cls = _TTS_VENDORS.get(config.tts_vendor)
    if adapter_cls is None:
        supported = sorted(_TTS_VENDORS.keys())
        raise ValueError(
            f"Unsupported TTS vendor '{config.tts_vendor}'. "
            f"Supported: {supported}"
        )
    primary = adapter_cls(config=config, **kwargs)

    if config.tts_fallback_vendor:
        fallback_cls = _TTS_VENDORS.get(config.tts_fallback_vendor)
        if fallback_cls is None:
            supported = sorted(_TTS_VENDORS.keys())
            raise ValueError(
                f"Unsupported TTS fallback vendor '{config.tts_fallback_vendor}'. "
                f"Supported: {supported}"
            )
        fallback = fallback_cls(config=config, **kwargs)
        return primary, fallback

    return primary

from contextlib import contextmanager


@contextmanager
def vendor_lifespan():
    """서버 시작 시 STT/TTS 벤더를 초기화하고 검증하는 lifespan 헬퍼.

    Usage:
        with vendor_lifespan() as (stt_engine, tts_engine):
            # use engines

    Raises:
        RuntimeError: health_check() 실패 시 서버 시작 중단
    """
    config = VendorConfig.from_env()
    stt_engine = create_stt_engine(config)
    tts_engine = create_tts_engine(config)

    # Handle tuple returns (when fallback is configured)
    stt_primary = stt_engine[0] if isinstance(stt_engine, tuple) else stt_engine
    tts_primary = tts_engine[0] if isinstance(tts_engine, tuple) else tts_engine

    if not stt_primary.health_check():
        logger.error("STT vendor '%s' health check failed", config.stt_vendor)
        raise RuntimeError(f"STT 벤더 '{config.stt_vendor}' 연결 실패 — 서버 시작 중단")

    if not tts_primary.health_check():
        logger.error("TTS vendor '%s' health check failed", config.tts_vendor)
        raise RuntimeError(f"TTS 벤더 '{config.tts_vendor}' 연결 실패 — 서버 시작 중단")

    logger.info("STT/TTS 벤더 연결 검증 완료")

    try:
        yield stt_engine, tts_engine
    finally:
        stt_primary.close()
        tts_primary.close()
