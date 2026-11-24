from pathlib import Path
from app.infrastructure.llm import get_llm
from app.schema.report_ai_schema import (
    CostItem,
    Evidence,
    FinanceCheck,
    FinanceRaw,
    ItemGrade,
    ItemReview,
    ReportAiLlmOutput,
    ReportAiResult,
    Suggestion,
)

PROMPT = "v3.2"
PROMPT_PATH = Path(__file__).resolve().parent.parent / "data" / "startfit_review_prompt.md"

async def analyze_report(text: str) -> ReportAiResult:
    # [1단계] 가짜 결과: 희수 쪽 연결·PDF 화면 테스트용 (text는 아직 안 씀)
    llm_output = ReportAiLlmOutput(
        status="OK",
        business_item="서울 마포구 망원동 10평 규모의 수제 스콘 전문 1인 디저트 카페",
        startup_type="점포형 소상공인 - 오프라인 매장에서 디저트와 음료를 판매하는 점포 중심 사업",
        summary=(
            "사업 아이템과 차별화 방향은 분명하고, 매출을 객단가 × 고객 수 × 영업일로 계산한 구조도 갖추고 있습니다. "
            "하지만 창업 비용 합계와 투자금 회수 기간에 계산 오류가 있고, 하루 80명이라는 핵심 가정의 근거가 약합니다. "
            "위험 관리 항목은 작성되지 않았습니다. 수치 오류를 고치고 고객 수 추정 근거를 보강하는 것이 가장 시급합니다."
        ),
        key_strengths=[
            "'스콘 전문점'이라는 차별화 포인트가 한 문장으로 명확합니다.",
            "예상 매출을 산출식으로 제시하여 검증이 가능합니다.",
            "창업 비용과 월 운영 비용을 구분해 표로 정리했습니다.",
        ],
        items=[
            ItemReview(
                item_key="item_differentiation",
                score=4,
                evidence=Evidence(
                    quote="망원동에는 디저트 카페가 많지만 스콘 전문점은 드물다",
                    page=1,
                    judgment="아이템과 핵심 메뉴는 명확하지만, 경쟁 매장과 비교한 근거는 제시되지 않았습니다.",
                ),
                strengths=["영국식 스콘과 계절 한정 메뉴라는 구체적인 상품 전략이 있습니다."],
                gaps=["'스콘 전문점은 드물다'는 주장에 대한 조사 내용(주변 매장 수, 판매 메뉴 비교)이 없습니다."],
            ),
            ItemReview(
                item_key="market_customer",
                score=2,
                evidence=Evidence(
                    quote="주변 카페를 직접 관찰한 결과, 하루 80명 정도의 손님은 충분히 확보할 수 있을 것으로 보인다",
                    page=1,
                    judgment="매출 전체가 이 가정에 달려 있는데, 관찰 일시·장소·방법이 적혀 있지 않습니다.",
                ),
                strengths=["주 고객층(20~30대 여성, 인근 직장인)과 유입 요인(망원시장 방문객)을 언급했습니다."],
                gaps=["수요 근거가 관찰 소감 수준이고, 경쟁 매장 분석과 평일·주말 수요 차이가 없습니다."],
            ),
            ItemReview(
                item_key="business_model_profit",
                score=3,
                evidence=Evidence(
                    quote="창업 비용 합계 7,500만 원",
                    page=2,
                    judgment="항목을 더하면 7,000만 원으로 합계가 맞지 않습니다.",
                ),
                strengths=["매출 산출식, 매출 비율로 계산한 재료비, 비용 항목별 금액이 제시되어 있습니다."],
                gaps=["손익분기점이 없고, 대출 상환액과 대표자 본인의 인건비가 비용에 포함되지 않았습니다."],
            ),
            ItemReview(
                item_key="marketing",
                score=2,
                evidence=Evidence(
                    quote="인스타그램 계정을 운영하고, 오픈 첫 주에는 음료 1+1 이벤트를 진행한다",
                    page=3,
                    judgment="오픈 초기 홍보 외에 지속적인 고객 확보 계획이 없습니다.",
                ),
                strengths=["오픈 전후의 홍보 채널(인스타그램, 블로거 시식)이 정해져 있습니다."],
                gaps=["월 마케팅비 30만 원의 사용 계획과 성과 측정 기준(팔로워 수, 재방문율 등)이 없습니다."],
            ),
            ItemReview(
                item_key="operation_plan",
                score=3,
                evidence=Evidence(
                    quote="대표 1인이 제과와 운영을 맡고, 주말에는 아르바이트 1명을 고용한다",
                    page=3,
                    judgment="평일에는 대표 혼자 매일 10시간 영업과 제과를 함께 해야 하므로 업무량이 과도할 수 있습니다.",
                ),
                strengths=["영업시간, 휴무일, 3~5월 추진 일정이 명확합니다."],
                gaps=["하루 제과 생산량과 준비 시간, 아르바이트 인건비 180만 원의 산출 근거(시급, 근무 시간)가 없습니다."],
            ),
            ItemReview(
                item_key="risk_management",
                score=1,
                evidence=Evidence(
                    quote=None,
                    page=None,
                    judgment="위험 요소나 대응 방안에 관한 내용이 문서 어디에도 없습니다.",
                ),
                strengths=[],
                gaps=["매출 부진, 재료비 상승, 대표자 부재 시 운영 등 주요 위험과 대응 방안 전체가 누락되었습니다."],
            ),
        ],
        finance=FinanceRaw(
            startup_costs=[
                CostItem(name="보증금", amount=30_000_000),
                CostItem(name="인테리어", amount=25_000_000),
                CostItem(name="설비", amount=12_000_000),
                CostItem(name="초기 재료", amount=3_000_000),
            ],
            startup_cost_total=75_000_000,
            funding=[
                CostItem(name="자기자본", amount=45_000_000),
                CostItem(name="대출", amount=30_000_000),
            ],
            unit_price=9_000,
            daily_customers=80,
            operating_days=26,
            monthly_sales=18_720_000,
            material_ratio=35,
            monthly_costs=[
                CostItem(name="임대료", amount=2_500_000),
                CostItem(name="재료비", amount=6_550_000),
                CostItem(name="아르바이트 인건비", amount=1_800_000),
                CostItem(name="공과금", amount=500_000),
                CostItem(name="마케팅비", amount=300_000),
                CostItem(name="기타", amount=350_000),
            ],
            monthly_cost_total=12_000_000,
            monthly_profit=6_700_000,
            payback_months=8,
        ),
        suggestions=[
            Suggestion(priority="높음", problem="창업 비용 합계 오류(7,500만 → 7,000만 원)",
                       action="합계를 고치거나, 누락된 500만 원 항목(예비비, 운영 자금 등)을 표에 추가해 자금 조달액과 맞추세요."),
            Suggestion(priority="높음", problem="투자금 회수 기간 오류(8개월)",
                       action="수정한 창업 비용과 실제 순이익으로 다시 계산하고 계산식을 함께 적으세요."),
            Suggestion(priority="높음", problem="하루 80명 가정의 근거 부족",
                       action="관찰한 날짜·시간대·매장 수와 평일·주말 손님 수를 나눠 기록하고, 보수적·기본·낙관 3가지 시나리오로 매출을 제시하세요."),
            Suggestion(priority="보통", problem="위험 관리 항목 누락",
                       action="매출 부진, 재료비 상승, 대표자 부재 등 위험 3가지 이상과 각각의 대응 방안을 작성하세요."),
            Suggestion(priority="보통", problem="손익분기점 미제시",
                       action="손익분기 월 매출과 하루 필요 고객 수를 계산해 넣으세요."),
            Suggestion(priority="낮음", problem="아르바이트 인건비 산출 근거 부재",
                       action="시급과 주당 근무 시간을 함께 적으세요."),
        ],
        final_opinion=(
            "아이템과 기본 계산 구조는 갖춰져 있지만, 계산 오류와 핵심 가정의 근거 부족 때문에 현재 상태로는 신뢰도가 낮습니다. "
            "먼저 창업 비용과 회수 기간을 바로잡고, 하루 고객 수 추정 근거를 보강한 뒤 위험 관리 항목을 추가하는 순서로 보완하시길 권합니다."
        ),
    )

    return ReportAiResult(
        llm=llm_output,
        grades=[
            ItemGrade(item_key="item_differentiation", grade="우수"),
            ItemGrade(item_key="market_customer", grade="미흡"),
            ItemGrade(item_key="business_model_profit", grade="보통"),
            ItemGrade(item_key="marketing", grade="미흡"),
            ItemGrade(item_key="operation_plan", grade="보통"),
            ItemGrade(item_key="risk_management", grade="매우 미흡"),
        ],
        total_score=47,
        finance_checks=[
            FinanceCheck(label="창업 비용 합계", original="7,500만 원",
                         formula="3,000 + 2,500 + 1,200 + 300 = 7,000만 원", result="불일치"),
            FinanceCheck(label="자금 조달", original="4,500만 + 3,000만 원",
                         formula="4,500 + 3,000 = 7,500만 원 (실제 비용 합계보다 500만 원 많음)", result="불일치"),
            FinanceCheck(label="예상 매출", original="월 1,872만 원",
                         formula="9,000원 × 80명 × 26일 = 18,720,000원", result="일치"),
            FinanceCheck(label="재료비", original="월 655만 원",
                         formula="18,720,000원 × 35% = 6,552,000원", result="일치"),
            FinanceCheck(label="운영 비용", original="월 1,200만 원",
                         formula="250 + 655 + 180 + 50 + 30 + 35 = 1,200만 원", result="일치"),
            FinanceCheck(label="월 순이익", original="약 670만 원",
                         formula="1,872 - 1,200 = 672만 원", result="일치"),
            FinanceCheck(label="투자금 회수 기간", original="약 8개월",
                         formula="7,500 ÷ 672 = 약 11.2개월", result="불일치"),
            FinanceCheck(label="손익분기점", original=None,
                         formula="고정비 545만 원 ÷ (1 - 35%) = 월 매출 약 839만 원", result="근거 누락"),
        ],
        prompt_version=PROMPT,
    )

    # [2단계] 실제 결과 (finance util·프롬프트 형식 정해진 뒤 위 가짜 결과를 이걸로 교체)
    # system_prompt = PROMPT_PATH.read_text(encoding="utf-8")
    # structured_llm = get_llm().with_structured_output(ReportAiLlmOutput)
    # llm_output = await structured_llm.ainvoke([
    #     ("system", system_prompt),
    #     ("human", f"<document>\n{text}\n</document>"),
    # ])
    # finance_checks = report_finance_util로 검산
    # grades, total_score = 점수 → 등급 변환
    # return ReportAiResult(...)