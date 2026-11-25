from datetime import time

from fastapi import Depends, HTTPException, status

from app.infrastructure.external.franchise_api import BrandApiError, load_brands
from app.repository.analysis_input_repository import AnalysisInputRepository, get_analysis_input_repository
from app.schema.support_schema import MyAnalysisOptionDTO
from app.schema.analysis_input_schema import (
    AnalysisInputCreateDTO,
    AreaSearchResponseDTO,
    BrandSearchResponseDTO,
)
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
                "상권 데이터 파일(app/data/seoul_trdar.csv)이 없습니다.",
            )
        return [AreaSearchResponseDTO(**a) for a in search_trdar(keyword, SEARCH_LIMIT)]

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
