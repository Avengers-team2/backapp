from datetime import date, datetime
from pydantic import BaseModel, ConfigDict, field_validator, model_validator
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
    user_interest_region: str | None = None
    user_interest_industry: str | None = None
    user_profile: str | None = "/users/default.jpg"

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


# 회원가입 요청 / DB 저장용 DTO
class UserCreateDTO(BaseModel):
    user_name: str | None = None
    user_email: str
    user_password: str | None = None  # 소셜 가입은 비밀번호 없음
    user_sex: str
    user_nickname: str | None = None
    user_birth: date
    user_phone: str
    user_provider: UserProvider = UserProvider.LOCAL
    user_provider_id: str | None = None
    user_status: str = "ACTIVE"  # 서버 기본값
    user_business_status: str
    user_interest_region: str | None = None
    user_interest_industry: str | None = None
    user_agree_terms: bool = False
    user_agree_privacy: bool = False
    user_agree_marketing: bool = False

    # 프론트 필드명(agree_terms 등)으로 보내도 받을 수 있게 변환
    @model_validator(mode="before")
    @classmethod
    def map_agree_fields(cls, data):
        if isinstance(data, dict):
            data = dict(data)
            for short in ("terms", "privacy", "marketing"):
                if f"agree_{short}" in data and f"user_agree_{short}" not in data:
                    data[f"user_agree_{short}"] = data.pop(f"agree_{short}")
        return data

    # 프론트에서 "kakao"처럼 소문자로 보내도 enum("KAKAO")으로 받을 수 있게 대문자로 변환
    @field_validator("user_provider", mode="before")
    @classmethod
    def normalize_provider(cls, value):
        if isinstance(value, str):
            return value.upper()
        return value

    class Config:
        from_attributes = True


# 회원정보 수정 요청 DTO (보낸 값만 수정)
class UserUpdateDTO(BaseModel):
    user_name: str | None = None
    user_password: str | None = None
    user_sex: str | None = None
    user_nickname: str | None = None
    user_birth: date | None = None
    user_phone: str | None = None
    user_business_status: str | None = None
    user_interest_region: str | None = None
    user_interest_industry: str | None = None
    user_agree_marketing: bool | None = None  # 마케팅 수신 동의는 나중에 변경 가능
    user_profile: str | None = "/users/default.jpg"

    class Config:
        from_attributes = True


# 회원정보 응답 DTO (비밀번호 제외)
class UserResponseDTO(BaseModel):
    user_id: int
    user_name: str | None = None
    user_email: str
    user_sex: str
    user_nickname: str | None = None
    user_birth: date
    user_phone: str
    user_created_at: datetime | None = None
    user_updated_at: datetime | None = None
    user_provider: UserProvider
    user_status: str
    user_business_status: str
    user_interest_region: str | None = None
    user_interest_industry: str | None = None
    user_agree_marketing: bool = False
    user_profile: str | None = "/users/default.jpg"

    class Config:
        from_attributes = True