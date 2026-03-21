"""Metrics overhead benchmark — NFR-001: ≤ 5ms P99."""

import asyncio
import statistics
import time

import pytest

from callbot.external.fake_system import FakeExternalSystem
from callbot.nlu.prompt_injection_filter import PromptInjectionFilter
from callbot.orchestrator.conversation_orchestrator import ConversationOrchestrator
from callbot.nlu.intent_classifier import IntentClassifier
from callbot.session.repository import CallbotDBRepository, InMemoryDBConnection
from callbot.session.session_manager import SessionManager
from callbot.session.session_store import InMemorySessionStore
from callbot.server.pipeline import TurnPipeline
from callbot.monitoring.in_memory import InMemoryCollector
from unittest.mock import MagicMock


class FakeLLMEngine:
    def generate_response(self, **kwargs):
        r = MagicMock(); r.text = "ok"; r.final_response = "ok"; return r
    def generate(self, context_text, user_text):
        return "ok"


def _make(with_metrics: bool):
    pif = PromptInjectionFilter()
    ic = IntentClassifier()
    db = InMemoryDBConnection()
    repo = CallbotDBRepository(db, retry_delays=[0,0,0])
    store = InMemorySessionStore()
    sm = SessionManager(repo, store)
    llm = FakeLLMEngine()
    orch = ConversationOrchestrator(intent_classifier=ic, llm_engine=llm, session_manager=sm)
    ext = FakeExternalSystem()
    metrics = InMemoryCollector() if with_metrics else None
    return TurnPipeline(pif=pif, orchestrator=orch, session_manager=sm,
                        llm_engine=llm, external_system=ext, metrics_collector=metrics)


def _bench(pipeline, n=1000):
    loop = asyncio.new_event_loop()
    times = []
    for _ in range(n):
        t0 = time.perf_counter()
        loop.run_until_complete(pipeline.process(None, "010-0000-0000", "요금 조회"))
        times.append((time.perf_counter() - t0) * 1000)
    loop.close()
    return times


def test_metrics_overhead_under_5ms():
    """NFR-001: metrics collection overhead ≤ 5ms at P99."""
    N = 1000
    without = _bench(_make(False), N)
    with_m = _bench(_make(True), N)

    without.sort()
    with_m.sort()

    p99_idx = int(N * 0.99)
    overhead_p99 = with_m[p99_idx] - without[p99_idx]

    median_without = statistics.median(without)
    median_with = statistics.median(with_m)
    overhead_median = median_with - median_without

    print(f"\nP99 overhead: {overhead_p99:.2f}ms, Median overhead: {overhead_median:.2f}ms")
    assert overhead_p99 < 5.0, f"P99 overhead {overhead_p99:.2f}ms exceeds 5ms limit"
