"""callbot.nlu.prompt_injection_filter — 프롬프트 인젝션 필터

STT 직후, 의도_분류기 이전에 고객 입력의 프롬프트 인젝션 패턴을 탐지한다.
P95 50ms 이내 처리를 보장하는 1차 방어 레이어.

Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7
"""
from __future__ import annotations

import logging
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field

from callbot.nlu.models import DetectionStats, FilterResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 탐지 패턴 정의
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _Pattern:
    name: str
    patterns: list[str]


# 역할 변경 시도 패턴
_ROLE_CHANGE_PATTERNS = _Pattern(
    name="역할_변경_시도",
    patterns=[
        r"당신은\s*이제\s*.+입니다",
        r"시스템\s*프롬프트를\s*무시",
        r"이전\s*지시를?\s*무시",
        r"지시를?\s*무시하고",
        r"새로운\s*역할을?\s*수행",
    ],
)

# 시스템 프롬프트 노출 요청 패턴
_PROMPT_EXPOSURE_PATTERNS = _Pattern(
    name="시스템_프롬프트_노출_요청",
    patterns=[
        r"내부\s*지시를?\s*알려",
        r"설정\s*내용을?\s*보여",
        r"시스템\s*프롬프트를?\s*출력",
        r"시스템\s*프롬프트를?\s*알려",
        r"지시사항을?\s*알려",
        r"당신의\s*지시",
    ],
)

# 범위 이탈 유도 패턴
_OUT_OF_SCOPE_PATTERNS = _Pattern(
    name="범위_이탈_유도",
    patterns=[
        r"통신\s*상담\s*말고\s*다른\s*역할",
        r"다른\s*역할을?\s*해",
        r"요리\s*레시피",
        r"주식\s*투자\s*조언",
    ],
)

# 영어 인젝션 패턴
_ENGLISH_INJECTION_PATTERNS = _Pattern(
    name="영어_인젝션_시도",
    patterns=[
        r"ignore\s+(all\s+)?(previous|prior|above)\s+(instructions?|prompts?)",
        r"disregard\s+(all\s+)?(previous|prior|above)",
        r"you\s+are\s+now\s+a",
        r"act\s+as\s+(a\s+)?\w+",
        r"pretend\s+(to\s+be|you\s+are)",
        r"reveal\s+(your|the)\s+(system\s+)?prompt",
        r"show\s+(me\s+)?(your|the)\s+(system\s+)?prompt",
        r"what\s+(are|is)\s+your\s+(instructions?|rules?|prompt)",
        r"forget\s+(all\s+)?(your\s+)?(previous\s+)?instructions?",
        r"new\s+role",
        r"jailbreak",
        r"DAN\s+mode",
    ],
)

_ALL_PATTERNS: list[_Pattern] = [
    _ROLE_CHANGE_PATTERNS,
    _PROMPT_EXPOSURE_PATTERNS,
    _OUT_OF_SCOPE_PATTERNS,
    _ENGLISH_INJECTION_PATTERNS,
]

# 컴파일된 정규식 캐시 (모듈 로드 시 1회 컴파일)
_COMPILED: list[tuple[str, list[re.Pattern[str]]]] = [
    (p.name, [re.compile(pat, re.IGNORECASE) for pat in p.patterns])
    for p in _ALL_PATTERNS
]


# ---------------------------------------------------------------------------
# 세션별 통계 저장소
# ---------------------------------------------------------------------------

@dataclass
class _SessionStats:
    detection_count: int = 0
    detected_patterns: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# PromptInjectionFilter
# ---------------------------------------------------------------------------

class PromptInjectionFilter:
    """프롬프트 인젝션 필터.

    STT 직후 고객 입력에서 프롬프트 인젝션 패턴을 탐지한다.
    정규식 + 키워드 기반으로 P95 50ms 이내 처리를 보장한다.
    """

    def __init__(self) -> None:
        self._stats: dict[str, _SessionStats] = defaultdict(_SessionStats)

    def filter(self, text: str, session_id: str) -> FilterResult:
        """프롬프트 인젝션 패턴 탐지.

        Args:
            text: STT_엔진이 반환한 텍스트
            session_id: 활성 세션 ID

        Returns:
            FilterResult(is_safe, detected_patterns, original_text, processing_time_ms)
        """
        start_ns = time.perf_counter_ns()

        detected: list[str] = []
        for pattern_name, compiled_list in _COMPILED:
            for regex in compiled_list:
                if regex.search(text):
                    if pattern_name not in detected:
                        detected.append(pattern_name)
                    break  # 해당 패턴 그룹에서 하나라도 매칭되면 다음 그룹으로

        elapsed_ms = (time.perf_counter_ns() - start_ns) // 1_000_000

        if detected:
            self._record_detection(session_id, detected, text)
            result = FilterResult.unsafe(
                detected_patterns=detected,
                original_text=text,
                processing_time_ms=elapsed_ms,
            )
        else:
            result = FilterResult.safe(
                original_text=text,
                processing_time_ms=elapsed_ms,
            )

        return result

    def get_detection_stats(self, session_id: str) -> DetectionStats:
        """세션별 탐지 통계 조회.

        Args:
            session_id: 조회할 세션 ID

        Returns:
            DetectionStats(session_id, detection_count, detected_patterns)
        """
        stats = self._stats[session_id]
        return DetectionStats(
            session_id=session_id,
            detection_count=stats.detection_count,
            detected_patterns=list(stats.detected_patterns),
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _record_detection(
        self, session_id: str, detected_patterns: list[str], original_text: str
    ) -> None:
        """탐지 기록: 세션 통계 업데이트 + 감사 로그."""
        stats = self._stats[session_id]
        stats.detection_count += 1
        stats.detected_patterns.extend(detected_patterns)

        # 감사 로그 (Requirements 1.7)
        import datetime
        logger.warning(
            "프롬프트 인젝션 탐지 | session_id=%s | patterns=%s | text=%r | timestamp=%s",
            session_id,
            detected_patterns,
            original_text,
            datetime.datetime.utcnow().isoformat(),
        )
