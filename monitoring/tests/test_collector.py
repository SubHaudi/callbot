"""Tests for MetricsCollector protocol conformance."""

from monitoring.collector import MetricsCollector


def test_inmemory_conforms_to_metrics_collector_protocol():
    """InMemoryCollector must satisfy the MetricsCollector protocol."""
    from monitoring.in_memory import InMemoryCollector

    collector = InMemoryCollector()
    assert isinstance(collector, MetricsCollector)
