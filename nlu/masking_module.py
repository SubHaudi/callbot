"""callbot.nlu.masking_module — 마스킹/복원 모듈

LLM 서비스 전송 전 고객 개인정보를 마스킹하고, 응답 수신 후 복원한다.

Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7
"""
from __future__ import annotations

from dataclasses import dataclass, field

from callbot.nlu.models import MaskedText, RestoreResult


# ---------------------------------------------------------------------------
# CustomerInfo
# ---------------------------------------------------------------------------

@dataclass
class CustomerInfo:
    """마스킹 대상 고객 개인정보."""
    name: str | None = None           # 고객명
    phone: str | None = None          # 전화번호
    birth_date: str | None = None     # 생년월일
    address: str | None = None        # 주소
    account_number: str | None = None # 계좌번호
    card_number: str | None = None    # 카드번호


# ---------------------------------------------------------------------------
# ResponseTemplate
# ---------------------------------------------------------------------------

def ResponseTemplate(template_name: str) -> str:
    """응답 템플릿 팩토리.

    Args:
        template_name: 템플릿 이름

    Returns:
        템플릿 문자열
    """
    if template_name == "masking_fallback":
        return "죄송합니다. 잠시 후 다시 말씀해 주세요."
    return ""


# ---------------------------------------------------------------------------
# 마스킹 필드 정의
# ---------------------------------------------------------------------------

# (CustomerInfo 속성명, 마스킹 토큰, 필드명)
_MASKING_FIELDS: list[tuple[str, str, str]] = [
    ("name",           "[고객명]",  "고객명"),
    ("phone",          "[전화번호]", "전화번호"),
    ("birth_date",     "[생년월일]", "생년월일"),
    ("address",        "[주소]",    "주소"),
    ("account_number", "[계좌번호]", "계좌번호"),
    ("card_number",    "[카드번호]", "카드번호"),
]


# ---------------------------------------------------------------------------
# MaskingModule
# ---------------------------------------------------------------------------

class MaskingModule:
    """마스킹/복원 모듈.

    mask(text, customer_info) → MaskedText
    restore(masked_response, mapping) → RestoreResult

    Invariant:
    - MaskedText.token_mapping의 모든 키는 masked_text에 포함
    """

    def mask(self, text: str, customer_info: CustomerInfo) -> MaskedText:
        """개인정보를 마스킹 토큰으로 대체한다.

        마스킹 대상: 고객명, 전화번호, 생년월일, 주소, 계좌번호, 카드번호
        마스킹 제외: 요금 정보(청구금액, 납부 내역, 요금제 정보)

        Args:
            text: 원본 텍스트
            customer_info: 마스킹할 고객 개인정보

        Returns:
            MaskedText (token_mapping의 모든 키가 masked_text에 포함됨을 보장)
        """
        masked_text = text
        token_mapping: dict[str, str] = {}
        masked_fields: list[str] = []

        # 원본 텍스트에서 각 필드 값의 위치를 찾아 한 번에 치환한다.
        # 이 방식은 이미 삽입된 토큰이 다음 값 검색에 영향을 주지 않도록 보장한다.
        #
        # 알고리즘:
        # 1. 원본 텍스트에서 각 필드 값의 모든 위치를 찾는다.
        # 2. 위치 기반으로 치환 구간 목록을 만든다 (겹치는 구간 제외).
        # 3. 구간 목록을 정렬하여 앞에서부터 순서대로 치환한다.

        # (start, end, token, field_name, original_value) 목록
        replacements: list[tuple[int, int, str, str, str]] = []
        original_text = text

        for attr, token, field_name in _MASKING_FIELDS:
            value = getattr(customer_info, attr)
            if value is None or value == "":
                continue
            # M-02: list/dict 타입 방어 — str만 마스킹 대상
            if not isinstance(value, str):
                continue
            # 원본 텍스트에서 모든 비겹침 위치 탐색
            search_start = 0
            while True:
                pos = original_text.find(value, search_start)
                if pos == -1:
                    break
                end = pos + len(value)
                # 기존 치환 구간과 겹치지 않는지 확인
                overlaps = any(
                    not (end <= r_start or pos >= r_end)
                    for r_start, r_end, _, _, _ in replacements
                )
                if not overlaps:
                    replacements.append((pos, end, token, field_name, value))
                search_start = end

        # 위치 순으로 정렬하여 앞에서부터 치환
        replacements.sort(key=lambda r: r[0])

        if replacements:
            parts: list[str] = []
            prev = 0
            for start, end, token, field_name, value in replacements:
                parts.append(original_text[prev:start])
                parts.append(token)
                if token not in token_mapping:
                    token_mapping[token] = value
                    masked_fields.append(field_name)
                prev = end
            parts.append(original_text[prev:])
            masked_text = "".join(parts)

        # 불변 조건 검증: 모든 토큰 키가 masked_text에 포함되어야 함
        for token in token_mapping:
            assert token in masked_text, (
                f"Invariant violated: token '{token}' not in masked_text"
            )

        return MaskedText(
            masked_text=masked_text,
            token_mapping=token_mapping,
            masked_fields=masked_fields,
        )

    def restore(self, masked_response: str, mapping: dict[str, str]) -> RestoreResult:
        """마스킹 토큰을 원본 값으로 복원한다.

        복원 실패(토큰이 응답에 없는 경우) 시 ResponseTemplate("masking_fallback")으로 대체.

        Args:
            masked_response: LLM이 반환한 마스킹된 응답
            mapping: mask() 호출 시 반환된 token_mapping

        Returns:
            RestoreResult
        """
        if not mapping:
            return RestoreResult.success(text=masked_response)

        restored_text = masked_response
        unrestored_tokens: list[str] = []

        for token, original_value in mapping.items():
            if token in restored_text:
                restored_text = restored_text.replace(token, original_value)
            else:
                unrestored_tokens.append(token)

        if unrestored_tokens:
            return RestoreResult.failure(
                text=ResponseTemplate("masking_fallback"),
                unrestored_tokens=unrestored_tokens,
            )

        return RestoreResult.success(text=restored_text)
