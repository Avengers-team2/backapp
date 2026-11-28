import asyncio
import os
from pathlib import Path
from typing import get_args
from app.infrastructure.llm import get_llm
from app.schema.report_ai_schema import (Evidence, FinanceRaw, ItemKey, ItemReview, ReportAiLlmOutput,
    ReportAiResult, Suggestion)
from app.util.report_paragraph_util import split_report_paragraphs
from app.util.report_specificity_util import is_specific
from app.util.report_model_feedback_util import (build_final_opinion, build_item_gaps, build_item_strengths,
    build_key_strengths, build_summary)
from app.util.report_finance_extract_util import extract_finance
from app.util.report_finance_util import (build_finance_checks, build_finance_suggestions, build_grades,
    calc_total_score, cap_profit_score, total_to_grade, PROFIT_ITEM_KEY, PROFIT_MAX_SCORE_WHEN_MISMATCH)

PROMPT = "v3.3"
PROMPT_PATH = Path(__file__).resolve().parent.parent / "llm_prompt" / "startfit_review_prompt.md"
ITEM_KEY_ORDER = get_args(ItemKey)   # 스키마에 정의된 6개 항목 key 순서 (①~⑥)
PRIORITY_ORDER = {"높음": 0, "보통": 1, "낮음": 2}
FINANCE_PROMPT_PATH = Path(__file__).resolve().parent.parent / "llm_prompt" / "startfit_finance_prompt.md"

# 문단 분류 모델 모드 (.env REVIEW_MODE=model 일 때 Gemini 대신 사용)
# MODEL_VERSION = "model-exp2"   # 상아 RoBERTa
# MODEL_VERSION = "model-tfidf"   # 희수 TF-IDF
# MODEL_VERSION = "model-ensemble"   # RoBERTa + TF-IDF 평균 (점수 = 문단 개수)
MODEL_VERSION = "model-ensemble-spec"   # RoBERTa + TF-IDF 평균, 점수 = 구체적 문단 기준

ITEM_NAMES = {
    "item_differentiation": "사업 아이템 및 차별성",
    "market_customer": "시장성 및 고객 분석",
    "business_model_profit": "사업 모델 및 수익성",
    "marketing": "마케팅 전략",
    "operation_plan": "운영 및 실행 계획",
    "risk_management": "위험 관리",
}

# 목차 제목에 이 단어가 있으면 문단이 0개여도 누락으로 보지 않음 (거짓 누락 줄이기)
SECTION_KEYWORDS = {
    "item_differentiation": ["차별", "아이템", "경쟁력"],
    "market_customer": ["시장", "고객", "상권", "입지"],
    "business_model_profit": ["수익", "매출", "재무", "자금", "비용"],
    "marketing": ["마케팅", "홍보", "판촉"],
    "operation_plan": ["운영", "실행", "일정"],
    "risk_management": ["위험", "리스크", "대응"],
}

async def analyze_report(text: str) -> ReportAiResult:
    if os.getenv("REVIEW_MODE") == "model":
        return await analyze_report_with_model(text)

    system_prompt = PROMPT_PATH.read_text(encoding="utf-8")
    structured_llm = get_llm().with_structured_output(ReportAiLlmOutput)

    messages = [
        ("system", system_prompt),
        ("human", f"<document>\n{text}\n</document>"),
    ]

    llm_output = await structured_llm.ainvoke(messages)

    if llm_output.status == "UNAVAILABLE":
        return ReportAiResult(llm=llm_output, prompt_version=PROMPT)

    # LLM이 항목 key를 헷갈려도 프롬프트 순서(①~⑥)대로 다시 붙인다
    if len(llm_output.items) != len(ITEM_KEY_ORDER):
        raise ValueError(f"평가 항목이 {len(ITEM_KEY_ORDER)}개가 아닙니다 (받은 개수: {len(llm_output.items)})")
    for item, key in zip(llm_output.items, ITEM_KEY_ORDER):
        item.item_key = key

    finance_checks = build_finance_checks(llm_output.finance)

    # 재무 수치가 틀린 기획서는 수익성 항목을 최대 "보통"으로 (등급·종합 점수 계산 전에)
    cap_profit_score(llm_output.items, finance_checks)

    # 재무 수치 오류를 개선 제안에 합치고 (LLM은 계산을 안 해서 모름) 높음 → 보통 → 낮음 순서로 정렬
    merged = build_finance_suggestions(finance_checks) + llm_output.suggestions
    llm_output.suggestions = sorted(merged, key=lambda s: PRIORITY_ORDER[s.priority])
    grades = build_grades(llm_output.items)
    total_score = calc_total_score(llm_output.items)
    total_grade = total_to_grade(total_score)

    return ReportAiResult(llm=llm_output, grades=grades, total_score=total_score, total_grade=total_grade,
        finance_checks=finance_checks, prompt_version=PROMPT)


def count_to_score(count: int) -> int:
    if count == 0:
        return 1
    if count == 1:
        return 2
    if count <= 3:
        return 3
    return 4


# 항목 점수: 관련 문단 수(total)와 그중 구체적인 문단 수(specific_count)로 정한다
def specificity_to_score(total: int, specific_count: int) -> int:
    if total == 0:
        return 1
    if specific_count == 0:
        return 2
    if specific_count == 1:
        return 3
    if specific_count >= 3 and specific_count * 2 >= total:
        return 5
    return 4


# 모델 모드 전용: 재무 검산이 절반 이상 "근거 누락"이면 수익성 점수를 최대 3단계로 묶는다
# (문단에 숫자는 있어도 검산할 근거가 없는 기획서가 수익성 우수를 받지 않도록)
def cap_profit_score_when_missing(items: list[ItemReview], checks) -> None:
    targets = list(checks)
    missing = sum(1 for check in targets if check.result == "근거 누락")
    if not targets or missing * 2 < len(targets):
        return
    for item in items:
        if item.item_key == PROFIT_ITEM_KEY and item.score > PROFIT_MAX_SCORE_WHEN_MISMATCH:
            item.score = PROFIT_MAX_SCORE_WHEN_MISMATCH


async def analyze_report_with_model(text: str) -> ReportAiResult:
    # torch·transformers가 없는 환경에서도 서버가 켜지도록 모델 모드일 때만 불러온다
    from app.infrastructure.paragraph_model import predict_paragraphs

    paragraphs = split_report_paragraphs(text)
    if not paragraphs:
        raise ValueError("문단을 찾지 못했습니다")

    preds = await asyncio.to_thread(predict_paragraphs, [para for _, _, para in paragraphs])
    sections = " ".join(section for _, section, _ in paragraphs)

    items = []
    suggestions = []
    specific_counts = {}   # 항목별 구체적 문단 수 (핵심 강점 문구용)
    total_paragraphs = 0   # 6개 항목으로 분류된 문단 수 (총평용)
    for key in ITEM_KEY_ORDER:
        matched = [(page, para, prob) for (page, _, para), (label, prob) in zip(paragraphs, preds) if label == key]
        specific = [m for m in matched if is_specific(m[1])]
        specific_counts[key] = len(specific)
        total_paragraphs += len(matched)
        count = len(matched)
        if count == 0 and any(word in sections for word in SECTION_KEYWORDS[key]):
            count = 1
        score = specificity_to_score(count, len(specific))

        if matched:
            # 구체적인 문단이 있으면 그중에서, 없으면 전체에서 확률이 가장 높은 문단을 근거로 보여준다
            best = max(specific or matched, key=lambda m: m[2])
            evidence = Evidence(quote=best[1][:100], page=best[0],
                                judgment=f"관련 문단 {len(matched)}개 중 구체적 문단 {len(specific)}개를 찾았습니다.")
            if not specific:
                suggestions.append(Suggestion(priority="보통",
                                              problem=f"{ITEM_NAMES[key]}에 구체적인 수치나 근거가 부족합니다.",
                                              action=f"{ITEM_NAMES[key]}에 금액·인원·기간 등 구체적인 수치를 추가해 주세요."))
        else:
            evidence = Evidence(quote=None, page=None, judgment="관련 문단을 찾지 못했습니다 (확인 필요).")

        # 잘된 점 / 보완할 점 (규칙으로 생성)
        matched_texts = [m[1] for m in matched]
        strengths = build_item_strengths(key, matched_texts, [m[1] for m in specific],
                                         best[1] if matched else None)
        gaps = build_item_gaps(key, ITEM_NAMES[key], matched_texts, len(specific))

        if score == 1:
            suggestions.append(Suggestion(priority="보통",
                                          problem=f"{ITEM_NAMES[key]} 관련 내용을 찾지 못했습니다.",
                                          action=f"{ITEM_NAMES[key]} 내용을 추가해 주세요."))

        items.append(ItemReview(item_key=key, score=score, evidence=evidence, strengths=strengths, gaps=gaps))

    finance, finance_source = await extract_finance_for_model(text, paragraphs)

    summary_head = f"문단 분류 모델로 항목별 관련 문단을 확인한 간이 검토 결과입니다. (재무 수치: {finance_source})"
    llm_output = ReportAiLlmOutput(status="OK", summary=summary_head,
                                   items=items, finance=finance, suggestions=suggestions)

    # 재무 수치는 원문 값만 뽑았으므로 Gemini 모드와 같은 방식으로 검산한다
    finance_checks = build_finance_checks(llm_output.finance)
    profit = next(item for item in llm_output.items if item.item_key == PROFIT_ITEM_KEY)
    before = profit.score
    cap_profit_score(llm_output.items, finance_checks)
    after_mismatch = profit.score
    cap_profit_score_when_missing(llm_output.items, finance_checks)
    # 상한으로 수익성 점수가 깎였으면 그 이유를 보완할 점에 적는다
    if after_mismatch < before:
        profit.gaps.append("재무 검산에서 맞지 않는 수치가 있어 보통 등급까지만 인정됩니다 (재무 수치 검산 참고)")
    elif profit.score < before:
        profit.gaps.append("재무 수치 대부분의 근거(세부 금액·산출 방식)가 없어 보통 등급까지만 인정됩니다")
    merged = build_finance_suggestions(finance_checks) + llm_output.suggestions
    llm_output.suggestions = sorted(merged, key=lambda s: PRIORITY_ORDER[s.priority])

    # 총평·핵심 강점·최종 의견 (점수 상한까지 적용한 최종 점수 기준)
    total_specific = sum(specific_counts.values())
    llm_output.summary = build_summary(summary_head, llm_output.items, ITEM_NAMES, total_paragraphs,
                                       total_specific, llm_output.suggestions)
    llm_output.key_strengths = build_key_strengths(llm_output.items, ITEM_NAMES, specific_counts)
    has_mismatch = any(check.result == "불일치" for check in finance_checks)
    llm_output.final_opinion = build_final_opinion(llm_output.items, ITEM_NAMES, has_mismatch)
    grades = build_grades(llm_output.items)
    total_score = calc_total_score(llm_output.items)
    total_grade = total_to_grade(total_score)

    return ReportAiResult(llm=llm_output, grades=grades, total_score=total_score, total_grade=total_grade,
        finance_checks=finance_checks, prompt_version=MODEL_VERSION)


async def extract_finance_for_model(text: str, paragraphs: list[tuple[int | None, str, str]]) -> tuple[FinanceRaw, str]:
    # 1) Gemini에 재무 수치만 묻는다 (짧은 별도 프롬프트, 출력은 FinanceRaw)
    # 2) Gemini가 실패하면(503·429 등) 규칙 추출로 대신한다 → 모델 모드는 Gemini 없이도 끝까지 돈다
    try:
        system_prompt = FINANCE_PROMPT_PATH.read_text(encoding="utf-8")
        structured_llm = get_llm().with_structured_output(FinanceRaw)
        messages = [
            ("system", system_prompt),
            ("human", f"<document>\n{text}\n</document>"),
        ]
        finance = await structured_llm.ainvoke(messages)
        if finance is None:
            raise ValueError("Gemini 재무 응답이 비어 있음")
        return finance, "Gemini 추출"
    except Exception as e:
        print(f"[재무 추출] Gemini 실패, 규칙 추출로 대신함: {type(e).__name__}: {e}")
        return extract_finance([(section, para) for _, section, para in paragraphs]), "규칙 추출 (Gemini 응답 실패)"
