"""callbot.nlu.enums — NLU 열거형 정의"""
from __future__ import annotations

from enum import Enum


class Intent(Enum):
    # Phase A 핵심 업무 의도
    BILLING_INQUIRY = "요금_조회"
    PAYMENT_CHECK = "납부_확인"
    PLAN_CHANGE = "요금제_변경"
    PLAN_INQUIRY = "요금제_조회"
    AGENT_CONNECT = "상담사_연결"
    # Phase A 보조 업무 의도
    GENERAL_INQUIRY = "일반_문의"
    COMPLAINT = "불만_접수"
    CANCELLATION = "해지_문의"
    # Phase C 추가 업무 의도
    DATA_USAGE_INQUIRY = "데이터_잔여량_조회"
    ADDON_CANCEL = "부가서비스_해지"
    # 시스템 제어 의도
    END_CALL = "통화_종료"
    SPEED_CONTROL = "속도_조절"
    REPEAT_REQUEST = "반복_요청"
    WAIT_REQUEST = "대기_요청"
    # 기타
    UNCLASSIFIED = "기타_미분류"


class ClassificationStatus(Enum):
    SUCCESS = "분류_성공"
    UNCLASSIFIED = "기타_미분류"
    FAILURE = "분류_실패"


class RelationType(Enum):
    COMPARISON = "비교"
    SEQUENTIAL = "순차"
    CONDITIONAL = "조건부"


class EntityType(Enum):
    PERIOD = "기간"
    AMOUNT = "금액"
    PLAN_NAME = "요금제명"
    SERVICE_NAME = "서비스명"


# 시스템 제어 의도 집합
SYSTEM_CONTROL_INTENTS: frozenset[Intent] = frozenset({
    Intent.END_CALL,
    Intent.SPEED_CONTROL,
    Intent.REPEAT_REQUEST,
    Intent.WAIT_REQUEST,
})

# 즉시 에스컬레이션 의도 집합
ESCALATION_INTENTS: frozenset[Intent] = frozenset({
    Intent.CANCELLATION,
    Intent.COMPLAINT,
})
