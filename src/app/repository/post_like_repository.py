from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import insert, select, delete, exists
from fastapi import Depends
from app.infrastructure.postgresql import get_postgresql_db
from app.model.post_like_model import PostLike


class PostLikeRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def exists_like(self, user_id: int, post_id: int) -> bool:
        query = select(exists().where(PostLike.user_id == user_id, PostLike.post_id == post_id))
        result = await self.db.execute(query)
        return result.scalar()


    async def create_like(self, user_id: int, post_id: int) -> None:
        query = insert(PostLike).values(user_id=user_id, post_id=post_id)
        await self.db.execute(query)


    async def delete_like(self, user_id: int, post_id: int) -> bool:
        query = delete(PostLike).where(PostLike.user_id == user_id, PostLike.post_id == post_id)
        result = await self.db.execute(query)
        return result.rowcount > 0


def get_post_like_repository(db: AsyncSession = Depends(get_postgresql_db)):
    return PostLikeRepository(db)