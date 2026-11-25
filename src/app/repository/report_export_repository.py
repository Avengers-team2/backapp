from fastapi import Depends
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.postgresql import get_postgresql_db
from app.model.report_export_model import ReportExport


class ReportExportRepository:

    # 생성자 주입
    def __init__(self, db: AsyncSession):
        self.db = db

    # 1. 검토 보고서 PDF 저장 기록 추가 (검토가 끝날 때)
    async def create_export(self, report_job_id: int, export_file_path: str, result_json: dict | None = None) -> int:
        query = (
            insert(ReportExport)
            .values(
                report_job_id=report_job_id,
                export_file_path=export_file_path,
                export_result_json=result_json,     # Gemini 검토 결과 원본 (결과 화면용)
            )
            .returning(ReportExport.export_id)
        )
        result = await self.db.execute(query)
        await self.db.commit()
        return result.scalar_one()

    # 2. 검토 요청의 가장 최근 보고서 PDF 조회 (다시 검토하면 새 PDF가 생기므로 최신 것)
    async def get_latest_by_job(self, report_job_id: int) -> ReportExport | None:
        query = (
            select(ReportExport)
            .where(ReportExport.report_job_id == report_job_id)
            .order_by(ReportExport.export_created_at.desc())
            .limit(1)
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()


# 주입 팩토리 메서드
def get_report_export_repository(db: AsyncSession = Depends(get_postgresql_db)):
    return ReportExportRepository(db)
