from __future__ import annotations
from typing import Protocol, runtime_checkable


@runtime_checkable
class VendorAdapter(Protocol):
    """벤더 어댑터 전용 프로토콜.

    기존 STTEngine/TTSEngine 추상 클래스를 변경하지 않고
    health_check()와 close()를 벤더 어댑터에만 제공한다.
    """

    def health_check(self) -> bool:
        """벤더 SDK에 테스트 요청을 보내 연결 상태를 확인한다.
        성공 시 True, 실패 시 False.
        """
        ...

    def close(self) -> None:
        """벤더 SDK 클라이언트 연결 및 활성 스트리밍 채널을 정리한다."""
        ...
