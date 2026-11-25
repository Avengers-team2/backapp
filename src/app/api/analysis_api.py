from fastapi import APIRouter, Query, Depends, status
from app.service.analysis_service import AnalysisService, get_analysis_service
from app.schema.common_schema import ApiResponseDTO
from app.schema.analysis_input_schema import AnalysisInputCreateDTO
from app.schema.user_schema import UserClaimDTO
from app.dependencie.auth_dependency import get_current_user

router = APIRouter()


# 상권 검색 (희망 지역 자동완성)
@router.get(
    "/areas",
    summary="상권 검색",
    response_model=ApiResponseDTO
)
async def search_areas(
    keyword: str = Query(..., min_length=1, max_length=50, description="상권명·동·구 검색어"),
    analysis_service: AnalysisService = Depends(get_analysis_service)
):
    areas = analysis_service.search_areas(keyword)

    return ApiResponseDTO(
        success=True,
        message="상권 검색 성공",
        data=areas
    )


# 가맹 브랜드 검색 (프랜차이즈 브랜드 자동완성)
@router.get(
    "/franchises",
    summary="가맹 브랜드 검색",
    response_model=ApiResponseDTO
)
async def search_franchises(
    keyword: str = Query(..., min_length=1, max_length=50, description="브랜드명 검색어"),
    analysis_service: AnalysisService = Depends(get_analysis_service)
):
    brands = await analysis_service.search_brands(keyword)

    return ApiResponseDTO(
        success=True,
        message="브랜드 검색 성공",
        data=brands
    )


@router.get(
    "/me",
    summary="내 분석 조건 목록",
    response_model=ApiResponseDTO
)
async def list_my_analyses(
    user_claims: UserClaimDTO = Depends(get_current_user),
    analysis_service: AnalysisService = Depends(get_analysis_service)
):
    analyses = await analysis_service.list_my_analyses(user_claims.user_id)

    return ApiResponseDTO(
        success=True,
        message="내 분석 목록 조회 성공",
        data=analyses
    )


# 분석 조건 저장 (분석 시작하기)
@router.post(
    "",
    summary="분석 조건 저장",
    response_model=ApiResponseDTO,
    status_code=status.HTTP_201_CREATED
)
async def create_analysis_input(
    analysis_input: AnalysisInputCreateDTO,
    user_claims: UserClaimDTO = Depends(get_current_user),
    analysis_service: AnalysisService = Depends(get_analysis_service)
):
    input_id = await analysis_service.create_input(user_claims.user_id, analysis_input)

    return ApiResponseDTO(
        success=True,
        message="분석 조건 저장 성공",
        data={"input_id": input_id}
    )
