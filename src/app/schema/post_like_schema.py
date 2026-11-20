from pydantic import BaseModel
from datetime import datetime


# VO
class PostLikeVO(BaseModel):
    like_id: int
    post_id: int
    user_id: int
    like_created_at: datetime | None = None


# DTO
class PostLikeCreateDTO(BaseModel):
    post_id: int

    class Config:
        from_attributes = True


class PostLikeResponseDTO(BaseModel):
    like_id: int
    post_id: int
    user_id: int
    like_created_at: datetime

    class Config:
        from_attributes = True


class PostLikeStatusResponseDTO(BaseModel):
    is_liked: bool = False
    post_like_count: int | None = 0

    class Config:
        from_attributes = True