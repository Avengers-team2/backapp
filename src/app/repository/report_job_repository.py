from datetime import datetime, timezone

from fastapi import Depends
from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.enum.report_enum import ReportStatus
from app.infrastructure.postgresql import get_postgresql_db
from app.model.report_job_model import ReportJob


class ReportJobRepository:

    # 생성자 주입
    def __init__(self, db: AsyncSession):
        self.db = db

    # 1. 검토 요청 저장 (업로드 완료)
    async def create_job(self, values: dict) -> int:
        query = (
            insert(ReportJob)
            .values(**values)
            .returning(ReportJob.report_job_id)
        )
        result = await self.db.execute(query)
        await self.db.commit()
        return result.scalar_one()

    # 2. 검토 요청 1건 조회
    async def get_by_id(self, report_job_id: int) -> ReportJob | None:
        query = (
            select(ReportJob)
            .where(ReportJob.report_job_id == report_job_id)
            .execution_options(populate_existing=True)   # 상태 변경 직후에도 최신 값으로 다시 읽기
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    # 3. 내 검토 요청 목록 (최신순)
    async def get_by_user(self, user_id: int, offset: int, limit: int) -> list[ReportJob]:
        query = (
            select(ReportJob)
            .where(ReportJob.user_id == user_id)
            .order_by(ReportJob.report_job_created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    # 4. 내 검토 요청 개수
    async def count_by_user(self, user_id: int) -> int:
        query = select(func.count()).select_from(ReportJob).where(ReportJob.user_id == user_id)
        result = await self.db.execute(query)
        return result.scalar_one()

    # 5. 상태 변경 (완료·실패면 완료 일시도 기록)
    async def update_status(
        self,
        report_job_id: int,
        status: ReportStatus,
        error_message: str | None = None
    ) -> None:
        values = {
            "report_job_status": status,
            "report_job_error_message": error_message,
        }
        if status in (ReportStatus.COMPLETED, ReportStatus.FAILED):
            values["report_job_completed_at"] = datetime.now(timezone.utc)

        query = (
            update(ReportJob)
            .where(ReportJob.report_job_id == report_job_id)
            .values(**values)
        )
        await self.db.execute(query)
        await self.db.commit()

    # 7. 다시 검토하기: 실패한 요청을 처음 단계로 되돌림 (에러 메시지·완료 일시 비움)
    async def reset_for_retry(self, report_job_id: int) -> None:
        query = (
            update(ReportJob)
            .where(ReportJob.report_job_id == report_job_id)
            .values(
                report_job_status=ReportStatus.FILE_CHECK,
                report_job_error_message=None,
                report_job_completed_at=None,
            )
        )
        await self.db.execute(query)
        await self.db.commit()

    # 6. 검토 요청 삭제
    async def delete_job(self, report_job_id: int) -> None:
        query = delete(ReportJob).where(ReportJob.report_job_id == report_job_id)
        await self.db.execute(query)
        await self.db.commit()


# 주입 팩토리 메서드
def get_report_job_repository(db: AsyncSession = Depends(get_postgresql_db)):
    return ReportJobRepository(db)
