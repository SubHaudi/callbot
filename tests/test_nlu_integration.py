"""Phase E 키워드+패턴 통합 테스트."""

from callbot.nlu.intent_classifier import (
    IntentClassifier, MockIntentClassifier, SessionContext
)
from callbot.nlu.enums import Intent


class TestKeywordPatternIntegration:
    """기존 키워드와 새 구어체 패턴이 모두 올바르게 분류되는지 통합 확인."""

    def _classify(self, text: str) -> Intent:
        clf = IntentClassifier(model=MockIntentClassifier())
        ctx = SessionContext(session_id="test", turn_count=0)
        return clf.classify(text, ctx).primary_intent

    # 기존 키워드 (회귀 테스트)
    def test_keyword_billing(self):
        assert self._classify("요금 조회해줘") == Intent.BILLING_INQUIRY

    def test_keyword_plan_change(self):
        assert self._classify("요금제 변경해주세요") == Intent.PLAN_CHANGE

    def test_keyword_payment(self):
        assert self._classify("납부 확인해주세요") == Intent.PAYMENT_CHECK

    def test_keyword_data(self):
        assert self._classify("데이터 잔여량 조회") == Intent.DATA_USAGE_INQUIRY

    def test_keyword_addon(self):
        assert self._classify("부가서비스 해지해줘") == Intent.ADDON_CANCEL

    def test_keyword_agent(self):
        assert self._classify("상담사 연결해주세요") == Intent.AGENT_CONNECT

    # 조사 변형
    def test_josa_variation_1(self):
        assert self._classify("요금을 알려줘") == Intent.BILLING_INQUIRY

    def test_josa_variation_2(self):
        assert self._classify("요금이 얼마야") == Intent.BILLING_INQUIRY

    # 줄임말
    def test_abbreviation_addon(self):
        assert self._classify("부가 빼줘") == Intent.ADDON_CANCEL

    def test_abbreviation_data(self):
        assert self._classify("데이터 좀 얼마나 남았어") == Intent.DATA_USAGE_INQUIRY

    # 경계 케이스: 부가서비스 해지 vs 일반 해지
    def test_addon_cancel_not_cancellation(self):
        assert self._classify("부가서비스 해지") == Intent.ADDON_CANCEL

    def test_general_cancel_is_cancellation(self):
        assert self._classify("해지 문의할게요") == Intent.CANCELLATION

    # UNCLASSIFIED
    def test_random_text_unclassified(self):
        assert self._classify("오늘 날씨 어때") == Intent.UNCLASSIFIED
