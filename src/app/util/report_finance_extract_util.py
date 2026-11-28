import re

from app.schema.report_ai_schema import CostItem, FinanceRaw

# 문단 분류 모델 모드에서 Gemini 대신 기획서 문단에서 재무 수치를 규칙으로 뽑는다.
# 뽑은 값은 Gemini 모드와 같은 FinanceRaw에 담아 기존 재무 검산(build_finance_checks)을 그대로 쓴다.
# 못 뽑은 칸은 None으로 남고, 검산 결과는 "근거 누락"이 된다.


# ─────────────────────────────────────────
# 금액·숫자 읽기
# ─────────────────────────────────────────
# "2억 5,000만 원", "4,250 만 원", "5 천만 원", "32,000 원" (PDF는 숫자와 단위 사이에 공백이 낄 수 있음)
NUM = r"\d{1,3}(?:,\s?\d{3})+|\d+(?:\.\d+)?"
AMOUNT_PATTERN = re.compile(
    rf"(?:(?P<eok>{NUM})\s*억\s*)?(?:(?P<num>{NUM})\s*(?P<unit>천만|백만|만|천)?\s*)?원"
)
UNIT_VALUES = {None: 1, "천": 1_000, "만": 10_000, "백만": 1_000_000, "천만": 10_000_000}


def _to_number(text: str) -> float:
    return float(text.replace(",", "").replace(" ", ""))


def find_amounts(text: str) -> list[tuple[int, int]]:
    """문단 안의 금액을 (원 단위 금액, 금액이 끝나는 위치) 목록으로 돌려준다."""
    amounts = []
    for m in AMOUNT_PATTERN.finditer(text):
        if not m.group("eok") and not m.group("num"):
            continue
        won = 0.0
        if m.group("eok"):
            won += _to_number(m.group("eok")) * 100_000_000
        if m.group("num"):
            won += _to_number(m.group("num")) * UNIT_VALUES[m.group("unit")]
        amounts.append((int(won), m.start()))
    return amounts


def amount_after(text: str, keyword_pattern: str) -> int | None:
    """키워드가 나온 뒤에 처음 나오는 금액."""
    k = re.search(keyword_pattern, text)
    if not k:
        return None
    for won, start in find_amounts(text):
        if start >= k.end():
            return won
    return None


# ─────────────────────────────────────────
# 규칙: 목차 제목 → 재무 구역
# ─────────────────────────────────────────
SECTION_RULES = [
    ("startup", r"창업\s*비용|창업\s*자금\s*소요|초기\s*투자|투자\s*비용|소요\s*자금"),
    ("funding", r"자금\s*조달|조달\s*계획"),
    ("monthly", r"운영\s*비용|운영비|고정비|월\s*비용|지출\s*계획"),
]

# 목차가 없는 기획서용: 항목 이름 키워드 → 재무 구역 ("보증금 ○○원"처럼 항목 이름과 금액이 같이 있는 문단)
ITEM_RULES = [
    ("startup", r"보증금|권리금|인테리어|시설비|설비|장비|집기|초기\s*재고|초기\s*자재|간판|가맹비"),
    ("funding", r"자기\s*자본|자부담|대출|차입|정책\s*자금|지원금|투자\s*유치"),
    ("monthly", r"임대료|월세|인건비|급여|재료비|원재료|자재비|공과금|관리비|통신비|소모품"),
]

TOTAL_PATTERN = r"^\W*(합계|총계|총액|계)\b|합\s*계"


def _section_kind(section: str) -> str | None:
    for kind, pattern in SECTION_RULES:
        if re.search(pattern, section):
            return kind
    return None


def _item_kind(text: str) -> str | None:
    for kind, pattern in ITEM_RULES:
        if re.search(pattern, text):
            return kind
    return None


def _item_name(text: str, amount_start: int) -> str:
    """금액 앞 글자를 항목 이름으로 쓴다. 앞의 목록 기호·뒤의 조사·기호는 뗀다."""
    name = text[:amount_start]
    name = re.sub(r"^[\s◾•·▪■□○●◦※\-\*\d.)]+", "", name)
    name = re.sub(r"[\s:：=\-]+$", "", name)
    name = re.sub(r"(은|는|이|가|으로|로|약)$", "", name).strip()
    return name or "항목"


# ─────────────────────────────────────────
# 문장 패턴: 매출·순이익·객단가 등
# ─────────────────────────────────────────
def _find_count(text: str, pattern: str) -> int | None:
    m = re.search(pattern, text)
    return int(_to_number(m.group(1))) if m else None


def extract_finance_values(paragraphs: list[tuple[str, str]]) -> dict:
    """[(section, 문단), ...] → FinanceRaw 필드 이름별 값 (dict)."""
    values = {
        "startup_costs": [], "startup_cost_total": None, "funding": [],
        "unit_price": None, "daily_customers": None, "operating_days": None,
        "monthly_sales": None, "material_ratio": None,
        "monthly_costs": [], "monthly_cost_total": None,
        "monthly_profit": None, "payback_months": None, "break_even_sales": None,
    }

    # 재무 목차가 하나라도 있으면 목차 기준, 없으면 항목 이름 키워드 기준
    # (목차가 있는데 키워드까지 쓰면 "마케팅 예산 80만 원"처럼 다른 목차의 금액이 두 번 더해짐)
    has_finance_section = any(_section_kind(section) for section, _ in paragraphs)

    for section, text in paragraphs:
        # 1) 문장 패턴 (목차와 관계없이)
        if values["unit_price"] is None:
            values["unit_price"] = amount_after(text, r"객단가")
        if values["daily_customers"] is None:
            values["daily_customers"] = _find_count(text, r"하루[^×x*=,.]*?(\d+)\s*(?:명|마리|건|팀|잔|개|인)")
        if values["operating_days"] is None:
            values["operating_days"] = _find_count(text, r"월\s*(\d+)\s*일")
        if values["material_ratio"] is None:
            m = re.search(r"매출(?:액)?의\s*(?:약\s*)?(\d+(?:\.\d+)?)\s*%", text)
            values["material_ratio"] = float(m.group(1)) if m else None
        if values["payback_months"] is None:
            m = re.search(r"회수[^.]*?(\d+(?:\.\d+)?)\s*개월", text)
            values["payback_months"] = float(m.group(1)) if m else None
        if values["break_even_sales"] is None:
            values["break_even_sales"] = amount_after(text, r"손익\s*분기")
        if values["monthly_sales"] is None and not re.search(r"손익\s*분기", text):
            values["monthly_sales"] = amount_after(text, r"(?:월\s*(?:예상\s*)?|예상\s*월?\s*)매출")
        if values["monthly_profit"] is None:
            values["monthly_profit"] = amount_after(text, r"순\s*이익|순\s*수익")
        if values["monthly_profit"] is None and re.search(r"남을|남는|남길|남겨", text):
            values["monthly_profit"] = amount_after(text, r"매달|매월|한\s*달|월")

        # 2) 항목·합계 (창업 비용 / 자금 조달 / 월 운영 비용)
        amounts = find_amounts(text)
        if not amounts:
            continue
        # "~다."로 끝나는 설명 문장은 표 행(항목 이름 + 금액)이 아니므로 항목으로 넣지 않는다
        is_sentence = text.rstrip().endswith(("다.", "다", "요.", "요"))
        if is_sentence:
            kind = None
        else:
            kind = _section_kind(section) if has_finance_section else _item_kind(text)
        if kind is None:
            # 목차 없는 기획서의 "창업 비용은 약 5천만 원" 같은 합계 문장
            if not has_finance_section and values["startup_cost_total"] is None and re.search(r"창업\s*비용|창업\s*자금", text):
                values["startup_cost_total"] = amounts[0][0]
            continue

        won, start = amounts[0]
        is_total = bool(re.search(TOTAL_PATTERN, text))
        if kind == "startup":
            if is_total:
                values["startup_cost_total"] = won
            else:
                values["startup_costs"].append({"name": _item_name(text, start), "amount": won})
        elif kind == "funding":
            if not is_total:
                values["funding"].append({"name": _item_name(text, start), "amount": won})
        elif kind == "monthly":
            if is_total:
                values["monthly_cost_total"] = won
            else:
                values["monthly_costs"].append({"name": _item_name(text, start), "amount": won})

    return values


def extract_finance(paragraphs: list[tuple[str, str]]) -> FinanceRaw:
    values = extract_finance_values(paragraphs)
    for key in ("startup_costs", "funding", "monthly_costs"):
        values[key] = [CostItem(**item) for item in values[key]]
    return FinanceRaw(**values)
