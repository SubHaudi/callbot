"""Phase D LLM 메트릭 테스트."""

from __future__ import annotations
import asyncio
from unittest.mock import MagicMock

from callbot.external.fake_system import FakeExternalSystem
from callbot.nlu.prompt_injection_filter import PromptInjectionFilter
from callbot.orchestrator.conversation_orchestrator import ConversationOrchestrator
from callbot.nlu.intent_classifier import IntentClassifier
from callbot.session.repository import CallbotDBRepository, InMemoryDBConnection
from callbot.session.session_manager import SessionManager
from callbot.session.session_store import InMemorySessionStore
from callbot.server.pipeline import TurnPipeline
from callbot.monitoring.in_memory import InMemoryCollector


class TokenTrackingLLMEngine:
    """FakeLLM that exposes token counts."""
    def generate_response(self, **kwargs):
        r = MagicMock(); r.text = "ok"; r.final_response = "ok"; return r

    def generate(self, context_text, user_text):
        return "ok"

    @property
    def last_input_tokens(self):
        return 150

    @property
    def last_output_tokens(self):
        return 50

    @property
    def model_name(self):
        return "sonnet-4"


def _make():
    pif = PromptInjectionFilter()
    ic = IntentClassifier()
    db = InMemoryDBConnection()
    repo = CallbotDBRepository(db, retry_delays=[0, 0, 0])
    store = InMemorySessionStore()
    sm = SessionManager(repo, store)
    llm = TokenTrackingLLMEngine()
    orch = ConversationOrchestrator(intent_classifier=ic, llm_engine=llm, session_manager=sm)
    ext = FakeExternalSystem()
    metrics = InMemoryCollector()
    pipeline = TurnPipeline(pif=pif, orchestrator=orch, session_manager=sm,
                            llm_engine=llm, external_system=ext, metrics_collector=metrics)
    return pipeline, metrics


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class TestLLMMetrics:
    def test_llm_request_counter(self):
        pipeline, metrics = _make()
        _run(pipeline.process(None, "010-0000-0000", "요금 조회해줘"))
        total = sum(
            metrics.get_counter("llm_requests_total", {"model": m})
            for m in ["sonnet-4", "unknown"]
        )
        assert total >= 1

    def test_llm_duration(self):
        pipeline, metrics = _make()
        _run(pipeline.process(None, "010-0000-0000", "요금 조회해줘"))
        obs = []
        for m in ["sonnet-4", "unknown"]:
            obs.extend(metrics.get_observations("llm_duration_ms", {"model": m}))
        assert len(obs) >= 1
        assert obs[0] >= 0

    def test_llm_token_tracking(self):
        pipeline, metrics = _make()
        _run(pipeline.process(None, "010-0000-0000", "요금 조회해줘"))
        input_tokens = metrics.get_counter("llm_input_tokens", {"model": "sonnet-4"})
        output_tokens = metrics.get_counter("llm_output_tokens", {"model": "sonnet-4"})
        assert input_tokens >= 1
        assert output_tokens >= 1

    def test_llm_cost_estimation(self):
        pipeline, metrics = _make()
        _run(pipeline.process(None, "010-0000-0000", "요금 조회해줘"))
        cost = metrics.get_counter("llm_estimated_cost_usd", {"model": "sonnet-4"})
        assert cost > 0

    def test_llm_error_counter_with_error_type(self):
        """LLM errors should track model + error_type dimensions."""
        pipeline, metrics = _make()
        # Normal call shouldn't produce errors
        _run(pipeline.process(None, "010-0000-0000", "요금 조회해줘"))
        errors = metrics.get_counter("llm_errors_total",
                                     {"model": "sonnet-4", "error_type": "exception"})
        assert errors == 0

    def test_llm_metrics_include_model_dimension(self):
        pipeline, metrics = _make()
        _run(pipeline.process(None, "010-0000-0000", "요금 조회해줘"))
        # All LLM metrics should use model dimension
        assert metrics.get_counter("llm_requests_total", {"model": "sonnet-4"}) >= 1
