"""이력이 없는 상권×업종(데이터에 없는 조합)을 '참고용으로 추정'한다.
- 콜드스타트 모델(상권 특성 + 같은 상권의 다른 업종 + 같은 업종의 다른 상권으로만 예측)로 순위·폐업 확률을 추정
- 유사 상권 평균 매출: 유동인구·주변 업종 매출이 비슷한 상권 20곳의 같은 업종 현재 매출(중앙값과 25~75% 범위)을 참고값으로 제공
정확도(테스트 조합 기준): 매출 금액은 중앙값 약 67% 오차, 업종 내 순위 상관 0.45, 폐업 AUC 0.65 — 금액은 보여주지 않고 참고값만 쓴다.
"""
import numpy as np
import pandas as pd

from .loader import CATEGORICAL, shift_quarter 

IND = "서비스_업종_코드"
AREA = "상권_코드"
Q = "기준_년분기_코드"
K = 20


def add_contexts(df: pd.DataFrame) -> pd.DataFrame:
    """기존 조합용: 자기 자신을 뺀 '같은 상권 다른 업종' 맥락 + 같은 업종·분기 평균 (학습 때와 같은 계산)."""
    d = df.copy()
    sales = d["당월_매출_금액"].fillna(0)
    store = d["점포_수"].fillna(0)
    keys = [d[AREA], d[Q]]
    n = sales.groupby(keys).transform("size")
    other_sales = sales.groupby(keys).transform("sum") - sales
    other_store = store.groupby(keys).transform("sum") - store
    d["ctx_other_n"] = (n - 1).astype(float)
    d["ctx_other_sales_log"] = np.log1p(other_sales)
    d["ctx_other_avg_sales_log"] = np.log1p(other_sales / (n - 1).where(n > 1))
    d["ctx_other_store_log"] = np.log1p(other_store)
    no_other = d["ctx_other_n"] == 0
    d.loc[no_other, ["ctx_other_sales_log", "ctx_other_avg_sales_log", "ctx_other_store_log"]] = np.nan
    ikeys = [d[IND], d[Q]]
    for name, col in [("ind_mean_log_sales", "log_매출"), ("ind_mean_close_rate", "폐업_률"), ("ind_mean_stores", "점포_수")]:
        d[name] = d[col].groupby(ikeys).transform("mean").to_numpy()
    d["ind_n_areas"] = sales.groupby(ikeys).transform("size").astype(float)
    d["log_pop"] = np.log1p(d["총_유동인구_수"])
    return d


class ColdEstimator:
    def __init__(self, bundle: dict, latest: pd.DataFrame):
        self.w = bundle
        self.cols = bundle["cold_columns"]
        self.levels = bundle["cat_levels"]
        self.df = add_contexts(latest)
        self.share_cols = [c for c in self.df.columns if c.startswith(("비중_시간대_", "비중_연령대_")) or c == "비중_여성"]
        self.areas = set(self.df[AREA].unique())
        self.industries = set(self.df[IND].unique())
        self._peer_cache = {}

    def _cat(self, x: pd.DataFrame) -> pd.DataFrame:
        x = x.copy()
        for c in CATEGORICAL:
            if c in x.columns:
                x[c] = pd.Categorical(x[c], categories=self.levels[c])
        return x

    def _peer_preds(self, industry: str, h: int):
        """같은 업종의 기존 조합을 콜드스타트 모델로 예측한 값 (순위 비교용)."""
        key = (industry, h)
        if key not in self._peer_cache:
            g = self._cat(self.df[self.df[IND] == industry][self.cols])
            ps = np.expm1(self.w["cold_sales"][h].predict(g))
            pc = self.w["cold_closure"][h].predict_proba(g)[:, 1]
            self._peer_cache[key] = (np.sort(ps), np.sort(pc))
        return self._peer_cache[key]

    @staticmethod
    def _pct(sorted_vals: np.ndarray, v: float) -> float:
        return round(float(np.searchsorted(sorted_vals, v, side="right") / len(sorted_vals) * 100), 1)

    def estimate(self, area: str, industry: str, h: int) -> dict:
        """-> {'row': 점수 계산용 한 행, 'reference_sales': 유사 상권 평균 매출 정보}"""
        a = self.df[self.df[AREA] == area]
        g = self.df[self.df[IND] == industry]
        base_q = a[Q].iloc[0]
        first = a.iloc[0]

        # 이 상권의 맥락 (그 업종이 없으니 '자기 자신 제외'가 아니라 이 상권의 모든 기존 업종)
        n = len(a)
        sales_sum = float(a["당월_매출_금액"].fillna(0).sum())
        store_sum = float(a["점포_수"].fillna(0).sum())
        x = {c: first[c] for c in self.cols if c in self.df.columns}
        x[IND] = industry
        x.update(ctx_other_n=float(n), ctx_other_sales_log=float(np.log1p(sales_sum)),
                 ctx_other_avg_sales_log=float(np.log1p(sales_sum / n)), ctx_other_store_log=float(np.log1p(store_sum)))
        for c in ["ind_mean_log_sales", "ind_mean_close_rate", "ind_mean_stores"]:
            x[c] = float(g[c].iloc[0])
        x["ind_n_areas"] = float(len(g))
        xdf = self._cat(pd.DataFrame([x])[self.cols])
        pred_sales = float(np.expm1(self.w["cold_sales"][h].predict(xdf))[0])
        prob = float(self.w["cold_closure"][h].predict_proba(xdf)[:, 1][0])
        ps, pc = self._peer_preds(industry, h)

        # 유사 상권 20곳 (유동인구, 주변 업종 매출이 비슷한 상권의 같은 업종)
        feats = ["log_pop", "ctx_other_sales_log"]
        q = np.array([np.log1p(first["총_유동인구_수"]) if pd.notna(first["총_유동인구_수"]) else np.nan, np.log1p(sales_sum)], dtype=float)
        cand = g[feats].to_numpy(dtype=float)
        med = np.nanmedian(cand, axis=0)
        cand = np.where(np.isnan(cand), med, cand)
        q = np.where(np.isnan(q), med, q)
        mu, sd = cand.mean(axis=0), cand.std(axis=0)
        sd[sd == 0] = 1.0
        dist = (((cand - mu) / sd - (q - mu) / sd) ** 2).sum(axis=1)
        idx = np.argsort(dist)[: min(K, len(g))]
        nb = g.iloc[idx]
        sales_nb = nb["당월_매출_금액"].dropna()
        ref = {"median": int(round(sales_nb.median())), "low": int(round(sales_nb.quantile(0.25))), "high": int(round(sales_nb.quantile(0.75))), "count": int(len(sales_nb)),
               "basis": f"유동인구·주변 업종 매출이 비슷한 상권 {len(sales_nb)}곳의 같은 업종 매출(분기 3개월 합계 기준, 최근 분기) 중앙값과 25~75% 범위"}

        tenure = g["운영_영업_개월_평균"].dropna().to_numpy()
        tenure_pct = None if pd.isna(first["운영_영업_개월_평균"]) or len(tenure) == 0 else round(float((tenure < first["운영_영업_개월_평균"]).mean() * 100), 1)
        row = {
            AREA: area, IND: industry, "base_quarter": base_q, "predict_quarter": shift_quarter(base_q, h), "horizon": h,
            "predicted_sales": None, "current_sales": None,  # 금액은 신뢰할 수 없어 비움 (순위만 사용)
            "sales_percentile": self._pct(ps, pred_sales), "closure_prob": round(prob, 4), "closure_percentile": self._pct(pc, prob),
            "industry_count": int(len(g)), "competition_density": None, "competition_percentile": None,
            "tenure_percentile": tenure_pct, "stability_label": str(first["상권_변화_지표"]), "model_version": f"coldstart-h{h}-v1",
        }
        for c in self.share_cols:  # 고객층·시간대 비중은 유사 상권의 평균으로 대신한다
            row[c.replace("비중_", "share_")] = round(float(nb[c].mean()), 4) if nb[c].notna().any() else None
        return {"row": row, "reference_sales": ref}
