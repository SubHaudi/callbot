"""Phase E NLU 성능 벤치마크 (NFR-001, NFR-004)."""

import time
from callbot.nlu.intent_classifier import MockIntentClassifier


class TestNLUPerformance:
    """NFR-001: NLU 분류 5ms 이내 P99."""

    def test_pattern_matching_p99_under_5ms(self):
        clf = MockIntentClassifier()
        utterances = [
            "요금 좀 알려줘", "요금제 바꿀래", "데이터 남은거",
            "부가 좀 빼줘", "납부 확인해줘", "상담사 연결",
            "오늘 날씨 어때",  # UNCLASSIFIED
        ]
        timings = []
        for _ in range(1000):
            for text in utterances:
                t0 = time.perf_counter()
                clf.predict(text)
                elapsed_ms = (time.perf_counter() - t0) * 1000
                timings.append(elapsed_ms)

        timings.sort()
        p99_idx = int(len(timings) * 0.99)
        p99 = timings[p99_idx]
        assert p99 <= 5.0, f"P99 = {p99:.2f}ms > 5ms"


class TestReDoSProtection:
    """NFR-004: 1000자 입력에 100ms 이내."""

    def test_long_input_no_redos(self):
        clf = MockIntentClassifier()
        # 1000자 랜덤 문자열
        long_input = "아" * 500 + "요금" + "아" * 498

        t0 = time.perf_counter()
        clf.predict(long_input)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        assert elapsed_ms <= 100.0, f"Elapsed = {elapsed_ms:.2f}ms > 100ms"

    def test_adversarial_input(self):
        clf = MockIntentClassifier()
        # ReDoS 공격 패턴
        adversarial = "데이터 " * 200

        t0 = time.perf_counter()
        clf.predict(adversarial)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        assert elapsed_ms <= 100.0, f"Elapsed = {elapsed_ms:.2f}ms > 100ms"
