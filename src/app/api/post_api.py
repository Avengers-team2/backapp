from fastapi import APIRouter, Query, Depends, status
from app.service.post_service import PostService, get_post_service
from app.schema.common_schema import ApiResponseDTO
from app.schema.post_schema import PostCreateDTO, PostUpdateDTO
from app.schema.user_schema import UserClaimDTO
from app.enum.post_enum import PostSortEnum, PostCategoryEnum
from app.dependencie.auth_dependency import get_current_user

router = APIRouter()


# 게시글 목록 조회
@router.get(
    "",
    summary="게시판 전체 조회",
    response_model=ApiResponseDTO
)
async def get_posts(
    page: int = Query(1, ge=1, description="페이지 번호"),
    size: int = Query(10, ge=1, le=50, description="페이지당 개수"),
    sort_by: PostSortEnum = Query(
        PostSortEnum.LATEST,
        description="정렬 기준(LATEST, OLDEST, VIEWS, LIKES)"
    ),
    keyword: str | None = Query(None, description="제목·내용 검색어"),
    category: PostCategoryEnum | None = Query(None, description="게시판 분류"),
    post_service: PostService = Depends(get_post_service)
):
    paged_posts = await post_service.get_post_list(page, size, sort_by, keyword, category)

    return ApiResponseDTO(
        success=True,
        message="전체 게시글 조회 성공",
        data=paged_posts
    )


# 내 글 목록 ("/{post_id}"보다 반드시 위에 있어야 함)
@router.get(
    "/me",
    summary="내 게시글 목록 조회",
    response_model=ApiResponseDTO
)
async def get_my_posts(
    page: int = Query(1, ge=1, description="페이지 번호"),
    size: int = Query(10, ge=1, le=50, description="페이지당 개수"),
    user_claims: UserClaimDTO = Depends(get_current_user),
    post_service: PostService = Depends(get_post_service)
):
    paged_posts = await post_service.get_my_posts(user_claims.user_id, page, size)

    return ApiResponseDTO(
        success=True,
        message="내 게시글 목록 조회 성공",
        data=paged_posts
    )


# 게시글 상세 조회
@router.get(
    "/{post_id}",
    summary="게시글 상세 조회",
    response_model=ApiResponseDTO
)
async def get_post_detail(
    post_id: int,
    post_service: PostService = Depends(get_post_service)
):
    detail = await post_service.get_post_detail(post_id)

    return ApiResponseDTO(
        success=True,
        message="게시글 상세 조회 성공",
        data=detail
    )


# 게시글 작성
@router.post(
    "",
    summary="게시글 작성",
    response_model=ApiResponseDTO,
    status_code=status.HTTP_201_CREATED
)
async def create_post(
    post: PostCreateDTO,
    user_claims: UserClaimDTO = Depends(get_current_user),
    post_service: PostService = Depends(get_post_service)
):
    new_post_id = await post_service.create_post(user_claims.user_id, post)

    return ApiResponseDTO(
        success=True,
        message="게시글 작성 성공",
        data={"post_id": new_post_id}
    )


# 게시글 수정
@router.put(
    "/{post_id}",
    summary="게시글 수정",
    response_model=ApiResponseDTO
)
async def update_post(
    post_id: int,
    update_dto: PostUpdateDTO,
    user_claims: UserClaimDTO = Depends(get_current_user),
    post_service: PostService = Depends(get_post_service)
):
    updated_id = await post_service.update_post(post_id, user_claims.user_id, update_dto)

    return ApiResponseDTO(
        success=True,
        message="게시글 수정 성공",
        data={"post_id": updated_id}
    )


# 게시글 삭제
@router.delete(
    "/{post_id}",
    summary="게시글 삭제",
    response_model=ApiResponseDTO
)
async def delete_post(
    post_id: int,
    user_claims: UserClaimDTO = Depends(get_current_user),
    post_service: PostService = Depends(get_post_service)
):
    await post_service.delete_post(post_id, user_claims.user_id)

    return ApiResponseDTO(
        success=True,
        message="게시글 삭제 성공"
    )


# 게시글 좋아요 토글 (누르면 좋아요, 다시 누르면 취소)
@router.post(
    "/{post_id}/like",
    summary="게시글 좋아요 / 좋아요 취소",
    response_model=ApiResponseDTO
)
async def toggle_like(
    post_id: int,
    user_claims: UserClaimDTO = Depends(get_current_user),
    post_service: PostService = Depends(get_post_service)
):
    like_status = await post_service.toggle_like(post_id, user_claims.user_id)

    return ApiResponseDTO(
        success=True,
        message="좋아요 취소" if not like_status.is_liked else "좋아요 성공",
        data=like_status
    )


# 내 북마크 목록
@router.get(
    "/bookmarks/me",
    summary="내 북마크 목록 조회",
    response_model=ApiResponseDTO
)
async def get_my_bookmarks(
    page: int = Query(1, ge=1, description="페이지 번호"),
    size: int = Query(10, ge=1, le=50, description="페이지당 개수"),
    user_claims: UserClaimDTO = Depends(get_current_user),
    post_service: PostService = Depends(get_post_service)
):
    paged_posts = await post_service.get_my_bookmarks(user_claims.user_id, page, size)

    return ApiResponseDTO(
        success=True,
        message="내 북마크 목록 조회 성공",
        data=paged_posts
    )


# 게시글 북마크 토글 (누르면 북마크, 다시 누르면 취소)
@router.post(
    "/{post_id}/bookmark",
    summary="게시글 북마크 / 북마크 취소",
    response_model=ApiResponseDTO
)
async def toggle_bookmark(
    post_id: int,
    user_claims: UserClaimDTO = Depends(get_current_user),
    post_service: PostService = Depends(get_post_service)
):
    bookmark_status = await post_service.toggle_bookmark(post_id, user_claims.user_id)

    return ApiResponseDTO(
        success=True,
        message="북마크 취소" if not bookmark_status.is_bookmarked else "북마크 성공",
        data=bookmark_status
    )