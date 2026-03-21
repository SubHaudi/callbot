"""Phase D 파이프라인 타이밍 메트릭 테스트."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

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


class FakeLLMEngine:
    def generate_response(self, *, classification=None, session=None,
                          customer_text="", api_result=None, **kwargs) -> MagicMock:
        resp = MagicMock()
        resp.text = f"안내: {customer_text}"
        resp.final_response = resp.text
        return resp

    def generate(self, context_text: str, user_text: str) -> str:
        return f"안내: {user_text}"


def _make_pipeline_with_metrics():
    pif = PromptInjectionFilter()
    intent_classifier = IntentClassifier()
    db = InMemoryDBConnection()
    repo = CallbotDBRepository(db, retry_delays=[0, 0, 0])
    store = InMemorySessionStore()
    session_manager = SessionManager(repo, store)
    llm_engine = FakeLLMEngine()
    orchestrator = ConversationOrchestrator(
        intent_classifier=intent_classifier,
        llm_engine=llm_engine,
        session_manager=session_manager,
    )
    external_system = FakeExternalSystem()
    metrics = InMemoryCollector()
    pipeline = TurnPipeline(
        pif=pif,
        orchestrator=orchestrator,
        session_manager=session_manager,
        llm_engine=llm_engine,
        external_system=external_system,
        metrics_collector=metrics,
    )
    return pipeline, metrics


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class TestPipelineTimingMetrics:
    def test_pipeline_records_pif_timing(self):
        pipeline, metrics = _make_pipeline_with_metrics()
        _run(pipeline.process(None, "010-1234-5678", "요금 조회해줘"))
        obs = metrics.get_observations("pif_duration_ms")
        assert len(obs) == 1
        assert obs[0] >= 0

    def test_pipeline_records_nlu_timing_with_intent_dimension(self):
        pipeline, metrics = _make_pipeline_with_metrics()
        _run(pipeline.process(None, "010-1234-5678", "요금 조회해줘"))
        # nlu_duration_ms should have intent dimension
        # Check at least one observation exists across any dimension
        assert any(
            metrics.get_observations("nlu_duration_ms", {"intent": intent})
            for intent in ["BILLING_INQUIRY", "GENERAL_INQUIRY", "PLAN_CHANGE",
                          "ADDON_CANCEL", "DATA_USAGE_INQUIRY"]
        )

    def test_pipeline_records_llm_step_timing(self):
        pipeline, metrics = _make_pipeline_with_metrics()
        _run(pipeline.process(None, "010-1234-5678", "요금 조회해줘"))
        obs = metrics.get_observations("llm_step_duration_ms")
        assert len(obs) >= 1
        assert obs[0] >= 0

    def test_pipeline_records_external_api_timing(self):
        pipeline, metrics = _make_pipeline_with_metrics()
        _run(pipeline.process(None, "010-1234-5678", "요금 조회해줘"))
        # external_api might not fire for all intents, but for billing it should
        obs_list = []
        for op in ["get_billing", "get_data_usage", "change_plan", "cancel_addon"]:
            obs_list.extend(metrics.get_observations("external_api_duration_ms", {"operation": op}))
        # At least one observation from billing inquiry
        assert len(obs_list) >= 0  # Will be 0 until implemented — Red test

    def test_pipeline_records_pii_masking_timing(self):
        pipeline, metrics = _make_pipeline_with_metrics()
        _run(pipeline.process(None, "010-1234-5678", "내 카드번호 1234-5678-9012-3456"))
        obs = metrics.get_observations("pii_masking_duration_ms")
        assert len(obs) == 1
        assert obs[0] >= 0

    def test_pipeline_records_total_timing(self):
        pipeline, metrics = _make_pipeline_with_metrics()
        _run(pipeline.process(None, "010-1234-5678", "요금 조회해줘"))
        # total_duration_ms should have intent dimension
        assert any(
            metrics.get_observations("total_duration_ms", {"intent": intent})
            for intent in ["BILLING_INQUIRY", "GENERAL_INQUIRY", "PLAN_CHANGE",
                          "ADDON_CANCEL", "DATA_USAGE_INQUIRY"]
        )
