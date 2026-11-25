from fastapi import APIRouter, Depends, Query

from app.dependencie.auth_dependency import get_optional_user
from app.schema.common_schema import ApiResponseDTO
from app.schema.user_schema import UserClaimDTO
from app.service.support_service import SearchScope, SupportService, get_support_service

router = APIRouter()


@router.get(
    "",
    summary="지원사업 공고 목록",
    response_model=ApiResponseDTO
)
async def search_programs(
    keyword: str = Query("", max_length=50),
    scope: SearchScope = Query(SearchScope.ALL),
    input_id: int | None = Query(None),
    user_claims: UserClaimDTO | None = Depends(get_optional_user),
    support_service: SupportService = Depends(get_support_service)
):
    programs = await support_service.search(
        keyword, scope, input_id, user_claims.user_id if user_claims else None
    )

    return ApiResponseDTO(
        success=True,
        message="지원사업 목록 조회 성공",
        data=programs
    )
