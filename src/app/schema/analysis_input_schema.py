from datetime import datetime, time
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel  # JS 카멜 -> Snake로 변경해서 받기


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
    