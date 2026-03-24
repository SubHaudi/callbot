#!/usr/bin/env python3
"""AWS Transcribe Streaming CLI — 마이크로 실시간 한국어 STT 테스트.

Usage:
    pip install amazon-transcribe aiofile pyaudio
    python stt_cli.py [--region ap-northeast-2] [--lang ko-KR]

마이크로 말하면 실시간으로 텍스트가 출력됩니다.
Ctrl+C로 종료.
"""
from __future__ import annotations

import argparse
import asyncio
import sys

# pyaudio import
try:
    import pyaudio
except ImportError:
    print("❌ pyaudio 필요: pip install pyaudio")
    print("   macOS: brew install portaudio && pip install pyaudio")
    print("   Ubuntu: sudo apt install portaudio19-dev && pip install pyaudio")
    sys.exit(1)

try:
    from amazon_transcribe.client import TranscribeStreamingClient
    from amazon_transcribe.handlers import TranscriptResultStreamHandler
    from amazon_transcribe.model import TranscriptEvent
except ImportError:
    print("❌ amazon-transcribe 필요: pip install amazon-transcribe")
    sys.exit(1)


SAMPLE_RATE = 16000
CHANNELS = 1
CHUNK_DURATION_MS = 100  # 100ms 단위 전송
CHUNK_SIZE = int(SAMPLE_RATE * CHUNK_DURATION_MS / 1000)  # 1600 samples
FORMAT = pyaudio.paInt16


class LiveHandler(TranscriptResultStreamHandler):
    """실시간 partial/final 결과를 터미널에 출력."""

    def __init__(self, output_stream):
        super().__init__(output_stream)
        self._last_partial = ""

    async def handle_transcript_event(self, transcript_event: TranscriptEvent):
        results = transcript_event.transcript.results
        for result in results:
            for alt in result.alternatives:
                text = alt.transcript
                if not text:
                    continue
                if result.is_partial:
                    # partial: 같은 줄에 덮어쓰기
                    sys.stdout.write(f"\r\033[K💬 {text}")
                    sys.stdout.flush()
                    self._last_partial = text
                else:
                    # final: 확정 — 줄바꿈
                    conf_items = alt.items or []
                    confs = [
                        getattr(item, "confidence", None)
                        for item in conf_items
                        if getattr(item, "confidence", None) is not None
                    ]
                    avg_conf = sum(float(c) for c in confs) / len(confs) if confs else 0
                    sys.stdout.write(f"\r\033[K✅ {text}")
                    if avg_conf > 0:
                        sys.stdout.write(f"  ({avg_conf:.0%})")
                    sys.stdout.write("\n")
                    sys.stdout.flush()
                    self._last_partial = ""


async def mic_stream(pa: pyaudio.PyAudio) -> asyncio.Queue:
    """마이크 → asyncio.Queue로 오디오 청크 전달."""
    queue: asyncio.Queue = asyncio.Queue()
    stream = pa.open(
        format=FORMAT,
        channels=CHANNELS,
        rate=SAMPLE_RATE,
        input=True,
        frames_per_buffer=CHUNK_SIZE,
        stream_callback=lambda data, *_: (queue.put_nowait(data), (None, pyaudio.paContinue))[1],
    )
    stream.start_stream()
    return queue, stream


async def run(region: str, lang: str):
    pa = pyaudio.PyAudio()
    queue, mic = await mic_stream(pa)

    client = TranscribeStreamingClient(region=region)
    stream = await client.start_stream_transcription(
        language_code=lang,
        media_sample_rate_hz=SAMPLE_RATE,
        media_encoding="pcm",
    )

    handler = LiveHandler(stream.output_stream)

    print(f"🎙️  마이크 준비 완료 (region={region}, lang={lang})")
    print(f"   말해보세요! Ctrl+C로 종료.\n")

    async def feed_audio():
        try:
            while True:
                chunk = await queue.get()
                await stream.input_stream.send_audio_event(audio_chunk=chunk)
        except asyncio.CancelledError:
            pass
        finally:
            await stream.input_stream.end_stream()

    feed_task = asyncio.create_task(feed_audio())

    try:
        await handler.handle_events()
    except asyncio.CancelledError:
        pass
    finally:
        feed_task.cancel()
        mic.stop_stream()
        mic.close()
        pa.terminate()


def main():
    parser = argparse.ArgumentParser(description="AWS Transcribe Streaming CLI — 실시간 한국어 STT")
    parser.add_argument("--region", default="ap-northeast-2", help="AWS region (default: ap-northeast-2)")
    parser.add_argument("--lang", default="ko-KR", help="언어 코드 (default: ko-KR)")
    args = parser.parse_args()

    print("=" * 50)
    print("  AWS Transcribe Streaming — 실시간 STT CLI")
    print("=" * 50)

    try:
        asyncio.run(run(args.region, args.lang))
    except KeyboardInterrupt:
        print("\n\n👋 종료!")


if __name__ == "__main__":
    main()
