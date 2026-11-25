from datetime import datetime
from pydantic import BaseModel, Field
from app.enum.post_enum import PostCategoryEnum
from app.schema.user_schema import UserSummaryDTO
from app.schema.post_comment_schema import CommentResponseDTO
from app.schema.post_image_schema import PostImageResponseDTO

MAX_POST_IMAGES = 10   # 게시글당 사진 최대 장수

# VO
class PostVO(BaseModel):
    post_id: int
    post_category: PostCategoryEnum
    post_title: str
    post_content: str
    post_view_count: int | None = 0
    post_like_count: int | None = 0
    post_created_at: datetime | None = None
    post_updated_at: datetime | None = None
    post_deleted_at: datetime | None = None

    user_id: int


# DTO
class PostCreateDTO(BaseModel):
    post_category: PostCategoryEnum
    post_title: str
    post_content: str
    post_image_urls: list[str] = Field(default_factory=list, max_length=MAX_POST_IMAGES)

    class Config:
        from_attributes = True


class PostUpdateDTO(BaseModel):
    post_category: PostCategoryEnum
    post_title: str
    post_content: str
    post_image_urls: list[str] = Field(default_factory=list, max_length=MAX_POST_IMAGES)

    class Config:
        from_attributes = True


class PostListResponseDTO(BaseModel):
    post_id: int
    post_category: PostCategoryEnum
    post_title: str
    post_view_count: int | None = 0
    post_like_count: int | None = 0
    post_created_at: datetime
    post_comment_count: int = 0

    user: UserSummaryDTO

    class Config:
        from_attributes = True


class PostDetailResponseDTO(PostListResponseDTO):
    is_liked: bool = False
    is_bookmarked: bool = False
    comments: list[CommentResponseDTO] = Field(default_factory=list)
    images: list[PostImageResponseDTO] = Field(default_factory=list)
    post_content: str
    post_updated_at: datetime | None = None
    post_deleted_at: datetime | None = None

    class Config:
        from_attributes = True


class PostLikeResponseDTO(BaseModel):
    is_liked: bool = False
    post_like_count: int | None = None

    class Config:
        from_attributes = True


class PostBookmarkResponseDTO(BaseModel):
    is_bookmarked: bool = False

    class Config:
        from_attributes = True