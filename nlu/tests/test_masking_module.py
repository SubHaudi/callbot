"""callbot.nlu.tests.test_masking_module — 마스킹/복원 모듈 테스트

Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7
"""
from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from callbot.nlu.masking_module import CustomerInfo, MaskingModule, ResponseTemplate
from callbot.nlu.models import MaskedText, RestoreResult


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

st_nonempty_text = st.text(min_size=1, max_size=50).filter(lambda s: s.strip())
st_optional_text = st.one_of(st.none(), st_nonempty_text)

# 마스킹 토큰 형식([...])을 포함하지 않는 텍스트 전략 (라운드트립 테스트용)
_TOKEN_PATTERN = "[고객명][전화번호][생년월일][주소][계좌번호][카드번호]"
st_safe_field_value = st.text(min_size=1, max_size=30).filter(
    lambda s: s.strip() and not any(tok in s for tok in ["[고객명]", "[전화번호]", "[생년월일]", "[주소]", "[계좌번호]", "[카드번호]"])
)
st_optional_safe_value = st.one_of(st.none(), st_safe_field_value)


def st_customer_info() -> st.SearchStrategy[CustomerInfo]:
    return st.builds(
        CustomerInfo,
        name=st_optional_text,
        phone=st_optional_text,
        birth_date=st_optional_text,
        address=st_optional_text,
        account_number=st_optional_text,
        card_number=st_optional_text,
    )


def st_customer_info_safe() -> st.SearchStrategy[CustomerInfo]:
    """마스킹 토큰 형식을 포함하지 않는 CustomerInfo 전략 (라운드트립 테스트용)."""
    return st.builds(
        CustomerInfo,
        name=st_optional_safe_value,
        phone=st_optional_safe_value,
        birth_date=st_optional_safe_value,
        address=st_optional_safe_value,
        account_number=st_optional_safe_value,
        card_number=st_optional_safe_value,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def module() -> MaskingModule:
    return MaskingModule()


# ---------------------------------------------------------------------------
# 5.3 마스킹 대상/제외 필드 단위 테스트
# Validates: Requirements 3.1, 3.2
# ---------------------------------------------------------------------------

def test_mask_replaces_customer_name(module: MaskingModule):
    """고객명이 마스킹 토큰으로 대체된다. Validates: Requirements 3.1"""
    info = CustomerInfo(name="홍길동")
    result = module.mask("안녕하세요 홍길동 고객님", info)
    assert "홍길동" not in result.masked_text
    assert "[고객명]" in result.masked_text
    assert "고객명" in result.masked_fields


def test_mask_replaces_phone(module: MaskingModule):
    """전화번호가 마스킹 토큰으로 대체된다. Validates: Requirements 3.1"""
    info = CustomerInfo(phone="010-1234-5678")
    result = module.mask("전화번호는 010-1234-5678입니다", info)
    assert "010-1234-5678" not in result.masked_text
    assert "[전화번호]" in result.masked_text
    assert "전화번호" in result.masked_fields


def test_mask_replaces_birth_date(module: MaskingModule):
    """생년월일이 마스킹 토큰으로 대체된다. Validates: Requirements 3.1"""
    info = CustomerInfo(birth_date="1990-01-15")
    result = module.mask("생년월일은 1990-01-15입니다", info)
    assert "1990-01-15" not in result.masked_text
    assert "[생년월일]" in result.masked_text
    assert "생년월일" in result.masked_fields


def test_mask_replaces_address(module: MaskingModule):
    """주소가 마스킹 토큰으로 대체된다. Validates: Requirements 3.1"""
    info = CustomerInfo(address="서울시 강남구")
    result = module.mask("주소는 서울시 강남구입니다", info)
    assert "서울시 강남구" not in result.masked_text
    assert "[주소]" in result.masked_text
    assert "주소" in result.masked_fields


def test_mask_replaces_account_number(module: MaskingModule):
    """계좌번호가 마스킹 토큰으로 대체된다. Validates: Requirements 3.1"""
    info = CustomerInfo(account_number="123-456-789012")
    result = module.mask("계좌번호는 123-456-789012입니다", info)
    assert "123-456-789012" not in result.masked_text
    assert "[계좌번호]" in result.masked_text
    assert "계좌번호" in result.masked_fields


def test_mask_replaces_card_number(module: MaskingModule):
    """카드번호가 마스킹 토큰으로 대체된다. Validates: Requirements 3.1"""
    info = CustomerInfo(card_number="1234-5678-9012-3456")
    result = module.mask("카드번호는 1234-5678-9012-3456입니다", info)
    assert "1234-5678-9012-3456" not in result.masked_text
    assert "[카드번호]" in result.masked_text
    assert "카드번호" in result.masked_fields


def test_mask_excludes_billing_amount(module: MaskingModule):
    """요금 정보(청구금액)는 마스킹하지 않는다. Validates: Requirements 3.2"""
    info = CustomerInfo(name="홍길동")
    text = "홍길동 고객님의 청구금액은 55,000원입니다"
    result = module.mask(text, info)
    assert "55,000원" in result.masked_text
    assert "청구금액" not in result.masked_fields


def test_mask_excludes_payment_history(module: MaskingModule):
    """납부 내역은 마스킹하지 않는다. Validates: Requirements 3.2"""
    info = CustomerInfo(name="홍길동")
    text = "홍길동 고객님의 납부 내역: 2024년 1월 50,000원"
    result = module.mask(text, info)
    assert "50,000원" in result.masked_text


def test_mask_no_fields_when_customer_info_empty(module: MaskingModule):
    """CustomerInfo가 모두 None이면 마스킹 없이 원본 텍스트 반환. Validates: Requirements 3.1"""
    info = CustomerInfo()
    text = "이번 달 요금이 얼마예요?"
    result = module.mask(text, info)
    assert result.masked_text == text
    assert result.token_mapping == {}
    assert result.masked_fields == []


def test_mask_multiple_fields(module: MaskingModule):
    """여러 필드가 동시에 마스킹된다. Validates: Requirements 3.1"""
    info = CustomerInfo(name="홍길동", phone="010-1234-5678")
    text = "홍길동 고객님 전화번호 010-1234-5678"
    result = module.mask(text, info)
    assert "홍길동" not in result.masked_text
    assert "010-1234-5678" not in result.masked_text
    assert "[고객명]" in result.masked_text
    assert "[전화번호]" in result.masked_text
    assert len(result.masked_fields) == 2


def test_mask_returns_masked_text_type(module: MaskingModule):
    """mask()는 MaskedText를 반환한다. Validates: Requirements 3.1"""
    info = CustomerInfo(name="홍길동")
    result = module.mask("홍길동 고객님", info)
    assert isinstance(result, MaskedText)


# ---------------------------------------------------------------------------
# 5.4 복원 실패 처리 단위 테스트
# Validates: Requirements 3.3, 3.4, 3.5
# ---------------------------------------------------------------------------

def test_restore_success_when_all_tokens_present(module: MaskingModule):
    """모든 토큰이 응답에 포함되면 복원 성공. Validates: Requirements 3.3, 3.4"""
    mapping = {"[고객명]": "홍길동"}
    result = module.restore("[고객명] 고객님 안녕하세요", mapping)
    assert result.is_success is True
    assert result.text == "홍길동 고객님 안녕하세요"
    assert result.unrestored_tokens == []


def test_restore_replaces_all_tokens(module: MaskingModule):
    """여러 토큰이 모두 복원된다. Validates: Requirements 3.3"""
    mapping = {"[고객명]": "홍길동", "[전화번호]": "010-1234-5678"}
    result = module.restore("[고객명] 고객님의 전화번호는 [전화번호]입니다", mapping)
    assert result.is_success is True
    assert "홍길동" in result.text
    assert "010-1234-5678" in result.text
    assert "[고객명]" not in result.text
    assert "[전화번호]" not in result.text


def test_restore_failure_when_token_missing_from_response(module: MaskingModule):
    """응답에 토큰이 없으면 복원 실패. Validates: Requirements 3.5"""
    mapping = {"[고객명]": "홍길동"}
    # LLM이 토큰을 제거한 경우 — 응답에 [고객명]이 없음
    result = module.restore("고객님 안녕하세요", mapping)
    assert result.is_success is False
    assert "[고객명]" in result.unrestored_tokens


def test_restore_failure_returns_fallback_text(module: MaskingModule):
    """복원 실패 시 ResponseTemplate("masking_fallback") 텍스트 반환. Validates: Requirements 3.5"""
    mapping = {"[고객명]": "홍길동"}
    result = module.restore("고객님 안녕하세요", mapping)
    assert result.is_success is False
    assert result.text == ResponseTemplate("masking_fallback")


def test_restore_returns_restore_result_type(module: MaskingModule):
    """restore()는 RestoreResult를 반환한다. Validates: Requirements 3.3"""
    result = module.restore("안녕하세요", {})
    assert isinstance(result, RestoreResult)


def test_restore_empty_mapping_is_success(module: MaskingModule):
    """빈 매핑으로 복원 시 성공 반환. Validates: Requirements 3.4"""
    result = module.restore("이번 달 요금은 55,000원입니다", {})
    assert result.is_success is True
    assert result.text == "이번 달 요금은 55,000원입니다"


def test_restore_partial_failure_tracks_unrestored_tokens(module: MaskingModule):
    """일부 토큰만 복원 실패 시 해당 토큰이 unrestored_tokens에 포함. Validates: Requirements 3.5"""
    mapping = {"[고객명]": "홍길동", "[전화번호]": "010-1234-5678"}
    # [전화번호]만 응답에 없음
    result = module.restore("[고객명] 고객님 안녕하세요", mapping)
    assert result.is_success is False
    assert "[전화번호]" in result.unrestored_tokens


# ---------------------------------------------------------------------------
# 5.1 MaskedText 토큰 포함 속성 테스트 (Property 5)
# Validates: Requirements 3.1, 3.6
# ---------------------------------------------------------------------------

@given(
    base_text=st.text(min_size=0, max_size=100),
    customer_info=st_customer_info(),
)
@settings(max_examples=100)
def test_property5_all_token_keys_in_masked_text(base_text: str, customer_info: CustomerInfo):
    """Property 5: MaskedText.token_mapping의 모든 키가 masked_text에 포함된다.
    Validates: Requirements 3.1, 3.6
    """
    module = MaskingModule()

    # 텍스트에 customer_info 값들을 삽입하여 마스킹이 실제로 일어나도록 함
    text = base_text
    if customer_info.name:
        text = customer_info.name + " " + text
    if customer_info.phone:
        text = text + " " + customer_info.phone
    if customer_info.birth_date:
        text = text + " " + customer_info.birth_date

    result = module.mask(text, customer_info)

    # 불변 조건: token_mapping의 모든 키가 masked_text에 포함
    for token in result.token_mapping:
        assert token in result.masked_text, (
            f"Token '{token}' not found in masked_text: '{result.masked_text}'"
        )


# ---------------------------------------------------------------------------
# 5.2 마스킹-복원 라운드트립 속성 테스트 (Property 7)
# Validates: Requirements 3.1, 3.2, 3.3
# ---------------------------------------------------------------------------

@given(
    base_text=st.text(min_size=0, max_size=100),
    customer_info=st_customer_info_safe(),
)
@settings(max_examples=100)
def test_property7_mask_restore_roundtrip(base_text: str, customer_info: CustomerInfo):
    """Property 7: mask → restore 후 원본 텍스트와 동일하다.
    Validates: Requirements 3.1, 3.2, 3.3
    """
    module = MaskingModule()

    # 텍스트에 customer_info 값들을 삽입
    text = base_text
    if customer_info.name:
        text = customer_info.name + " " + text
    if customer_info.phone:
        text = text + " " + customer_info.phone
    if customer_info.birth_date:
        text = text + " " + customer_info.birth_date
    if customer_info.address:
        text = text + " " + customer_info.address
    if customer_info.account_number:
        text = text + " " + customer_info.account_number
    if customer_info.card_number:
        text = text + " " + customer_info.card_number

    masked = module.mask(text, customer_info)
    restored = module.restore(masked.masked_text, masked.token_mapping)

    assert restored.is_success is True
    assert restored.text == text


# ---------------------------------------------------------------------------
# ResponseTemplate 테스트
# ---------------------------------------------------------------------------

def test_response_template_masking_fallback():
    """ResponseTemplate("masking_fallback")은 fallback 문자열을 반환한다."""
    text = ResponseTemplate("masking_fallback")
    assert isinstance(text, str)
    assert len(text) > 0


# ---------------------------------------------------------------------------
# M-02: list/dict 필드 방어 테스트
# ---------------------------------------------------------------------------

def test_mask_handles_non_string_field_gracefully(module: MaskingModule):
    """M-02: CustomerInfo 필드에 비문자열 값이 들어와도 에러 없이 무시한다."""
    info = CustomerInfo(name="홍길동", phone=["010", "1234", "5678"])  # type: ignore[arg-type]
    result = module.mask("전화번호는 01012345678입니다", info)
    # phone은 list라서 마스킹 안 됨, name은 마스킹됨
    assert "[전화번호]" not in result.masked_text
    # name이 텍스트에 없으므로 마스킹 안 됨 (홍길동이 텍스트에 없음)
    assert result.masked_text == "전화번호는 01012345678입니다"


def test_mask_handles_dict_field_gracefully(module: MaskingModule):
    """M-02: dict 필드도 에러 없이 무시한다."""
    info = CustomerInfo(name={"first": "길동", "last": "홍"})  # type: ignore[arg-type]
    result = module.mask("홍길동 고객님", info)
    assert result.masked_text == "홍길동 고객님"
