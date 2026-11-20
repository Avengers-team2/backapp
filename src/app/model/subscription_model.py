from datetime import datetime, timezone
from sqlalchemy import BigInteger, Boolean, DateTime, Enum, ForeignKey, Identity
from sqlalchemy.orm import Mapped, mapped_column
from app.enum.subscription_enum import SubscriptionStatus

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING


class Subscription(Base):
    __tablename__ = "subscriptions"

    # PK
    subscription_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    # FK
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)

    subscription_status: Mapped[SubscriptionStatus] = mapped_column(Enum(SubscriptionStatus, native_enum=False, length=20), default=SubscriptionStatus.ACTIVE, nullable=False, )

    subscription_current_period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    subscription_current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    subscription_created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc),)
    subscription_cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    subscription_cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))