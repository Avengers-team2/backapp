from pathlib import Path
from typing import get_args
from app.infrastructure.llm import get_llm
from app.schema.report_ai_schema import ItemKey, ReportAiLlmOutput, ReportAiResult
from app.util.report_finance_util import build_finance_checks, build_finance_suggestions, build_grades, calc_total_score

PROMPT = "v3.2"
PROMPT_PATH = Path(__file__).resolve().parent.parent / "data" / "startfit_review_prompt.md"
ITEM_KEY_ORDER = get_args(ItemKey)   # 스키마에 정의된 6개 항목 key 순서 (①~⑥)
PRIORITY_ORDER = {"높음": 0, "보통": 1, "낮음": 2}

async def analyze_report(text: str) -> ReportAiResult:
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

    # 재무 수치 오류를 개선 제안에 합치고 (LLM은 계산을 안 해서 모름) 높음 → 보통 → 낮음 순서로 정렬
    merged = build_finance_suggestions(finance_checks) + llm_output.suggestions
    llm_output.suggestions = sorted(merged, key=lambda s: PRIORITY_ORDER[s.priority])
    grades = build_grades(llm_output.items)
    total_score = calc_total_score(llm_output.items)

    return ReportAiResult(llm=llm_output, grades=grades, total_score=total_score,
        finance_checks=finance_checks, prompt_version=PROMPT)