from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import insert, select, update, func
from fastapi import Depends
from app.infrastructure.postgresql import get_postgresql_db
from app.model.post_comment_model import PostComment


class CommentRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    # 삭제 안 된 댓글 1개 조회 (답글 대상 확인, 작성자 확인에 사용)
    async def get_by_id(self, comment_id: int) -> PostComment | None:
        query = select(PostComment).where(
            PostComment.comment_id == comment_id,
            PostComment.comment_deleted_at.is_(None)
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()


    async def create_comment(
        self,
        user_id: int,
        post_id: int,
        comment_content: str,
        parent_comment_id: int | None
    ) -> int:
        query = (
            insert(PostComment)
                .values(
                    user_id=user_id,
                    post_id=post_id,
                    comment_content=comment_content,
                    parent_comment_id=parent_comment_id
                )
                .returning(PostComment.comment_id)
        )
        result = await self.db.execute(query)
        await self.db.commit()
        return result.scalar_one()


    async def update_comment(self, comment_id: int, comment_content: str) -> int | None:
        query = (
            update(PostComment)
                .where(PostComment.comment_id == comment_id, PostComment.comment_deleted_at.is_(None))
                .values(comment_content=comment_content, comment_updated_at=func.now())
                .returning(PostComment.comment_id)
        )
        result = await self.db.execute(query)
        await self.db.commit()
        return result.scalar_one_or_none()


    async def delete_comment(self, comment_id: int) -> bool:
        query = (
            update(PostComment)
                .where(PostComment.comment_id == comment_id, PostComment.comment_deleted_at.is_(None))
                .values(comment_deleted_at=func.now())
        )
        result = await self.db.execute(query)
        await self.db.commit()
        return result.rowcount > 0


def get_comment_repository(db: AsyncSession = Depends(get_postgresql_db)):
    return CommentRepository(db)