from datetime import datetime, timedelta, timezone
from sqlalchemy import BigInteger, Integer, String, DateTime, Identity, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column


from app.infrastructure.postgresql import Base

KST = timezone(timedelta(hours=9))


class PostImage(Base):
    __tablename__ = "post_image"

    image_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    post_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("posts.post_id"), nullable=False)
    image_url: Mapped[str] = mapped_column(String(500), nullable=False)
    image_sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    image_created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(KST)
    )
