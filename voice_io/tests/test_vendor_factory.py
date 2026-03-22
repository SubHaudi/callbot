"""callbot.voice_io.tests.test_vendor_factory — 벤더 팩토리 단위 테스트

Requirements: 3.4, 3.5, 3.6, 5.4
"""
from __future__ import annotations

import pytest

from callbot.voice_io.vendor_config import VendorConfig
from callbot.voice_io.vendor_factory import (
    _STT_VENDORS,
    _TTS_VENDORS,
    create_stt_engine,
    create_tts_engine,
    register_stt_vendor,
    register_tts_vendor,
)


# ---------------------------------------------------------------------------
# 테스트용 더미 어댑터
# ---------------------------------------------------------------------------

class _DummySTTAdapter:
    """테스트용 STT 어댑터 스텁."""

    def __init__(self, config: VendorConfig, **kwargs):
        self.config = config
        self.kwargs = kwargs


class _DummyTTSAdapter:
    """테스트용 TTS 어댑터 스텁."""

    def __init__(self, config: VendorConfig, **kwargs):
        self.config = config
        self.kwargs = kwargs


class _DummyFallbackSTT:
    """테스트용 STT 폴백 어댑터 스텁."""

    def __init__(self, config: VendorConfig, **kwargs):
        self.config = config
        self.kwargs = kwargs


class _DummyFallbackTTS:
    """테스트용 TTS 폴백 어댑터 스텁."""

    def __init__(self, config: VendorConfig, **kwargs):
        self.config = config
        self.kwargs = kwargs


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clean_registries():
    """각 테스트 전후로 레지스트리를 초기화한다."""
    saved_stt = dict(_STT_VENDORS)
    saved_tts = dict(_TTS_VENDORS)
    _STT_VENDORS.clear()
    _TTS_VENDORS.clear()
    yield
    _STT_VENDORS.clear()
    _STT_VENDORS.update(saved_stt)
    _TTS_VENDORS.clear()
    _TTS_VENDORS.update(saved_tts)


def _make_config(
    stt_vendor: str = "test-stt",
    tts_vendor: str = "test-tts",
    stt_fallback_vendor: str | None = None,
    tts_fallback_vendor: str | None = None,
) -> VendorConfig:
    return VendorConfig(
        stt_vendor=stt_vendor,
        tts_vendor=tts_vendor,
        stt_fallback_vendor=stt_fallback_vendor,
        tts_fallback_vendor=tts_fallback_vendor,
    )


# ---------------------------------------------------------------------------
# register 함수 테스트
# ---------------------------------------------------------------------------

class TestRegisterVendor:
    def test_register_stt_vendor(self):
        register_stt_vendor("test-stt", _DummySTTAdapter)
        assert "test-stt" in _STT_VENDORS
        assert _STT_VENDORS["test-stt"] is _DummySTTAdapter

    def test_register_tts_vendor(self):
        register_tts_vendor("test-tts", _DummyTTSAdapter)
        assert "test-tts" in _TTS_VENDORS
        assert _TTS_VENDORS["test-tts"] is _DummyTTSAdapter

    def test_register_overwrites_existing(self):
        register_stt_vendor("v1", _DummySTTAdapter)
        register_stt_vendor("v1", _DummyFallbackSTT)
        assert _STT_VENDORS["v1"] is _DummyFallbackSTT


# ---------------------------------------------------------------------------
# create_stt_engine 테스트
# ---------------------------------------------------------------------------

class TestCreateSTTEngine:
    def test_returns_adapter_instance(self):
        register_stt_vendor("test-stt", _DummySTTAdapter)
        config = _make_config(stt_vendor="test-stt")
        engine = create_stt_engine(config)
        # Phase F: create_stt_engine now wraps in FallbackSTTEngine
        from callbot.voice_io.fallback_stt import FallbackSTTEngine
        assert isinstance(engine, FallbackSTTEngine)
        assert isinstance(engine._primary, _DummySTTAdapter)
        assert engine._primary.config is config

    def test_passes_kwargs_to_adapter(self):
        register_stt_vendor("test-stt", _DummySTTAdapter)
        config = _make_config(stt_vendor="test-stt")
        engine = create_stt_engine(config, threshold=0.5)
        from callbot.voice_io.fallback_stt import FallbackSTTEngine
        assert isinstance(engine, FallbackSTTEngine)
        assert engine._primary.kwargs == {"threshold": 0.5}

    def test_unsupported_vendor_raises_valueerror(self):
        with pytest.raises(ValueError, match="Unsupported STT vendor 'unknown'"):
            create_stt_engine(_make_config(stt_vendor="unknown"))

    def test_unsupported_vendor_error_includes_supported_list(self):
        register_stt_vendor("alpha", _DummySTTAdapter)
        register_stt_vendor("beta", _DummySTTAdapter)
        with pytest.raises(ValueError, match=r"Supported: \['alpha', 'beta'\]"):
            create_stt_engine(_make_config(stt_vendor="unknown"))

    def test_fallback_returns_wrapped(self):
        """Phase F: fallback vendor가 있어도 FallbackSTTEngine으로 래핑 반환."""
        register_stt_vendor("primary", _DummySTTAdapter)
        register_stt_vendor("fallback", _DummyFallbackSTT)
        config = _make_config(stt_vendor="primary", stt_fallback_vendor="fallback")
        result = create_stt_engine(config)
        from callbot.voice_io.fallback_stt import FallbackSTTEngine
        assert isinstance(result, FallbackSTTEngine)
        assert isinstance(result._primary, _DummySTTAdapter)

    def test_fallback_unsupported_raises_valueerror(self):
        register_stt_vendor("primary", _DummySTTAdapter)
        config = _make_config(stt_vendor="primary", stt_fallback_vendor="missing")
        with pytest.raises(ValueError, match="Unsupported STT fallback vendor 'missing'"):
            create_stt_engine(config)

    def test_no_fallback_returns_single_engine(self):
        register_stt_vendor("test-stt", _DummySTTAdapter)
        config = _make_config(stt_vendor="test-stt", stt_fallback_vendor=None)
        result = create_stt_engine(config)
        assert not isinstance(result, tuple)


# ---------------------------------------------------------------------------
# create_tts_engine 테스트
# ---------------------------------------------------------------------------

class TestCreateTTSEngine:
    def test_returns_adapter_instance(self):
        register_tts_vendor("test-tts", _DummyTTSAdapter)
        config = _make_config(tts_vendor="test-tts")
        engine = create_tts_engine(config)
        assert isinstance(engine, _DummyTTSAdapter)
        assert engine.config is config

    def test_passes_kwargs_to_adapter(self):
        register_tts_vendor("test-tts", _DummyTTSAdapter)
        config = _make_config(tts_vendor="test-tts")
        engine = create_tts_engine(config, voice="Seoyeon")
        assert engine.kwargs == {"voice": "Seoyeon"}

    def test_unsupported_vendor_raises_valueerror(self):
        with pytest.raises(ValueError, match="Unsupported TTS vendor 'unknown'"):
            create_tts_engine(_make_config(tts_vendor="unknown"))

    def test_unsupported_vendor_error_includes_supported_list(self):
        register_tts_vendor("alpha", _DummyTTSAdapter)
        register_tts_vendor("beta", _DummyTTSAdapter)
        with pytest.raises(ValueError, match=r"Supported: \['alpha', 'beta'\]"):
            create_tts_engine(_make_config(tts_vendor="unknown"))

    def test_fallback_returns_tuple(self):
        register_tts_vendor("primary", _DummyTTSAdapter)
        register_tts_vendor("fallback", _DummyFallbackTTS)
        config = _make_config(tts_vendor="primary", tts_fallback_vendor="fallback")
        result = create_tts_engine(config)
        assert isinstance(result, tuple)
        assert len(result) == 2
        primary, fallback = result
        assert isinstance(primary, _DummyTTSAdapter)
        assert isinstance(fallback, _DummyFallbackTTS)

    def test_fallback_unsupported_raises_valueerror(self):
        register_tts_vendor("primary", _DummyTTSAdapter)
        config = _make_config(tts_vendor="primary", tts_fallback_vendor="missing")
        with pytest.raises(ValueError, match="Unsupported TTS fallback vendor 'missing'"):
            create_tts_engine(config)

    def test_no_fallback_returns_single_engine(self):
        register_tts_vendor("test-tts", _DummyTTSAdapter)
        config = _make_config(tts_vendor="test-tts", tts_fallback_vendor=None)
        result = create_tts_engine(config)
        assert not isinstance(result, tuple)


# ---------------------------------------------------------------------------
# Property-Based Tests (Hypothesis)
# ---------------------------------------------------------------------------

from hypothesis import given, settings
import hypothesis.strategies as st


# Feature: callbot-voice-io, Property 5: 벤더 팩토리 등록-조회 일관성
# **Validates: Requirements 3.4, 3.5, 3.6**

_vendor_id_st = st.text(
    min_size=1,
    alphabet=st.characters(whitelist_categories=("L", "N")),
)


@given(vendor_id=_vendor_id_st)
@settings(max_examples=100)
def test_stt_registered_vendor_returns_instance(vendor_id: str):
    """등록된 STT 벤더 식별자로 create_stt_engine 호출 시 해당 어댑터 인스턴스를 반환한다."""
    # Feature: callbot-voice-io, Property 5: 벤더 팩토리 등록-조회 일관성
    _STT_VENDORS.clear()
    _TTS_VENDORS.clear()

    register_stt_vendor(vendor_id, _DummySTTAdapter)
    config = _make_config(stt_vendor=vendor_id)
    engine = create_stt_engine(config)
    from callbot.voice_io.fallback_stt import FallbackSTTEngine
    assert isinstance(engine, FallbackSTTEngine)
    assert isinstance(engine._primary, _DummySTTAdapter)
    assert engine._primary.config is config


@given(vendor_id=_vendor_id_st)
@settings(max_examples=100)
def test_tts_registered_vendor_returns_instance(vendor_id: str):
    """등록된 TTS 벤더 식별자로 create_tts_engine 호출 시 해당 어댑터 인스턴스를 반환한다."""
    # Feature: callbot-voice-io, Property 5: 벤더 팩토리 등록-조회 일관성
    _STT_VENDORS.clear()
    _TTS_VENDORS.clear()

    register_tts_vendor(vendor_id, _DummyTTSAdapter)
    config = _make_config(tts_vendor=vendor_id)
    engine = create_tts_engine(config)
    assert isinstance(engine, _DummyTTSAdapter)
    assert engine.config is config


@given(
    registered_id=_vendor_id_st,
    unregistered_id=_vendor_id_st,
)
@settings(max_examples=100)
def test_stt_unregistered_vendor_raises_valueerror_with_supported_list(
    registered_id: str, unregistered_id: str
):
    """미등록 STT 벤더 식별자로 호출 시 ValueError가 발생하고 지원 목록이 포함된다."""
    # Feature: callbot-voice-io, Property 5: 벤더 팩토리 등록-조회 일관성
    from hypothesis import assume

    assume(registered_id != unregistered_id)

    _STT_VENDORS.clear()
    _TTS_VENDORS.clear()

    register_stt_vendor(registered_id, _DummySTTAdapter)
    config = _make_config(stt_vendor=unregistered_id)

    with pytest.raises(ValueError) as exc_info:
        create_stt_engine(config)

    error_msg = str(exc_info.value)
    assert unregistered_id in error_msg
    assert registered_id in error_msg


@given(
    registered_id=_vendor_id_st,
    unregistered_id=_vendor_id_st,
)
@settings(max_examples=100)
def test_tts_unregistered_vendor_raises_valueerror_with_supported_list(
    registered_id: str, unregistered_id: str
):
    """미등록 TTS 벤더 식별자로 호출 시 ValueError가 발생하고 지원 목록이 포함된다."""
    # Feature: callbot-voice-io, Property 5: 벤더 팩토리 등록-조회 일관성
    from hypothesis import assume

    assume(registered_id != unregistered_id)

    _STT_VENDORS.clear()
    _TTS_VENDORS.clear()

    register_tts_vendor(registered_id, _DummyTTSAdapter)
    config = _make_config(tts_vendor=unregistered_id)

    with pytest.raises(ValueError) as exc_info:
        create_tts_engine(config)

    error_msg = str(exc_info.value)
    assert unregistered_id in error_msg
    assert registered_id in error_msg
