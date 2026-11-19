from datetime import datetime
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel  # JS 카멜 -> Snake로 변경해서 받기

from app.enum.payment_enum import PaymentStatus

# VO
class PaymentVO(BaseModel):
    payment_id: int
    subscription_id: int
    payment_order_id: str
    payment_provider_tx_id: str | None = None
    payment_amount: int
    payment_status: PaymentStatus = PaymentStatus.READY
    payment_method: str | None = None
    payment_paid_at: datetime
    payment_created_at: datetime | None = None

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)
            