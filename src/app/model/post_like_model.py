from datetime import datetime, timedelta, timezone
from sqlalchemy import BigInteger, DateTime, Identity, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


from app.infrastructure.postgresql import Base

KST = timezone(timedelta(hours=9))


class PostLike(Base):
    __tablename__ = "post_like"

    like_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    post_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("posts.post_id"), nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.user_id"), nullable=False)
    like_created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(KST)
    )

    __table_args__ = (
        UniqueConstraint("user_id", "post_id", name="uq_post_like_user_post"),
    )