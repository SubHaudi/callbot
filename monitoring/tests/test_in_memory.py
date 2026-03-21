"""Tests for InMemoryCollector."""

import pytest


def _make_collector():
    from monitoring.in_memory import InMemoryCollector
    return InMemoryCollector()


class TestInMemoryIncrement:
    def test_increment_default(self):
        c = _make_collector()
        c.increment("requests_total")
        assert c.get_counter("requests_total") == 1

    def test_increment_custom_value(self):
        c = _make_collector()
        c.increment("requests_total", value=5)
        assert c.get_counter("requests_total") == 5

    def test_increment_accumulates(self):
        c = _make_collector()
        c.increment("requests_total")
        c.increment("requests_total", value=3)
        assert c.get_counter("requests_total") == 4


class TestInMemoryObserve:
    def test_observe_records_value(self):
        c = _make_collector()
        c.observe("duration_ms", 42.5)
        assert c.get_observations("duration_ms") == [42.5]

    def test_observe_multiple(self):
        c = _make_collector()
        c.observe("duration_ms", 10.0)
        c.observe("duration_ms", 20.0)
        assert c.get_observations("duration_ms") == [10.0, 20.0]


class TestInMemorySetGauge:
    def test_set_gauge(self):
        c = _make_collector()
        c.set_gauge("active_sessions", 5)
        assert c.get_gauge("active_sessions") == 5

    def test_set_gauge_overwrites(self):
        c = _make_collector()
        c.set_gauge("active_sessions", 5)
        c.set_gauge("active_sessions", 3)
        assert c.get_gauge("active_sessions") == 3


class TestInMemoryDimensions:
    def test_increment_with_dimensions(self):
        c = _make_collector()
        c.increment("intent_total", dimensions={"intent": "billing"})
        c.increment("intent_total", dimensions={"intent": "usage"})
        c.increment("intent_total", dimensions={"intent": "billing"})
        assert c.get_counter("intent_total", {"intent": "billing"}) == 2
        assert c.get_counter("intent_total", {"intent": "usage"}) == 1

    def test_observe_with_dimensions(self):
        c = _make_collector()
        c.observe("nlu_ms", 10.0, dimensions={"intent": "billing"})
        c.observe("nlu_ms", 20.0, dimensions={"intent": "usage"})
        assert c.get_observations("nlu_ms", {"intent": "billing"}) == [10.0]
        assert c.get_observations("nlu_ms", {"intent": "usage"}) == [20.0]

    def test_gauge_with_dimensions(self):
        c = _make_collector()
        c.set_gauge("active", 5, dimensions={"region": "kr"})
        assert c.get_gauge("active", {"region": "kr"}) == 5
