"""점수 결과에 붙일 근거 문장(detail), 위험 요인(risks), 개선 방향(improvements)을 '규칙'으로 만든다.
LLM 을 쓰지 않으므로 같은 입력이면 항상 같은 문장이 나온다 (일관성).

임계값(70, 30 등)은 임시값이다. 팀이 바꾸고 싶으면 아래 상수만 고치면 된다.
실행 확인: ml/ 폴더에서  python -m inference.explain
"""
from typing import Optional

import pandas as pd

from .scoring import AGE_KEYS, SCORING_VERSION, TIME_BANDS, _num, _sum, _to_spans, score_row
from .schemas import AnalysisResult, Indicator, Indicators, Prediction

HIGH = 70  # 이 백분위 이상이면 '위험/많음'으로 본다
LOW = 30  # 이 백분위 이하면 '낮음/짧음'으로 본다

STABILITY_NAME = {"LH": "상권확장", "HH": "정체", "LL": "다이나믹", "HL": "상권축소"}
AGE_NAME = {"10": "10대", "20": "20대", "30": "30대", "40": "40대", "50": "50대", "60_이상": "60대 이상"}
BAND_NAME = {"00_06": "0~6시", "06_11": "6~11시", "11_14": "11~14시", "14_17": "14~17시", "17_21": "17~21시", "21_24": "21~24시"}
INDICATOR_NAME = {"sales": "매출 잠재력", "competition": "경쟁 강도", "customer": "고객층 적합도", "time": "운영시간 적합도", "closure": "폐업 위험", "stability": "상권 안정성"}


def _quarter_label(code) -> str:
    """'20271' -> '2027년 1분기'. 없으면 '다음 분기'."""
    c = None if code is None or (isinstance(code, float) and pd.isna(code)) else str(code)
    if c is None or len(c) != 5:
        return "다음 분기"
    return f"{c[:4]}년 {c[4]}분기"


def _top(percentile: float) -> int:
    """백분위(클수록 상위) -> '상위 N%' 의 N. 최소 1."""
    return max(1, round(100 - percentile))


def _rank_text(percentile: float) -> str:
    """백분위를 읽기 쉬운 순위 문구로. 절반 이상이면 '상위 N%', 아니면 '하위 N%'."""
    if percentile >= 50:
        return f"상위 {_top(percentile)}%"
    return f"하위 {max(1, round(percentile))}%"


def _coverage(user: dict) -> dict:
    """사용자의 영업시간이 각 시간대 구간을 얼마나 덮는지 (0~1)."""
    spans = _to_spans(user.get("open_h"), user.get("close_h"), user.get("hours"))
    bands = user.get("bands") or []
    cov = {}
    for name, (s, e) in TIME_BANDS.items():
        c = sum(max(0, min(e, b) - max(s, a)) for a, b in spans) / (e - s)
        cov[name] = 1.0 if name in bands else min(c, 1.0)
    return cov


def _has_time_input(user: dict) -> bool:
    return bool(user.get("bands") or user.get("hours") or (user.get("open_h") is not None and user.get("close_h") is not None))


GENDER_NAME = {"여": "여성", "남": "남성"}


def _customer_detail(row, s: dict, user: dict) -> str:
    """타깃 고객층과 이 상권·업종의 실제 매출 고객층(연령·성별 비중)을 비교한 문장."""
    parts = [f"이 업종 상권 중 타깃 고객층 적합도는 {_rank_text(s['customer'])}입니다 (타깃과 실제 매출 고객층의 겹침 {s['customer_overlap']:.0f}%)"]

    ta = user.get("target_age")
    if ta:
        ages = {k: _num(row.get(f"share_연령대_{k}")) for k in AGE_KEYS}
        total = _sum(ages.values())
        ages = {k: v / total for k, v in ages.items()}  # 점수 계산(customer_fit)과 같은 기준
        order = sorted(ages.items(), key=lambda kv: -kv[1])  # 비율이 높은 순서 (같으면 AGE_KEYS 순서 유지)
        rank = {k: i + 1 for i, (k, _) in enumerate(order)}
        best = min((k for k in AGE_KEYS if k in ta), key=lambda k: rank[k])  # 선택한 타깃 중 비율이 가장 높은 연령대
        top_k, top_v = order[0]
        if rank[best] == 1:
            parts.append(f"{AGE_NAME[best]}({ages[best] * 100:.0f}%) 고객층은 이 상권·업종에서 매출 비율이 가장 높아 좋은 타깃입니다")
        else:
            parts.append(
                f"선택한 타깃 중 가장 비율이 높은 고객층은 {AGE_NAME[best]}({ages[best] * 100:.0f}%)로 전체 {rank[best]}번째입니다. "
                f"이 상권·업종에서 가장 비율이 높은 고객층은 {AGE_NAME[top_k]}({top_v * 100:.0f}%)입니다"
            )

    tg = user.get("target_gender")
    if tg:
        f = _num(row.get("share_여성"))
        share = {"여": f, "남": 1 - f}
        sel = [g for g in ("여", "남") if g in tg]
        if len(sel) == 1:  # 둘 다 고른 경우는 비교할 것이 없다
            x = share[sel[0]]
            parts.append(f"{GENDER_NAME[sel[0]]} 고객 비율은 {x * 100:.0f}%로 {'더 높은' if x >= 0.5 else '낮은'} 편입니다")
    return ". ".join(parts)


STABILITY_MEANING = {"LH": "새 점포가 늘며 커지는 상권", "HH": "개업·폐업이 모두 적은 정체된 상권", "LL": "개업·폐업이 모두 활발한 상권", "HL": "문 닫는 점포가 많아 줄어드는 상권"}


def _sales_detail(row, s: dict, n: int) -> str:
    text = f"동일 업종 {n:,}개 상권 중 예측 매출이 {_rank_text(s['sales'])}입니다"
    ps, cs = _num(row.get("predicted_sales")), _num(row.get("current_sales"))
    if ps is not None and cs:
        change = (ps / cs - 1) * 100
        text += f". {_quarter_label(row.get('predict_quarter'))} 예측 매출은 현재 기준 대비 {'+' if change >= 0 else ''}{change:.0f}% 수준입니다"
    return text


def _competition_detail(row, s: dict, p: float) -> str:
    """경쟁 근거: 점포 밀도 순위. 고객층 점수가 있으면 함께 엮어 '타깃은 맞는데 경쟁이 적다' 식으로 연결."""
    if p < 100 - HIGH:
        text = f"유동인구 대비 비슷한 업종 점포가 적어 경쟁 부담이 낮은 편입니다 (동일 업종 상권 중 점포 밀도 {_rank_text(p)})"
        c = s.get("customer")
        if c is not None and c >= HIGH:
            text += ". 선택한 타깃 고객층이 이 상권의 실제 고객 분포와 잘 맞아 경쟁력이 있습니다"
    elif p < HIGH:
        text = f"유동인구 대비 점포 밀도가 중간 수준입니다 (동일 업종 상권 중 점포 밀도 {_rank_text(p)})"
    else:
        text = f"유동인구 대비 비슷한 업종 점포가 많아 경쟁이 심한 편입니다 (동일 업종 상권 중 점포 밀도 {_rank_text(p)})"
        c = s.get("customer")
        if c is not None and c < LOW:
            text += ". 타깃 고객층도 이 상권의 실제 고객과 잘 맞지 않아 차별화가 더 필요합니다"
    return text


def _time_detail(row, s: dict) -> str:
    text = f"입력한 영업시간이 이 상권·업종 매출의 {s['time']:.0f}%가 발생하는 시간대와 겹칩니다"
    shares = {b: _num(row.get(f"share_시간대_{b}")) for b in TIME_BANDS}
    shares = {b: v for b, v in shares.items() if v is not None}
    if shares:
        b, v = max(shares.items(), key=lambda kv: kv[1])
        text += f". 매출이 가장 몰리는 시간대는 {BAND_NAME[b]}({v * 100:.0f}%)입니다"
    return text


def make_indicators(row, s: dict, user: dict) -> Indicators:
    """6개 지표마다 점수와 근거 문장(점수가 없으면 이유)을 만든다."""
    out = {}

    # 매출 잠재력
    if s["sales"] is not None:
        n = int(_num(row.get("industry_count")) or 0)
        out["sales"] = Indicator(score=s["sales"], detail=_sales_detail(row, s, n))
    else:
        out["sales"] = Indicator(reason="자료 없음")

    # 경쟁 강도 (밀도 백분위가 클수록 경쟁이 심함)
    p = _num(row.get("competition_percentile"))
    if s["competition"] is not None and p is not None:
        out["competition"] = Indicator(score=s["competition"], detail=_competition_detail(row, s, p))
    else:
        out["competition"] = Indicator(reason="자료 없음 (유동인구 자료가 없는 상권)")

    # 고객층 적합도
    if s["customer"] is not None:
        out["customer"] = Indicator(score=s["customer"], detail=_customer_detail(row, s, user))
    elif not (user.get("target_age") or user.get("target_gender")):
        out["customer"] = Indicator(reason="타깃 고객층이 입력되지 않았습니다")
    else:
        out["customer"] = Indicator(reason="자료 없음 (이 상권·업종의 연령·성별 매출 자료 없음)")

    # 운영시간 적합도
    if s["time"] is not None:
        out["time"] = Indicator(score=s["time"], detail=_time_detail(row, s))
    else:
        out["time"] = Indicator(reason="영업시간이 입력되지 않았습니다")

    # 폐업 위험 (폐업 확률 백분위가 클수록 위험)
    cp = _num(row.get("closure_percentile"))
    prob = _num(row.get("closure_prob"))
    if s["closure"] is not None and cp is not None:
        word = "낮은 편" if cp < 100 - HIGH else "중간 수준" if cp < HIGH else "높은 편"
        extra = f". {_quarter_label(row.get('predict_quarter'))}에 폐업률이 10% 이상일 확률은 약 {prob * 100:.0f}%로 예측됩니다" if prob is not None else ""
        out["closure"] = Indicator(score=s["closure"], detail=f"동일 업종 상권 대비 폐업 위험이 {word}입니다{extra}")
    else:
        out["closure"] = Indicator(reason="자료 없음")

    # 상권 안정성
    if s["stability"] is not None:
        label = row.get("stability_label")
        parts = []
        if label in STABILITY_NAME:
            parts.append(f"상권 변화 지표는 '{STABILITY_NAME[label]}'({STABILITY_MEANING[label]})")
        tp = _num(row.get("tenure_percentile"))
        if tp is not None:
            parts.append(f"운영 영업 기간은 동일 업종 상권 중 {_rank_text(tp)}")
        out["stability"] = Indicator(score=s["stability"], detail=", ".join(parts) + "입니다")
    else:
        out["stability"] = Indicator(reason="자료 없음")

    return Indicators(**out)


def make_risks(row, s: dict) -> list:
    risks = []
    cp = _num(row.get("closure_percentile"))
    if cp is not None and cp >= HIGH:
        risks.append(f"동일 업종 대비 폐업 위험이 높은 편입니다 (폐업 위험 상위 {_top(cp)}%)")
    comp = _num(row.get("competition_percentile"))
    if comp is not None and comp >= HIGH:
        risks.append("유동인구 대비 점포가 많아 경쟁이 심한 편입니다")
    if row.get("stability_label") == "HL":
        risks.append("상권이 축소되는 추세(상권축소)입니다")
    tp = _num(row.get("tenure_percentile"))
    if tp is not None and tp <= LOW:
        risks.append("운영 영업 기간이 동일 업종 상권 중 짧은 편입니다")
    sp = _num(row.get("sales_percentile"))
    if sp is not None and sp <= LOW:
        risks.append("예측 매출이 동일 업종 상권 중 하위권입니다")
    if s["time"] is not None and s["time"] < 50:
        risks.append("영업시간이 매출이 많은 시간대와 겹치는 비중이 낮습니다")
    if s["reliability"] != "높음":
        names = ", ".join(INDICATOR_NAME[k] for k in s["missing"])
        risks.append(f"일부 지표({names})가 계산되지 않아 종합 점수의 신뢰도가 '{s['reliability']}'입니다")
    return risks


def make_improvements(row, s: dict, user: dict) -> list:
    tips = []
    # 영업시간: 매출은 몰려 있는데 영업시간이 덮지 못하는 구간
    if s["time"] is not None and s["time"] < 80 and _has_time_input(user):
        cov = _coverage(user)
        gaps = {b: float(row[f"share_시간대_{b}"]) * (1 - cov[b]) for b in TIME_BANDS if _num(row.get(f"share_시간대_{b}")) is not None}
        if gaps:
            b, gap = max(gaps.items(), key=lambda kv: kv[1])
            if gap >= 0.08:
                tips.append(f"이 상권·업종은 {BAND_NAME[b]}에 매출의 {float(row[f'share_시간대_{b}']) * 100:.0f}%가 발생합니다. 이 시간대까지 영업하면 운영시간 적합도를 높일 수 있습니다")
    # 고객층: 타깃과 실제 매출 고객이 다를 때 (겹침 % 기준)
    ov = s.get("customer_overlap")
    if ov is not None and ov < 40 and user.get("target_age"):
        ages = {k: _num(row.get(f"share_연령대_{k}")) for k in AGE_KEYS}
        ages = {k: v for k, v in ages.items() if v is not None}
        total = _sum(ages.values())
        if ages and total > 0:
            ages = {k: v / total for k, v in ages.items()}  # 점수 계산(customer_fit)과 같은 기준으로 맞춤
            top, v = max(ages.items(), key=lambda kv: kv[1])
            # 타깃이 아닌 연령대가 주요 고객이고, 타깃과의 겹침보다 확실히(10%p 이상) 클 때만 안내
            if top not in user["target_age"] and v - ov / 100 >= 0.10:
                tips.append(f"이 상권·업종의 주요 매출 고객은 {AGE_NAME[top]}({v * 100:.0f}%)입니다. 타깃 고객층을 조정하거나 이 고객층을 함께 겨냥하는 것을 검토해 보세요")
    comp = _num(row.get("competition_percentile"))
    if comp is not None and comp >= HIGH:
        tips.append("경쟁 점포가 많으므로 메뉴·가격·서비스에서 차별화 요소를 준비하세요")
    cp = _num(row.get("closure_percentile"))
    if cp is not None and cp >= HIGH:
        tips.append("폐업 위험이 높은 편이므로 초기 투자금과 고정비 부담을 보수적으로 계획하세요")
    return tips


def build_result(row, user: Optional[dict] = None, analysis_id: Optional[int] = None, peers: Optional[list] = None, peer_fits: Optional[list] = None) -> AnalysisResult:
    """predictions.csv 한 행 + 사용자 입력 -> 화면/백엔드로 넘길 결과 (schemas.AnalysisResult).
    타깃 고객층을 입력했다면 같은 업종 상권 목록(peers, 이 상권 포함)이 필요하다 (고객층 순위 계산용)."""
    user = user or {}
    s = score_row(row, user, peers, peer_fits)
    ps = _num(row.get("predicted_sales"))
    return AnalysisResult(
        analysis_id=analysis_id,
        area_code=str(row["상권_코드"]),
        industry_code=str(row["서비스_업종_코드"]),
        total_score=s["total"],
        reliability=s["reliability"],
        indicators=make_indicators(row, s, user),
        prediction=Prediction(
            base_quarter=str(row["base_quarter"]),
            predict_quarter=str(row["predict_quarter"]),
            predicted_sales=None if ps is None else int(round(ps)),
        ),
        risks=make_risks(row, s),
        improvements=make_improvements(row, s, user),
        model_version=str(row["model_version"]),
        scoring_version=SCORING_VERSION,
    )

