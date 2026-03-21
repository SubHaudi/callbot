"""callbot.nlu.patterns — 인텐트별 정규식 패턴 정의 (Phase E)

구어체, 줄임말, 조사 변형을 포함한 정규식 기반 인텐트 매칭 패턴.
MockIntentClassifier._match_primary_intent()에서 사용.
"""
from __future__ import annotations

import re
from typing import List, Tuple

from callbot.nlu.enums import Intent

# 패턴 우선순위: 더 구체적인 패턴이 앞에 위치
# 각 항목: (컴파일된 정규식 리스트, 매핑 인텐트)
_PATTERN_RULES: List[Tuple[List[re.Pattern], Intent]] = [
    # 요금제 변경 (PLAN_CHANGE) — "변경" 키워드 필수
    ([
        re.compile(r"요금제.*(?:변경|바꿔|바꾸|바꿀|변경해|갈아타)"),
        re.compile(r"(?:플랜|요금제).*(?:바꿔|바꾸|바꿀|변경)"),
        re.compile(r"다른\s*요금제"),
        re.compile(r"요금제\s*바꿀래"),
        re.compile(r"요금제\s*변경"),
    ], Intent.PLAN_CHANGE),

    # 요금제 조회 (PLAN_INQUIRY)
    ([
        re.compile(r"요금제.*(?:조회|알려|뭐|어떤|종류|목록|보여)"),
        re.compile(r"(?:무슨|어떤)\s*요금제"),
        re.compile(r"요금제\s*(?:뭐|뭘|뭔)"),
        re.compile(r"요금제\s*(?:있|좀)"),
    ], Intent.PLAN_INQUIRY),

    # 요금 조회 (BILLING_INQUIRY)
    ([
        re.compile(r"요금.*(?:조회|알려|얼마|확인|보여)"),
        re.compile(r"(?:이번|지난|저번)\s*달?\s*요금"),
        re.compile(r"(?:그거|이거)\s*얼마"),
        re.compile(r"요금\s*(?:좀|나온|나와)"),
        re.compile(r"(?:얼마|돈|비용).*(?:나와|나온|내야|냈)"),
        re.compile(r"청구.*(?:금액|내역|얼마)"),
    ], Intent.BILLING_INQUIRY),

    # 납부 확인 (PAYMENT_CHECK)
    ([
        re.compile(r"납부.*(?:확인|했|됐|완료|언제)"),
        re.compile(r"(?:돈|요금).*(?:냈|납부|입금)"),
        re.compile(r"(?:결제|납부)\s*(?:했|됐|완료)"),
        re.compile(r"납부\s*(?:좀|확인)"),
    ], Intent.PAYMENT_CHECK),

    # 데이터 잔여량 조회 (DATA_USAGE_INQUIRY)
    ([
        re.compile(r"데이터.*(?:잔여|남은|남아|얼마나|확인)"),
        re.compile(r"(?:남은|잔여)\s*데이터"),
        re.compile(r"데이터\s*(?:좀|얼마)"),
        re.compile(r"(?:기가|GB|gb).*(?:남|얼마)"),
    ], Intent.DATA_USAGE_INQUIRY),

    # 부가서비스 해지 (ADDON_CANCEL)
    ([
        re.compile(r"부가.*(?:해지|취소|빼|없애|끊)"),
        re.compile(r"(?:부가|서비스).*(?:빼줘|없애줘|끊어줘)"),
        re.compile(r"부가\s*(?:좀|서비스)\s*(?:해지|빼)"),
    ], Intent.ADDON_CANCEL),

    # 상담사 연결 (AGENT_CONNECT)
    ([
        re.compile(r"상담사|상담원|사람"),
        re.compile(r"(?:직원|담당자).*(?:연결|바꿔|통화)"),
        re.compile(r"사람.*(?:연결|바꿔|좀)"),
    ], Intent.AGENT_CONNECT),

    # 불만 접수 (COMPLAINT)
    ([
        re.compile(r"불만|불편|화[가나]|짜증"),
        re.compile(r"(?:항의|컴플레인|민원)"),
    ], Intent.COMPLAINT),

    # 해지 문의 (CANCELLATION)
    ([
        re.compile(r"해지(?!.*부가)"),  # "부가" 없는 해지
        re.compile(r"(?:탈퇴|끊을|끊고)"),
    ], Intent.CANCELLATION),

    # 통화 종료 (END_CALL)
    ([
        re.compile(r"종료|끊어|끊을게|끊겠|그만"),
        re.compile(r"(?:됐어|다\s*했어|끝)"),
    ], Intent.END_CALL),

    # 속도 조절 (SPEED_CONTROL)
    ([
        re.compile(r"(?:빠르|느리|속도)"),
        re.compile(r"(?:천천히|빨리)\s*(?:말|해)"),
    ], Intent.SPEED_CONTROL),

    # 반복 요청 (REPEAT_REQUEST)
    ([
        re.compile(r"(?:다시|반복|뭐라고|못\s*들)"),
    ], Intent.REPEAT_REQUEST),

    # 대기 요청 (WAIT_REQUEST)
    ([
        re.compile(r"(?:잠깐|잠시|대기|기다려)"),
    ], Intent.WAIT_REQUEST),
]
