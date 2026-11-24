from app.schema.report_ai_schema import (
    CostItem,
    FinanceCheck,
    FinanceRaw,
    ItemGrade,
    ItemReview,
    Suggestion,
)

# ─────────────────────────────────────────
# 설정값
# ─────────────────────────────────────────

# 1. 일치로 볼 허용 오차 (원문은 "약 670만 원"처럼 반올림이 많음)
TOLERANCE_RATE = 0.01    # 1% 이내면 일치

# . 항목별 배점 (예시 PDF 기준 가안, 합계 100)
ITEM_WEIGHTS = {
    "item_differentiation": 20,
    "market_customer": 20,
    "business_model_profit": 20,
    "marketing": 15,
    "operation_plan": 15,
    "risk_management": 10,
}



def sum_items(items: list[CostItem]) -> int | None:
    total = 0
    found = False          # 금액이 하나라도 있었는지

    for item in items:
        if item.amount is None:
            continue       # 금액 없는 항목은 건너뜀
        total += item.amount
        found = True

    return total if found else None


def to_manwon(won: int | float) -> str:
    man = won / 10000

    if man.is_integer():
        return f"{int(man):,}만 원"
    else:
        return f"{man:,.1f}만 원"
    

def is_match(original: float, calculated: float) -> bool:
    if original == 0:
        return original == calculated

    diff = abs(original - calculated) / original
    return diff <= TOLERANCE_RATE


def check_startup_total(f: FinanceRaw) -> FinanceCheck:
    label = "창업 비용 합계"
    calc = sum_items(f.startup_costs)
    original = f.startup_cost_total

    # 계산할 값이나 원문 합계가 없으면 근거 누락
    if calc is None or original is None:
        return FinanceCheck(
            label=label,
            original=to_manwon(original) if original is not None else None,
            formula=None,
            result="근거 누락",
        )

    # 계산식: "3,000만 원 + 2,500만 원 + ... = 7,000만 원"
    parts = [to_manwon(item.amount) for item in f.startup_costs if item.amount is not None]
    formula = " + ".join(parts) + f" = {to_manwon(calc)}"

    result = "일치" if is_match(original, calc) else "불일치"

    return FinanceCheck(
        label=label,
        original=to_manwon(original),
        formula=formula,
        result=result,
    )


def check_funding(f: FinanceRaw) -> FinanceCheck:
    label = "자금 조달"

    fund = sum_items(f.funding) 
    cost = sum_items(f.startup_costs)

    if fund is None or cost is None:
        return FinanceCheck(label=label, original=None, formula=None, result="근거 누락")
    
    parts = [to_manwon(item.amount) for item in f.funding if item.amount is not None]
    original = " + ".join(parts)

    # 계산식: "4,500만 원 + 3,000만 원 = 7,500만 원"
    formula = original + f" = {to_manwon(fund)}"

    # 모은 돈이 쓸 돈보다 많은지/적은지 설명 붙이기
    gap = fund - cost
    if gap > 0:
        formula += f" (비용 합계보다 {to_manwon(gap)} 많음)"
    elif gap < 0:
        formula += f" (비용 합계보다 {to_manwon(-gap)} 부족)"

    # 쓸 돈 기준으로 모은 돈이 맞는지 판정
    result = "일치" if is_match(cost, fund) else "불일치"

    return FinanceCheck(label=label, original=original, formula=formula, result=result)


def check_sales(f: FinanceRaw) -> FinanceCheck:
    label = "예상 매출"

    price = f.unit_price
    customers = f.daily_customers
    days = f.operating_days
    original = f.monthly_sales

    if price is None or customers is None or days is None or original is None: 
        display = to_manwon(original) if (original != None) else None

        return FinanceCheck(label=label, original=display, formula=None, result="근거 누락")

    calc = price * customers * days 
    formula = f"{price:,}원 x {customers}명 x {days}일 = {calc:,}원"

    if is_match(original, calc) == True:
        result = "일치"
    else:
        result = "불일치"

    return FinanceCheck(label=label, original=to_manwon(original), formula=formula, result=result)


def check_monthly_cost(f: FinanceRaw) -> FinanceCheck:
    label = "운영 비용"

    calc = sum_items(f.monthly_costs)
    original = f.monthly_cost_total

    if calc is None or original is None:
        display = to_manwon(original) if original is not None else None
        return FinanceCheck(label=label, original=display, formula=None, result="근거 누락")

    parts = [to_manwon(item.amount) for item in f.monthly_costs if item.amount is not None]
    formula = " + ".join(parts) + f" = {to_manwon(calc)}"

    if is_match(original, calc) == True:
        result = "일치"
    else:
        result = "불일치"

    return FinanceCheck(label=label, original=to_manwon(original), formula=formula, result=result)


def check_profit(f: FinanceRaw) -> FinanceCheck:
    label = "월 순이익"

    sales = f.monthly_sales
    cost = f.monthly_cost_total
    original = f.monthly_profit

    if sales is None or cost is None or original is None:
        display = to_manwon(original) if original is not None else None
        return FinanceCheck(label=label, original=display, formula=None, result="근거 누락")

    calc = sales - cost
    formula = to_manwon(sales) + " - " + to_manwon(cost) + " = " + to_manwon(calc)

    if is_match(original, calc) == True:
        result = "일치"
    else:
        result = "불일치"

    return FinanceCheck(label=label, original=to_manwon(original), formula=formula, result=result)


def check_payback(f: FinanceRaw) -> FinanceCheck:
    label = "투자금 회수 기간"

    cost = sum_items(f.startup_costs)
    if cost is None:
        cost = f.startup_cost_total

    if f.monthly_sales is not None and f.monthly_cost_total is not None:
        profit = f.monthly_sales - f.monthly_cost_total
    else:
        profit = f.monthly_profit

    original = f.payback_months
    if cost is None or profit is None or original is None:
        display = f"약 {original}개월" if original is not None else None
        return FinanceCheck(label=label, original=display, formula=None, result="근거 누락")
    if profit <= 0:
        display = f"약 {original}개월" if original is not None else None
        return FinanceCheck(label=label, original=display, formula=None, result="근거 누락")

    calc = round(cost / profit, 1)
    formula = f"{to_manwon(cost)} ÷ {to_manwon(profit)} = 약 {calc}개월"

    if is_match(original, calc) == True:
        result = "일치"
    else:
        result = "불일치"

    return FinanceCheck(label=label, original=f"약 {original}개월", formula=formula, result=result)


def check_break_even(f: FinanceRaw) -> FinanceCheck:
    return FinanceCheck(label="손익분기점", original=None, formula=None, result="근거 누락")


def build_finance_checks(f: FinanceRaw) -> list[FinanceCheck]:
    checks = []

    checks.append(check_startup_total(f))
    checks.append(check_funding(f))
    checks.append(check_sales(f))
    checks.append(check_monthly_cost(f))
    checks.append(check_profit(f))
    checks.append(check_payback(f))
    checks.append(check_break_even(f))

    return checks


def score_to_grade(score: int) -> str:
    if score >= 4:
        return "우수"
    elif score == 3:
        return "보통"
    elif score == 2:
        return "미흡"
    else:
        return "매우 미흡"


def build_grades(items: list[ItemReview]) -> list[ItemGrade]:
    grades = []

    for item in items:
        grade = score_to_grade(item.score)
        grades.append(ItemGrade(item_key=item.item_key, grade=grade))

    return grades


def calc_total_score(items: list[ItemReview]) -> int:
    total = 0

    for item in items:
        weight = ITEM_WEIGHTS[item.item_key]
        total += (weight * item.score / 5)

    return round(total)


# 재무 검산 결과를 개선 제안으로 바꾸기
# LLM은 계산을 안 하니까 수치 오류를 모름 → 백엔드가 직접 제안을 만들어 앞에 붙인다
def build_finance_suggestions(checks: list[FinanceCheck]) -> list[Suggestion]:
    suggestions = []

    for check in checks:
        # 원문 수치가 계산과 다르면 신뢰도에 직접 영향 → 높음
        if check.result == "불일치":
            suggestions.append(Suggestion(
                priority="높음",
                problem=f"{check.label} 수치 오류 (원문: {check.original})",
                action=f"검산 결과({check.formula})와 맞지 않습니다. 원문 수치를 다시 계산해 고치거나, 빠진 항목을 표에 추가해 맞추세요.",
            ))
        # 손익분기점은 원문에 없으면 항상 근거 누락 → 보통
        elif check.label == "손익분기점" and check.result == "근거 누락":
            suggestions.append(Suggestion(
                priority="보통",
                problem="손익분기점 미제시",
                action="고정비와 재료비 비율로 손익분기 월 매출과 하루에 필요한 고객 수를 계산해 넣으세요.",
            ))

    return suggestions
