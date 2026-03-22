"""Voice I/O E2E 테스트 — Phase F

테스트 레벨:
  Level 1: IAM 권한 확인 (Polly, Transcribe)
  Level 2: Polly TTS 단독 (텍스트→오디오→파일 저장)
  Level 3: Transcribe STT 단독 (오디오→텍스트)
  Level 4: 라운드트립 (Polly TTS → Transcribe STT → WER 측정)
  Level 5: VoiceServer 파이프라인 E2E

사용법:
  # 전체 실행 (IAM 권한 필요)
  pytest callbot/voice_io/tests/test_e2e_voice_io.py -v

  # Level 1만 (권한 확인)
  pytest callbot/voice_io/tests/test_e2e_voice_io.py -v -k "iam"

  # mock으로 파이프라인만
  pytest callbot/voice_io/tests/test_e2e_voice_io.py -v -k "mock"

환경변수:
  SKIP_AWS_E2E=1  → AWS 호출 테스트 스킵
"""
from __future__ import annotations

import os
import json
import time
import pytest
import subprocess
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Any, List, Tuple

# ── Skip 조건 ──────────────────────────────────────────────
SKIP_AWS = os.environ.get("SKIP_AWS_E2E", "") == "1"
aws_required = pytest.mark.skipif(SKIP_AWS, reason="SKIP_AWS_E2E=1")


# ── WER 계산 유틸 ──────────────────────────────────────────
def compute_wer(reference: str, hypothesis: str) -> float:
    """Word Error Rate 계산 (Levenshtein distance on words)."""
    ref_words = reference.strip().split()
    hyp_words = hypothesis.strip().split()
    r, h = len(ref_words), len(hyp_words)
    # DP
    d = [[0] * (h + 1) for _ in range(r + 1)]
    for i in range(r + 1):
        d[i][0] = i
    for j in range(h + 1):
        d[0][j] = j
    for i in range(1, r + 1):
        for j in range(1, h + 1):
            sub = 0 if ref_words[i - 1] == hyp_words[j - 1] else 1
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + sub)
    return d[r][h] / max(r, 1)


# ── 한국어 테스트 문장 ─────────────────────────────────────
KO_TEST_SENTENCES = [
    "안녕하세요 무엇을 도와드릴까요",
    "계좌 잔액을 확인해 주세요",
    "카드 분실 신고를 하고 싶습니다",
    "이체 금액은 오만 원입니다",
    "감사합니다 좋은 하루 되세요",
]


# ═══════════════════════════════════════════════════════════
# Level 1: IAM 권한 확인
# ═══════════════════════════════════════════════════════════
class TestIAMPermissions:
    """AWS IAM 권한 확인 — Polly, Transcribe 접근 가능 여부."""

    @aws_required
    def test_polly_describe_voices(self):
        """polly:DescribeVoices 권한 확인."""
        import boto3
        client = boto3.client("polly", region_name="ap-northeast-2")
        resp = client.describe_voices(LanguageCode="ko-KR")
        voices = [v["Id"] for v in resp["Voices"]]
        assert "Seoyeon" in voices, f"Seoyeon not in {voices}"

    @aws_required
    def test_polly_synthesize(self):
        """polly:SynthesizeSpeech 권한 확인."""
        import boto3
        client = boto3.client("polly", region_name="ap-northeast-2")
        resp = client.synthesize_speech(
            Text="테스트", OutputFormat="pcm",
            VoiceId="Seoyeon", Engine="neural", SampleRate="16000",
        )
        data = resp["AudioStream"].read()
        assert len(data) > 0

    @aws_required
    def test_transcribe_permissions(self):
        """transcribe:StartStreamTranscription 또는 ListVocabularies 권한."""
        import boto3
        client = boto3.client("transcribe", region_name="ap-northeast-2")
        # ListVocabularies는 가벼운 읽기 호출
        resp = client.list_vocabularies(MaxResults=1)
        assert "Vocabularies" in resp

    @aws_required
    def test_transcribe_start_job(self):
        """transcribe:StartTranscriptionJob 권한 — 배치 방식 확인.

        NOTE: 실제 S3 파일 필요. 여기서는 dry-run 수준으로 확인.
        권한 에러 vs NotFound 에러 구분.
        """
        import boto3
        from botocore.exceptions import ClientError
        client = boto3.client("transcribe", region_name="ap-northeast-2")
        try:
            client.start_transcription_job(
                TranscriptionJobName=f"e2e-test-{int(time.time())}",
                LanguageCode="ko-KR",
                MediaFormat="wav",
                Media={"MediaFileUri": "s3://nonexistent-bucket-e2e/test.wav"},
            )
        except ClientError as e:
            code = e.response["Error"]["Code"]
            # AccessDeniedException → 권한 없음
            # BadRequestException → 권한은 있지만 S3 파일 없음 (OK)
            if code == "AccessDeniedException":
                pytest.fail(f"No transcribe:StartTranscriptionJob permission: {e}")
            # 그 외는 권한은 있다는 뜻


# ═══════════════════════════════════════════════════════════
# Level 2: Polly TTS 단독 테스트
# ═══════════════════════════════════════════════════════════
class TestPollyTTSE2E:
    """Polly TTS 실제 호출 테스트."""

    @aws_required
    def test_synthesize_korean(self):
        """한국어 문장 → PCM 오디오 생성."""
        from callbot.voice_io.polly_tts import PollyTTSEngine
        tts = PollyTTSEngine()
        result = tts.synthesize("안녕하세요 무엇을 도와드릴까요", session_id="test-1")
        assert len(result.data) > 1000  # PCM 데이터 크기 최소값
        assert result.encoding == "pcm"
        assert result.sample_rate == 24000

    @aws_required
    def test_ssml_generation(self):
        """SSML 올바르게 생성되는지."""
        from callbot.voice_io.polly_tts import PollyTTSEngine
        tts = PollyTTSEngine()
        ssml = tts.text_to_ssml("테스트 & <문장>", speed_factor=0.9)
        assert "&amp;" in ssml
        assert "&lt;" in ssml
        assert 'rate="90%"' in ssml

    @aws_required
    def test_synthesize_all_test_sentences(self):
        """모든 테스트 문장 TTS 변환 성공."""
        from callbot.voice_io.polly_tts import PollyTTSEngine
        tts = PollyTTSEngine()
        for sentence in KO_TEST_SENTENCES:
            result = tts.synthesize(sentence, session_id="test-batch")
            assert len(result.data) > 0, f"Empty audio for: {sentence}"


# ═══════════════════════════════════════════════════════════
# Level 3: Transcribe STT (실제 API) — 배치 방식
# ═══════════════════════════════════════════════════════════
class TestTranscribeSTTBatch:
    """AWS Transcribe 배치 방식 STT 테스트.

    TranscribeSTTEngine은 현재 mock 전용이므로,
    여기서는 boto3 직접 호출로 배치 STT를 테스트.
    """

    @aws_required
    def test_batch_transcribe_via_s3(self):
        """Polly→S3→Transcribe 배치 라운드트립.

        NOTE: S3 버킷 필요. 환경변수 E2E_S3_BUCKET 설정.
        """
        bucket = os.environ.get("E2E_S3_BUCKET")
        if not bucket:
            pytest.skip("E2E_S3_BUCKET not set")

        import boto3
        polly = boto3.client("polly", region_name="ap-northeast-2")
        s3 = boto3.client("s3", region_name="ap-northeast-2")
        transcribe = boto3.client("transcribe", region_name="ap-northeast-2")

        text = "안녕하세요 무엇을 도와드릴까요"

        # 1) Polly → PCM
        resp = polly.synthesize_speech(
            Text=text, OutputFormat="pcm",
            VoiceId="Seoyeon", Engine="neural", SampleRate="16000",
        )
        pcm_data = resp["AudioStream"].read()

        # 2) PCM → WAV (Transcribe 배치는 WAV 필요)
        import struct, io
        wav_buf = io.BytesIO()
        # WAV header
        sr, bps, ch = 16000, 16, 1
        data_size = len(pcm_data)
        wav_buf.write(b"RIFF")
        wav_buf.write(struct.pack("<I", 36 + data_size))
        wav_buf.write(b"WAVEfmt ")
        wav_buf.write(struct.pack("<IHHIIHH", 16, 1, ch, sr, sr * ch * bps // 8, ch * bps // 8, bps))
        wav_buf.write(b"data")
        wav_buf.write(struct.pack("<I", data_size))
        wav_buf.write(pcm_data)

        # 3) S3 업로드
        key = f"e2e-test/{int(time.time())}.wav"
        s3.put_object(Bucket=bucket, Key=key, Body=wav_buf.getvalue())

        # 4) Transcribe 배치 작업
        job_name = f"e2e-{int(time.time())}"
        try:
            transcribe.start_transcription_job(
                TranscriptionJobName=job_name,
                LanguageCode="ko-KR",
                MediaFormat="wav",
                Media={"MediaFileUri": f"s3://{bucket}/{key}"},
            )

            # 폴링 (최대 60초)
            for _ in range(30):
                time.sleep(2)
                status = transcribe.get_transcription_job(TranscriptionJobName=job_name)
                state = status["TranscriptionJob"]["TranscriptionJobStatus"]
                if state in ("COMPLETED", "FAILED"):
                    break

            assert state == "COMPLETED", f"Job {state}"
            uri = status["TranscriptionJob"]["Transcript"]["TranscriptFileUri"]

            # 결과 가져오기
            import urllib.request
            with urllib.request.urlopen(uri) as resp:
                result = json.loads(resp.read())
            transcript = result["results"]["transcripts"][0]["transcript"]
            wer = compute_wer(text, transcript)
            print(f"\n[E2E] Reference: {text}")
            print(f"[E2E] Hypothesis: {transcript}")
            print(f"[E2E] WER: {wer:.2%}")
            assert wer < 0.3, f"WER too high: {wer:.2%}"

        finally:
            # 정리
            try:
                transcribe.delete_transcription_job(TranscriptionJobName=job_name)
            except Exception:
                pass
            try:
                s3.delete_object(Bucket=bucket, Key=key)
            except Exception:
                pass


# ═══════════════════════════════════════════════════════════
# Level 4: 라운드트립 + WER (스트리밍 방식)
# ═══════════════════════════════════════════════════════════
class TestRoundtripStreaming:
    """Polly TTS → Transcribe Streaming STT 라운드트립.

    amazon-transcribe-streaming-sdk 필요:
      pip install amazon-transcribe
    """

    @aws_required
    def test_streaming_roundtrip(self):
        """Polly → 스트리밍 Transcribe → WER 측정."""
        try:
            from amazon_transcribe.client import TranscribeStreamingClient
            from amazon_transcribe.handlers import TranscriptResultStreamHandler
            from amazon_transcribe.model import TranscriptEvent
        except ImportError:
            pytest.skip("amazon-transcribe not installed: pip install amazon-transcribe")

        import asyncio
        import boto3

        text = "계좌 잔액을 확인해 주세요"

        # 1) Polly → PCM 16kHz
        polly = boto3.client("polly", region_name="ap-northeast-2")
        resp = polly.synthesize_speech(
            Text=text, OutputFormat="pcm",
            VoiceId="Seoyeon", Engine="neural", SampleRate="16000",
        )
        pcm_data = resp["AudioStream"].read()

        # 2) Streaming Transcribe
        final_text = []

        class Handler(TranscriptResultStreamHandler):
            async def handle_transcript_event(self, event: TranscriptEvent):
                for result in event.transcript.results:
                    if not result.is_partial:
                        for alt in result.alternatives:
                            final_text.append(alt.transcript)

        async def run():
            client = TranscribeStreamingClient(region="ap-northeast-2")
            stream = await client.start_stream_transcription(
                language_code="ko-KR",
                media_sample_rate_hz=16000,
                media_encoding="pcm",
            )
            handler = Handler(stream.output_stream)

            # 청크 전송 (4KB씩)
            chunk_size = 4096
            for i in range(0, len(pcm_data), chunk_size):
                await stream.input_stream.send_audio_event(
                    audio_chunk=pcm_data[i:i + chunk_size]
                )
            await stream.input_stream.end_stream()
            await handler.handle_events()

        asyncio.run(run())

        hypothesis = " ".join(final_text)
        wer = compute_wer(text, hypothesis)
        print(f"\n[Streaming E2E] Reference: {text}")
        print(f"[Streaming E2E] Hypothesis: {hypothesis}")
        print(f"[Streaming E2E] WER: {wer:.2%}")
        assert wer < 0.3, f"WER too high: {wer:.2%}"


# ═══════════════════════════════════════════════════════════
# Level 5: VoiceServer 파이프라인 E2E (mock pipeline)
# ═══════════════════════════════════════════════════════════
class TestVoiceServerE2EMock:
    """VoiceServer 파이프라인을 mock pipeline으로 E2E 검증."""

    @pytest.fixture
    def mock_pipeline(self):
        pipeline = MagicMock()
        result = MagicMock(response_text="네, 확인하겠습니다.")
        pipeline.process = AsyncMock(return_value=result)
        return pipeline

    @pytest.fixture
    def mock_stt(self):
        from callbot.voice_io.models import STTResult, StreamHandle, PartialResult
        stt = MagicMock()
        stt.start_stream.return_value = StreamHandle(session_id="s1", stream_id="st1")
        stt.process_audio_chunk.return_value = PartialResult(text="", is_final=False)
        stt.get_final_result.return_value = STTResult.create(
            text="잔액 확인해 주세요",
            confidence=0.95,
            processing_time_ms=120,
            threshold=0.5,
        )
        return stt

    @pytest.fixture
    def mock_tts(self):
        from callbot.voice_io.models import AudioStream
        tts = MagicMock()
        tts.synthesize.return_value = AudioStream(
            session_id="s1", data=b"\x00" * 1000, encoding="pcm", sample_rate=24000,
        )
        tts.is_playing.return_value = False
        return tts

    @pytest.mark.asyncio
    async def test_full_pipeline(self, mock_stt, mock_tts, mock_pipeline):
        """STT→Pipeline→TTS 전체 플로우."""
        from callbot.voice_io.voice_server import VoiceServer
        server = VoiceServer(
            stt_engine=mock_stt, tts_engine=mock_tts,
            pipeline=mock_pipeline, audio_converter=None,
        )
        session = server.create_session()
        result = await server.handle_audio(session.session_id, b"\x00" * 3200)

        assert result["transcript"] == "잔액 확인해 주세요"
        assert result["response_text"] == "네, 확인하겠습니다."
        assert len(result["audio"]) > 0
        mock_pipeline.process.assert_called_once_with(
            session_id=session.session_id, caller_id=session.session_id, text="잔액 확인해 주세요"
        )

    @pytest.mark.asyncio
    async def test_barge_in(self, mock_stt, mock_tts, mock_pipeline):
        """Barge-in 중단 테스트."""
        from callbot.voice_io.voice_server import VoiceServer
        server = VoiceServer(
            stt_engine=mock_stt, tts_engine=mock_tts,
            pipeline=mock_pipeline, audio_converter=None,
        )
        session = server.create_session()
        # TTS 재생 중 상태 설정
        server._sessions[session.session_id].is_tts_playing = True
        result = await server.handle_interrupt(session.session_id)
        assert result["status"] == "interrupted"
        mock_tts.stop_playback.assert_called_once()


# ═══════════════════════════════════════════════════════════
# Level 5b: VoiceServer + 실제 Polly (하이브리드)
# ═══════════════════════════════════════════════════════════
class TestVoiceServerHybrid:
    """실제 Polly TTS + mock STT/Pipeline으로 하이브리드 E2E."""

    @aws_required
    @pytest.mark.asyncio
    async def test_real_polly_in_pipeline(self):
        """실제 Polly로 TTS 생성, 나머지는 mock."""
        from callbot.voice_io.polly_tts import PollyTTSEngine
        from callbot.voice_io.voice_server import VoiceServer
        from callbot.voice_io.models import STTResult, StreamHandle, PartialResult

        stt = MagicMock()
        stt.start_stream.return_value = StreamHandle(session_id="s1", stream_id="st1")
        stt.process_audio_chunk.return_value = PartialResult(text="", is_final=False)
        stt.get_final_result.return_value = STTResult.create(
            text="테스트 입력", confidence=0.9,
            processing_time_ms=100, threshold=0.5,
        )

        pipeline = MagicMock()
        result = MagicMock(response_text="감사합니다")
        pipeline.process = AsyncMock(return_value=result)

        tts = PollyTTSEngine()
        server = VoiceServer(stt_engine=stt, tts_engine=tts, pipeline=pipeline)
        session = server.create_session()
        result = await server.handle_audio(session.session_id, b"\x00" * 3200)

        assert result["response_text"] == "감사합니다"
        assert len(result["audio"]) > 1000  # 실제 Polly 오디오


# ═══════════════════════════════════════════════════════════
# WER 벤치마크 — 다수 문장
# ═══════════════════════════════════════════════════════════
class TestWERBenchmark:
    """한국어 WER 품질 벤치마크 — Polly→Transcribe 라운드트립."""

    @aws_required
    def test_wer_benchmark_batch(self):
        """모든 테스트 문장에 대해 배치 Transcribe WER 측정.

        NOTE: E2E_S3_BUCKET 환경변수 필요.
        """
        bucket = os.environ.get("E2E_S3_BUCKET")
        if not bucket:
            pytest.skip("E2E_S3_BUCKET not set")

        import boto3, struct, io
        polly = boto3.client("polly", region_name="ap-northeast-2")
        s3 = boto3.client("s3", region_name="ap-northeast-2")
        transcribe_client = boto3.client("transcribe", region_name="ap-northeast-2")

        results: List[Tuple[str, str, float]] = []

        for text in KO_TEST_SENTENCES:
            # Polly → PCM → WAV → S3 → Transcribe
            resp = polly.synthesize_speech(
                Text=text, OutputFormat="pcm",
                VoiceId="Seoyeon", Engine="neural", SampleRate="16000",
            )
            pcm = resp["AudioStream"].read()

            wav_buf = io.BytesIO()
            sr, bps, ch = 16000, 16, 1
            wav_buf.write(b"RIFF")
            wav_buf.write(struct.pack("<I", 36 + len(pcm)))
            wav_buf.write(b"WAVEfmt ")
            wav_buf.write(struct.pack("<IHHIIHH", 16, 1, ch, sr, sr * ch * bps // 8, ch * bps // 8, bps))
            wav_buf.write(b"data")
            wav_buf.write(struct.pack("<I", len(pcm)))
            wav_buf.write(pcm)

            key = f"e2e-wer/{int(time.time())}-{hash(text) % 10000}.wav"
            s3.put_object(Bucket=bucket, Key=key, Body=wav_buf.getvalue())

            job_name = f"wer-{int(time.time())}-{hash(text) % 10000}"
            try:
                transcribe_client.start_transcription_job(
                    TranscriptionJobName=job_name, LanguageCode="ko-KR",
                    MediaFormat="wav",
                    Media={"MediaFileUri": f"s3://{bucket}/{key}"},
                )
                for _ in range(30):
                    time.sleep(2)
                    st = transcribe_client.get_transcription_job(TranscriptionJobName=job_name)
                    state = st["TranscriptionJob"]["TranscriptionJobStatus"]
                    if state in ("COMPLETED", "FAILED"):
                        break

                if state == "COMPLETED":
                    import urllib.request
                    uri = st["TranscriptionJob"]["Transcript"]["TranscriptFileUri"]
                    with urllib.request.urlopen(uri) as r:
                        hyp = json.loads(r.read())["results"]["transcripts"][0]["transcript"]
                    wer = compute_wer(text, hyp)
                    results.append((text, hyp, wer))
                else:
                    results.append((text, "[FAILED]", 1.0))
            finally:
                try:
                    transcribe_client.delete_transcription_job(TranscriptionJobName=job_name)
                except Exception:
                    pass
                try:
                    s3.delete_object(Bucket=bucket, Key=key)
                except Exception:
                    pass

        # 결과 출력
        print("\n" + "=" * 60)
        print("WER Benchmark Results")
        print("=" * 60)
        avg_wer = 0.0
        for ref, hyp, wer in results:
            print(f"  REF: {ref}")
            print(f"  HYP: {hyp}")
            print(f"  WER: {wer:.2%}")
            print("-" * 40)
            avg_wer += wer
        avg_wer /= max(len(results), 1)
        print(f"  AVG WER: {avg_wer:.2%}")
        print("=" * 60)
        assert avg_wer < 0.2, f"Average WER too high: {avg_wer:.2%}"
