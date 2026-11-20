from datetime import date, datetime, timezone
from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Identity, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING
 

class SupportBookmark(Base):
    __tablename__ = "support_bookmark"

    # PK
    bookmark_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    # FK
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.user_id"), nullable=False)

    bookmark_program_id: Mapped[str] = mapped_column(String(100), nullable=False)
    bookmark_program_source: Mapped[str] = mapped_column(String(30), nullable=False)
    bookmark_deadline_date: Mapped[date | None] = mapped_column(Date)

    bookmark_notify_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    bookmark_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    bookmark_created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc),)

    # 중복 북마크 막기
    __table_args__ = (
        UniqueConstraint(
            "user_id", "bookmark_program_source", "bookmark_program_id",
            name="uq_support_bookmark_user_program",
        ),
    )