import os

from fastapi import Depends, HTTPException, status

from app.enum.report_enum import ReportStatus
from app.repository.report_export_repository import ReportExportRepository, get_report_export_repository
from app.repository.report_job_repository import ReportJobRepository, get_report_job_repository
from app.schema.report_export_schema import ReportExportDownloadDTO
from app.service.s3_service import S3Service, get_s3_service

DOWNLOAD_URL_EXPIRES_IN = 3600   # 다운로드 링크 유효 시간(초), s3_service.get_download_url과 동일


# 예외처리
# 트랜잭션 관리
class ReportExportService:

    def __init__(
        self,
        report_export_repo: ReportExportRepository,
        report_job_repo: ReportJobRepository,
        s3_service: S3Service
    ):
        self.report_export_repo = report_export_repo
        self.report_job_repo = report_job_repo
        self.s3_service = s3_service

    # 1. 검토 보고서 PDF 다운로드 링크 발급 (결과 화면의 'PDF 내려받기' 버튼)
    async def get_download_url(self, user_id: int, report_job_id: int) -> ReportExportDownloadDTO:
        job = await self.report_job_repo.get_by_id(report_job_id)

        if job is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "검토 요청을 찾을 수 없습니다.")
        if job.user_id != user_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "본인의 검토 보고서만 내려받을 수 있습니다.")
        if job.report_job_status != ReportStatus.COMPLETED:
            raise HTTPException(status.HTTP_409_CONFLICT, "검토가 끝난 기획서만 보고서를 내려받을 수 있습니다.")

        export = await self.report_export_repo.get_latest_by_job(report_job_id)
        if export is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "검토 보고서 PDF가 아직 만들어지지 않았습니다.")

        url = await self.s3_service.get_download_url(export.export_file_path)

        return ReportExportDownloadDTO(
            download_url=url,
            file_name=os.path.basename(export.export_file_path),
            expires_in=DOWNLOAD_URL_EXPIRES_IN
        )


# 레포지토리 주입 팩토리 함수
def get_report_export_service(
        report_export_repo: ReportExportRepository = Depends(get_report_export_repository),
        report_job_repo: ReportJobRepository = Depends(get_report_job_repository),
        s3_service: S3Service = Depends(get_s3_service)
    ):
    return ReportExportService(report_export_repo, report_job_repo, s3_service)
