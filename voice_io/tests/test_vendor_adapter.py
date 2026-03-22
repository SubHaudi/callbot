from __future__ import annotations
"""VendorAdapter 프로토콜 단위 테스트."""

from callbot.voice_io.vendor_adapter import VendorAdapter


class _GoodAdapter:
    """health_check()와 close()를 모두 구현한 클래스."""

    def health_check(self) -> bool:
        return True

    def close(self) -> None:
        pass


class _MissingClose:
    """close()가 없는 클래스."""

    def health_check(self) -> bool:
        return True


class _MissingHealthCheck:
    """health_check()가 없는 클래스."""

    def close(self) -> None:
        pass


def test_isinstance_true_for_conforming_class():
    adapter = _GoodAdapter()
    assert isinstance(adapter, VendorAdapter)


def test_isinstance_false_when_close_missing():
    obj = _MissingClose()
    assert not isinstance(obj, VendorAdapter)


def test_isinstance_false_when_health_check_missing():
    obj = _MissingHealthCheck()
    assert not isinstance(obj, VendorAdapter)


def test_health_check_returns_bool():
    adapter = _GoodAdapter()
    result = adapter.health_check()
    assert result is True


def test_close_returns_none():
    adapter = _GoodAdapter()
    result = adapter.close()
    assert result is None
