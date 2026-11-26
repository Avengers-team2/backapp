"""모델 직접 사용: 사용자 입력(상권·업종·조건) -> 모델 예측 -> 점수·근거 문장 -> 결과.
model_weight3.pth 하나(모델 + 최근 분기 입력 표 + 정보판용 표)만 쓴다. predictions.csv 는 필요 없다.

사용:
    from serving2.service import AnalysisService       # serving2 폴더를 프로젝트에 복사한 뒤
    svc = AnalysisService()                            # 서버 시작 때 1번
    result = svc.analyze("3110946", "CS100001", {"bands": ["11_14"], "target_age": {"20": 1.0}})   # 항상 dict 를 돌려준다 (예외 없음)
    svc.list_areas()                                   # 화면 선택지: 모든 상권
    svc.list_industries("3110946")                     # 화면 선택지: 모든 업종과 상태

analyze 결과의 estimateType (화면이 이 값으로 분기한다)
  "normal"       : 그 상권·업종의 매출 기록이 있음 -> 입력값에 맞춰 분석 (점수·근거 문장·예측 매출)
  "noData"       : 점수를 낼 수 없음. totalScore·각 score 는 null, scoreLabel "?" -> 안내 문구(dataNotice) + 정보판(infoPanel)
                   noDataReason: "noRecord" 지원 업종인데 이 상권에 기록 없음 / "unsupportedIndustry" 매출 데이터가 없는 업종
                                 / "areaWithoutSales" 매출 데이터가 없는 상권 (둘 다면 두 값을 쉼표로)
  "invalidInput" : 존재하지 않는 상권/업종 코드 (invalidFields 에 어떤 코드가 틀렸는지)

list_industries 의 status: "analyzed"(기록 있음) / "noRecord"(지원 업종, 이 상권 기록 없음) / "unsupported"(매출 데이터가 없는 업종)
"""
import io
from datetime import date
from typing import Optional

import numpy as np
import pandas as pd

from .cold import ColdEstimator
from .explain import build_result
from .loader import CATEGORICAL, WEIGHTS_PATH, load_weights, shift_quarter
from .panel import AREA_NAME, IND_NAME, info_panel
from .scoring import SCORING_VERSION, customer_fit

IND = "서비스_업종_코드"
NOTICES = {
    "noRecord": "이 상권에는 이 업종의 매출 기록이 없어 점수를 계산하지 않았습니다. 대신 이 상권의 실제 현황과 비슷한 상권의 같은 업종 데이터를 보여드립니다.",
    "unsupportedIndustry": "이 업종은 매출 데이터가 없어 점수를 계산하지 않았습니다. 대신 이 상권의 현황과, 비슷한 상권의 이 업종 점포 현황을 보여드립니다.",
    "areaWithoutSales": "이 상권은 매출 데이터가 없어 점수를 계산하지 않았습니다. 대신 이 상권의 유동인구·점포 현황과 비슷한 상권의 같은 업종 데이터를 보여드립니다.",
    "both": "이 상권과 이 업종 모두 매출 데이터가 없어 점수를 계산하지 않았습니다. 대신 이 상권의 유동인구·점포 현황과 비슷한 상권의 이 업종 점포 현황을 보여드립니다.",
}


def pick_predict_quarter(base_quarter: str, today: Optional[date] = None, max_horizon: int = 5) -> dict:
    """오늘 기준 '다음 분기'가 기준 분기에서 몇 분기 뒤인지."""
    today = today or date.today()
    q = lambda c: int(c[:4]) * 4 + int(c[4]) - 1
    wanted = today.year * 4 + (today.month - 1) // 3 + 1 - q(base_quarter)
    h = min(max(wanted, 1), max_horizon)
    return {"predict_quarter": shift_quarter(base_quarter, h), "horizon": h, "capped": wanted > max_horizon}


class AnalysisService:
    def __init__(self, weights_path=WEIGHTS_PATH):
        self.w = load_weights(weights_path)
        self.cols = self.w["feature_columns"]
        df = pd.read_csv(io.BytesIO(self.w["latest_features_csv"]), dtype={"상권_코드": str, IND: str, "기준_년분기_코드": str})
        self.base_q = df["기준_년분기_코드"].iloc[0]
        self.df = df
        self.groups = {k: g for k, g in df.groupby(IND)}
        self.cold = ColdEstimator(self.w, df)  # 정보판 계산(비슷한 상권 찾기)용 맥락 표
        self.area_tbl = pd.read_csv(io.BytesIO(self.w["area_latest_csv"]), dtype={"상권_코드": str}).set_index("상권_코드", drop=False)
        self.store_tbl = pd.read_csv(io.BytesIO(self.w["store_latest_csv"]), dtype={"상권_코드": str, IND: str})
        self.sales_areas = set(df["상권_코드"])
        self.all_areas = set(self.area_tbl.index)
        self.all_industries = set(IND_NAME)

    # ---------- 화면 선택지용 ----------
    def list_areas(self) -> list:
        return [{"areaCode": a, "areaName": AREA_NAME.get(a), "hasSalesData": a in self.sales_areas} for a in sorted(self.all_areas)]

    def list_industries(self, area_code: Optional[str] = None) -> list:
        """모든 업종(100개)과 상태. area_code 를 주면 그 상권 기준의 상태, 안 주면 지원 여부만."""
        have = set()
        if area_code is not None:
            if area_code not in self.all_areas:
                return []
            have = set(self.df.loc[self.df["상권_코드"] == area_code, IND])
        out = []
        for k in sorted(self.all_industries):
            supported = k in self.groups
            status = "unsupported" if not supported else ("analyzed" if k in have else "noRecord") if area_code is not None else ("supported" if supported else "unsupported")
            out.append({"industryCode": k, "industryName": IND_NAME.get(k), "status": status})
        return out

    # ---------- 같은 업종 전체를 기존 모델로 예측 (순위·고객층 비교용) ----------
    def predict_industry(self, industry: str, horizon: int) -> pd.DataFrame:
        g = self.groups[industry]
        stability = g["상권_변화_지표"].astype(str).to_numpy()
        x = g.copy()
        for c in CATEGORICAL:
            x[c] = pd.Categorical(x[c], categories=self.w["cat_levels"][c])
        out = g[["상권_코드", IND]].copy().reset_index(drop=True)
        out["current_sales"] = g["당월_매출_금액"].round().astype("int64").to_numpy()
        pop = g["총_유동인구_수"].where(g["총_유동인구_수"] > 0)
        out["competition_density"] = (g["유사_업종_점포_수"] / pop * 1000).round(4).to_numpy()
        out["tenure"] = g["운영_영업_개월_평균"].to_numpy()
        for c in [c for c in g.columns if c.startswith(("비중_시간대_", "비중_연령대_")) or c == "비중_여성"]:
            out[c.replace("비중_", "share_")] = g[c].round(4).to_numpy()
        out["stability_label"] = stability
        out["base_quarter"] = self.base_q
        delta = self.w["sales"][horizon].predict(x[self.cols])
        out["predicted_sales"] = np.expm1(g["log_매출"].to_numpy() + delta).round().astype("int64")
        out["closure_prob"] = self.w["closure"][horizon].predict_proba(x[self.cols])[:, 1].round(4)
        pct = lambda s: (s.rank(pct=True) * 100).round(1)
        out["competition_percentile"] = pct(out["competition_density"])
        out["tenure_percentile"] = pct(out["tenure"])
        out["sales_percentile"] = pct(out["predicted_sales"])
        out["closure_percentile"] = pct(out["closure_prob"])
        out["industry_count"] = len(out)
        out["horizon"] = horizon
        out["predict_quarter"] = shift_quarter(self.base_q, horizon)
        out["model_version"] = f"horizon{horizon}-final-v1"
        return out.drop(columns="tenure")

    # ---------- 분석 ----------
    def analyze(self, area_code: str, industry_code: str, user: Optional[dict] = None, horizon: Optional[int] = None,
                today: Optional[date] = None, analysis_id: Optional[int] = None) -> dict:
        """항상 dict 를 돌려준다 (예외를 던지지 않음). estimateType 으로 분기."""
        user = user or {}
        area_code, industry_code = str(area_code), str(industry_code)
        bad = [n for n, ok in (("areaCode", area_code in self.all_areas), ("industryCode", industry_code in self.all_industries)) if not ok]
        if bad:
            return self._invalid(area_code, industry_code, analysis_id, bad)

        pick = pick_predict_quarter(self.base_q, today)
        h = horizon or pick["horizon"]
        supported = industry_code in self.groups
        has_record = supported and bool(((self.df["상권_코드"] == area_code) & (self.df[IND] == industry_code)).any())
        if not has_record:  # 점수는 내지 않고(물음표) 정보판만 보여준다
            return self._no_data(area_code, industry_code, analysis_id, pick, supported)

        peers = self.predict_industry(industry_code, h)
        row = peers[peers["상권_코드"] == area_code].iloc[0]
        fits = None
        if user.get("target_age") or user.get("target_gender"):
            fits = [customer_fit(r, user.get("target_age"), user.get("target_gender")) for r in peers.to_dict("records")]
        out = build_result(row, user, analysis_id, peer_fits=fits).model_dump(by_alias=True)
        out.update({"dataNotLatest": bool(pick["capped"]), "estimateType": "normal", "noDataReason": None, "dataNotice": None, "referenceSales": None, "infoPanel": None, "invalidFields": None})
        return out

    def _invalid(self, area_code, industry_code, analysis_id, bad) -> dict:
        return {"analysisId": analysis_id, "areaCode": area_code, "industryCode": industry_code, "totalScore": None, "scoreLabel": None, "reliability": None,
                "indicators": None, "prediction": None, "risks": [], "improvements": [], "modelVersion": None, "scoringVersion": SCORING_VERSION, "dataNotLatest": False,
                "estimateType": "invalidInput", "noDataReason": None, "dataNotice": "존재하지 않는 상권 또는 업종 코드입니다", "referenceSales": None, "infoPanel": None, "invalidFields": bad}

    def _no_data(self, area_code, industry_code, analysis_id, pick, supported) -> dict:
        """점수·예측·위험 요인은 비우고 물음표 표시용 값(scoreLabel)과 정보판을 준다."""
        reasons = []
        if not supported:
            reasons.append("unsupportedIndustry")
        elif area_code in self.sales_areas:
            reasons.append("noRecord")
        if area_code not in self.sales_areas:
            reasons.append("areaWithoutSales")
        key = "both" if len(reasons) == 2 else reasons[0]
        panel = info_panel(self.cold, area_code, industry_code, self.area_tbl, self.store_tbl, supported)
        reason_text = "이 상권·업종은 매출 기록이 없어 점수를 계산하지 않았습니다"
        q = lambda: {"score": None, "scoreLabel": "?", "detail": None, "reason": reason_text}
        return {
            "analysisId": analysis_id, "areaCode": area_code, "industryCode": industry_code,
            "totalScore": None, "scoreLabel": "?", "reliability": None,
            "indicators": {k: q() for k in ["sales", "competition", "customer", "time", "closure", "stability"]},
            "prediction": {"baseQuarter": self.base_q, "predictQuarter": None, "predictedSales": None, "scope": "상권·업종 단위 예측입니다"},
            "risks": [], "improvements": [], "modelVersion": None, "scoringVersion": SCORING_VERSION, "dataNotLatest": bool(pick["capped"]),
            "estimateType": "noData", "noDataReason": ",".join(reasons), "dataNotice": NOTICES[key],
            "referenceSales": panel.pop("referenceSales"), "infoPanel": panel, "invalidFields": None,
        }
