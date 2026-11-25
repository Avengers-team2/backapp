from fastapi import APIRouter, Depends, Query

from app.dependencie.auth_dependency import get_current_user
from app.schema.common_schema import ApiResponseDTO
from app.schema.support_schema import SupportBookmarkRequestDTO
from app.schema.user_schema import UserClaimDTO
from app.service.support_bookmark_service import SupportBookmarkService, get_support_bookmark_service

router = APIRouter()


@router.post(
    "/support",
    summary="지원사업 관심 등록/해제",
    response_model=ApiResponseDTO
)
async def toggle_support_bookmark(
    body: SupportBookmarkRequestDTO,
    user_claims: UserClaimDTO = Depends(get_current_user),
    bookmark_service: SupportBookmarkService = Depends(get_support_bookmark_service)
):
    result = await bookmark_service.toggle(user_claims.user_id, body.source, body.source_id)

    return ApiResponseDTO(
        success=True,
        message="관심 등록" if result.is_bookmarked else "관심 해제",
        data=result
    )


@router.get(
    "/support/keys",
    summary="내 관심 지원사업 키 목록",
    response_model=ApiResponseDTO
)
async def list_support_bookmark_keys(
    user_claims: UserClaimDTO = Depends(get_current_user),
    bookmark_service: SupportBookmarkService = Depends(get_support_bookmark_service)
):
    keys = await bookmark_service.list_keys(user_claims.user_id)

    return ApiResponseDTO(
        success=True,
        message="관심 지원사업 키 조회 성공",
        data=keys
    )


@router.get(
    "/support/me",
    summary="내 관심 지원사업 목록",
    response_model=ApiResponseDTO
)
async def list_my_support_bookmarks(
    keyword: str = Query("", max_length=50),
    user_claims: UserClaimDTO = Depends(get_current_user),
    bookmark_service: SupportBookmarkService = Depends(get_support_bookmark_service)
):
    items = await bookmark_service.list_my_bookmarks(user_claims.user_id, keyword)

    return ApiResponseDTO(
        success=True,
        message="관심 지원사업 목록 조회 성공",
        data=items
    )
