from fastapi import Depends
from sqlalchemy import insert
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


def get_analysis_input_repository(db: AsyncSession = Depends(get_postgresql_db)):
    return AnalysisInputRepository(db)
