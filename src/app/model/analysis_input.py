from datetime import datetime, time, timezone
from sqlalchemy import BigInteger, String, Text, Integer, Boolean, DateTime, ForeignKey, Numeric, Identity, JSON, Time
from sqlalchemy.orm import Mapped, mapped_column

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING


class AnalysisInput(Base):
    __tablename__ = "analysis_input"

    # PK
    input_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    # FK
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.user_id"), nullable=False)
    
    input_trdar_cd: Mapped[str] = mapped_column(String(20), nullable=False)

    input_industry_large: Mapped[str] = mapped_column(String(20), nullable=False)
    input_industry_mid: Mapped[str] = mapped_column(String(50), nullable=False)
    input_industry_small: Mapped[str] = mapped_column(String(10), nullable=False)

    input_store_size: Mapped[str | None] = mapped_column(String(20))

    input_is_franchise: Mapped[bool | None] = mapped_column(Boolean)
    input_franchise_brand: Mapped[str | None] = mapped_column(String(100))

    input_opening_time: Mapped[time | None] = mapped_column(Time)
    input_closing_time: Mapped[time | None] = mapped_column(Time)
    input_operating_days: Mapped[str | None] = mapped_column(String(10))

    input_target_ages: Mapped[str | None] = mapped_column(String(50))
    input_target_gender: Mapped[str | None] = mapped_column(String(10))

    input_extra_note: Mapped[str | None] = mapped_column(Text)

    input_use_purpose: Mapped[str | None] = mapped_column(String(30))

    input_requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc),)
    
    input_deposit_budget: Mapped[int | None] = mapped_column(BigInteger)
    input_monthly_rent_max: Mapped[int | None] = mapped_column(BigInteger)
    input_interior_budget_max: Mapped[int | None] = mapped_column(BigInteger)


