"""
상권×업종 분석 (ML 팀 서비스 app/data/analysis 를 감싸는 얇은 층)

- 점수·근거 문장·위험/개선 문장·예측 매출·정보판: ML 팀 AnalysisService (app/data/analysis, model_weight3.pth)
- 화면용 차트 데이터(요일/시간대 매출, 손님, 유동인구, 개업·폐업, 평균 비교, 상위 N%): 같은 입력표에서 뽑는다
- 서버 시작 후 첫 호출 때 한 번 로드 (약 5초), 이후 호출은 0.1초 미만
"""
import math
from functools import lru_cache

IND = "서비스_업종_코드"
WEEKDAYS = [("월", "월요일"), ("화", "화요일"), ("수", "수요일"), ("목", "목요일"), ("금", "금요일"), ("토", "토요일"), ("일", "일요일")]
AGES = ["10", "20", "30", "40", "50", "60_이상"]
HOURS = [("00~06", "00_06"), ("06~11", "06_11"), ("11~14", "11_14"), ("14~17", "14_17"), ("17~21", "17_21"), ("21~24", "21_24")]


@lru_cache(maxsize=1)
def _service():
    """ML 서비스 로드. 파일/라이브러리 문제로 실패하면 None"""
    try:
        from app.data.analysis import AnalysisService
        return AnalysisService()
    except Exception as e:  # noqa: BLE001 - 어떤 이유든 서버가 죽지 않게 하고 503 으로 안내
        print(f"[분석 모델 로드 실패] {type(e).__name__}: {e}")
        return None


def is_model_loaded() -> bool:
    return _service() is not None


def _f(v) -> float:
    v = float(v)
    return 0.0 if math.isnan(v) else v


def _quarter_code(base: str, back: int) -> str:
    idx = int(base[:4]) * 4 + int(base[4]) - 1 - back
    return f"{idx // 4}{idx % 4 + 1}"


def _closure_grade(prob: float) -> str:
    # 모델의 폐업 확률 = '다음 분기 폐업률이 10% 이상일 확률'
    return "낮음" if prob < 0.2 else "보통" if prob < 0.5 else "높음"


def _build_extra(svc, row, industry_df, rank_percent: float) -> dict:
    """화면용 추가 데이터 (프론트 AnalysisResultDetail 형태). 모두 가장 최근 기준 분기 값"""
    base = svc.base_q
    # 입력표에 있는 과거 분기: 현재, 1·2분기 전, 4분기 전 (3분기 전은 없음)
    open_close = [
        {
            "quarter": _quarter_code(base, back),
            "open": int(_f(row[f"{p}개업_점포_수"])),
            "close": int(_f(row[f"{p}폐업_점포_수"])),
        }
        for back, p in ((4, "lag4_"), (2, "lag2_"), (1, "lag1_"), (0, ""))
    ]

    def mean(col: str) -> float:
        return _f(industry_df[col].mean())

    return {
        "sales_by_weekday": {k: _f(row[f"{c}_매출_금액"]) for k, c in WEEKDAYS},
        "sales_by_hour": {k: _f(row[f"시간대_{c}_매출_금액"]) for k, c in HOURS},
        "customer_by_age": {k: _f(row[f"연령대_{k}_매출_건수"]) for k in AGES},
        "customer_by_gender": {"여": _f(row["여성_매출_건수"]), "남": _f(row["남성_매출_건수"])},
        "foot_traffic": {
            "age": {k: _f(row[f"연령대_{k}_유동인구_수"]) for k in AGES},
            "hour": {k: _f(row[f"시간대_{c}_유동인구_수"]) for k, c in HOURS},
            "weekday": {k: _f(row[f"{c}_유동인구_수"]) for k, c in WEEKDAYS},
        },
        "open_close_trend": open_close,
        "compare_average": [
            {"label": "점포 수", "mine": _f(row["점포_수"]), "average": mean("점포_수"), "unit": "개"},
            {"label": "점포당 매출", "mine": _f(row["점포당_매출"]), "average": mean("점포당_매출"), "unit": "원"},
            {"label": "개업률", "mine": _f(row["개업_률"]), "average": mean("개업_률"), "unit": "%"},
            {"label": "폐업률", "mine": _f(row["폐업_률"]), "average": mean("폐업_률"), "unit": "%"},
            {"label": "유동인구", "mine": _f(row["총_유동인구_수"]), "average": mean("총_유동인구_수"), "unit": "명"},
        ],
        "rank_percent": rank_percent,
    }


def has_prediction(trdar_cd: str, industry_cd: str) -> bool:
    svc = _service()
    if not svc or industry_cd not in svc.groups:
        return False
    return bool((svc.groups[industry_cd]["상권_코드"] == trdar_cd).any())


def _rank_percent(svc, industry_cd: str, trdar_cd: str, horizon: int) -> float:
    """사용자 입력 없이 점수를 매겼을 때 같은 업종 안에서 상위 몇 %인지"""
    from app.data.analysis.scoring import score_row

    peers = svc.predict_industry(industry_cd, horizon)
    totals = [score_row(r, {}, None)["total"] for r in peers.to_dict("records")]
    mine = totals[int((peers["상권_코드"] == trdar_cd).to_numpy().argmax())]
    return round(sum(1 for t in totals if t is not None and t > mine) / len(totals) * 100, 1)


def analyze(trdar_cd: str, industry_cd: str, user: dict) -> dict | None:
    """ML 응답(camelCase 그대로, estimateType: normal/noData/invalidInput) + normal 일 때 화면용 값. 모델을 못 불러오면 None"""
    svc = _service()
    if svc is None:
        return None

    ml = svc.analyze(trdar_cd, industry_cd, user)
    if ml["estimateType"] != "normal":
        return {"ml": ml}

    from app.data.analysis.service import pick_predict_quarter

    h = pick_predict_quarter(svc.base_q)["horizon"]
    peers = svc.predict_industry(industry_cd, h)
    prow = peers[peers["상권_코드"] == trdar_cd].iloc[0]
    group = svc.groups[industry_cd]
    row = group[group["상권_코드"] == trdar_cd].iloc[0]

    current = int(prow["current_sales"])
    predicted = ml["prediction"]["predictedSales"]
    prob = float(prow["closure_prob"])
    return {
        "ml": ml,
        "horizon": h,
        "current_sales": current,
        "sales_change_rate": round(predicted / current - 1, 4) if predicted and current else None,
        "closure_probability": prob,
        "closure_grade": _closure_grade(prob),
        "store_count": int(_f(row["점포_수"])),
        "similar_store_count": int(_f(row["유사_업종_점포_수"])),
        "extra": _build_extra(svc, row, group, _rank_percent(svc, industry_cd, trdar_cd, h)),
    }


def sales_area_codes() -> set | None:
    """매출 데이터가 있는 상권 코드들 (이 밖의 상권은 점수 없이 정보판만 나간다). 모델을 못 불러오면 None"""
    svc = _service()
    return None if svc is None else svc.sales_areas


def list_industries(trdar_cd: str) -> list | None:
    """상권 기준 업종 목록과 상태(analyzed / noRecord / unsupported). 모델을 못 불러오면 None"""
    svc = _service()
    return None if svc is None else svc.list_industries(trdar_cd)


def get_extra(trdar_cd: str, industry_cd: str) -> dict | None:
    """화면용 추가 데이터만 계산 (예전에 저장된 결과에 추가 필드가 없을 때 보충용)"""
    svc = _service()
    if svc is None or not has_prediction(trdar_cd, industry_cd):
        return None
    from app.data.analysis.service import pick_predict_quarter

    group = svc.groups[industry_cd]
    row = group[group["상권_코드"] == trdar_cd].iloc[0]
    h = pick_predict_quarter(svc.base_q)["horizon"]
    return _build_extra(svc, row, group, _rank_percent(svc, industry_cd, trdar_cd, h))


def get_model_store_count(trdar_cd: str, industry_cd: str) -> dict | None:
    """모델 입력표의 해당 상권×업종 점포 수 (기준 분기 시점). 기록이 없으면 None"""
    svc = _service()
    if svc is None or not has_prediction(trdar_cd, industry_cd):
        return None
    group = svc.groups[industry_cd]
    row = group[group["상권_코드"] == trdar_cd].iloc[0]
    return {"count": int(_f(row["점포_수"])), "base_quarter": svc.base_q}


def industry_name(industry_cd: str) -> str | None:
    """모델 업종 코드의 이름 (ML 팀 업종 이름표). 모델을 못 불러오면 None"""
    if _service() is None:
        return None
    from app.data.analysis.panel import IND_NAME

    return IND_NAME.get(industry_cd)
