from datetime import date, datetime
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel  # JS 카멜 -> Snake로 변경해서 받기

from app.enum.user_enum import UserProvider

# VO
class UserVO(BaseModel):
    user_id: int
    user_name: str | None = None
    user_email: str
    user_password: str | None = None
    user_sex: str
    user_nickname: str | None = None
    user_birth: date
    user_phone: str
    user_created_at: datetime | None = None
    user_deleted_at: datetime | None = None
    user_updated_at: datetime | None = None
    user_provider: UserProvider
    user_provider_id: str | None = None
    user_status: str
    user_business_status: str

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


class UserSummaryDTO(BaseModel):
    user_id: int
    user_nickname: str | None = None

    class Config:
        from_attributes = True

# JWT 토큰에 담는 로그인 사용자 정보
class UserClaimDTO(BaseModel):
    user_id: int
    user_email: str
    user_provider: UserProvider

    class Config:
        from_attributes = True