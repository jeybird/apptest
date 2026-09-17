"""
네이버 증권 랭킹 페이지 화면에 표시된 텍스트를 숫자로 변환하는 유틸리티 함수 모음.

화면 표시 예시:
    - 현재가/고가/저가/거래량 : "11,440", "8,927,607주" (콤마, 단위 문자 포함)
    - 거래대금/시가총액       : "95,664백만", "2,997억"  (억/백만 단위 축약 표기)
    - 전일대비                : "+2,640(+30.00%)", "-409(-2.94%)"

주의:
    - '조' 단위(예: "1.2조")까지는 지원하지만, "1조 2,345억"처럼 두 단위가 섞인
      표기는 이 페이지에서 쓰이지 않는다고 가정하고 별도 처리하지 않았습니다.
      만약 실제 페이지에서 그런 표기가 확인되면 parse_won_amount를 보완해야 합니다.
    - 이 함수들은 예외를 던지는 대신 파싱 실패 시 None을 반환합니다.
      (수백 건을 순회하며 저장하는 크롤러 특성상, 값 하나 파싱 실패로 전체가
       중단되지 않도록 하기 위함입니다.)
"""
import re
from typing import Optional, Tuple

# 단위 문자 -> 곱해야 할 배수. 반드시 문자열이 긴 것부터(백만이 만보다 먼저) 검사해야
# "95,664백만"이 "만" 단위로 잘못 인식되는 것을 막을 수 있습니다.
_UNIT_MULTIPLIER = {
    "백만": 1_000_000,
    "조": 1_000_000_000_000,
    "억": 100_000_000,
    "만": 10_000,
}
_UNIT_CHECK_ORDER = ("백만", "조", "억", "만")


def parse_won_amount(text: Optional[str]) -> Optional[int]:
    """
    '95,664백만', '2,997억', '11,440' 같은 문자열을 원(KRW) 단위 정수로 변환합니다.
    파싱할 수 없는 값이면 None을 반환합니다.
    """
    if text is None:
        return None
    cleaned = text.strip().replace(",", "")
    if cleaned in ("", "-", "N/A"):
        return None

    for unit in _UNIT_CHECK_ORDER:
        if cleaned.endswith(unit):
            number_part = cleaned[: -len(unit)]
            try:
                return int(round(float(number_part) * _UNIT_MULTIPLIER[unit]))
            except ValueError:
                return None

    # 단위 문자가 없으면 순수 숫자(원 단위)로 간주하고 숫자만 추출
    digits = re.sub(r"[^\d\-]", "", cleaned)
    if digits in ("", "-"):
        return None
    try:
        return int(digits)
    except ValueError:
        return None


def parse_change(text: Optional[str]) -> Tuple[Optional[int], Optional[float]]:
    """
    '+2,640(+30.00%)' / '-409(-2.94%)' 형태의 전일대비 문자열을
    (변동가: int, 등락률: float) 튜플로 변환합니다.
    상승/하락 화살표(▲▼) 같은 부가 기호는 무시합니다.
    괄호 형식이 아니면 등락률은 None으로 반환합니다.
    """
    if text is None:
        return None, None
    cleaned = text.strip()
    if cleaned in ("", "-", "N/A"):
        return None, None

    match = re.search(r"([+-]?[\d,]+(?:\.\d+)?)\s*\(\s*([+-]?[\d.]+)\s*%\s*\)", cleaned)
    if match:
        price_str, rate_str = match.groups()
        change_price = _to_int_or_none(price_str.replace(",", ""))
        change_rate = _to_float_or_none(rate_str)
        return change_price, change_rate

    # 괄호(등락률) 표기가 없는 경우, 숫자만이라도 최대한 추출
    digits = re.sub(r"[^\d\-.]", "", cleaned)
    return _to_int_or_none(digits), None


def parse_int(text: Optional[str]) -> Optional[int]:
    """'8,927,607주', '11,440' 같은 문자열에서 숫자만 추출해 int로 변환합니다."""
    if text is None:
        return None
    digits = re.sub(r"[^\d\-]", "", text)
    if digits in ("", "-"):
        return None
    return _to_int_or_none(digits)


def _to_int_or_none(value: str) -> Optional[int]:
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


def _to_float_or_none(value: str) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
