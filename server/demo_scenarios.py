"""callbot.server.demo_scenarios — E2E 데모 시나리오 정의 및 실행기.

Phase Q: 사전 정의된 시나리오로 전체 통화 흐름을 자동 시연한다.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ScenarioTurn:
    """시나리오의 단일 턴."""
    user_text: str
    expected_intent: Optional[str] = None
    description: str = ""


@dataclass
class DemoScenario:
    """E2E 데모 시나리오 정의."""
    id: str
    name: str
    description: str
    category: str
    turns: list[ScenarioTurn] = field(default_factory=list)


@dataclass
class TurnResultDetail:
    """시나리오 실행의 턴별 결과."""
    turn_number: int
    user_text: str
    bot_response: str
    action_type: str
    expected_intent: Optional[str]
    actual_intent: Optional[str]
    intent_match: bool
    response_time_ms: float


@dataclass
class ScenarioResult:
    """시나리오 실행 전체 결과."""
    scenario_id: str
    scenario_name: str
    success: bool
    session_id: str
    turns: list[TurnResultDetail] = field(default_factory=list)
    total_time_ms: float = 0.0
    avg_response_time_ms: float = 0.0
    intent_accuracy: float = 0.0
    error: Optional[str] = None


# ── 시나리오 정의 ──

SCENARIOS: dict[str, DemoScenario] = {}


def _register(s: DemoScenario) -> DemoScenario:
    SCENARIOS[s.id] = s
    return s


_register(DemoScenario(
    id="billing-inquiry",
    name="요금 조회",
    description="이번 달 청구 요금을 조회하는 기본 시나리오",
    category="조회",
    turns=[
        ScenarioTurn("이번 달 요금이 얼마예요?", "billing_inquiry", "요금 조회 요청"),
    ],
))

_register(DemoScenario(
    id="plan-change",
    name="요금제 변경",
    description="현재 요금제를 확인하고 새 요금제로 변경하는 멀티턴 시나리오",
    category="변경",
    turns=[
        ScenarioTurn("요금제 변경하고 싶어요", "plan_change", "요금제 변경 시작"),
        ScenarioTurn("2", "plan_select", "요금제 선택 (2번)"),
        ScenarioTurn("네", "plan_confirm", "변경 확인"),
    ],
))

_register(DemoScenario(
    id="addon-cancel",
    name="부가서비스 해지",
    description="부가서비스 목록 조회 후 특정 서비스를 해지하는 시나리오",
    category="해지",
    turns=[
        ScenarioTurn("부가서비스 해지해줘", "addon_cancel", "부가서비스 해지 시작"),
        ScenarioTurn("데이터 쉐어링 해지", "addon_select", "해지할 서비스 선택"),
    ],
))

_register(DemoScenario(
    id="data-usage",
    name="데이터 잔여량 조회",
    description="현재 데이터 사용량과 잔여량을 조회하는 시나리오",
    category="조회",
    turns=[
        ScenarioTurn("데이터 잔여량 알려줘", "data_usage", "데이터 사용량 조회"),
    ],
))

_register(DemoScenario(
    id="mixed-conversation",
    name="혼합 대화",
    description="요금 조회 후 요금제 변경으로 이어지는 복합 시나리오",
    category="복합",
    turns=[
        ScenarioTurn("이번 달 요금 좀 알려주세요", "billing_inquiry", "요금 조회"),
        ScenarioTurn("요금제를 바꾸고 싶은데요", "plan_change", "요금제 변경 전환"),
        ScenarioTurn("1", "plan_select", "요금제 선택 (1번)"),
        ScenarioTurn("네 변경해주세요", "plan_confirm", "변경 확인"),
    ],
))


def list_scenarios() -> list[dict[str, Any]]:
    """시나리오 목록 반환."""
    return [
        {
            "id": s.id,
            "name": s.name,
            "description": s.description,
            "category": s.category,
            "turn_count": len(s.turns),
        }
        for s in SCENARIOS.values()
    ]


async def run_scenario(scenario_id: str, pipeline: Any, caller_id: str = "01099990000") -> ScenarioResult:
    """시나리오를 실행하고 결과를 반환한다."""
    scenario = SCENARIOS.get(scenario_id)
    if scenario is None:
        return ScenarioResult(
            scenario_id=scenario_id,
            scenario_name="unknown",
            success=False,
            session_id="",
            error=f"Unknown scenario: {scenario_id}",
        )

    start_total = time.monotonic()
    session_id: Optional[str] = None
    turn_results: list[TurnResultDetail] = []
    success = True

    for i, turn in enumerate(scenario.turns):
        t0 = time.monotonic()
        try:
            result = await pipeline.process(
                session_id=session_id,
                caller_id=caller_id,
                text=turn.user_text,
            )
            elapsed = (time.monotonic() - t0) * 1000
            session_id = result.session_id

            actual_intent = result.context.get("intent") or result.action_type
            intent_match = (
                turn.expected_intent is None
                or turn.expected_intent.lower() in actual_intent.lower()
                or actual_intent.lower() in turn.expected_intent.lower()
            )

            turn_results.append(TurnResultDetail(
                turn_number=i + 1,
                user_text=turn.user_text,
                bot_response=result.response_text,
                action_type=result.action_type,
                expected_intent=turn.expected_intent,
                actual_intent=actual_intent,
                intent_match=intent_match,
                response_time_ms=round(elapsed, 1),
            ))
        except Exception as exc:
            elapsed = (time.monotonic() - t0) * 1000
            turn_results.append(TurnResultDetail(
                turn_number=i + 1,
                user_text=turn.user_text,
                bot_response=f"ERROR: {exc}",
                action_type="error",
                expected_intent=turn.expected_intent,
                actual_intent=None,
                intent_match=False,
                response_time_ms=round(elapsed, 1),
            ))
            success = False

    total_time = (time.monotonic() - start_total) * 1000
    times = [t.response_time_ms for t in turn_results]
    intent_checks = [t for t in turn_results if t.expected_intent is not None]
    intent_matches = sum(1 for t in intent_checks if t.intent_match)

    return ScenarioResult(
        scenario_id=scenario_id,
        scenario_name=scenario.name,
        success=success and all(t.action_type != "error" for t in turn_results),
        session_id=session_id or "",
        turns=turn_results,
        total_time_ms=round(total_time, 1),
        avg_response_time_ms=round(sum(times) / len(times), 1) if times else 0,
        intent_accuracy=round(intent_matches / len(intent_checks) * 100, 1) if intent_checks else 100.0,
    )
