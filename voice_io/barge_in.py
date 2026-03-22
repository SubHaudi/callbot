"""callbot.voice_io.barge_in — 바지인 콜백 인터페이스"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class BargeInHandler(Protocol):
    """STT가 TTS의 재생을 중단시키기 위한 의존성 주입 프로토콜.

    STT_엔진은 TTS_엔진을 직접 임포트하지 않고 이 프로토콜을 통해
    stop_playback()을 호출한다.
    """

    def stop_playback(self, session_id: str) -> None:
        """바지인 감지 시 TTS 재생을 즉시 중단한다 (P95 200ms).

        세션 상태를 stopped 플래그로 전환 (세션 삭제가 아님, M-30).
        이미 stopped인 세션에 대해 다시 호출 시 무시.
        """
        ...

    def speech_start(self, session_id: str) -> None:
        """사용자 발화 시작 감지 콜백 (M-29).

        VAD가 음성 활동을 감지했을 때 호출.
        """
        ...

    def speech_end(self, session_id: str) -> None:
        """사용자 발화 종료 감지 콜백 (M-29).

        VAD가 침묵을 감지하여 발화 종료로 판단했을 때 호출.
        """
        ...
