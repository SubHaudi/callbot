"""callbot.session.session_store — 세션 저장소 추상 인터페이스 및 인메모리 구현체"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from callbot.session.models import SessionContext


class SessionStoreBase(ABC):
    """세션 저장소 추상 인터페이스.

    save/load/delete/exists 메서드를 추상 메서드로 정의한다.
    """

    @abstractmethod
    def save(self, context: SessionContext) -> None:
        """SessionContext 전체를 원자적으로 저장한다."""
        ...

    @abstractmethod
    def load(self, session_id: str) -> Optional[SessionContext]:
        """session_id로 SessionContext를 조회한다. 없으면 None."""
        ...

    @abstractmethod
    def delete(self, session_id: str) -> None:
        """session_id에 해당하는 세션을 삭제한다."""
        ...

    @abstractmethod
    def exists(self, session_id: str) -> bool:
        """session_id에 해당하는 세션이 존재하는지 확인한다."""
        ...

    def count(self) -> int:
        """활성 세션 수를 반환한다. 서브클래스에서 효율적으로 오버라이드 가능."""
        raise NotImplementedError


class InMemorySessionStore(SessionStoreBase):
    """테스트 및 로컬 개발용 인메모리 구현체.

    객체 참조를 직접 저장하므로 save() 후 load()는 동일 객체를 반환한다.
    """

    def __init__(self) -> None:
        self._store: dict[str, SessionContext] = {}

    def save(self, context: SessionContext) -> None:
        self._store[context.session_id] = context

    def load(self, session_id: str) -> Optional[SessionContext]:
        return self._store.get(session_id)

    def delete(self, session_id: str) -> None:
        self._store.pop(session_id, None)

    def exists(self, session_id: str) -> bool:
        return session_id in self._store

    def count(self) -> int:
        return len(self._store)
