from datetime import datetime, timezone
from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

class ReportExport(Base):
    __tablename__ = "report_export"

    # PK
    export_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    # FK
    report_job_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("report_job.report_job_id"), nullable=False,)

    export_file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    export_created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc),)
    export_result_json: Mapped[dict | None] = mapped_column(JSONB)    # 기획서 AI 검토 결과 (ReportAiResult)