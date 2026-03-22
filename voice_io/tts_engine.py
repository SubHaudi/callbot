"""callbot.voice_io.tts_engine — TTS 엔진 인터페이스 및 기본 구현"""
from __future__ import annotations

from abc import ABC, abstractmethod

from callbot.voice_io.enums import NumberType
from callbot.voice_io.models import AudioStream

# ---------------------------------------------------------------------------
# 설정 상수
# ---------------------------------------------------------------------------

TTS_SPEED_MIN: float = 0.7
TTS_SPEED_MAX: float = 1.3
TTS_SPEED_DEFAULT: float = 1.0

# 한국어 숫자 변환 상수
_KO_DIGITS = ["영", "일", "이", "삼", "사", "오", "육", "칠", "팔", "구"]
_KO_PHONE_DIGITS = ["공", "일", "이", "삼", "사", "오", "육", "칠", "팔", "구"]
_KO_ORDINALS = {
    1: "첫", 2: "두", 3: "세", 4: "네", 5: "다섯",
    6: "여섯", 7: "일곱", 8: "여덟", 9: "아홉", 10: "열",
}


# ---------------------------------------------------------------------------
# 추상 기반 클래스
# ---------------------------------------------------------------------------

class TTSEngine(ABC):
    """TTS 엔진 추상 기반 클래스."""

    @abstractmethod
    def synthesize(self, text: str, session_id: str) -> AudioStream:
        """텍스트를 음성으로 변환 (P95 1초 이내 재생 시작)."""
        ...

    @abstractmethod
    def stop_playback(self, session_id: str) -> None:
        """바지인 시 즉시 재생 중단 (P95 200ms)."""
        ...

    @abstractmethod
    def set_speed(self, session_id: str, speed_factor: float) -> None:
        """말하기 속도 조절 (0.7=느리게, 1.0=기본, 1.3=빠르게)."""
        ...

    @abstractmethod
    def format_number(self, value: str, number_type: NumberType) -> str:
        """숫자를 한국어 자연어로 변환 (예: 52000 → '오만 이천')."""
        ...

    @abstractmethod
    def replay_last_response(self, session_id: str) -> AudioStream:
        """직전 응답 재생 (반복_요청 의도 처리 시 사용)."""
        ...


# ---------------------------------------------------------------------------
# 기본 구현체 (벤더 SDK 없이 동작, 테스트용)
# ---------------------------------------------------------------------------

class TTSEngineBase(TTSEngine):
    """벤더 SDK 없이 동작하는 TTS 엔진 기본 구현체.

    실제 음성 합성은 수행하지 않으며, 테스트 및 개발 환경에서 사용한다.
    """

    def __init__(self) -> None:
        # 세션별 속도 팩터 상태 관리
        self._session_speeds: dict[str, float] = {}
        # 세션별 마지막 응답 캐시
        self._last_response: dict[str, str] = {}

    def synthesize(self, text: str, session_id: str) -> AudioStream:
        """텍스트를 AudioStream으로 변환하고 _last_response에 캐시한다."""
        self._last_response[session_id] = text
        return AudioStream(session_id=session_id)

    def stop_playback(self, session_id: str) -> None:
        """재생 중단 — 기본 구현은 no-op."""
        pass

    def speech_start(self, session_id: str) -> None:
        """사용자 발화 시작 감지 콜백 — 기본 구현은 no-op."""
        pass

    def speech_end(self, session_id: str) -> None:
        """사용자 발화 종료 감지 콜백 — 기본 구현은 no-op."""
        pass

    def set_speed(self, session_id: str, speed_factor: float) -> None:
        """세션별 속도 팩터를 설정한다. speed_factor ∈ [0.7, 1.3] 범위 검증."""
        if not (TTS_SPEED_MIN <= speed_factor <= TTS_SPEED_MAX):
            raise ValueError(
                f"speed_factor must be in [{TTS_SPEED_MIN}, {TTS_SPEED_MAX}], "
                f"got {speed_factor}"
            )
        self._session_speeds[session_id] = speed_factor

    def format_number(self, value: str, number_type: NumberType) -> str:
        """숫자를 한국어 자연어 형태로 변환한다."""
        if number_type == NumberType.AMOUNT:
            return format_amount(value)
        elif number_type == NumberType.DATE:
            return format_date(value)
        elif number_type == NumberType.PHONE:
            return format_phone(value)
        elif number_type == NumberType.ORDINAL:
            return format_ordinal(value)
        raise ValueError(f"Unknown NumberType: {number_type}")

    def replay_last_response(self, session_id: str) -> AudioStream:
        """직전 synthesize() 응답을 동일한 속도 설정으로 재생한다."""
        text = self._last_response[session_id]  # KeyError if no prior synthesize
        return self.synthesize(text, session_id)


# ---------------------------------------------------------------------------
# 한국어 숫자 변환 헬퍼 함수
# ---------------------------------------------------------------------------

def korean_number(n: int) -> str:
    """정수를 한국어 숫자 읽기로 변환한다 (만, 억 단위 포함).

    한국어 관습: 십/백/천 앞의 '일'은 생략 (예: 1000 → 천, 10 → 십)
    만/억 앞의 '일'은 생략 (예: 10000 → 만, 100000000 → 억)
    """
    if n == 0:
        return "영"

    units = [
        (100_000_000, "억"),
        (10_000, "만"),
        (1_000, "천"),
        (100, "백"),
        (10, "십"),
    ]

    result = ""
    for unit_val, unit_name in units:
        if n >= unit_val:
            digit = n // unit_val
            n %= unit_val
            # 한국어 관습: 모든 단위 앞 '일'은 생략 (일십→십, 일백→백, 일천→천, 일만→만, 일억→억)
            if digit == 1:
                result += unit_name
            else:
                result += _KO_DIGITS[digit] + unit_name
    if n > 0:
        result += _KO_DIGITS[n]

    return result


def format_amount(value: str) -> str:
    """금액 숫자를 한국어로 변환. 예: '52000' → '오만 이천'"""
    n = int(value)
    if n == 0:
        return "영"

    # 억 단위
    eok = n // 100_000_000
    n %= 100_000_000
    # 만 단위
    man = n // 10_000
    n %= 10_000
    # 천 이하
    rest = n

    parts = []
    if eok:
        eok_str = "" if eok == 1 else korean_number(eok)
        parts.append(eok_str + "억")
    if man:
        man_str = "" if man == 1 else korean_number(man)
        parts.append(man_str + "만")
    if rest:
        parts.append(korean_number(rest))

    return " ".join(parts)


def format_date(value: str) -> str:
    """날짜 숫자(YYYYMMDD)를 한국어로 변환. 예: '20240115' → '이천이십사년 일월 십오일'"""
    year = int(value[:4])
    month = int(value[4:6])
    day = int(value[6:8])

    year_str = korean_number(year) + "년"
    month_str = korean_number(month) + "월"
    day_str = korean_number(day) + "일"

    return f"{year_str} {month_str} {day_str}"


def format_phone(value: str) -> str:
    """전화번호를 한국어 숫자 읽기로 변환. 예: '01012345678' → '공일공 일이삼사 오육칠팔'"""
    # 각 자리를 한국어로 변환 (0 → 공)
    digits_ko = "".join(_KO_PHONE_DIGITS[int(c)] for c in value)

    # 전화번호 그룹 분리 규칙
    length = len(value)
    if length == 11:
        # 010-XXXX-XXXX 형식
        groups = [digits_ko[:3], digits_ko[3:7], digits_ko[7:]]
    elif length == 10:
        # 02X-XXXX-XXXX 또는 0XX-XXX-XXXX
        if value.startswith("02"):
            groups = [digits_ko[:2], digits_ko[2:6], digits_ko[6:]]
        else:
            groups = [digits_ko[:3], digits_ko[3:6], digits_ko[6:]]
    elif length == 9:
        # 02-XXXX-XXXX
        groups = [digits_ko[:2], digits_ko[2:6], digits_ko[6:]]
    else:
        # 그룹 분리 없이 전체 반환
        return digits_ko

    return " ".join(groups)


def format_ordinal(value: str) -> str:
    """서수를 한국어로 변환. 예: '3' → '세 번째'"""
    n = int(value)
    if n in _KO_ORDINALS:
        return f"{_KO_ORDINALS[n]} 번째"
    # 10 초과는 일반 숫자 + 번째
    return f"{korean_number(n)} 번째"


# ---------------------------------------------------------------------------
# 하위 호환 alias — 기존 `_` prefix 이름을 유지
# ---------------------------------------------------------------------------
_korean_number = korean_number
_format_amount = format_amount
_format_date = format_date
_format_phone = format_phone
_format_ordinal = format_ordinal
