from datetime import date

from fastapi import Depends
from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.postgresql import get_postgresql_db
from app.model.support_bookmark_model import SupportBookmark


class SupportBookmarkRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def exists_bookmark(self, user_id: int, source: str, source_id: str) -> bool:
        query = select(SupportBookmark.bookmark_id).where(
            SupportBookmark.user_id == user_id,
            SupportBookmark.bookmark_program_source == source,
            SupportBookmark.bookmark_program_id == source_id,
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none() is not None

    async def create_bookmark(self, user_id: int, source: str, source_id: str, deadline: date | None) -> None:
        query = insert(SupportBookmark).values(
            user_id=user_id,
            bookmark_program_source=source,
            bookmark_program_id=source_id,
            bookmark_deadline_date=deadline,
        )
        await self.db.execute(query)
        await self.db.commit()

    async def delete_bookmark(self, user_id: int, source: str, source_id: str) -> None:
        query = delete(SupportBookmark).where(
            SupportBookmark.user_id == user_id,
            SupportBookmark.bookmark_program_source == source,
            SupportBookmark.bookmark_program_id == source_id,
        )
        await self.db.execute(query)
        await self.db.commit()

    async def list_bookmarks(self, user_id: int) -> list[SupportBookmark]:
        query = (
            select(SupportBookmark)
            .where(SupportBookmark.user_id == user_id)
            .order_by(SupportBookmark.bookmark_created_at.desc())
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())


def get_support_bookmark_repository(db: AsyncSession = Depends(get_postgresql_db)):
    return SupportBookmarkRepository(db)
