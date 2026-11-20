from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Identity, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column
from app.enum.payment_enum import PaymentStatus

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING


class Payment(Base):
    __tablename__ = "payments"

    # PK
    payment_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    # FK
    subscription_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("subscriptions.subscription_id"), nullable=False, )

    payment_order_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    payment_provider_tx_id: Mapped[str | None] = mapped_column(String(200))

    payment_amount: Mapped[Decimal] = mapped_column(Numeric(12, 0), nullable=False)
    payment_status: Mapped[PaymentStatus] = mapped_column(Enum(PaymentStatus, native_enum=False, length=20), default=PaymentStatus.READY, nullable=False,)
    payment_method: Mapped[str | None] = mapped_column(String(30))

    payment_paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payment_created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,default=lambda: datetime.now(timezone.utc),)