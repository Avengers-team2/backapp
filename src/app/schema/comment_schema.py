from datetime import datetime

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel  # JS 카멜 -> Snake로 변경해서 받기


# VO
class PostCommentVO(BaseModel):
    comment_id: int
    user_id: int
    post_id: int
    parent_comment_id: int | None = None
    comment_content: str
    comment_created_at: datetime | None = None
    comment_updated_at: datetime | None = None
    comment_deleted_at: datetime | None = None

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)
           