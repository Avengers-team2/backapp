# 1. import
#    - BaseModel, Field (pydantic)
#    - Literal (typing)  ← 정해진 값만 오게 할 때

# ─────────────────────────────────────────
# [A] LLM이 채우는 부분 (with_structured_output에 넘길 스키마)
#     Field(description="...")에 적은 설명을 LLM이 지시로 읽으니까 구체적으로 써
# ─────────────────────────────────────────

# 2. Evidence: 판단 근거
#    - quote: 원문 인용 (없으면 None)
#    - page: 페이지 번호 (없으면 None)
#    - judgment: LLM 판단

# 3. ItemReview: 항목 1개 평가
#    - item_key: 6개 항목 중 하나 (Literal로 6개 key 고정, key 이름은 희수랑 합의)
#    - score: 1~5 (내부용, Field(ge=1, le=5))
#    - evidence: Evidence
#    - strengths: 장점 (list[str])
#    - gaps: 부족하거나 누락된 내용 (list[str])

# 4. CostItem: 비용 항목 1개
#    - name: 항목 이름
#    - amount: 금액 (원 단위 int, 없으면 None)

# 5. FinanceRaw: 기획서에 적힌 수치 그대로 (계산 금지, 없으면 None)
#    - startup_costs: list[CostItem]   창업 비용 항목들
#    - startup_cost_total: 원문 합계
#    - funding: list[CostItem]          자금 조달
#    - unit_price, daily_customers, operating_days, material_ratio
#    - monthly_costs: list[CostItem]
#    - monthly_profit, payback_months: 원문에 적힌 값

# 6. Suggestion: 개선 제안 1개
#    - priority: Literal["높음", "보통", "낮음"]
#    - problem: 문제
#    - action: 고칠 방법

# 7. ReportAiLlmOutput: LLM 출력 전체 (이걸 LLM에 넘김)
#    - business_item, startup_type: 기본 정보
#    - summary: 총평
#    - key_strengths: list[str]
#    - items: list[ItemReview]  (6개)
#    - finance: FinanceRaw
#    - suggestions: list[Suggestion]
#    - final_opinion: 최종 의견

# ─────────────────────────────────────────
# [B] 백엔드가 계산해서 붙이는 부분 (report_finance_util 결과)
# ─────────────────────────────────────────

# 8. FinanceCheck: 재무 검산 표의 한 줄
#    - label: 구분 (창업 비용, 예상 매출 ...)
#    - original: 원문 수치
#    - formula: 계산식 문자열
#    - result: Literal["일치", "불일치", "근거 누락"]

# 9. ReportAiResult: analyze_report가 최종으로 돌려주는 것 (희수가 받는 모양)
#    - llm: ReportAiLlmOutput
#    - grades: 항목별 등급 (점수 → 등급, 백엔드 변환)
#    - total_score: 100점 환산 (내부용, PDF에 안 나감)
#    - finance_checks: list[FinanceCheck]
#    - prompt_version: "v3"