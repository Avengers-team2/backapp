from datetime import datetime
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel  # JS 카멜 -> Snake로 변경해서 받기

from app.enum.subscription_enum import SubscriptionStatus

# VO
class SubscriptionVO(BaseModel):
    subscription_id: int
    user_id: int
    subscription_status: SubscriptionStatus = SubscriptionStatus.ACTIVE
    subscription_current_period_start: datetime | None = None
    subscription_current_period_end: datetime | None = None
    subscription_created_at: datetime | None = None
    subscription_cancel_at_period_end: bool = False
    subscription_cancel_requested_at: datetime | None = None

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)
    