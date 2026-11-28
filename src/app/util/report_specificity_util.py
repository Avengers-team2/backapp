import re

# 기획서 문단이 "구체적인지" 규칙으로 판단한다 (문단 분류 모델 모드의 항목 점수에 사용).
# 기준: 계획에 묶인 수치 = "숫자 + 단위" (llm/data/specificity_guideline.md 1번)
# - 학습 모델(klue/roberta-base)도 시도했지만 실제 문서에서 Macro F1 0.47로 낮아 규칙을 사용한다.
# - 비즈폼 실제 문단 523개 기준 Macro F1 0.907 (참고 수치, 노션 학습 계획 페이지 5번 참고)
# - 한계: 숫자 없이 구체적인 문단(경쟁사 특징, 웹사이트 기능 등)은 잡지 못한다.

# 숫자 뒤에 오는 단위 (숫자와 단위 사이 공백 0~1개 허용)
UNITS = [
    "만 원", "만원", "천 원", "천원", "원", "억", "만", "천",
    "명", "인", "%", "퍼센트",
    "개월", "년", "월", "일", "주", "시간", "분", "초",
    "평", "㎡", "m2", "제곱미터", "km", "m", "kg", "g",
    "회", "잔", "개", "건", "곳", "대", "석", "세", "배", "위", "종", "가지", "단계", "차",
]
NUM = r"\d[\d,]*(?:\.\d+)?"
NUM_UNIT_PATTERN = re.compile(NUM + r"\s?(?:" + "|".join(re.escape(u) for u in UNITS) + ")")

# 이름 속 숫자는 수치로 보지 않는다 (예: 코로나19, COVID-19)
NAME_NUMBER_PATTERN = re.compile(r"코로나\s?19|COVID\s?-?\s?19", re.IGNORECASE)

# 나이대 표현도 수치로 보지 않는다 (예: "10대, 20대 학생" → 누구나 쓸 수 있는 막연한 고객층)
# "냉장고 2대"처럼 개수를 뜻하는 "대"는 그대로 수치로 본다
AGE_GROUP_PATTERN = re.compile(r"(?<!\d)[1-9]0\s?대")


def is_specific(text: str) -> bool:
    # 1) 이름 속 숫자, 나이대 표현 지우기
    cleaned = NAME_NUMBER_PATTERN.sub("", text)
    cleaned = AGE_GROUP_PATTERN.sub("", cleaned)
    # 2) "숫자 + 단위"가 있으면 구체적
    return NUM_UNIT_PATTERN.search(cleaned) is not None
