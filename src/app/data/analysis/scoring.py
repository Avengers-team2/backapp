"""6개 지표를 0~100 점수로 바꾸고 가중합하는 계산 (모델과 분리 -> 가중치를 바꿔도 재학습 불필요).

입력: data/processed/predictions.csv 의 한 행(상권×업종) + 사용자 입력(타깃 고객, 영업시간)
출력: 6개 지표 점수, 종합 점수, 신뢰도

[결정 기록]
- 매출 잠재력   : 예측 매출의 같은 업종 내 백분위 (높을수록 좋음)
- 경쟁 강도     : 유동인구 1,000명당 유사 업종 점포 수의 업종 내 백분위를 뒤집음 (밀도가 낮을수록 좋음 - 가정)
- 고객층 적합도 : 사용자가 정한 타깃 연령·성별 분포와 그 상권×업종의 '매출 비중'이 겹치는 정도(겹침 %)를 구하고,
                  점수는 그 겹침이 같은 업종 상권들 중 차지하는 순위(백분위)로 쓴다 (다른 지표와 같은 눈높이). 화면에는 겹침 %도 설명으로 보여준다.
- 운영시간 적합도: 영업시간이 걸치는 시간대의 매출 비중 합. 6구간 안은 균등 분포로 가정 (정밀도 낮음 -> 화면에 안내)
- 폐업 위험     : 폐업 확률(다음 분기 폐업률 10% 이상)의 업종 내 백분위를 뒤집음 (낮을수록 좋음)
- 상권 안정성   : 변화지표 라벨 점수와 운영 영업 개월 수 백분위의 평균 (라벨 점수는 임시값, 팀 합의 필요)
- 값이 없는 지표는 0점이 아니라 빼고, 남은 가중치를 다시 나눈다 (멘토 제안). 대신 신뢰도로 알려준다.
- 이중 반영 주의: 경쟁 강도와 폐업 위험은 둘 다 점포 정보를 일부 반영한다 (가중치 조정/발표 때 설명).
- 등급(A~D) 기준은 아직 없음 (백테스트로 근거를 만든 뒤 정함).
"""
from typing import Optional

import pandas as pd

# 점수 계산 규칙의 버전. 아래 값(WEIGHTS, STABILITY_LABEL_SCORE)이나 explain.py 의 기준값(HIGH, LOW)·문장 규칙을
# 바꾸면 이 값도 올린다 (s1 -> s2). 결과에 같이 저장되어, 나중에 점수가 다를 때 원인(데이터/모델/규칙)을 구분할 수 있다.
# 자바스크립트(inference_js/scoring.js)의 SCORING_VERSION 과 항상 같아야 한다.
SCORING_VERSION = "s5"  # s1: 초안 가중치(25/20/15/10/20/10) -> s2: 가중치 조정 (3-G) -> s3: 고객층 점수를 업종 내 순위로 (3-H) -> s4: 폐업 문구에 예측 분기 표시 (3-I)

WEIGHTS = {
    "sales": 0.30,
    "competition": 0.10,  # 백테스트에서 근거가 약해(오히려 반대 방향) 20 -> 10
    "customer": 0.15,
    "time": 0.10,
    "closure": 0.25,
    "stability": 0.10,
}

# 상권 변화 지표 라벨 -> 안정성 점수 (임시값, 팀 합의 필요)
STABILITY_LABEL_SCORE = {"LH": 90, "HH": 70, "LL": 50, "HL": 20}  # LH=상권확장, HH=정체, LL=다이나믹, HL=상권축소

# 시간대 구간 (시작시, 끝시). 컬럼은 share_시간대_{이름}
TIME_BANDS = {"00_06": (0, 6), "06_11": (6, 11), "11_14": (11, 14), "14_17": (14, 17), "17_21": (17, 21), "21_24": (21, 24)}
AGE_KEYS = ["10", "20", "30", "40", "50", "60_이상"]


def _num(x) -> Optional[float]:
    """빈 값(None/NaN)이면 None, 아니면 float."""
    if x is None or pd.isna(x):
        return None
    return float(x)


def _sum(values) -> float:
    """왼쪽부터 차례로 더한다. 파이썬 3.12+ 의 sum() 은 오차를 보정해서 버전에 따라 결과가 달라지고
    JS 구현과도 어긋나므로, 점수 계산에서는 sum() 대신 이 함수를 쓴다."""
    total = 0.0
    for v in values:
        total += v
    return total


def _normalize(d: dict) -> dict:
    """합이 1이 되도록 맞춘다. 음수/전부 0이면 오류."""
    s = _sum(d.values())
    if any(v < 0 for v in d.values()) or s <= 0:
        raise ValueError(f"비중이 올바르지 않음: {d}")
    return {k: v / s for k, v in d.items()}


def combine_scores(parts: dict) -> tuple:
    """값이 없는 지표(None)는 빼고 남은 가중치로 다시 나눔 -> (종합점수, 신뢰도, 빠진 지표 목록)"""
    valid = {k: v for k, v in parts.items() if v is not None}
    missing = [k for k in WEIGHTS if parts.get(k) is None]
    if not valid:
        return None, "낮음", missing
    w_sum = round(_sum(WEIGHTS[k] for k in valid), 9)  # 0.7999999999999999 같은 오차로 기준(0.8)이 어긋나지 않게
    total = round(_sum(WEIGHTS[k] * v for k, v in valid.items()) / w_sum, 9)
    reliability = "높음" if w_sum >= 0.8 else "보통" if w_sum >= 0.5 else "낮음"
    return round(total, 1), reliability, missing


def customer_fit(row, target_age: Optional[dict] = None, target_gender: Optional[dict] = None) -> Optional[float]:
    """타깃 분포와 상권×업종 매출 비중이 겹치는 정도 (0~100).
    target_age 예: {"20": 0.5, "30": 0.5}, target_gender 예: {"여": 0.7, "남": 0.3}
    둘 다 안 주면 None (지표에서 제외). 둘 다 주면 평균.
    """
    parts = []
    if target_age:
        area = {k: _num(row.get(f"share_연령대_{k}")) for k in AGE_KEYS}
        if any(v is None for v in area.values()):
            return None
        total = _sum(area.values())
        if total <= 0:
            return None
        area = {k: v / total for k, v in area.items()}
        t = _normalize(target_age)
        unknown = [k for k in t if k not in area]
        if unknown:
            raise ValueError(f"알 수 없는 연령대: {unknown} (가능: {AGE_KEYS})")
        parts.append(_sum(min(p, area[k]) for k, p in t.items()))
    if target_gender:
        f = _num(row.get("share_여성"))
        if f is None:
            return None
        area = {"여": f, "남": 1 - f}
        t = _normalize(target_gender)
        unknown = [k for k in t if k not in area]
        if unknown:
            raise ValueError(f"알 수 없는 성별: {unknown} (가능: 여, 남)")
        parts.append(_sum(min(p, area[k]) for k, p in t.items()))
    if not parts:
        return None
    return round(_sum(parts) / len(parts) * 100, 1)


def _to_spans(open_h: Optional[int], close_h: Optional[int], hours: Optional[list]) -> list:
    """영업시간 입력을 겹치지 않는 (시작, 끝) 구간 목록으로 만든다.
    - 구간 1개: open_h, close_h  /  여러 개: hours=[(11, 14), (17, 22)]
    - 밤을 넘기는 영업(18~2시)은 (18,24)+(0,2) 로 나누고, 겹치는 구간은 합쳐서 두 번 세지 않는다.
    """
    pairs = list(hours) if hours else ([(open_h, close_h)] if open_h is not None and close_h is not None else [])
    spans = []
    for a, b in pairs:
        if not (0 <= a <= 24 and 0 <= b <= 24) or a == b:
            raise ValueError(f"영업시간이 올바르지 않음: {a}~{b} (0~24, 시작과 끝이 같으면 안 됨)")
        spans += [(a, b)] if a < b else [(a, 24), (0, b)]
    merged = []
    for a, b in sorted(spans):
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    return merged


def time_fit(
    row,
    open_h: Optional[int] = None,
    close_h: Optional[int] = None,
    hours: Optional[list] = None,
    bands: Optional[list] = None,
) -> Optional[float]:
    """영업시간이 걸치는 시간대의 매출 비중 합 (0~100). 입력 방식은 3가지 (섞어서 써도 됨):
    - bands: 6개 시간대 구간을 여러 개 고름. 예) ["06_11", "11_14", "14_17", "17_21"]
             고른 구간의 매출 비중을 그대로 더한다 (정확, 균등 분포 가정 필요 없음)
    - hours: 시각 구간 여러 개. 예) [(11, 14), (17, 22)]  (구간 안은 균등 분포로 가정 -> 정밀도 낮음)
    - open_h, close_h: 시각 구간 1개. 밤을 넘기는 영업(18~2시)도 처리
    아무것도 안 주면 None (지표에서 제외). 같은 구간이 겹쳐도 두 번 세지 않는다.
    """
    if bands:
        unknown = [b for b in bands if b not in TIME_BANDS]
        if unknown:
            raise ValueError(f"알 수 없는 시간대: {unknown} (가능: {list(TIME_BANDS)})")
    spans = _to_spans(open_h, close_h, hours)
    if not spans and not bands:
        return None
    share = 0.0
    for name, (s, e) in TIME_BANDS.items():
        v = _num(row.get(f"share_시간대_{name}"))
        if v is None:
            return None
        covered = sum(max(0, min(e, b) - max(s, a)) for a, b in spans) / (e - s)  # 시각 입력이 이 구간을 덮는 비율
        if bands and name in bands:
            covered = 1.0
        share += v * min(covered, 1.0)
    return round(min(share, 1.0) * 100, 1)


def stability_score(label: Optional[str], tenure_percentile) -> Optional[float]:
    """라벨 점수와 운영 영업 개월 백분위의 평균. 하나만 있으면 그것만 쓴다."""
    parts = []
    if label in STABILITY_LABEL_SCORE:
        parts.append(STABILITY_LABEL_SCORE[label])
    t = _num(tenure_percentile)
    if t is not None:
        parts.append(t)
    return round(_sum(parts) / len(parts), 1) if parts else None


def percentile_in(values: list, x: float) -> Optional[float]:
    """x 가 values 안에서 차지하는 백분위 (0~100, 클수록 상위). 같은 값은 평균 순위 (pandas rank(pct=True) 와 같은 방식)."""
    if not values:
        return None
    less = sum(1 for v in values if v < x)
    equal = sum(1 for v in values if v == x)
    rank = less + (equal + 1) / 2
    return round(rank / len(values) * 100, 1)


def score_row(row, user: Optional[dict] = None, peers: Optional[list] = None, peer_fits: Optional[list] = None) -> dict:
    """한 상권×업종의 6개 지표와 종합 점수.
    user 예: {"target_age": {"20": 0.6, "30": 0.4}, "target_gender": {"여": 1.0}, "open_h": 10, "close_h": 22}
    영업 구간이 여러 개면 "hours": [(11, 14), (17, 22)] 로 주고,
    6개 시간대를 직접 고르는 화면이면 "bands": ["06_11", "11_14", "14_17", "17_21"] 로 준다 (이쪽이 더 정확).

    고객층 점수는 '같은 업종 상권들 중 순위'(백분위)로 계산한다 (다른 지표와 같은 눈높이로 맞추기 위해).
    그래서 타깃을 입력했다면 같은 업종의 다른 상권들(peers, 이 상권 포함)이 필요하다.
    같은 업종을 여러 번 점수화할 때는 peer_fits(각 상권의 겹침 값 목록)를 미리 계산해 넘기면 빠르다.
    결과의 customer_overlap 은 '타깃과 실제 매출 고객층이 겹치는 비율'(화면 설명용)이다.
    """
    user = user or {}
    comp = _num(row.get("competition_percentile"))
    clos = _num(row.get("closure_percentile"))
    ta, tg = user.get("target_age"), user.get("target_gender")
    overlap = customer_fit(row, ta, tg)
    customer = None
    if overlap is not None:
        if peer_fits is None:
            if peers is None:
                raise ValueError("고객층 순위를 계산하려면 같은 업종 상권 목록(peers)이 필요합니다")
            peer_fits = [customer_fit(p, ta, tg) for p in peers]
        customer = percentile_in([f for f in peer_fits if f is not None], overlap)
    parts = {
        "sales": _num(row.get("sales_percentile")),
        "competition": None if comp is None else round(100 - comp, 1),
        "customer": customer,
        "time": time_fit(row, user.get("open_h"), user.get("close_h"), user.get("hours"), user.get("bands")),
        "closure": None if clos is None else round(100 - clos, 1),
        "stability": stability_score(row.get("stability_label"), row.get("tenure_percentile")),
    }
    total, reliability, missing = combine_scores(parts)
    return {**parts, "total": total, "reliability": reliability, "missing": missing, "customer_overlap": overlap}


def score_industry(pred: pd.DataFrame, industry_code: str, user: Optional[dict] = None) -> pd.DataFrame:
    """한 업종의 모든 상권을 점수화해서 종합 점수 순으로 돌려준다."""
    sub = pred[pred["서비스_업종_코드"] == industry_code]
    user = user or {}
    fits = [customer_fit(r, user.get("target_age"), user.get("target_gender")) for _, r in sub.iterrows()]  # 한 번만 계산
    rows = [{"상권_코드": r["상권_코드"], **score_row(r, user, peer_fits=fits)} for _, r in sub.iterrows()]
    return pd.DataFrame(rows).sort_values("total", ascending=False).reset_index(drop=True)

