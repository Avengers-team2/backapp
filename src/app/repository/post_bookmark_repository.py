from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import insert, select, delete, exists, func, desc
from sqlalchemy.orm import joinedload
from fastapi import Depends
from app.infrastructure.postgresql import get_postgresql_db
from app.model.post_bookmark_model import PostBookmark
from app.model.post_model import Post
from app.repository.post_repository import comment_count_subquery

class PostBookmarkRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def exists_bookmark(self, user_id: int, post_id: int) -> bool:
        query = select(exists().where(PostBookmark.user_id == user_id, PostBookmark.post_id == post_id))
        result = await self.db.execute(query)
        return result.scalar()


    async def create_bookmark(self, user_id: int, post_id: int) -> None:
        query = insert(PostBookmark).values(user_id=user_id, post_id=post_id)
        await self.db.execute(query)


    async def delete_bookmark(self, user_id: int, post_id: int) -> bool:
        query = delete(PostBookmark).where(PostBookmark.user_id == user_id, PostBookmark.post_id == post_id)
        result = await self.db.execute(query)
        return result.rowcount > 0


    async def find_my_bookmarks(self, user_id: int, offset: int, limit: int):
        query = (
            select(Post, comment_count_subquery().label("comment_count"))
                .join(PostBookmark, PostBookmark.post_id == Post.post_id)
                .options(joinedload(Post.user))
                .where(PostBookmark.user_id == user_id, Post.post_deleted_at.is_(None))
                .order_by(desc(PostBookmark.bookmark_created_at))
                .offset(offset)
                .limit(limit)
        )
        count_query = (
            select(func.count(PostBookmark.bookmark_id))
                .join(Post, Post.post_id == PostBookmark.post_id)
                .where(PostBookmark.user_id == user_id, Post.post_deleted_at.is_(None))
        )

        count_result = await self.db.execute(count_query)
        total = count_result.scalar_one()
        result = await self.db.execute(query)
        return list(result.tuples().all()), total


def get_post_bookmark_repository(db: AsyncSession = Depends(get_postgresql_db)):
    return PostBookmarkRepository(db)