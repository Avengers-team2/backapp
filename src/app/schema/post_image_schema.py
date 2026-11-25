from pydantic import BaseModel
from datetime import datetime


# VO
class PostImageVO(BaseModel):
    image_id: int
    post_id: int
    image_url: str
    image_sort_order: int
    image_created_at: datetime | None = None


# DTO
class PostImageResponseDTO(BaseModel):
    image_id: int
    image_url: str
    image_sort_order: int

    class Config:
        from_attributes = True
