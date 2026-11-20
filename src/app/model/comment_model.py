from datetime import datetime, timezone
from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.postgresql import Base


class PostComment(Base):
    __tablename__ = "post_comments"

    # PK
    comment_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    # FK
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.user_id"), nullable=False)
    post_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("posts.post_id"), nullable=False)
    parent_comment_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("post_comments.comment_id"))

    comment_content: Mapped[str] = mapped_column(Text, nullable=False)

    comment_created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), )
    comment_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),onupdate=lambda: datetime.now(timezone.utc),)
    comment_deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    