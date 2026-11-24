from pydantic import BaseModel, Field
from typing import Literal

priority: Literal["높음", "보통", "낮음"]


class Evidence(BaseModel):
    quote: str | None = Field(
        default=None,
        description="판단 근거가 된 기획서 원문을 그대로 짧게 인용. 고쳐 쓰지 말 것. 관련 내용이 없으면 null",
    )
    page: int | None = Field(
        default=None,
        description="인용한 문장이 있는 페이지 번호. 알 수 없으면 null",
    )
    judgment: str = Field(
        description="원문을 바탕으로 한 평가 의견 1~2문장. 기획서에 없는 내용은 추측하지 말 것",
    )



ItemKey = Literal[
    "item_differentiation",    # 사업 아이템 및 차별성
    "market_customer",         # 시장성 및 고객 분석
    "business_model_profit",   # 사업 모델 및 수익성
    "marketing",               # 마케팅 전략
    "operation_plan",          # 운영 및 실행 계획
    "risk_management",         # 위험 관리
]

class ItemReview(BaseModel):
    item_key: ItemKey = Field(
        description="평가 항목 key. 6개 항목 각각 한 번씩만 사용",
    )
    score: int = Field(
        ge=1, le=5,
        description="항목 평가 단계 1~5 (5가 가장 우수). 관련 내용이 전혀 없으면 1",
    )
    evidence: Evidence = Field(
        description="이 점수를 준 근거",
    )
    strengths: list[str] = Field(
        default_factory=list,
        description="기획서에서 잘된 점. 원문에 근거한 내용만, 없으면 빈 리스트",
    )
    gaps: list[str] = Field(
        default_factory=list,
        description="부족하거나 누락된 내용. 무엇이 왜 부족한지 구체적으로",
    )


# ─────────────────────────────────────────
# 재무 원문 수치 (LLM은 뽑기만, 계산은 백엔드)
# ─────────────────────────────────────────

class CostItem(BaseModel):
    name: str = Field(
        description="비용 또는 자금 항목 이름. 기획서에 적힌 이름 그대로",
    )
    amount: int | None = Field(
        default=None,
        description="금액을 원 단위 정수로 변환 (예: '7,500만 원' → 75000000). 금액이 없으면 null",
    )


class FinanceRaw(BaseModel):
    startup_costs: list[CostItem] = Field(
        default_factory=list,
        description="창업 비용 항목들 (보증금, 인테리어, 설비 등). 없으면 빈 리스트",
    )
    startup_cost_total: int | None = Field(
        default=None,
        description="기획서에 적힌 창업 비용 합계(원). 직접 더하지 말고 원문 값 그대로, 없으면 null",
    )
    funding: list[CostItem] = Field(
        default_factory=list,
        description="자금 조달 항목들 (자기자본, 대출 등). 없으면 빈 리스트",
    )
    unit_price: int | None = Field(
        default=None,
        description="객단가(원). 원문 값 그대로, 없으면 null",
    )
    daily_customers: int | None = Field(
        default=None,
        description="하루 예상 고객 수. 원문 값 그대로, 없으면 null",
    )
    operating_days: int | None = Field(
        default=None,
        description="월 영업일 수. 원문 값 그대로, 없으면 null",
    )
    monthly_sales: int | None = Field(
        default=None,
        description="기획서에 적힌 월 예상 매출(원). 직접 계산하지 말 것, 없으면 null",
    )
    material_ratio: float | None = Field(
        default=None,
        description="재료비 비율을 퍼센트 숫자로 (35%면 35). 없으면 null",
    )
    monthly_costs: list[CostItem] = Field(
        default_factory=list,
        description="월 운영 비용 항목들 (임대료, 재료비, 인건비 등). 없으면 빈 리스트",
    )
    monthly_cost_total: int | None = Field(
        default=None,
        description="기획서에 적힌 월 운영 비용 합계(원). 직접 더하지 말 것, 없으면 null",
    )
    monthly_profit: int | None = Field(
        default=None,
        description="기획서에 적힌 월 순이익(원). 직접 계산하지 말 것, 없으면 null",
    )
    payback_months: float | None = Field(
        default=None,
        description="기획서에 적힌 투자금 회수 기간(개월). 직접 계산하지 말 것, 없으면 null",
    )


# ─────────────────────────────────────────
# 개선 제안
# ─────────────────────────────────────────

class Suggestion(BaseModel):
    priority: Literal["높음", "보통", "낮음"] = Field(
        description="높음: 신뢰도에 직접 영향(수치 오류, 핵심 가정 근거 부족) / 보통: 타당성 보완 / 낮음: 문서 구성·표현",
    )
    problem: str = Field(
        description="기획서의 어떤 부분이 문제인지. 해당 내용을 구체적으로 짚을 것",
    )
    action: str = Field(
        description="이 기획서에 맞춘 구체적인 수정 방법. 일반론 금지",
    )


# ─────────────────────────────────────────
# [A] LLM 출력 전체 (with_structured_output에 넘기는 스키마)
# ─────────────────────────────────────────

class ReportAiLlmOutput(BaseModel):
    status: Literal["OK", "UNAVAILABLE"] = Field(
        description="OK: 정상 평가 / UNAVAILABLE: 사업계획서가 아니거나 내용이 너무 적거나 텍스트가 제대로 추출되지 않아 평가 불가",
    )
    unavailable_reason: str = Field(
        default="",
        description="status가 UNAVAILABLE일 때만 평가 불가 사유 한 문장. OK면 빈 문자열",
    )
    guide: str = Field(
        default="",
        description="status가 UNAVAILABLE일 때만 사용자가 다시 올릴 때 필요한 내용 안내 1~2문장. OK면 빈 문자열",
    )

    business_item: str = Field(
        default="",
        description="사업 아이템 한 줄 요약 (지역, 규모, 업종 포함)",
    )
    startup_type: str = Field(
        default="",
        description="창업 유형과 그렇게 판단한 이유 한 문장",
    )
    summary: str = Field(
        default="",
        description="총평 3~4문장. 강점, 가장 큰 문제, 가장 시급한 보완점 순서",
    )
    key_strengths: list[str] = Field(
        default_factory=list,
        description="핵심 강점 최대 3개. 원문에 근거한 내용만",
    )
    items: list[ItemReview] = Field(
        default_factory=list,
        description="6개 평가 항목 각각의 평가. status가 OK면 반드시 6개, 항목 key 중복 금지. UNAVAILABLE이면 빈 리스트",
    )
    finance: FinanceRaw = Field(
        default_factory=FinanceRaw,
        description="기획서에 적힌 재무 수치. 계산하지 말고 원문 값만 옮길 것",
    )
    suggestions: list[Suggestion] = Field(
        default_factory=list,
        description="개선 제안 목록. 우선순위가 높은 것부터",
    )
    final_opinion: str = Field(
        default="",
        description="최종 의견 2~3문장. 무엇부터 어떤 순서로 보완할지",
    )


# ─────────────────────────────────────────
# [B] 백엔드가 계산해서 붙이는 부분 (LLM에는 넘기지 않음)
# ─────────────────────────────────────────

Grade = Literal["우수", "보통", "미흡", "매우 미흡"]   # 가안: 희수랑 합의 후 확정
CheckResult = Literal["일치", "불일치", "근거 누락"]


class ItemGrade(BaseModel):
    item_key: ItemKey
    grade: Grade                # 점수 → 등급 변환 결과 (PDF에 보이는 값)


class FinanceCheck(BaseModel):
    label: str                  # 구분 (창업 비용, 예상 매출, 투자금 회수 기간 ...)
    original: str | None = None # 원문 수치 (표에 그대로 보여줄 글자)
    formula: str | None = None  # 계산식 문자열 (예: "3,000 + 2,500 + 1,200 + 300 = 7,000만 원")
    result: CheckResult


class ReportAiResult(BaseModel):
    llm: ReportAiLlmOutput
    grades: list[ItemGrade] = Field(default_factory=list)
    total_score: int | None = None              # 100점 환산 (내부용, PDF에 안 나감)
    finance_checks: list[FinanceCheck] = Field(default_factory=list)
    prompt_version: str = "v3"