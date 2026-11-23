from datetime import datetime, time
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


# VO
class AnalysisInputVO(BaseModel):
    input_id: int
    user_id: int
    input_trdar_cd: str
    input_industry_large: str
    input_industry_mid: str
    input_industry_small: str
    input_store_size: str | None = None
    input_is_franchise: bool | None = None
    input_franchise_brand: str | None = None
    input_opening_time: time | None = None
    input_closing_time: time | None = None
    input_operating_days: str | None = None
    input_target_ages: str | None = None
    input_target_gender: str | None = None
    input_extra_note: str | None = None
    input_use_purpose: str | None = None
    input_requested_at: datetime 
    input_deposit_budget: int | None = None
    input_monthly_rent_max: int | None = None
    input_interior_budget_max: int | None = None

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


# DTO
class AnalysisInputCreateDTO(BaseModel):
    trdar_cd: str = Field(min_length=1, max_length=20)
    industry_large: str = Field(min_length=1, max_length=20)
    industry_mid: str = Field(min_length=1, max_length=50)
    industry_small: str = Field(min_length=1, max_length=10)
    deposit_min: int = Field(ge=0)
    deposit_max: int = Field(gt=0)
    monthly_rent_max: int | None = Field(default=None, ge=0)
    interior_budget_max: int | None = Field(default=None, ge=0)
    store_size: str | None = None
    operating_times: list[str] = []
    target_ages: list[str] = []
    target_gender: str | None = None
    business_status: str = Field(min_length=1, max_length=30)
    is_franchise: str | None = None
    franchise_brand: str | None = Field(default=None, max_length=100)
    extra_note: str | None = Field(default=None, max_length=500)


class AreaSearchResponseDTO(BaseModel):
    code: str
    name: str
    gu: str
    dong: str


class BrandSearchResponseDTO(BaseModel):
    id: str
    name: str
    category: str
    alias_of: str | None = None
    disclosure_url: str | None = None
