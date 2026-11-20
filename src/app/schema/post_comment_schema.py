from pydantic import BaseModel, Field
from datetime import datetime
from app.schema.user_schema import UserSummaryDTO


# VO
class CommentVO(BaseModel):
    comment_id: int
    parent_comment_id: int | None = None
    comment_content: str
    comment_created_at: datetime | None = None
    comment_updated_at: datetime | None = None
    comment_deleted_at: datetime | None = None

    user_id: int
    post_id: int


# DTO
class CommentCreateDTO(BaseModel):
    comment_content: str
    parent_comment_id: int | None = None

    class Config:
        from_attributes = True


class CommentUpdateDTO(BaseModel):
    comment_content: str

    class Config:
        from_attributes = True


class CommentResponseDTO(BaseModel):
    comment_id: int
    comment_content: str
    parent_comment_id: int | None = None
    comment_created_at: datetime | None = None
    comment_updated_at: datetime | None = None
    comment_deleted_at: datetime | None = None

    user: UserSummaryDTO
    children: list["CommentResponseDTO"] = Field(default_factory=list)

    class Config:
        from_attributes = True