# Voice I/O E2E 테스트 전략 — Phase F

## 📌 현황 요약

| 항목 | 상태 |
|------|------|
| IAM Role | `claw-dev-role` — **Polly/Transcribe 권한 없음** ❌ |
| PollyTTSEngine | boto3 직접 호출 (권한만 있으면 즉시 동작) |
| TranscribeSTTEngine | `_client.transcribe()` 커스텀 메서드 — **실제 API 아님** |
| AudioConverter | ffmpeg opus↔PCM (동작 확인 필요) |
| VoiceServer | STT→Pipeline→TTS 파이프라인 (mock E2E 통과 ✅) |

## 1. IAM 권한 확보 (선행 조건)

```bash
# 현재 권한 확인
aws polly describe-voices --language-code ko-KR 2>&1
aws transcribe list-vocabularies --max-results 1 2>&1
```

**필요한 IAM 정책:**
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "polly:SynthesizeSpeech",
        "polly:DescribeVoices"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "transcribe:StartStreamTranscription",
        "transcribe:StartTranscriptionJob",
        "transcribe:GetTranscriptionJob",
        "transcribe:DeleteTranscriptionJob",
        "transcribe:ListVocabularies"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": ["s3:PutObject", "s3:GetObject", "s3:DeleteObject"],
      "Resource": "arn:aws:s3:::YOUR-E2E-BUCKET/e2e-*"
    }
  ]
}
```

## 2. TranscribeSTTEngine 실제 API 연동 방안

현재 `_transcribe_sync`가 `self._client.transcribe()`를 호출하는데 이건 boto3에 없는 메서드.

### Option A: 배치 Transcribe (S3 경유)
- 장점: 간단, 안정적
- 단점: 지연 10~30초, S3 필요
- 용도: 품질 측정, WER 벤치마크

### Option B: Streaming Transcribe (권장 — 프로덕션용)
```bash
pip install amazon-transcribe
```

`_transcribe_sync` 교체 코드:
```python
# callbot/voice_io/transcribe_stt.py 수정
import asyncio
from amazon_transcribe.client import TranscribeStreamingClient
from amazon_transcribe.handlers import TranscriptResultStreamHandler
from amazon_transcribe.model import TranscriptEvent

def _transcribe_sync(self, audio_data: bytes) -> Dict[str, Any]:
    """실제 AWS Transcribe Streaming 호출."""
    final_texts = []

    class Handler(TranscriptResultStreamHandler):
        async def handle_transcript_event(self, event: TranscriptEvent):
            for result in event.transcript.results:
                if not result.is_partial:
                    for alt in result.alternatives:
                        final_texts.append(alt.transcript)

    async def _run():
        client = TranscribeStreamingClient(region=self._region)
        stream = await client.start_stream_transcription(
            language_code=self._language_code,
            media_sample_rate_hz=self._sample_rate,
            media_encoding="pcm",
        )
        handler = Handler(stream.output_stream)
        chunk_size = 4096
        for i in range(0, len(audio_data), chunk_size):
            await stream.input_stream.send_audio_event(
                audio_chunk=audio_data[i:i + chunk_size]
            )
        await stream.input_stream.end_stream()
        await handler.handle_events()

    asyncio.run(_run())
    text = " ".join(final_texts)
    return {"text": text, "confidence": 0.9 if text else 0.0}
```

## 3. E2E 테스트 레벨

| Level | 대상 | AWS 필요 | 파일 |
|-------|------|----------|------|
| 1 | IAM 권한 확인 | ✅ | `test_e2e_voice_io.py::TestIAMPermissions` |
| 2 | Polly TTS 단독 | ✅ | `test_e2e_voice_io.py::TestPollyTTSE2E` |
| 3 | Transcribe STT 배치 | ✅+S3 | `test_e2e_voice_io.py::TestTranscribeSTTBatch` |
| 4 | 라운드트립 스트리밍 | ✅ | `test_e2e_voice_io.py::TestRoundtripStreaming` |
| 5a | VoiceServer mock | ❌ | `test_e2e_voice_io.py::TestVoiceServerE2EMock` ✅ 통과 |
| 5b | VoiceServer hybrid | ✅ | `test_e2e_voice_io.py::TestVoiceServerHybrid` |
| WER | 한국어 품질 벤치마크 | ✅+S3 | `test_e2e_voice_io.py::TestWERBenchmark` |

## 4. 실행 방법

```bash
# mock 테스트만 (즉시 실행 가능)
python3 -m pytest callbot/voice_io/tests/test_e2e_voice_io.py -v -k "mock"

# IAM 권한 확인
python3 -m pytest callbot/voice_io/tests/test_e2e_voice_io.py -v -k "iam"

# 전체 E2E (권한 + S3 버킷 필요)
E2E_S3_BUCKET=my-callbot-e2e python3 -m pytest callbot/voice_io/tests/test_e2e_voice_io.py -v

# AWS 테스트 스킵
SKIP_AWS_E2E=1 python3 -m pytest callbot/voice_io/tests/test_e2e_voice_io.py -v
```

## 5. WER 측정 기준

| 수준 | WER | 판정 |
|------|-----|------|
| 우수 | < 10% | 프로덕션 OK |
| 양호 | 10~20% | 후처리로 보완 가능 |
| 미달 | 20~30% | 커스텀 vocabulary 필요 |
| 불합격 | > 30% | 다른 STT 검토 |

한국어 Polly→Transcribe 라운드트립은 일반적으로 WER 5~15% 수준.

## 6. 다음 단계 (TODO)

1. **IAM 정책 추가** → claw-dev-role에 Polly + Transcribe 권한
2. **S3 버킷 생성** → 배치 Transcribe E2E용
3. **`amazon-transcribe` SDK 설치** → 스트리밍 STT 연동
4. **TranscribeSTTEngine `_transcribe_sync` 교체** → 실제 API
5. **CI에 mock 테스트 추가** → Level 5a는 즉시 가능
6. **커스텀 vocabulary** → 금융 도메인 용어 (계좌, 이체 등)
