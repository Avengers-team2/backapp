from datetime import date, datetime, timedelta, timezone
from sqlalchemy import BigInteger, Date, String, Text, Enum, DateTime, Identity, UniqueConstraint, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.enum.user_enum import UserProvider
from app.model.post_model import Post

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

# 순환참조 (stack over flow 방지 옵션)
# if TYPE_CHECKING:
#     from app.users.post_model import Post

KST = timezone(timedelta(hours=9)) # UTC+9


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_name: Mapped[str | None] = mapped_column(Text)
    user_email: Mapped[str] = mapped_column(Text, nullable=False)
    user_password: Mapped[str | None] = mapped_column(Text)
    user_sex: Mapped[str] = mapped_column(String(10), nullable=False)
    user_nickname: Mapped[str | None] = mapped_column(Text)
    user_birth: Mapped[date] = mapped_column(Date, nullable=False)
    user_phone: Mapped[str] = mapped_column(String(20), nullable=False)

    user_created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    user_deleted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    user_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    user_provider: Mapped[UserProvider] = mapped_column(Enum(UserProvider, native_enum=False), default=UserProvider.LOCAL, nullable=False)
    user_provider_id: Mapped[str | None] = mapped_column(Text, unique=True)

    user_status: Mapped[str] = mapped_column(String(20), nullable=False)
    user_business_status: Mapped[str] = mapped_column(String(30), nullable=False)

    __table_args__ = (
        UniqueConstraint("user_email", "user_provider", name="uq_users_email_provider"),
    )

    # 관계
    # cascade: User가 삭제되면 참조된 테이블을 모두 같이 연쇄삭제
    posts: Mapped[list["Post"]] = relationship("Post", back_populates="user", cascade="all, delete-orphan")