"""callbot.business.enums — 비즈니스 계층 열거형 정의"""
from __future__ import annotations

from enum import Enum


class AuthType(Enum):
    BIRTHDATE = "생년월일"   # 6자리 YYMMDD
    PASSWORD = "비밀번호"    # 4자리 숫자


class AgentGroup(Enum):
    BILLING = "요금/과금 상담"
    PLAN_SERVICE = "요금제/서비스 변경 상담"
    CANCELLATION_COMPLAINT = "해지/불만 상담"
    GENERAL = "일반 상담"


class BillingOperation(Enum):
    QUERY_BILLING = "요금_조회"
    QUERY_PAYMENT = "납부_확인"
    QUERY_PLANS = "요금제_목록_조회"
    CHANGE_PLAN = "요금제_변경"
    ROLLBACK_PLAN_CHANGE = "요금제_변경_롤백"
    # Phase C 추가
    QUERY_DATA_USAGE = "데이터_잔여량_조회"
    CANCEL_ADDON = "부가서비스_해지"


class CustomerDBOperation(Enum):
    IDENTIFY = "고객_식별"
    VERIFY_AUTH = "인증_검증"
    QUERY_CUSTOMER = "고객_정보_조회"


class APIErrorType(Enum):
    TIMEOUT = "타임아웃"
    CONNECTION = "연결_실패"
    SERVER_ERROR = "서버_오류"
    CLIENT_ERROR = "클라이언트_오류"
    PARTIAL_FAILURE = "부분_장애"


class CircuitStatus(Enum):
    CLOSED = "정상"
    OPEN = "차단"
    HALF_OPEN = "시험"
