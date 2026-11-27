# 검토 점수·등급 기준 (상아·희수 합의, 2026-11-25)
# - 항목 점수: Gemini 평가 1~5단계 × 20 (20~100점)
# - 항목 등급: report_finance_util.score_to_grade (4·5 우수 / 3 보통 / 2 미흡 / 1 매우 미흡)
# - 종합 점수: report_finance_util.calc_total_score (가중치 20·20·20·15·15·10, 100점)
# - 종합 등급: 80↑ 우수 / 60~79 보통 / 40~59 미흡 / 40↓ 매우 미흡
# - 보완 필요: 등급 "미흡" 이하 (점수 60 미만)
# - 재무 검산 "불일치"가 1건이라도 있으면 "사업 모델 및 수익성"은 최대 3단계(보통)

from app.schema.report_ai_schema import ReportAiResult
from app.util.report_finance_util import build_grades, calc_total_score

FINANCE_CAP_ITEM = "business_model_profit"   # 재무 불일치 시 상한을 거는 항목
FINANCE_CAP_LEVEL = 3                          # 최대 3단계 (보통)
WEAK_SCORE = 60                                # 이 점수 미만이면 보완 필요 (미흡 이하)


# 1~5단계 → 100점 환산
def item_score(level: int) -> int:
    return level * 20


# 종합 점수 → 종합 등급
def total_grade(score: int | None) -> str | None:
    if score is None:
        return None
    if score >= 80:
        return "우수"
    if score >= 60:
        return "보통"
    if score >= 40:
        return "미흡"
    return "매우 미흡"


# 재무 검산 "불일치"가 있으면 수익성 항목을 최대 3단계로 낮추고, 등급·종합 점수를 다시 계산
def apply_finance_cap(result: ReportAiResult) -> ReportAiResult:
    has_mismatch = any(check.result == "불일치" for check in result.finance_checks)
    if not has_mismatch or not result.llm.items:
        return result

    changed = False
    for item in result.llm.items:
        if item.item_key == FINANCE_CAP_ITEM and item.score > FINANCE_CAP_LEVEL:
            item.score = FINANCE_CAP_LEVEL
            changed = True

    if changed:
        result.grades = build_grades(result.llm.items)
        result.total_score = calc_total_score(result.llm.items)

    return result
