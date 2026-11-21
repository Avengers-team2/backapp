"""
공공 API 응답 값을 공통 형태로 바꾸는 도우미 함수들
(HTML 제거, 날짜 변환, 지역 추출 등)
"""

import html
import re
from datetime import date, datetime

# 시·도 약칭 ← 응답에 나올 수 있는 표기들
REGION_ALIASES: dict[str, list[str]] = {
    "서울": ["서울", "서울특별시", "서울시"],
    "부산": ["부산", "부산광역시"],
    "대구": ["대구", "대구광역시"],
    "인천": ["인천", "인천광역시"],
    "광주": ["광주", "광주광역시"],
    "대전": ["대전", "대전광역시"],
    "울산": ["울산", "울산광역시"],
    "세종": ["세종", "세종특별자치시"],
    "경기": ["경기", "경기도"],
    "강원": ["강원", "강원도", "강원특별자치도"],
    "충북": ["충북", "충청북도"],
    "충남": ["충남", "충청남도"],
    "전북": ["전북", "전라북도", "전북특별자치도"],
    "전남": ["전남", "전라남도"],
    "경북": ["경북", "경상북도"],
    "경남": ["경남", "경상남도"],
    "제주": ["제주", "제주도", "제주특별자치도"],
}
_ALIAS_TO_REGION = {alias: region for region, aliases in REGION_ALIASES.items() for alias in aliases}
_ALIAS_TO_REGION["전남광주"] = "전남"  # 기업마당 해시태그 표기 (아래 to_regions 에서 광주도 추가)
NATIONWIDE = "전국"


def split_csv(value: str | None) -> list[str]:
    """'a, b,c' → ['a', 'b', 'c']"""
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]


def strip_html(value: str | None) -> str | None:
    """HTML 태그 제거 + 엔티티(&nbsp; 등) 복원 + 공백 정리. 줄바꿈은 유지"""
    if not value:
        return None
    text = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>|</li>", "\n", value)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text).replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip() or None


def parse_date(value: str | None) -> date | None:
    """'20261123' / '2026-11-23' / '2026.11.23' → date. 형식이 다르면 None"""
    if not value:
        return None
    digits = re.sub(r"\D", "", value.strip())
    if len(digits) != 8:
        return None
    try:
        return datetime.strptime(digits, "%Y%m%d").date()
    except ValueError:
        return None


def parse_period(value: str | None) -> tuple[date | None, date | None]:
    """'2026-11-16 ~ 2026-11-18' → (시작일, 마감일). 날짜가 아니면 (None, None)"""
    if not value or "~" not in value:
        return None, None
    start, _, end = value.partition("~")
    return parse_date(start), parse_date(end)


def to_regions(*values: str | None) -> list[str]:
    """
    여러 문자열(해시태그, 기관명, 공고명 등)에서 시·도를 찾아 약칭 리스트로 반환.
    - '전국'이 있거나 시·도가 15곳 이상이면 ['전국']
    - 하나도 못 찾으면 [] (알 수 없음)
    """
    found: set[str] = set()
    for value in values:
        if not value:
            continue
        if NATIONWIDE in value:
            return [NATIONWIDE]
        for token in re.split(r"[,\s\[\]()·/]+", value):
            region = _ALIAS_TO_REGION.get(token)
            if region:
                found.add(region)
                if token == "전남광주":
                    found.add("광주")
    if len(found) >= 15:
        return [NATIONWIDE]
    order = list(REGION_ALIASES)
    return sorted(found, key=order.index)


def clip(value: str | None, length: int) -> str | None:
    """DB 컬럼 길이에 맞게 자르기"""
    if value is None:
        return None
    value = value.strip()
    return value[:length] if value else None
