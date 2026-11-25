from fastapi import Depends
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.postgresql import get_postgresql_db
from app.model.analysis_input import AnalysisInput


class AnalysisInputRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_input(self, values: dict) -> int:
        query = (
            insert(AnalysisInput)
            .values(**values)
            .returning(AnalysisInput.input_id)
        )
        result = await self.db.execute(query)
        await self.db.commit()
        return result.scalar_one()

    async def get_input(self, input_id: int, user_id: int) -> AnalysisInput | None:
        query = select(AnalysisInput).where(
            AnalysisInput.input_id == input_id,
            AnalysisInput.user_id == user_id,
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def list_inputs(self, user_id: int, limit: int) -> list[AnalysisInput]:
        query = (
            select(AnalysisInput)
            .where(AnalysisInput.user_id == user_id)
            .order_by(AnalysisInput.input_requested_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())


def get_analysis_input_repository(db: AsyncSession = Depends(get_postgresql_db)):
    return AnalysisInputRepository(db)
