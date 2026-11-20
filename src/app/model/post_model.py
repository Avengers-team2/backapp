from datetime import datetime, timedelta, timezone
from sqlalchemy import BigInteger, Integer, String, Text, DateTime, Identity, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship


from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

KST = timezone(timedelta(hours=9))

if TYPE_CHECKING:
    from app.model.user_model import User
    from app.model.post_comment_model import PostComment


class Post(Base):
    __tablename__ = "posts"

    post_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.user_id"), nullable=False)
    post_category: Mapped[str] = mapped_column(String(20), nullable=False)
    post_title: Mapped[str] = mapped_column(String(200), nullable=False)
    post_content: Mapped[str] = mapped_column(Text, nullable=False)
    post_image_url: Mapped[str | None] = mapped_column(String(500))
    post_created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(KST)
    )
    post_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    post_deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    post_view_count: Mapped[int | None] = mapped_column(Integer, default=0)
    post_like_count: Mapped[int | None] = mapped_column(Integer, default=0)

    # 관계
    user: Mapped["User"] = relationship("User")
    comments: Mapped[list["PostComment"]] = relationship("PostComment", back_populates="post")