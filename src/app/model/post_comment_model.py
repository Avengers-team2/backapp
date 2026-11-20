from datetime import datetime, timedelta, timezone
from sqlalchemy import BigInteger, Text, DateTime, Identity, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship


from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

KST = timezone(timedelta(hours=9))

if TYPE_CHECKING:
    from app.model.user_model import User
    from app.model.post_model import Post


class PostComment(Base):
    __tablename__ = "post_comments"

    comment_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.user_id"), nullable=False)
    post_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("posts.post_id"), nullable=False)
    parent_comment_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("post_comments.comment_id"), nullable=True
    )
    comment_content: Mapped[str] = mapped_column(Text, nullable=False)
    comment_created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(KST)
    )
    comment_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    comment_deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # 관계
    user: Mapped["User"] = relationship("User")
    post: Mapped["Post"] = relationship("Post", back_populates="comments")

    # 대댓글 (자기 참조)
    parent: Mapped["PostComment | None"] = relationship(
        "PostComment", remote_side=[comment_id], back_populates="children"
    )
    children: Mapped[list["PostComment"]] = relationship("PostComment", back_populates="parent")