from datetime import datetime, timezone
from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Identity, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.enum.report_enum import ReportStatus

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING


class ReportJob(Base):
    __tablename__ = "report_job"

    # PK
    report_job_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    # FK
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.user_id"), nullable=False)

    report_job_file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    report_job_file_type: Mapped[str] = mapped_column(String(10), nullable=False)
    report_job_file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    report_job_file_path: Mapped[str] = mapped_column(String(500), nullable=False)

    report_job_created_at: Mapped[datetime] = mapped_column( DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc),)
    report_job_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    report_job_status: Mapped[ReportStatus] = mapped_column(Enum(ReportStatus, native_enum=False, length=20), default=ReportStatus.PENDING, nullable=False,)
    report_job_error_message: Mapped[str | None] = mapped_column(Text)