"""
분석 입력(프론트 화면 값) -> 점수 계산용 사용자 입력(user) 변환

프론트가 보내는 값 (frontapp/app/(protected)/analysis/_component/analysis.data.ts)
  연령   : "10대" "20대" ... "60대 이상"
  성별   : "상관없음" "여성" "남성"
  운영시간: "아침 07~11시" "점심 11~15시" "오후 15~22시" "저녁 22~02시" "새벽 02~07시" "미정"

점수 계산 쪽이 받는 형식 (ML 팀 가이드)
  target_age:    {"20": 0.5, "30": 0.5}      키는 "10" "20" "30" "40" "50" "60_이상"
  target_gender: {"여": 1.0}                  "여" 또는 "남"
  hours:         [[11, 14], [17, 22]]         시각 구간 여러 개 (구간 안 균등 분포 가정이라 정밀도는 낮음)
  * 선택하지 않은 항목은 키를 아예 넣지 않는다 (그 지표만 빠지고 나머지로 종합 점수를 계산)
"""

# 화면 연령 칩 -> 점수 계산용 키
AGE_KEYS = {
    "10대": "10",
    "20대": "20",
    "30대": "30",
    "40대": "40",
    "50대": "50",
    "60대 이상": "60_이상",
}

# 화면 성별 -> 점수 계산용 키 ("상관없음"은 입력 없음으로 본다)
GENDER_KEYS = {"여성": "여", "남성": "남"}

# 화면 운영시간 칩 -> 시각 구간 (자정을 넘는 구간은 둘로 나눔). "미정"은 없음
OPERATING_HOURS = {
    "아침 07~11시": [[7, 11]],
    "점심 11~15시": [[11, 15]],
    "오후 15~22시": [[15, 22]],
    "저녁 22~02시": [[22, 24], [0, 2]],
    "새벽 02~07시": [[2, 7]],
}


def build_scoring_user(
    target_ages: list[str] | None,
    target_gender: str | None,
    operating_times: list[str] | None,
) -> dict:
    user: dict = {}

    ages = [AGE_KEYS[a] for a in dict.fromkeys(target_ages or []) if a in AGE_KEYS]
    if ages:
        user["target_age"] = {age: 1 / len(ages) for age in ages}  # 고른 연령에 똑같이 나눔

    gender = GENDER_KEYS.get(target_gender or "")
    if gender:
        user["target_gender"] = {gender: 1.0}

    hours = [h for slot in dict.fromkeys(operating_times or []) for h in OPERATING_HOURS.get(slot, [])]
    if hours:
        user["hours"] = hours

    return user
