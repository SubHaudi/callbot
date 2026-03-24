"""Phase Q: E2E 데모 시나리오 테스트."""
from __future__ import annotations

import asyncio
import pytest

from server.demo_scenarios import (
    SCENARIOS,
    DemoScenario,
    ScenarioTurn,
    TurnResultDetail,
    list_scenarios,
    run_scenario,
)


# ── 시나리오 정의 테스트 ──


class TestScenarioDefinitions:
    """시나리오 정의가 올바른지 확인."""

    def test_at_least_3_scenarios_defined(self):
        assert len(SCENARIOS) >= 3

    def test_at_most_10_scenarios(self):
        assert len(SCENARIOS) <= 10

    def test_each_scenario_has_turns(self):
        for sid, s in SCENARIOS.items():
            assert len(s.turns) > 0, f"{sid} has no turns"

    def test_each_scenario_has_name(self):
        for sid, s in SCENARIOS.items():
            assert s.name, f"{sid} missing name"

    def test_each_scenario_has_category(self):
        for sid, s in SCENARIOS.items():
            assert s.category, f"{sid} missing category"

    def test_scenario_ids_unique(self):
        ids = list(SCENARIOS.keys())
        assert len(ids) == len(set(ids))

    def test_list_scenarios_returns_dicts(self):
        items = list_scenarios()
        assert isinstance(items, list)
        assert len(items) == len(SCENARIOS)
        for item in items:
            assert "id" in item
            assert "name" in item
            assert "turn_count" in item

    def test_billing_inquiry_scenario_exists(self):
        assert "billing-inquiry" in SCENARIOS

    def test_plan_change_scenario_exists(self):
        assert "plan-change" in SCENARIOS

    def test_addon_cancel_scenario_exists(self):
        assert "addon-cancel" in SCENARIOS


# ── 시나리오 실행 테스트 (mock pipeline) ──


class FakePipelineResult:
    def __init__(self, session_id, response_text, action_type, context=None):
        self.session_id = session_id
        self.response_text = response_text
        self.action_type = action_type
        self.context = context or {}


class FakePipeline:
    """테스트용 가짜 파이프라인."""

    def __init__(self):
        self.calls = []

    async def process(self, session_id=None, caller_id="", text=""):
        self.calls.append({"session_id": session_id, "caller_id": caller_id, "text": text})
        return FakePipelineResult(
            session_id=session_id or "sess-001",
            response_text=f"응답: {text}",
            action_type="billing_inquiry",
            context={"intent": "billing_inquiry"},
        )


class TestRunScenario:
    """run_scenario 함수 테스트."""

    @pytest.fixture
    def pipeline(self):
        return FakePipeline()

    def test_unknown_scenario_returns_error(self, pipeline):
        result = asyncio.get_event_loop().run_until_complete(
            run_scenario("nonexistent", pipeline)
        )
        assert not result.success
        assert "Unknown scenario" in result.error

    def test_billing_inquiry_runs(self, pipeline):
        result = asyncio.get_event_loop().run_until_complete(
            run_scenario("billing-inquiry", pipeline)
        )
        assert result.scenario_id == "billing-inquiry"
        assert result.session_id
        assert len(result.turns) == 1
        assert result.total_time_ms >= 0
        assert result.avg_response_time_ms >= 0

    def test_plan_change_multi_turn(self, pipeline):
        result = asyncio.get_event_loop().run_until_complete(
            run_scenario("plan-change", pipeline)
        )
        assert len(result.turns) == 3
        # session_id should be passed through
        assert pipeline.calls[1]["session_id"] == "sess-001"

    def test_intent_accuracy_calculated(self, pipeline):
        result = asyncio.get_event_loop().run_until_complete(
            run_scenario("billing-inquiry", pipeline)
        )
        # FakePipeline returns billing_inquiry intent → match
        assert result.intent_accuracy == 100.0

    def test_turn_details_populated(self, pipeline):
        result = asyncio.get_event_loop().run_until_complete(
            run_scenario("billing-inquiry", pipeline)
        )
        t = result.turns[0]
        assert t.turn_number == 1
        assert t.user_text
        assert t.bot_response
        assert t.response_time_ms >= 0


class FailingPipeline:
    async def process(self, **kw):
        raise RuntimeError("boom")


class TestScenarioErrorHandling:
    def test_pipeline_error_captured(self):
        result = asyncio.get_event_loop().run_until_complete(
            run_scenario("billing-inquiry", FailingPipeline())
        )
        assert not result.success
        assert result.turns[0].action_type == "error"
        assert "boom" in result.turns[0].bot_response


# ── API 라우터 테스트 ──


class TestDemoRoutes:
    """데모 API 엔드포인트 테스트."""

    @pytest.fixture
    def client(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from server.demo_routes import router

        app = FastAPI()
        app.include_router(router)

        # Set up fake pipeline
        fake = FakePipeline()
        app.state.pipeline = fake

        return TestClient(app)

    def test_get_scenarios(self, client):
        res = client.get("/api/v1/demo/scenarios")
        assert res.status_code == 200
        data = res.json()
        assert len(data) >= 3
        assert data[0]["id"]

    def test_run_scenario(self, client):
        res = client.post("/api/v1/demo/scenarios/billing-inquiry/run")
        assert res.status_code == 200
        data = res.json()
        assert data["scenario_id"] == "billing-inquiry"
        assert data["session_id"]
        assert len(data["turns"]) > 0

    def test_run_unknown_scenario_404(self, client):
        res = client.post("/api/v1/demo/scenarios/nonexistent/run")
        assert res.status_code == 404

    def test_run_all_scenarios(self, client):
        res = client.post("/api/v1/demo/scenarios/run-all")
        assert res.status_code == 200
        data = res.json()
        assert len(data) >= 3

    def test_no_pipeline_503(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from server.demo_routes import router

        app = FastAPI()
        app.include_router(router)
        # no pipeline set
        c = TestClient(app)
        res = c.post("/api/v1/demo/scenarios/billing-inquiry/run")
        assert res.status_code == 503


# ── E2E 데모 HTML 페이지 ──


class TestE2EDemoPage:
    def test_html_file_exists(self):
        import pathlib
        html = pathlib.Path(__file__).resolve().parent.parent / "server" / "static" / "e2e-demo.html"
        assert html.exists()

    def test_html_contains_scenario_grid(self):
        import pathlib
        html = pathlib.Path(__file__).resolve().parent.parent / "server" / "static" / "e2e-demo.html"
        content = html.read_text()
        assert "scenarioGrid" in content
        assert "runAll" in content
        assert "/api/v1/demo" in content
