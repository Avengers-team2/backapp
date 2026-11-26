"""
분석 결과 화면에 붙이는 추가 정보 (모델 데이터에서 계산, DB에는 저장하지 않음)

  1) area_industries   : 이 상권에서 점포가 많은 업종 순위 (점포 표 기준, 매출 데이터 없는 업종 포함)
  2) sales_trend/forecast: 최근 5분기 매출 + 1~5분기 뒤 예측 매출·폐업 확률
  3) recommended_industries: 이 상권에서 점수가 높은 다른 업종 TOP 5 (사용자 입력과 무관한 4개 지표 기준)
  4) area_compare      : 같은 업종의 같은 구 평균·서울 평균과 비교, 구 안 순위, 구 안 상위 상권
  5) franchise         : 프랜차이즈 비중 (이 상권 vs 서울 평균)

주의: 금액(매출)은 `당월_매출_금액` 기준이며, 화면에서는 "분기 매출 합계"로 표기하기로 했다 (ML 팀 최종 확인 전 가정).
"""
import math
from functools import lru_cache

import numpy as np
import pandas as pd

from app.util.industry_map_util import front_industries_by_code
from app.util.trdar_geo_util import _load as _load_geo
from app.util.trdar_predict_util import _service

IND = "서비스_업종_코드"
TOP_RANK = 10
TOP_RECOMMEND = 5
TOP_GU_AREAS = 5

_peers_cache: dict[tuple[str, int], pd.DataFrame] = {}


def _f(v, digits: int | None = None):
    v = float(v)
    if math.isnan(v) or math.isinf(v):
        return None
    return round(v, digits) if digits is not None else v


def _quarter_code(base: str, n: int) -> str:
    idx = int(base[:4]) * 4 + int(base[4]) - 1 + n
    return f"{idx // 4}{idx % 4 + 1}"


@lru_cache(maxsize=1)
def _gu_map() -> dict[str, str]:
    """상권 코드 -> 구 이름 (폴리곤 파일 기준)"""
    loaded = _load_geo()
    if loaded is None:
        return {}
    return {f["properties"]["code"]: f["properties"]["gu"] for f in loaded[0]}


def _front_label(industry_code: str) -> dict | None:
    items = front_industries_by_code().get(industry_code)
    return items[0] if items else None


def _peers(svc, industry: str, horizon: int) -> pd.DataFrame:
    key = (industry, horizon)
    if key not in _peers_cache:
        _peers_cache[key] = svc.predict_industry(industry, horizon)
    return _peers_cache[key]


def _horizon(svc) -> int:
    from app.data.analysis.service import pick_predict_quarter

    return pick_predict_quarter(svc.base_q)["horizon"]


# ---------- 1) 이 상권에서 많은 업종 ----------
def _area_industries(svc, trdar_cd: str, industry_cd: str, names: dict, record_pairs: set) -> dict | None:
    t = svc.store_tbl
    rows = t[t["상권_코드"] == trdar_cd]
    if rows.empty:
        return None
    total = int(rows["점포_수"].sum())
    rows = rows.sort_values(["점포_수", IND], ascending=[False, True]).reset_index(drop=True)

    def item(rank: int, r) -> dict:
        n = int(r["점포_수"])
        return {
            "rank": rank,
            "industry_code": r[IND],
            "industry_name": names.get(r[IND]),
            "front_industry": _front_label(r[IND]),
            "store_count": n,
            "share": round(n / total, 4) if total else None,
            "open_rate": _f(r["개업_률"], 1),
            "close_rate": _f(r["폐업_률"], 1),
            "franchise_count": int(r["프랜차이즈_점포_수"]),
            "franchise_ratio": round(float(r["프랜차이즈_점포_수"]) / n, 3) if n else None,
            "has_sales_data": (trdar_cd, r[IND]) in record_pairs,  # 점수 분석이 되는 조합인가
        }

    items = [item(i + 1, r) for i, r in rows.iterrows()]
    mine = next((x for x in items if x["industry_code"] == industry_cd), None)
    return {
        "total_store_count": total,
        "industry_kind_count": len(items),
        "top": items[:TOP_RANK],
        "my_industry": mine,  # 선택 업종의 순위 (이 상권에 점포가 없으면 null)
    }


# ---------- 2) 매출 추세 + 예측 ----------
def _row_frame(svc, row: pd.Series) -> pd.DataFrame:
    x = row.to_frame().T
    for c in svc.cols:
        if c not in x:
            x[c] = np.nan
    x = x[svc.cols].copy()
    for c in ("서비스_업종_코드", "상권_구분_코드", "상권_변화_지표"):
        x[c] = pd.Categorical(x[c].astype(str), categories=svc.w["cat_levels"][c])
    for c in x.columns:
        if c not in ("서비스_업종_코드", "상권_구분_코드", "상권_변화_지표"):
            x[c] = pd.to_numeric(x[c], errors="coerce")
    return x


def _trend(svc, row: pd.Series, selected: int) -> dict:
    base = svc.base_q
    logs = [("lag4_log_매출", -4), ("lag3_log_매출", -3), ("lag2_log_매출", -2), ("lag1_log_매출", -1), ("log_매출", 0)]
    actual = [
        {"quarter": _quarter_code(base, back), "sales": _f(np.expm1(row[col])), "kind": "actual"}
        for col, back in logs
        if pd.notna(row[col])
    ]
    x = _row_frame(svc, row)
    cur_log, cur_sales = float(row["log_매출"]), float(row["당월_매출_금액"])
    forecast = []
    for h in range(1, 6):
        pred = float(np.expm1(cur_log + float(svc.w["sales"][h].predict(x)[0])))
        prob = float(svc.w["closure"][h].predict_proba(x)[0, 1])
        forecast.append({
            "horizon": h,
            "quarter": _quarter_code(base, h),
            "predicted_sales": int(round(pred)),
            "change_rate": round(pred / cur_sales - 1, 4) if cur_sales else None,
            "closure_probability": round(prob, 4),
            "is_selected": h == selected,  # 분석 결과에 쓰인 예측 시점
        })
    return {
        "sales_trend": actual + [{"quarter": f["quarter"], "sales": f["predicted_sales"], "kind": "predicted"} for f in forecast],
        "forecast": forecast,
    }


# ---------- 3) 다른 업종 추천 ----------
def _recommend(svc, trdar_cd: str, industry_cd: str, names: dict, horizon: int) -> dict:
    from app.data.analysis.scoring import score_row

    scored = []
    for ind, g in svc.groups.items():
        if not (g["상권_코드"] == trdar_cd).any():
            continue
        peers = _peers(svc, ind, horizon)
        prow = peers[peers["상권_코드"] == trdar_cd].iloc[0]
        s = score_row(prow, {}, None)  # 사용자 입력과 무관: 매출·경쟁·폐업·안정성
        if s["total"] is None:
            continue
        cur = float(prow["current_sales"])
        scored.append({
            "industry_code": ind,
            "industry_name": names.get(ind),
            "front_industry": _front_label(ind),
            "total_score": s["total"],
            "sales_score": s["sales"],
            "competition_score": s["competition"],
            "closure_score": s["closure"],
            "stability_score": s["stability"],
            "store_count": int(_f(g[g["상권_코드"] == trdar_cd].iloc[0]["점포_수"]) or 0),
            "sales_change_rate": round(float(prow["predicted_sales"]) / cur - 1, 4) if cur else None,
        })
    scored.sort(key=lambda x: (-x["total_score"], x["industry_code"]))
    rank = next((i + 1 for i, x in enumerate(scored) if x["industry_code"] == industry_cd), None)
    return {
        "basis": "매출·경쟁·폐업·안정성 4개 지표 (사용자 입력 무관)",
        "candidate_count": len(scored),
        "my_industry_rank": rank,  # 선택 업종이 이 상권 후보 중 몇 위인지 (기록 없으면 null)
        "items": [x for x in scored if x["industry_code"] != industry_cd][:TOP_RECOMMEND],
    }


# ---------- 4) 상권 비교 + 5) 프랜차이즈 ----------
def _compare(svc, trdar_cd: str, industry_cd: str, names: dict) -> dict | None:
    g = svc.groups.get(industry_cd)
    if g is None:
        return None
    gu = _gu_map().get(trdar_cd)
    gug = g[g["상권_코드"].map(_gu_map()) == gu] if gu else g.iloc[0:0]
    mine_rows = g[g["상권_코드"] == trdar_cd]

    top = gug.sort_values("당월_매출_금액", ascending=False).head(TOP_GU_AREAS)
    top_areas = [{
        "area_code": r["상권_코드"],
        "area_name": names_area(svc, r["상권_코드"]),
        "sales": _f(r["당월_매출_금액"]),
        "store_count": int(_f(r["점포_수"]) or 0),
        "close_rate": _f(r["폐업_률"], 1),
        "is_mine": r["상권_코드"] == trdar_cd,
    } for _, r in top.iterrows()]

    out = {"gu": gu, "gu_area_count": int(len(gug)), "seoul_area_count": int(len(g)), "gu_top_areas": top_areas, "rows": None, "gu_rank": None, "franchise": None}
    if mine_rows.empty:
        return out
    m = mine_rows.iloc[0]
    metrics = [
        ("매출", "당월_매출_금액", "원"), ("점포당 매출", "점포당_매출", "원"), ("점포 수", "점포_수", "개"),
        ("폐업률", "폐업_률", "%"), ("개업률", "개업_률", "%"), ("유동인구", "총_유동인구_수", "명"),
    ]
    out["rows"] = [{
        "label": label, "unit": unit, "mine": _f(m[col]),
        "gu_average": _f(gug[col].mean()) if len(gug) else None,
        "seoul_average": _f(g[col].mean()),
    } for label, col, unit in metrics]
    if len(gug):
        sales_rank = int((gug["당월_매출_금액"] > m["당월_매출_금액"]).sum()) + 1
        out["gu_rank"] = {"sales_rank": sales_rank, "total": int(len(gug))}

    stores = max(float(m["점포_수"]), 0)
    sum_all = float(g["점포_수"].sum())
    out["franchise"] = {
        "franchise_store_count": int(_f(m["프랜차이즈_점포_수"]) or 0),
        "store_count": int(stores),
        "ratio": round(float(m["프랜차이즈_점포_수"]) / stores, 3) if stores else None,
        "seoul_average_ratio": round(float(g["프랜차이즈_점포_수"].sum()) / sum_all, 3) if sum_all else None,  # 점포 수 가중 평균
    }
    return out


def names_area(svc, code: str) -> str | None:
    from app.data.analysis.panel import AREA_NAME

    return AREA_NAME.get(code)


def build_insights(trdar_cd: str, industry_cd: str) -> dict | None:
    """선택한 상권·업종의 추가 정보. 모델을 못 불러오면 None. 계산이 무거우니 별도 스레드에서 부를 것"""
    svc = _service()
    if svc is None:
        return None
    from app.data.analysis.panel import IND_NAME

    horizon = _horizon(svc)
    record_pairs = set(zip(svc.df["상권_코드"], svc.df[IND]))
    has_record = (trdar_cd, industry_cd) in record_pairs
    compare = _compare(svc, trdar_cd, industry_cd, IND_NAME) if industry_cd in svc.groups else None

    out = {
        "area_code": trdar_cd,
        "industry_code": industry_cd,
        "industry_name": IND_NAME.get(industry_cd),
        "base_quarter": svc.base_q,
        "has_sales_data": has_record,
        "area_industries": _area_industries(svc, trdar_cd, industry_cd, IND_NAME, record_pairs),
        "sales_trend": None,
        "forecast": None,
        "recommended_industries": _recommend(svc, trdar_cd, industry_cd, IND_NAME, horizon),
        "area_compare": compare,
        "franchise": compare["franchise"] if compare else None,
        "notice": "매출 금액은 분기(3개월) 합계 기준입니다.",
    }
    if has_record:
        g = svc.groups[industry_cd]
        row = g[g["상권_코드"] == trdar_cd].iloc[0]
        out.update(_trend(svc, row, horizon))
    return out
