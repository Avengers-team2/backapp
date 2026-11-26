"""점수를 낼 수 없는 조합에서 점수 대신 보여줄 '정보판'.
점수는 내지 않고(물음표) 실제 데이터와 '비슷한 상권' 데이터를 보여준다. 모델 예측이 아니라 데이터에 있는 그대로의 값이다.

  areaProfile      : 이 상권의 유동인구·유형·변화 지표·영업 개월            (모든 상권 1,650개 가능)
  otherIndustries  : 이 상권의 다른 업종 현황 (매출 기록이 있으면 매출 순, 없으면 점포 수 순)
  similarAreas     : 비슷한 상권 요약과 목록 (유동인구 등이 비슷한 상권 중 이 업종이 있는 곳)
  referenceSales   : 비슷한 상권의 같은 업종 현재 매출 (매출 데이터가 있는 업종만)

점수를 못 내는 이유(reason)
  noRecord            : 지원하는 업종인데 이 상권에 매출 기록이 없음
  unsupportedIndustry : 매출 데이터가 없는 업종 (점포 데이터만 있음)
  areaWithoutSales    : 매출 데이터가 없는 상권 (유동인구·점포 데이터만 있음)
"""
from pathlib import Path

import numpy as np
import pandas as pd

IND, AREA, K = "서비스_업종_코드", "상권_코드", 20
DATA = Path(__file__).resolve().parent / "data"
AREA_TYPE = {"A": "발달상권", "D": "골목상권", "R": "전통시장", "U": "관광특구"}
CHANGE_NAME = {"LH": "상권확장", "HH": "정체", "LL": "다이나믹", "HL": "상권축소"}
CHANGE_MEANING = {"LH": "새 점포가 늘며 커지는 상권", "HH": "개업·폐업이 모두 적은 정체된 상권", "LL": "개업·폐업이 모두 활발한 상권", "HL": "문 닫는 점포가 많아 줄어드는 상권"}
AGE = {"10": "10대", "20": "20대", "30": "30대", "40": "40대", "50": "50대", "60_이상": "60대 이상"}
BAND = {"00_06": "0~6시", "06_11": "6~11시", "11_14": "11~14시", "14_17": "14~17시", "17_21": "17~21시", "21_24": "21~24시"}


def _names() -> tuple:
    a = pd.read_csv(DATA / "district_names.csv", dtype=str, encoding="utf-8-sig")
    i = pd.read_csv(DATA / "industry_names.csv", dtype=str, encoding="utf-8-sig")
    return dict(zip(a["상권_코드"], a["상권_코드_명"])), dict(zip(i["서비스_업종_코드"], i["서비스_업종_코드_명"]))


AREA_NAME, IND_NAME = _names()


def _f(x, nd=None):
    if x is None or pd.isna(x):
        return None
    return round(float(x), nd) if nd is not None else int(round(float(x)))


def knn_rows(cand: np.ndarray, q: np.ndarray, k: int = K) -> np.ndarray:
    """후보 행렬(cand)에서 질의(q)와 가장 가까운 k개 행의 위치 (표준화한 거리, 빈 값은 중앙값으로)."""
    med = np.nanmedian(cand, axis=0)
    med = np.where(np.isnan(med), 0.0, med)
    cand = np.where(np.isnan(cand), med, cand)
    q = np.where(np.isnan(q), med, q)
    mu, sd = cand.mean(axis=0), cand.std(axis=0)
    sd[sd == 0] = 1.0
    dist = (((cand - q) / sd) ** 2).sum(axis=1)
    return np.argsort(dist, kind="stable")[: min(k, len(cand))]


def area_profile(area: str, area_tbl: pd.DataFrame, store_tbl: pd.DataFrame) -> dict:
    a = area_tbl.loc[area]
    pop = a["총_유동인구_수"]
    ages = {AGE[k]: a.get(f"연령대_{k}_유동인구_수") for k in AGE}
    ages = {n: float(v) for n, v in ages.items() if pd.notna(v)}
    bands = {BAND[k]: a.get(f"시간대_{k}_유동인구_수") for k in BAND}
    bands = {n: float(v) for n, v in bands.items() if pd.notna(v)}
    wk = [a.get("토요일_유동인구_수"), a.get("일요일_유동인구_수")]
    top_age = max(ages.items(), key=lambda kv: kv[1]) if ages else None
    top_band = max(bands.items(), key=lambda kv: kv[1]) if bands else None
    chg = str(a["상권_변화_지표"]) if pd.notna(a["상권_변화_지표"]) else None
    s = store_tbl[(store_tbl[AREA] == area) & (store_tbl["점포_수"] > 0)]
    return {
        "areaName": AREA_NAME.get(area), "areaType": AREA_TYPE.get(a["상권_구분_코드"], a["상권_구분_코드"]),
        "changeIndicator": None if chg is None else {"code": chg, "name": CHANGE_NAME.get(chg), "meaning": CHANGE_MEANING.get(chg)},
        "floatingPopulation": None if pd.isna(pop) else {
            "total": _f(pop),
            "topAgeGroup": None if not top_age else {"name": top_age[0], "share": round(top_age[1] / sum(ages.values()), 3)},
            "busiestTimeBand": None if not top_band else {"name": top_band[0], "share": round(top_band[1] / sum(bands.values()), 3)},
            "weekendShare": None if any(pd.isna(w) for w in wk) else round(float(sum(wk)) / float(pop), 3),
        },
        "operatingMonthsAvg": _f(a["운영_영업_개월_평균"], 1), "closedMonthsAvg": _f(a["폐업_영업_개월_평균"], 1),
        "industryCountInArea": int(len(s)), "storeCountInArea": _f(s["점포_수"].sum()),
    }


def other_industries(area: str, sales_df: pd.DataFrame, store_tbl: pd.DataFrame) -> dict:
    """매출 기록이 있는 상권은 매출 순, 없는 상권은 점포 수 순."""
    rows = sales_df[sales_df[AREA] == area]
    if len(rows):
        top = rows.sort_values("당월_매출_금액", ascending=False).head(8)
        items = [{"industryCode": r[IND], "industryName": IND_NAME.get(r[IND]), "sales": _f(r["당월_매출_금액"]), "storeCount": _f(r["점포_수"]), "closeRate": _f(r["폐업_률"], 1)} for _, r in top.iterrows()]
        return {"basis": "sales", "items": items}
    s = store_tbl[(store_tbl[AREA] == area) & (store_tbl["점포_수"] > 0)].sort_values("점포_수", ascending=False).head(8)
    items = [{"industryCode": r[IND], "industryName": IND_NAME.get(r[IND]), "sales": None, "storeCount": _f(r["점포_수"]), "closeRate": _f(r["폐업_률"], 1)} for _, r in s.iterrows()]
    return {"basis": "storeCount", "items": items}


def _sales_similar(est, area: str, industry: str, area_tbl: pd.DataFrame):
    """매출 데이터가 있는 업종: 같은 업종 기록이 있는 상권 중 비슷한 상권 (유동인구, 있으면 주변 업종 매출)."""
    g = est.df[est.df[IND] == industry]
    own = est.df[est.df[AREA] == area]
    pop = area_tbl.loc[area, "총_유동인구_수"]
    qpop = np.log1p(pop) if pd.notna(pop) else np.nan
    if len(own):
        feats, q = ["log_pop", "ctx_other_sales_log"], np.array([qpop, np.log1p(float(own["당월_매출_금액"].fillna(0).sum()))], dtype=float)
    else:
        feats, q = ["log_pop"], np.array([qpop], dtype=float)
    nb = g.iloc[knn_rows(g[feats].to_numpy(dtype=float), q)]
    s = nb["당월_매출_금액"].dropna()
    sh = nb[[c for c in nb.columns if c.startswith("비중_")]].mean()
    ta = max(((AGE[k], sh.get(f"비중_연령대_{k}")) for k in AGE if pd.notna(sh.get(f"비중_연령대_{k}"))), key=lambda kv: kv[1], default=None)
    tb = max(((BAND[k], sh.get(f"비중_시간대_{k}")) for k in BAND if pd.notna(sh.get(f"비중_시간대_{k}"))), key=lambda kv: kv[1], default=None)
    summary = {
        "basis": "sales", "count": int(len(nb)), "closeRateAvg": _f(nb["폐업_률"].mean(), 1), "storeCountMedian": _f(nb["점포_수"].median()),
        "topCustomerAge": None if ta is None else {"name": ta[0], "share": round(float(ta[1]), 3)},
        "topSalesTimeBand": None if tb is None else {"name": tb[0], "share": round(float(tb[1]), 3)}, "femaleShare": _f(sh.get("비중_여성"), 3),
    }
    top5 = [{"areaCode": r[AREA], "areaName": AREA_NAME.get(r[AREA]), "sales": _f(r["당월_매출_금액"]), "storeCount": _f(r["점포_수"]), "closeRate": _f(r["폐업_률"], 1),
             "floatingPopulation": _f(r["총_유동인구_수"])} for _, r in nb.head(5).iterrows()]
    ref = {"median": _f(s.median()), "low": _f(s.quantile(0.25)), "high": _f(s.quantile(0.75)), "count": int(len(s)),
           "basis": f"유동인구 등이 비슷한 상권 {len(s)}곳의 같은 업종 매출(분기 3개월 합계 기준, 최근 분기) 중앙값과 25~75% 범위"}
    return {"summary": summary, "top5": top5}, ref


def _store_similar(area: str, industry: str, area_tbl: pd.DataFrame, store_tbl: pd.DataFrame):
    """매출 데이터가 없는 업종: 점포 데이터로 비슷한 상권 (유동인구, 상권의 전체 점포 수)."""
    total = store_tbl.groupby(AREA)["점포_수"].sum()
    s = store_tbl[(store_tbl[IND] == industry) & (store_tbl["점포_수"] > 0) & (store_tbl[AREA] != area)].copy()
    if s.empty:
        return None
    s = s.join(area_tbl[["총_유동인구_수"]], on=AREA)
    s["lp"] = np.log1p(s["총_유동인구_수"])
    s["lt"] = np.log1p(s[AREA].map(total))
    pop = area_tbl.loc[area, "총_유동인구_수"]
    q = np.array([np.log1p(pop) if pd.notna(pop) else np.nan, np.log1p(total.get(area, np.nan))], dtype=float)
    nb = s.iloc[knn_rows(s[["lp", "lt"]].to_numpy(dtype=float), q)]
    fr = (nb["프랜차이즈_점포_수"].sum() / nb["점포_수"].sum()) if nb["점포_수"].sum() > 0 else np.nan
    summary = {"basis": "storeCount", "count": int(len(nb)), "storeCountMedian": _f(nb["점포_수"].median()), "closeRateAvg": _f(nb["폐업_률"].mean(), 1),
               "openRateAvg": _f(nb["개업_률"].mean(), 1), "franchiseShare": _f(fr, 3)}
    top5 = [{"areaCode": r[AREA], "areaName": AREA_NAME.get(r[AREA]), "sales": None, "storeCount": _f(r["점포_수"]), "closeRate": _f(r["폐업_률"], 1),
             "openRate": _f(r["개업_률"], 1), "floatingPopulation": _f(r["총_유동인구_수"])} for _, r in nb.head(5).iterrows()]
    return {"summary": summary, "top5": top5}


def info_panel(est, area: str, industry: str, area_tbl: pd.DataFrame, store_tbl: pd.DataFrame, supported_industry: bool) -> dict:
    """est: cold.ColdEstimator (최근 분기 입력 표와 맥락 계산을 들고 있음)"""
    panel = {
        "areaProfile": area_profile(area, area_tbl, store_tbl),
        "otherIndustries": other_industries(area, est.df, store_tbl),
        "similarAreas": None, "referenceSales": None,
        "industryName": IND_NAME.get(industry),
    }
    if supported_industry:
        panel["similarAreas"], panel["referenceSales"] = _sales_similar(est, area, industry, area_tbl)
    else:
        panel["similarAreas"] = _store_similar(area, industry, area_tbl, store_tbl)
    return panel
