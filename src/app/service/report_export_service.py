import os

from fastapi import Depends, HTTPException, status

from app.enum.report_enum import ReportStatus
from app.repository.report_export_repository import ReportExportRepository, get_report_export_repository
from app.repository.report_job_repository import ReportJobRepository, get_report_job_repository
from app.schema.report_export_schema import (
    ReportExportDownloadDTO,
    ReportResultDTO,
    ReportResultFinanceDTO,
    ReportResultItemDTO,
    ReportResultSuggestionDTO,
)
from app.schema.report_ai_schema import ReportAiResult
from app.service.s3_service import AWS_S3_BUCKET
from app.util.report_pdf_util import ITEM_LABELS
from app.util.report_score_util import item_score, total_grade
from app.service.s3_service import S3Service, get_s3_service

DOWNLOAD_URL_EXPIRES_IN = 3600   # 다운로드 링크 유효 시간(초), s3_service.get_download_url과 동일

# 결과 화면 점수 카드용 짧은 항목 이름 (카드 6개가 한 줄에 들어가도록)
ITEM_SHORT_LABELS = {
    "item_differentiation": "아이템·차별성",
    "market_customer": "시장·고객",
    "business_model_profit": "사업모델·수익성",
    "marketing": "마케팅",
    "operation_plan": "운영·실행",
    "risk_management": "위험 관리",
}


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


    # 2. 검토 결과 조회 (결과 화면: 종합 점수, 항목별 점수, 보완할 점, 보고서 미리보기)
    async def get_result(self, user_id: int, report_job_id: int) -> ReportResultDTO:
        job = await self.report_job_repo.get_by_id(report_job_id)

        if job is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "검토 요청을 찾을 수 없습니다.")
        if job.user_id != user_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "본인의 검토 결과만 볼 수 있습니다.")
        if job.report_job_status != ReportStatus.COMPLETED:
            raise HTTPException(status.HTTP_409_CONFLICT, "검토가 끝난 기획서만 결과를 볼 수 있습니다.")

        export = await self.report_export_repo.get_latest_by_job(report_job_id)
        if export is None or not export.export_result_json:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "검토 결과가 아직 저장되지 않았습니다.")

        result = ReportAiResult.model_validate(export.export_result_json)
        llm = result.llm
        grades = {g.item_key: g.grade for g in result.grades}

        items = [
            ReportResultItemDTO(
                item_key=item.item_key,
                label=ITEM_LABELS.get(item.item_key, item.item_key),
                short_label=ITEM_SHORT_LABELS.get(item.item_key, item.item_key),
                score=item_score(item.score),
                grade=grades.get(item.item_key, ""),
                judgment=item.evidence.judgment,
                strengths=item.strengths,
                gaps=item.gaps,
            )
            for item in llm.items
        ]

        # 보고서 PDF 용량 (화면의 "PDF · 2.4MB" 표시용, 못 읽어도 결과는 보여 줌)
        pdf_size = None
        try:
            head = await self.s3_service.s3_client.head_object(Bucket=AWS_S3_BUCKET, Key=export.export_file_path)
            pdf_size = head.get("ContentLength")
        except Exception:
            pass

        # 원본 미리보기 주소: PDF만 브라우저에서 바로 볼 수 있음 (DOCX는 None)
        original_url = None
        if job.report_job_file_type == "pdf":
            try:
                original_url = await self.s3_service.s3_client.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": AWS_S3_BUCKET, "Key": job.report_job_file_path},
                    ExpiresIn=DOWNLOAD_URL_EXPIRES_IN,
                )
            except Exception:
                pass

        return ReportResultDTO(
            report_job_id=report_job_id,
            file_name=job.report_job_file_name,
            file_type=job.report_job_file_type,
            business_item=llm.business_item,
            reviewed_at=job.report_job_completed_at,
            total_score=result.total_score,
            total_grade=total_grade(result.total_score),
            summary=llm.summary,
            key_strengths=llm.key_strengths,
            items=items,
            suggestions=[ReportResultSuggestionDTO(**s.model_dump()) for s in llm.suggestions],
            finance_checks=[ReportResultFinanceDTO(**c.model_dump()) for c in result.finance_checks],
            final_opinion=llm.final_opinion,
            pdf_file_name=os.path.basename(export.export_file_path),
            pdf_size=pdf_size,
            original_url=original_url,
        )


# 레포지토리 주입 팩토리 함수
def get_report_export_service(
        report_export_repo: ReportExportRepository = Depends(get_report_export_repository),
        report_job_repo: ReportJobRepository = Depends(get_report_job_repository),
        s3_service: S3Service = Depends(get_s3_service)
    ):
    return ReportExportService(report_export_repo, report_job_repo, s3_service)
