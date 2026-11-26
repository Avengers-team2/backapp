import asyncio
from datetime import time

from fastapi import Depends, HTTPException, status

from app.infrastructure.external.franchise_api import BrandApiError, load_brands
from app.repository.analysis_input_repository import AnalysisInputRepository, get_analysis_input_repository
from app.schema.support_schema import MyAnalysisOptionDTO
from app.schema.analysis_input_schema import (
    AnalysisInputCreateDTO,
    AreaLocateResponseDTO,
    AreaPolygonResponseDTO,
    AreaSearchResponseDTO,
    BrandSearchResponseDTO,
)
from app.infrastructure.external.store_api import StoreApiError
from app.util.industry_map_util import front_industries_by_code, to_industry_code
from app.util.store_industry_map import has_rule
from app.util.trdar_insight_util import build_insights
from app.util.trdar_store_util import classify_stores, get_area_stores
from app.util.scoring_input_util import build_scoring_user
from app.util.trdar_predict_util import analyze, get_extra, get_model_store_count, industry_name, list_industries, sales_area_codes
from app.util.trdar_geo_util import find_trdar_by_point, get_trdar_center, get_trdar_polygon, is_geo_data_loaded
from app.util.trdar_util import exists_trdar, load_trdar_list, normalize, search_trdar
from app.util.trdar_util import exists_trdar, find_trdar, load_trdar_list, normalize, search_trdar

# 화면의 운영 시간 칩 → (시작 시, 끝 시)
OPERATING_SLOTS: dict[str, tuple[int, int]] = {
    "아침 07~11시": (7, 11),
    "점심 11~15시": (11, 15),
    "오후 15~22시": (15, 22),
    "저녁 22~02시": (22, 2),
    "새벽 02~07시": (2, 7),
}

FRANCHISE_MAP = {"예": True, "아니요": False}

SEARCH_LIMIT = 8
MY_ANALYSIS_LIMIT = 10


class AnalysisService:
    def __init__(self, input_repo: AnalysisInputRepository):
        self.input_repo = input_repo

    async def create_input(self, user_id: int, dto: AnalysisInputCreateDTO) -> int:
        if dto.deposit_min > dto.deposit_max:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "보증금 최소값이 최대값보다 큽니다.")
        if not exists_trdar(dto.trdar_cd):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "존재하지 않는 상권 코드입니다.")

        values = to_input_values(dto)
        values["user_id"] = user_id
        return await self.input_repo.create_input(values)

    async def run_analysis(self, user_id: int, input_id: int) -> dict:
        """저장된 분석 조건으로 예측/점수를 계산해 analysis 테이블에 저장하고 결과를 돌려준다 (같은 조건이면 저장된 결과 재사용)"""
        inp = await self._get_own_input(user_id, input_id)
        saved = await self.input_repo.get_analysis_by_input(input_id)
        if saved and "scoring_version" in (saved.analysis_result_detail or {}):  # 예전 임시 모델 결과는 다시 계산
            return to_result(saved, inp)

        industry_cd = to_industry_code(inp.input_industry_large, inp.input_industry_mid, inp.input_industry_small)
        if industry_cd is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "아직 예측 모델이 지원하지 않는 업종입니다.")

        ages = [a for a in (inp.input_target_ages or "").split(",") if a]
        user = build_scoring_user(ages, inp.input_target_gender, None)
        if inp.input_opening_time and inp.input_closing_time:
            start, end = inp.input_opening_time.hour, inp.input_closing_time.hour
            user["hours"] = [[start, end]] if start < end else [[start, 24], [0, end]]

        # 모델 첫 로드는 수 초 걸리는 무거운 계산이라 이벤트 루프를 막지 않게 별도 스레드에서 실행
        result = await asyncio.to_thread(analyze, inp.input_trdar_cd, industry_cd, user)
        if result is None:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "예측 모델 파일(app/data/analysis)을 불러오지 못했습니다.")

        ml = result["ml"]
        if ml["estimateType"] == "invalidInput":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"존재하지 않는 코드입니다: {', '.join(ml['invalidFields'] or [])}")

        ind = ml["indicators"]
        pred = ml["prediction"]
        # ML 응답 전체를 detail 에 보관 (normal: 점수·근거·위험·개선 + 화면용 차트값, noData: 안내문구 + 정보판)
        detail = {
            "industry_code": industry_cd,
            "scoring_user": user,
            "estimate_type": ml["estimateType"],
            "scoring_version": ml["scoringVersion"],
            "model_version": ml["modelVersion"],
            "reliability": ml["reliability"],
            "data_not_latest": ml["dataNotLatest"],
            "indicators": {k: {"score": v["score"], "detail": v["detail"], "reason": v["reason"]} for k, v in ind.items()},
            "risks": ml["risks"],
            "improvements": ml["improvements"],
            "no_data_reason": ml["noDataReason"],
            "data_notice": ml["dataNotice"],
            "reference_sales": ml["referenceSales"],
            "info_panel": ml["infoPanel"],
        }
        values = {
            "input_id": input_id,
            "analysis_total_score": ml["totalScore"],
            "analysis_sales_score": ind["sales"]["score"],
            "analysis_competition_score": ind["competition"]["score"],
            "analysis_customer_score": ind["customer"]["score"],
            "analysis_time_score": ind["time"]["score"],
            "analysis_closure_score": ind["closure"]["score"],
            "analysis_stability_score": ind["stability"]["score"],
            "analysis_predicted_sales": pred["predictedSales"],
            "analysis_predict_quarter": pred["predictQuarter"],
            "analysis_model_version": ml["modelVersion"],
            "analysis_data_quarter": pred["baseQuarter"],
            "analysis_closure_grade": None,  # normal 일 때만 아래에서 채움
        }
        if ml["estimateType"] == "normal":
            values["analysis_closure_grade"] = result["closure_grade"]
            detail.update({
                "current_sales": result["current_sales"],
                "sales_change_rate": result["sales_change_rate"],
                "closure_probability": result["closure_probability"],
                "horizon": result["horizon"],
                "store_count": result["store_count"],
                "similar_store_count": result["similar_store_count"],
                **result["extra"],
            })
        values["analysis_result_detail"] = detail
        analysis = await self.input_repo.create_analysis(values)
        return to_result(analysis)

    async def get_area_stores(self, trdar_code: str, industry_code: str | None, large: str | None,
                              mid: str | None, small: str | None, brand: str | None) -> dict:
        """상권 안 현재 점포: 선택 업종과 같은 점포(일반/프랜차이즈 분리) + 경쟁 현황 카드용 요약"""
        if industry_code is None and large and mid and small:
            industry_code = to_industry_code(large, mid, small)
        if industry_code is None or not has_rule(industry_code):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "업종을 확인할 수 없습니다. industry_code 또는 업종 대·중·소분류를 보내 주세요.")

        try:
            area = await get_area_stores(trdar_code)
            if area is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "존재하지 않는 상권 코드입니다.")
            classified = await classify_stores(area["stores"], industry_code, brand)
        except StoreApiError as e:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e))
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "점포 정보를 불러오지 못했습니다.")

        independent, franchise = classified["same_industry_stores"], classified["franchise_stores"]
        same_total = len(independent) + len(franchise)
        first_floor = sum(1 for x in independent + franchise if x["floor"] == "1")
        model = await asyncio.to_thread(get_model_store_count, trdar_code, industry_code)
        name = await asyncio.to_thread(industry_name, industry_code)
        return {
            "area_code": trdar_code,
            "industry_code": industry_code,
            "industry_name": name,
            "data_month": area["stdr_ym"],  # 상가정보 기준월 (YYYYMM)
            "same_industry_stores": independent,  # 선택 업종 일반 점포 (지도 점 1종류)
            "franchise_stores": franchise,  # 선택 업종 프랜차이즈 점포 (지도 점 다른 종류, is_my_brand 로 내 브랜드 강조)
            "summary": {
                "total_store_count": len(area["stores"]),  # 상권 안 모든 업종 점포
                "same_industry_count": same_total,
                "independent_count": len(independent),
                "franchise_count": len(franchise),
                "first_floor_count": first_floor,
                "first_floor_ratio": round(first_floor / same_total, 3) if same_total else None,
                "same_brand_count": sum(1 for x in franchise if x["is_my_brand"]) if brand else None,
                "model_store_count": model["count"] if model else None,  # 모델 기준 분기 점포 수 (비교용)
                "model_base_quarter": model["base_quarter"] if model else None,
                "change_vs_model": same_total - model["count"] if model else None,
            },
            "notice": "프랜차이즈 여부는 상호명과 공정위 브랜드 목록을 비교한 추정입니다. 점포 수 기준이 모델 데이터와 달라 차이가 있을 수 있습니다.",
        }

    async def get_insights(self, user_id: int, input_id: int) -> dict:
        """결과 화면 추가 정보: 업종 순위, 매출 추세·예측, 다른 업종 추천, 상권 비교, 프랜차이즈 비중"""
        inp = await self._get_own_input(user_id, input_id)
        industry_cd = to_industry_code(inp.input_industry_large, inp.input_industry_mid, inp.input_industry_small)
        if industry_cd is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "아직 예측 모델이 지원하지 않는 업종입니다.")
        data = await asyncio.to_thread(build_insights, inp.input_trdar_cd, industry_cd)
        if data is None:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "예측 모델 파일(app/data/analysis)을 불러오지 못했습니다.")
        return data

    async def list_area_industries(self, trdar_code: str) -> list:
        """상권 기준 업종 목록과 분석 가능 여부 (analyzed / noRecord / unsupported)"""
        items = await asyncio.to_thread(list_industries, trdar_code)
        if items is None:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "예측 모델 파일(app/data/analysis)을 불러오지 못했습니다.")
        if not items:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "존재하지 않는 상권 코드입니다.")
        # 프론트 업종(대·중·소)에 상태를 붙일 수 있게, 각 모델 업종에 연결된 프론트 업종을 같이 준다
        front = front_industries_by_code()
        return [{**item, "frontIndustries": front.get(item["industryCode"], [])} for item in items]

    async def get_result(self, user_id: int, input_id: int) -> dict:
        inp = await self._get_own_input(user_id, input_id)
        saved = await self.input_repo.get_analysis_by_input(input_id)
        if saved is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "아직 분석 결과가 없습니다.")
        return to_result(saved, inp)

    async def _get_own_input(self, user_id: int, input_id: int):
        inp = await self.input_repo.get_input(input_id)
        if inp is None or inp.user_id != user_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "분석 조건을 찾을 수 없습니다.")
        return inp

    async def search_areas(self, keyword: str) -> list[AreaSearchResponseDTO]:
    async def list_my_analyses(self, user_id: int) -> list[MyAnalysisOptionDTO]:
        inputs = await self.input_repo.list_inputs(user_id, MY_ANALYSIS_LIMIT)
        options = []
        for item in inputs:
            area = find_trdar(item.input_trdar_cd)
            place = area["name"] if area else item.input_trdar_cd
            gu = area["gu"] if area else ""
            parts = [gu, item.input_industry_small, item.input_use_purpose]
            options.append(MyAnalysisOptionDTO(
                input_id=item.input_id,
                label=f"{place} · {item.input_industry_small}",
                summary=" · ".join(p for p in parts if p),
            ))
        return options

    def search_areas(self, keyword: str) -> list[AreaSearchResponseDTO]:
        if not load_trdar_list():
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "상권 데이터 파일(app/data/analysis_input/seoul_trdar.csv)이 없습니다.",
            )
        # 서버 시작 후 첫 호출은 모델 로드(수 초)가 걸리므로 이벤트 루프를 막지 않게 별도 스레드에서 확인
        sales_areas = await asyncio.to_thread(sales_area_codes)
        results = []
        for area in search_trdar(keyword, SEARCH_LIMIT):
            center = get_trdar_center(area["code"])
            results.append(AreaSearchResponseDTO(
                **area,
                center_lat=center[0] if center else None,
                center_lng=center[1] if center else None,
                has_sales_data=None if sales_areas is None else area["code"] in sales_areas,
            ))
        return results

    def locate_areas(self, lat: float, lng: float, nearby_m: int) -> AreaLocateResponseDTO:
        if not is_geo_data_loaded():
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "상권 폴리곤 파일(app/data/geo/seoul_trdar.geojson)이 없습니다.",
            )
        return AreaLocateResponseDTO(**find_trdar_by_point(lat, lng, nearby_m))

    def get_area_polygon(self, trdar_code: str) -> AreaPolygonResponseDTO:
        if not is_geo_data_loaded():
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "상권 폴리곤 파일(app/data/geo/seoul_trdar.geojson)이 없습니다.",
            )
        area = get_trdar_polygon(trdar_code)
        if area is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "존재하지 않는 상권 코드입니다.")
        return AreaPolygonResponseDTO(**area)

    async def search_brands(self, keyword: str) -> list[BrandSearchResponseDTO]:
        try:
            brands = await load_brands()
        except BrandApiError as e:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"브랜드 목록을 불러오지 못했습니다. {e}")
        except Exception:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "브랜드 목록을 불러오지 못했습니다.")

        key = normalize(keyword)
        if not key:
            return []
        starts = [b for b in brands if normalize(b["name"]).startswith(key)]
        contains = [b for b in brands if key in normalize(b["name"]) and b not in starts]
        return [BrandSearchResponseDTO(**b) for b in (starts + contains)[:SEARCH_LIMIT]]


def _num(v):
    return None if v is None else float(v)


def to_result(a, inp=None) -> dict:
    """analysis 행 -> 응답 (프론트 Analysis 타입과 같은 snake_case)"""
    detail = dict(a.analysis_result_detail or {})
    if inp is not None and detail.get("estimate_type", "normal") == "normal" and "rank_percent" not in detail and detail.get("industry_code"):
        # 화면용 추가 필드가 생기기 전에 저장된 결과는 지금 계산해서 보충한다
        detail.update(get_extra(inp.input_trdar_cd, detail["industry_code"]) or {})
    return {
        "analysis_id": a.analysis_id,
        "input_id": a.input_id,
        "analysis_total_score": _num(a.analysis_total_score),
        "analysis_grade": a.analysis_grade,
        "analysis_sales_score": _num(a.analysis_sales_score),
        "analysis_competition_score": _num(a.analysis_competition_score),
        "analysis_customer_score": _num(a.analysis_customer_score),
        "analysis_time_score": _num(a.analysis_time_score),
        "analysis_closure_score": _num(a.analysis_closure_score),
        "analysis_stability_score": _num(a.analysis_stability_score),
        "analysis_closure_grade": a.analysis_closure_grade,
        "analysis_predicted_sales": a.analysis_predicted_sales,
        "analysis_predict_quarter": a.analysis_predict_quarter,
        "analysis_model_version": a.analysis_model_version,
        "analysis_data_quarter": a.analysis_data_quarter,
        "analysis_result_detail": detail,
        "analysis_is_saved": a.analysis_is_saved,
        "analysis_created_at": a.analysis_created_at.isoformat() if a.analysis_created_at else None,
    }


def to_operating_hours(slots: list[str]) -> tuple[time | None, time | None]:
    picked = [s for s in OPERATING_SLOTS if s in slots]
    if not picked:
        return None, None
    start = OPERATING_SLOTS[picked[0]][0]
    end = OPERATING_SLOTS[picked[-1]][1]
    return time(start), time(end)


def to_input_values(dto: AnalysisInputCreateDTO) -> dict:
    opening, closing = to_operating_hours(dto.operating_times)
    is_franchise = FRANCHISE_MAP.get(dto.is_franchise or "")

    return {
        "input_trdar_cd": dto.trdar_cd,
        "input_industry_large": dto.industry_large,
        "input_industry_mid": dto.industry_mid,
        "input_industry_small": dto.industry_small,
        "input_store_size": dto.store_size or None,
        "input_is_franchise": is_franchise,
        "input_franchise_brand": dto.franchise_brand if is_franchise else None,
        "input_opening_time": opening,
        "input_closing_time": closing,
        "input_target_ages": ",".join(dto.target_ages)[:50] or None,
        "input_target_gender": dto.target_gender or None,
        "input_extra_note": dto.extra_note or None,
        "input_use_purpose": dto.business_status,
        "input_deposit_budget": dto.deposit_max,
        "input_monthly_rent_max": dto.monthly_rent_max,
        "input_interior_budget_max": dto.interior_budget_max,
    }


def get_analysis_service(
        input_repository: AnalysisInputRepository = Depends(get_analysis_input_repository)
    ):
    return AnalysisService(input_repository)
