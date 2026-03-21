"""Phase E 구어체 인식률 벤치마크 테스트 (FR-008)."""

from callbot.nlu.intent_classifier import (
    IntentClassifier, MockIntentClassifier, SessionContext
)
from callbot.nlu.enums import Intent

# 30개 구어체 테스트셋 — 현실적 발화
_COLLOQUIAL_TEST_SET = [
    # BILLING_INQUIRY (6개)
    ("요금 좀 알려줘", Intent.BILLING_INQUIRY),
    ("그거 얼마야", Intent.BILLING_INQUIRY),
    ("이번 달 요금 나왔어?", Intent.BILLING_INQUIRY),
    ("요금이 얼마나 나왔어", Intent.BILLING_INQUIRY),
    ("청구 금액 알려줘", Intent.BILLING_INQUIRY),
    ("비용 얼마 내야 돼", Intent.BILLING_INQUIRY),
    # PLAN_CHANGE (3개)
    ("요금제 바꿀래", Intent.PLAN_CHANGE),
    ("플랜 변경하고 싶어", Intent.PLAN_CHANGE),
    ("다른 요금제로 갈아타고 싶어", Intent.PLAN_CHANGE),
    # PLAN_INQUIRY (3개)
    ("무슨 요금제 있어?", Intent.PLAN_INQUIRY),
    ("요금제 뭐 있어", Intent.PLAN_INQUIRY),
    ("어떤 요금제가 있나요", Intent.PLAN_INQUIRY),
    # PAYMENT_CHECK (3개)
    ("납부 확인 좀 해줘", Intent.PAYMENT_CHECK),
    ("돈 냈는데 확인 좀", Intent.PAYMENT_CHECK),
    ("결제 됐어?", Intent.PAYMENT_CHECK),
    # DATA_USAGE_INQUIRY (3개)
    ("데이터 남은거 확인해줘", Intent.DATA_USAGE_INQUIRY),
    ("기가 얼마나 남았어", Intent.DATA_USAGE_INQUIRY),
    ("데이터 좀 얼마나 남았어", Intent.DATA_USAGE_INQUIRY),
    # ADDON_CANCEL (3개)
    ("부가 좀 빼줘", Intent.ADDON_CANCEL),
    ("부가서비스 없애줘", Intent.ADDON_CANCEL),
    ("부가 해지해줘", Intent.ADDON_CANCEL),
    # AGENT_CONNECT (2개)
    ("사람 좀 바꿔줘", Intent.AGENT_CONNECT),
    ("상담원 연결해줘", Intent.AGENT_CONNECT),
    # END_CALL (2개)
    ("됐어 끊을게", Intent.END_CALL),
    ("그만할게", Intent.END_CALL),
    # SPEED_CONTROL (1개)
    ("좀 천천히 말해줘", Intent.SPEED_CONTROL),
    # REPEAT_REQUEST (1개)
    ("다시 말해줘", Intent.REPEAT_REQUEST),
    # COMPLAINT (1개)
    ("불만 있어", Intent.COMPLAINT),
    # CANCELLATION (1개)
    ("해지하고 싶어", Intent.CANCELLATION),
    # WAIT_REQUEST (1개)
    ("잠깐만요", Intent.WAIT_REQUEST),
]


class TestColloquialRecognitionRate:
    """FR-008: 구어체 인식률 80% 이상 (24/30+), UNCLASSIFIED ≤ 30%."""

    def test_recognition_rate_at_least_80_percent(self):
        clf = IntentClassifier(model=MockIntentClassifier())
        ctx = SessionContext(session_id="bench", turn_count=0)

        correct = 0
        unclassified = 0
        failures = []

        for text, expected in _COLLOQUIAL_TEST_SET:
            result = clf.classify(text, ctx)
            actual = result.primary_intent
            if actual == expected:
                correct += 1
            else:
                failures.append(f"  '{text}': expected {expected.name}, got {actual.name}")
            if actual == Intent.UNCLASSIFIED:
                unclassified += 1

        total = len(_COLLOQUIAL_TEST_SET)
        rate = correct / total
        unclass_rate = unclassified / total

        msg = (
            f"Recognition: {correct}/{total} ({rate:.0%}), "
            f"UNCLASSIFIED: {unclassified}/{total} ({unclass_rate:.0%})\n"
        )
        if failures:
            msg += "Failures:\n" + "\n".join(failures)

        assert rate >= 0.80, msg
        assert unclass_rate <= 0.30, msg
