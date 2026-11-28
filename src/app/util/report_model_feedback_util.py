import re

# 문단 분류 모델 모드(REVIEW_MODE=model)에서 Gemini 없이 검토 보고서 문구를 규칙으로 만든다.
# - 항목별 잘된 점 / 보완할 점, 핵심 강점, 총평, 최종 의견
# - 키워드 규칙이라 완벽하지 않지만, 같은 기획서면 항상 같은 결과가 나온다.


# ─────────────────────────────────────────
# 항목별 "있어야 할 요소" 체크리스트: (요소 이름, 키워드 정규식)
# 해당 항목으로 분류된 문단 안에 키워드가 하나라도 있으면 그 요소가 있다고 본다.
# ─────────────────────────────────────────
ITEM_CHECKLIST = {
    "item_differentiation": [
        ("핵심 상품·서비스", r"메뉴|상품|제품|서비스|클래스|판매|파는|제공|코스|업종|예약"),
        ("경쟁사·기존 업체 대비 차이", r"경쟁|기존|대형|다른 (?:가게|매장|업체)|차별|대비|보다|유일|처음|만의|없음|없는"),
        ("가격·구성", r"\d[\d,]*\s?원|가격|요금|세트|패키지|구성|코스|단위"),
    ],
    "market_customer": [
        ("타깃 고객", r"고객|타깃|타겟|대상|직장인|학생|주부|가구|연령|손님"),
        ("상권·입지 범위", r"반경|상권|역\b|역 |거리|입지|위치|골목|\d+\s?m\b|km"),
        ("경쟁 점포 현황", r"경쟁|점포|매장|업체|\d+\s?곳"),
        ("수요 근거(조사·통계)", r"조사|통계|관찰|설문|\d[\d,]*\s?명|\d+\s?%"),
    ],
    "business_model_profit": [
        ("가격(객단가)", r"객단가|가격|단가|\d[\d,]*\s?원"),
        ("매출 산출 근거", r"매출|판매량|하루|일 평균|고객 수|\d+\s?명"),
        ("비용 구성", r"비용|임대료|월세|인건비|재료비|원가"),
        ("손익분기·회수 계획", r"손익분기|회수|순이익|이익"),
    ],
    "marketing": [
        ("홍보 채널", r"인스타|SNS|블로그|전단|네이버|당근|광고|유튜브|카카오|리뷰|체험단"),
        ("실행 시기·기간", r"오픈|첫\s?(?:달|주)|매주|매월|기간|시즌|\d+\s?(?:주|개월|월|일)"),
        ("혜택·예산", r"할인|쿠폰|증정|무료|적립|예산|\d+\s?%|\d[\d,]*\s?원"),
    ],
    "operation_plan": [
        ("인력 구성", r"직원|인력|아르바이트|알바|대표|\d+\s?명"),
        ("영업시간·운영 방식", r"영업|운영 시간|오전|오후|휴무|예약|\d+\s?시"),
        ("준비 일정", r"일정|계약|인테리어|오픈|사업자등록|\d+\s?월"),
        ("재료·공급처", r"공급|재료|거래처|매입|구매|납품|입고|시장|산지|직거래"),
    ],
    "risk_management": [
        ("위험 요인", r"위험|리스크|비수기|하락|감소|부족|문제|경쟁|상승|사고|부상|민원|분쟁|손실|불황|변동"),
        ("대응 방안", r"대응|대비|보완|줄이|늘려|늘리|확보|대책|전환|조정|주의|예방|보험|교육|점검|매뉴얼"),
    ],
}

SNIPPET_LEN = 60   # 잘된 점에 인용할 문장 길이


def check_elements(item_key: str, texts: list[str]) -> tuple[list[str], list[str]]:
    # 1) 해당 항목 문단을 하나로 합친다
    joined = " ".join(texts)
    present, missing = [], []
    # 2) 요소마다 키워드가 있는지 본다
    for name, pattern in ITEM_CHECKLIST.get(item_key, []):
        (present if re.search(pattern, joined) else missing).append(name)
    return present, missing


def _snippet(text: str) -> str:
    # 문단 첫 문장(또는 앞부분)만 짧게 자른다
    text = re.sub(r"^[◾•\-\s]+", "", text.strip())
    first = re.split(r"(?<=[.다])\s", text, maxsplit=1)[0]
    return first if len(first) <= SNIPPET_LEN else first[:SNIPPET_LEN] + "…"


def build_item_strengths(item_key: str, matched_texts: list[str], specific_texts: list[str],
                         evidence_text: str | None = None) -> list[str]:
    # 1) 구체적 문단을 최대 2개 인용 (원문 근거로 이미 보여준 문단은 빼고)
    others = [t for t in specific_texts if t != evidence_text]
    strengths = [f"수치 근거가 있습니다: “{_snippet(t)}”" for t in others[:2]]
    # 2) 체크리스트에서 갖춘 요소
    present, _ = check_elements(item_key, matched_texts)
    if present:
        strengths.append(f"다루고 있는 내용: {', '.join(present)}")
    return strengths


def build_item_gaps(item_key: str, item_name: str, matched_texts: list[str], specific_count: int) -> list[str]:
    # 1) 관련 문단이 없으면 항목 전체 누락
    if not matched_texts:
        return [f"{item_name} 관련 내용을 찾지 못함"]
    gaps = []
    # 2) 문단은 있는데 수치가 없으면
    if specific_count == 0:
        gaps.append("금액·인원·기간 같은 수치 없이 서술 위주로 쓰여 있습니다")
    # 3) 관련 문단이 하나뿐이면
    if len(matched_texts) == 1:
        gaps.append("관련 내용이 한 문단뿐이라 조금 더 자세히 쓰면 좋습니다")
    # 4) 체크리스트에서 빠진 요소
    _, missing = check_elements(item_key, matched_texts)
    for name in missing:
        gaps.append(f"{name}에 대한 내용이 보이지 않습니다")
    return gaps


def build_key_strengths(items, item_names: dict, specific_counts: dict) -> list[str]:
    # 점수 4 이상 항목을 점수 높은 순으로 최대 3개
    top = sorted([i for i in items if i.score >= 4], key=lambda i: -i.score)[:3]
    return [f"{item_names[i.item_key]}: 구체적 문단 {specific_counts[i.item_key]}개로 내용이 뒷받침됩니다" for i in top]


def build_summary(head: str, items, item_names: dict, total_paragraphs: int, total_specific: int,
                  suggestions) -> str:
    # 1) 모드 안내  2) 구체적 문단 비율  3) 가장 잘된 항목  4) 가장 부족한 항목  5) 가장 시급한 보완점
    ratio = round(total_specific / total_paragraphs * 100) if total_paragraphs else 0
    best = max(items, key=lambda i: i.score)
    worst = min(items, key=lambda i: i.score)
    sentences = [
        head,
        f"항목으로 분류된 문단 {total_paragraphs}개 중 수치·근거가 있는 구체적 문단은 {total_specific}개({ratio}%)입니다.",
    ]
    if best.score != worst.score:
        sentences.append(f"가장 충실한 항목은 {item_names[best.item_key]}, 가장 부족한 항목은 {item_names[worst.item_key]}입니다.")
    if suggestions:
        sentences.append(f"가장 먼저 보완할 점은 “{suggestions[0].problem}”입니다.")
    return " ".join(sentences)


def build_final_opinion(items, item_names: dict, has_mismatch: bool) -> str:
    # 보완 순서: 재무 수치 오류 → 1단계 항목(누락) → 2단계 항목(수치 부족) → 3단계 항목(보강)
    steps = []
    if has_mismatch:
        steps.append("재무 검산에서 맞지 않는 수치를 바로잡으세요.")
    missing = [item_names[i.item_key] for i in items if i.score == 1]
    weak = [item_names[i.item_key] for i in items if i.score == 2]
    normal = [item_names[i.item_key] for i in items if i.score == 3]
    if missing:
        steps.append(f"빠진 항목({', '.join(missing)})의 내용을 추가하세요.")
    if weak:
        steps.append(f"수치가 부족한 항목({', '.join(weak)})에 금액·인원·기간 등 근거를 보강하세요.")
    if normal:
        steps.append(f"보통 등급 항목({', '.join(normal)})은 항목별 보완할 점과 개선 제안을 참고해 내용을 더 채우세요.")
    if not steps:
        return "전체 항목에 수치 근거가 고르게 갖춰져 있습니다. 개선 제안을 참고해 세부 내용을 다듬으세요."
    order = ["먼저", "다음으로", "이어서", "마지막으로"]
    if len(steps) == 1:
        return steps[0]
    return " ".join(f"{order[min(i, 3) if i < len(steps) - 1 else 3]} {step}" for i, step in enumerate(steps))
