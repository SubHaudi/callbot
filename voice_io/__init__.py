from __future__ import annotations
"""callbot.voice_io — 음성 I/O 계층 (STT, TTS, DTMF)"""
from callbot.voice_io.models import STTResult, DTMFResult, StreamHandle, PartialResult, AudioStream
from callbot.voice_io.enums import NumberType
from callbot.voice_io.stt_engine import STTEngine, STTEngineBase
from callbot.voice_io.tts_engine import TTSEngine, TTSEngineBase
from callbot.voice_io.dtmf_processor import DTMFProcessor
from callbot.voice_io.barge_in import BargeInHandler
from callbot.voice_io.config import VoiceIOConfig
from callbot.voice_io.vendor_config import VendorConfig
from callbot.voice_io.vendor_adapter import VendorAdapter
from callbot.voice_io.exceptions import VendorConnectionError
from callbot.voice_io.vendor_factory import create_stt_engine, create_tts_engine
# These imports trigger adapter registration at module load time
from callbot.voice_io.stt_vendor_adapter import STTVendorAdapter
from callbot.voice_io.tts_vendor_adapter import TTSVendorAdapter

__all__ = [
    # Data models
    "STTResult",
    "DTMFResult",
    "StreamHandle",
    "PartialResult",
    "AudioStream",
    # Enums
    "NumberType",
    # STT
    "STTEngine",
    "STTEngineBase",
    # TTS
    "TTSEngine",
    "TTSEngineBase",
    # DTMF
    "DTMFProcessor",
    # Barge-in
    "BargeInHandler",
    # Config
    "VoiceIOConfig",
    # Vendor
    "VendorConfig",
    "VendorAdapter",
    "VendorConnectionError",
    "create_stt_engine",
    "create_tts_engine",
    "STTVendorAdapter",
    "TTSVendorAdapter",
]
