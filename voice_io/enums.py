from __future__ import annotations
"""callbot.voice_io.enums — 열거형 정의"""
from enum import Enum


class NumberType(Enum):
    AMOUNT = "금액"    # 52000 → "오만 이천"
    DATE = "날짜"      # 20240115 → "이천이십사년 일월 십오일"
    PHONE = "전화번호" # 01012345678 → "공일공 일이삼사 오육칠팔"
    ORDINAL = "서수"   # 3 → "세 번째"
