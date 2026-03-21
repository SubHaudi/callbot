"""Tests for CloudWatchCollector EMF output."""

import json

from monitoring.cloudwatch import CloudWatchCollector


class TestCloudWatchEMF:
    def test_increment_emf_format(self, capsys):
        c = CloudWatchCollector(namespace="Test")
        c.increment("requests_total", value=1, dimensions={"intent": "billing"})
        c.flush()
        out = capsys.readouterr().out.strip()
        emf = json.loads(out)
        assert emf["requests_total"] == 1
        assert emf["intent"] == "billing"
        assert "_aws" in emf
        md = emf["_aws"]["CloudWatchMetrics"][0]
        assert md["Namespace"] == "Test"
        assert {"Name": "requests_total", "Unit": "Count"} in md["Metrics"]
        assert "intent" in md["Dimensions"][0]

    def test_observe_emf_format(self, capsys):
        c = CloudWatchCollector(namespace="Test")
        c.observe("duration_ms", 42.5, dimensions={"op": "query"})
        c.flush()
        out = capsys.readouterr().out.strip()
        emf = json.loads(out)
        assert emf["duration_ms"] == 42.5
        assert emf["op"] == "query"

    def test_gauge_emf_format(self, capsys):
        c = CloudWatchCollector(namespace="Test")
        c.set_gauge("active_sessions", 5)
        c.flush()
        out = capsys.readouterr().out.strip()
        emf = json.loads(out)
        assert emf["active_sessions"] == 5

    def test_fire_and_forget(self, capsys, monkeypatch):
        """EMF output failure must not raise exceptions (NFR-003)."""
        c = CloudWatchCollector(namespace="Test")
        c.increment("test_metric")

        import io
        def bad_write(*args, **kwargs):
            raise IOError("disk full")

        monkeypatch.setattr("sys.stdout", type("BadStdout", (), {"write": bad_write, "flush": lambda s: None})())
        # Should not raise
        c.flush()

    def test_dimensions_in_emf(self, capsys):
        c = CloudWatchCollector(namespace="Test")
        c.increment("errors", dimensions={"model": "sonnet", "error_type": "timeout"})
        c.flush()
        out = capsys.readouterr().out.strip()
        emf = json.loads(out)
        assert emf["model"] == "sonnet"
        assert emf["error_type"] == "timeout"
        dims = emf["_aws"]["CloudWatchMetrics"][0]["Dimensions"][0]
        assert "model" in dims
        assert "error_type" in dims
