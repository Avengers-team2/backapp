from pydantic import BaseModel
from datetime import datetime


# VO
class PostBookmarkVO(BaseModel):
    bookmark_id: int
    user_id: int
    post_id: int
    bookmark_created_at: datetime | None = None


# DTO
class PostBookmarkCreateDTO(BaseModel):
    post_id: int

    class Config:
        from_attributes = True


class PostBookmarkResponseDTO(BaseModel):
    bookmark_id: int
    user_id: int
    post_id: int
    bookmark_created_at: datetime

    class Config:
        from_attributes = True


class PostBookmarkStatusResponseDTO(BaseModel):
    is_bookmarked: bool = False

    class Config:
        from_attributes = True