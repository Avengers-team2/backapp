from fastapi import APIRouter, Query, Depends
from app.service.post_service import PostService, get_post_service
from app.schema.common_schema import ApiResponseDTO
from app.enum.post_enum import PostSortEnum, PostCategoryEnum

router = APIRouter()

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
