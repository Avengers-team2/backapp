from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import BigInteger, Boolean, CHAR, DateTime, ForeignKey, Identity, JSON, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING


class Analysis(Base):
    __tablename__ = "analysis"

    # PK
    analysis_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    # FK
    input_id: Mapped[int] = mapped_column(BigInteger,ForeignKey("analysis_input.input_id"),nullable=False,)

    analysis_total_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    analysis_grade: Mapped[str | None] = mapped_column(CHAR(1))

    analysis_sales_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    analysis_competition_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    analysis_customer_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    analysis_time_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    analysis_closure_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    analysis_stability_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))

    analysis_closure_grade: Mapped[str | None] = mapped_column(String(10))

    analysis_predicted_sales: Mapped[int | None] = mapped_column(BigInteger)
    analysis_predict_quarter: Mapped[str | None] = mapped_column(CHAR(5))
    analysis_model_version: Mapped[str | None] = mapped_column(String(30))
    analysis_data_quarter: Mapped[str] = mapped_column(CHAR(5), nullable=False)

    analysis_result_detail: Mapped[dict | None] = mapped_column(JSON)

    analysis_is_saved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    analysis_created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc),)