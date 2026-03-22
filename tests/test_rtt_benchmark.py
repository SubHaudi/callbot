"""Phase F TASK-020: RTT + Barge-in 벤치마크 테스트."""
from __future__ import annotations

import asyncio
import time
import statistics
import pytest
from unittest.mock import MagicMock
from dataclasses import dataclass

from callbot.voice_io.voice_server import VoiceServer
from callbot.voice_io.models import STTResult, StreamHandle, AudioStream, PartialResult


@dataclass
class MockPipelineResult:
    response_text: str


def _make_delayed_stt(stt_delay_sec: float = 2.5):
    """STT mock with configurable delay."""
    stt = MagicMock()
    stt.start_stream.return_value = StreamHandle(session_id="s1", stream_id="st1")
    stt.process_audio_chunk.return_value = PartialResult(text="", is_final=False)

    def delayed_final(*args, **kwargs):
        time.sleep(stt_delay_sec)
        return STTResult.create(text="요금 조회", confidence=0.9, processing_time_ms=int(stt_delay_sec * 1000))

    stt.get_final_result.side_effect = delayed_final
    return stt


def _make_delayed_tts(tts_delay_sec: float = 0.8):
    """TTS mock with configurable delay."""
    tts = MagicMock()

    def delayed_synth(text, session_id):
        time.sleep(tts_delay_sec)
        return AudioStream(session_id=session_id, data=b"\x00" * 1000)

    tts.synthesize.side_effect = delayed_synth
    return tts


def _make_delayed_pipeline(llm_delay_sec: float = 2.5):
    """Pipeline mock with configurable delay."""
    pipeline = MagicMock()

    def delayed_process(session_id, text):
        time.sleep(llm_delay_sec)
        return MockPipelineResult(response_text="요금은 55,000원입니다.")

    pipeline.process.side_effect = delayed_process
    return pipeline


class TestRTTBenchmark:
    """NFR-001: RTT P95 ≤ 8초 벤치마크.

    Mock 지연: STT 2.5s + LLM 2.5s + TTS 0.8s = 5.8s
    예상 RTT: ~5.8s (< 8.0s 버짓)
    """

    @pytest.mark.asyncio
    async def test_rtt_within_budget(self):
        """단일 요청 RTT ≤ 8초."""
        stt = _make_delayed_stt(0.25)  # 10x 빠르게 (실제 2.5s mock은 너무 느림)
        tts = _make_delayed_tts(0.08)
        pipeline = _make_delayed_pipeline(0.25)
        server = VoiceServer(stt_engine=stt, tts_engine=tts, pipeline=pipeline)

        session = server.create_session()
        t0 = time.perf_counter()
        result = await server.handle_audio(session.session_id, b"audio_data")
        elapsed = time.perf_counter() - t0

        assert result["transcript"] == "요금 조회"
        # 0.25 + 0.25 + 0.08 = 0.58s scaled (실제 5.8s)
        # 스케일 팩터 10x → 실제 RTT = elapsed * 10
        estimated_real_rtt = elapsed * 10
        assert estimated_real_rtt <= 8.0, f"Estimated RTT {estimated_real_rtt:.2f}s > 8.0s budget"

    @pytest.mark.asyncio
    async def test_rtt_p95_multiple_runs(self):
        """10회 반복 P95 ≤ 8초."""
        stt = _make_delayed_stt(0.025)  # 100x 빠르게
        tts = _make_delayed_tts(0.008)
        pipeline = _make_delayed_pipeline(0.025)
        server = VoiceServer(stt_engine=stt, tts_engine=tts, pipeline=pipeline)

        latencies = []
        for _ in range(10):
            session = server.create_session()
            t0 = time.perf_counter()
            await server.handle_audio(session.session_id, b"audio")
            elapsed = time.perf_counter() - t0
            latencies.append(elapsed * 100)  # 100x 스케일

        p95 = sorted(latencies)[int(len(latencies) * 0.95)]
        assert p95 <= 8.0, f"P95 RTT {p95:.2f}s > 8.0s budget"


class TestBargeInLatency:
    """FR-005: Barge-in 중단 지연 P95 < 200ms."""

    @pytest.mark.asyncio
    async def test_barge_in_latency_p95(self):
        """10회 interrupt 지연 P95 < 200ms."""
        tts = MagicMock()
        server = VoiceServer(tts_engine=tts)

        latencies = []
        for _ in range(10):
            session = server.create_session()
            session.is_tts_playing = True
            t0 = time.perf_counter()
            await server.handle_interrupt(session.session_id)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            latencies.append(elapsed_ms)

        p95 = sorted(latencies)[int(len(latencies) * 0.95)]
        assert p95 < 200, f"Barge-in P95 {p95:.1f}ms >= 200ms"
        tts.stop_playback.assert_called()
