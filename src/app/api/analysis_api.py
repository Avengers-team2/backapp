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
    areas = await analysis_service.search_areas(keyword)

    return ApiResponseDTO(
        success=True,
        message="상권 검색 성공",
        data=areas
    )


# 좌표로 상권 폴리곤 찾기 (지도에 상권 영역 표시)
# 주소 → 좌표 변환은 프론트(카카오 지도 장소검색)가 하고, 여기서는 좌표만 받는다.
@router.get(
    "/areas/locate",
    summary="좌표가 속한 상권 폴리곤 조회",
    response_model=ApiResponseDTO
)
async def locate_areas(
    lat: float = Query(..., ge=-90, le=90, description="위도 (예: 37.5006)"),
    lng: float = Query(..., ge=-180, le=180, description="경도 (예: 127.0364)"),
    nearby_m: int = Query(300, ge=0, le=1000, description="상권 안이 아닐 때 가까운 상권을 찾을 반경(m)"),
    analysis_service: AnalysisService = Depends(get_analysis_service)
):
    result = analysis_service.locate_areas(lat, lng, nearby_m)

    return ApiResponseDTO(
        success=True,
        message="상권 폴리곤 조회 성공",
        data=result
    )


# 상권 코드로 폴리곤 조회 (상권 검색 자동완성에서 고른 상권을 지도에 표시)
@router.get(
    "/areas/{trdar_code}/polygon",
    summary="상권 코드로 폴리곤 조회",
    response_model=ApiResponseDTO
)
async def get_area_polygon(
    trdar_code: str,
    analysis_service: AnalysisService = Depends(get_analysis_service)
):
    area = analysis_service.get_area_polygon(trdar_code)

    return ApiResponseDTO(
        success=True,
        message="상권 폴리곤 조회 성공",
        data=area
    )


# 상권의 업종 목록과 분석 가능 여부 (분석 가능 / 이 상권에 기록 없음 / 지원하지 않는 업종)
@router.get(
    "/areas/{trdar_code}/industries",
    summary="상권별 업종 목록과 분석 가능 여부",
    response_model=ApiResponseDTO
)
async def list_area_industries(
    trdar_code: str,
    analysis_service: AnalysisService = Depends(get_analysis_service)
):
    items = await analysis_service.list_area_industries(trdar_code)

    return ApiResponseDTO(success=True, message="업종 목록 조회 성공", data=items)


# 상권 안 현재 점포 (지도 점 표시 + 경쟁 현황 카드)
# 업종은 industry_code(모델 코드) 또는 industry_large/mid/small(프론트 업종 이름) 중 하나로 보낸다.
@router.get(
    "/areas/{trdar_code}/stores",
    summary="상권 안 같은 업종·프랜차이즈 점포와 경쟁 현황",
    response_model=ApiResponseDTO
)
async def get_area_stores(
    trdar_code: str,
    industry_code: str | None = Query(None, max_length=10, description="모델 업종 코드 (예: CS100010)"),
    industry_large: str | None = Query(None, max_length=20),
    industry_mid: str | None = Query(None, max_length=50),
    industry_small: str | None = Query(None, max_length=50),
    brand: str | None = Query(None, max_length=100, description="사용자가 고른 프랜차이즈 브랜드명 (내 브랜드 강조용)"),
    user_claims: UserClaimDTO = Depends(get_current_user),
    analysis_service: AnalysisService = Depends(get_analysis_service)
):
    data = await analysis_service.get_area_stores(
        trdar_code, industry_code, industry_large, industry_mid, industry_small, brand
    )

    return ApiResponseDTO(success=True, message="상권 점포 조회 성공", data=data)


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


# 분석 실행 (저장된 조건으로 모델 예측·점수 계산 후 결과 저장). 이미 결과가 있으면 그대로 돌려준다.
@router.post(
    "/{input_id}/run",
    summary="분석 실행",
    response_model=ApiResponseDTO
)
async def run_analysis(
    input_id: int,
    user_claims: UserClaimDTO = Depends(get_current_user),
    analysis_service: AnalysisService = Depends(get_analysis_service)
):
    result = await analysis_service.run_analysis(user_claims.user_id, input_id)

    return ApiResponseDTO(success=True, message="분석 성공", data=result)


# 결과 화면 추가 정보 (업종 순위, 매출 추세·예측, 다른 업종 추천, 상권 비교, 프랜차이즈 비중)
@router.get(
    "/{input_id}/insights",
    summary="분석 결과 추가 정보",
    response_model=ApiResponseDTO
)
async def get_analysis_insights(
    input_id: int,
    user_claims: UserClaimDTO = Depends(get_current_user),
    analysis_service: AnalysisService = Depends(get_analysis_service)
):
    data = await analysis_service.get_insights(user_claims.user_id, input_id)

    return ApiResponseDTO(success=True, message="추가 정보 조회 성공", data=data)


# 분석 결과 조회
@router.get(
    "/{input_id}/result",
    summary="분석 결과 조회",
    response_model=ApiResponseDTO
)
async def get_analysis_result(
    input_id: int,
    user_claims: UserClaimDTO = Depends(get_current_user),
    analysis_service: AnalysisService = Depends(get_analysis_service)
):
    result = await analysis_service.get_result(user_claims.user_id, input_id)

    return ApiResponseDTO(success=True, message="분석 결과 조회 성공", data=result)
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
