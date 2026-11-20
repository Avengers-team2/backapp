from datetime import date, datetime
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel  # JS 카멜 -> Snake로 변경해서 받기

# VO
class SupportBookmarkVO(BaseModel):
    bookmark_id: int
    user_id: int
    bookmark_program_id: str
    bookmark_program_source: str
    bookmark_deadline_date: date | None = None
    bookmark_notify_enabled: bool = False
    bookmark_notified_at: datetime | None = None
    bookmark_created_at: datetime | None = None

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)
    