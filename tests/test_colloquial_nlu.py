"""Phase E 구어체 NLU 분류 테스트."""

from callbot.nlu.intent_classifier import (
    IntentClassifier, MockIntentClassifier, SessionContext
)
from callbot.nlu.enums import Intent


class TestColloquialClassification:
    """FR-001/002/003: 구어체, 조사변형, 줄임말 패턴 인식."""

    def _classify(self, text: str) -> Intent:
        clf = IntentClassifier(model=MockIntentClassifier())
        ctx = SessionContext(session_id="test", turn_count=0)
        result = clf.classify(text, ctx)
        return result.primary_intent

    def test_billing_colloquial_1(self):
        assert self._classify("요금 좀 알려줘") == Intent.BILLING_INQUIRY

    def test_billing_colloquial_2(self):
        assert self._classify("그거 얼마야") == Intent.BILLING_INQUIRY

    def test_billing_colloquial_3(self):
        assert self._classify("이번 달 요금 나왔어?") == Intent.BILLING_INQUIRY

    def test_data_colloquial_1(self):
        assert self._classify("데이터 남은거 확인해줘") == Intent.DATA_USAGE_INQUIRY

    def test_data_colloquial_2(self):
        assert self._classify("기가 얼마나 남았어") == Intent.DATA_USAGE_INQUIRY

    def test_addon_colloquial_1(self):
        assert self._classify("부가 좀 빼줘") == Intent.ADDON_CANCEL

    def test_addon_colloquial_2(self):
        assert self._classify("부가서비스 없애줘") == Intent.ADDON_CANCEL

    def test_plan_change_colloquial(self):
        assert self._classify("요금제 바꿀래") == Intent.PLAN_CHANGE

    def test_plan_inquiry_colloquial(self):
        assert self._classify("무슨 요금제 있어?") == Intent.PLAN_INQUIRY

    def test_payment_colloquial(self):
        assert self._classify("돈 냈는데 확인 좀") == Intent.PAYMENT_CHECK

    def test_agent_colloquial(self):
        assert self._classify("사람 좀 바꿔줘") == Intent.AGENT_CONNECT

    def test_end_call_colloquial(self):
        assert self._classify("됐어 끊을게") == Intent.END_CALL
