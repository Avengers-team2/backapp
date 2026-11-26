import asyncio
import hashlib
import io
import os
import traceback
import unicodedata
import uuid
from datetime import datetime

from fastapi import Depends, HTTPException, UploadFile, status

from app.enum.report_enum import ReportStatus
from app.enum.s3_enum import S3Folder
from app.infrastructure.postgresql import AsyncSessionLocal
from app.model.report_job_model import ReportJob
from app.repository.report_job_repository import ReportJobRepository, get_report_job_repository
from app.schema.common_schema import PageResponseDTO
from app.schema.report_job_schema import ReportJobResponseDTO
from app.service.s3_service import S3Service, get_s3_service
from app.service.s3_service import AWS_S3_BUCKET
from app.repository.report_export_repository import ReportExportRepository
from app.service.report_ai_service import analyze_report
from app.util.report_pdf_util import build_report_pdf
from app.util.report_text_util import extract_report_text, has_enough_text

ALLOWED_FILE_TYPES = {"pdf", "docx"}        # 기획서 허용 형식 (hwp는 팀 결정 후 추가)
MAX_FILE_SIZE = 10 * 1024 * 1024            # 10MB (s3_api와 동일)
DELETABLE_STATUSES = {ReportStatus.PENDING, ReportStatus.FAILED}   # 시작 전이거나 실패한 것만 삭제 가능


# 예외처리
# 트랜잭션 관리
class ReportJobService:

    def __init__(self, report_job_repo: ReportJobRepository, s3_service: S3Service):
        self.report_job_repo = report_job_repo
        self.s3_service = s3_service

    # 1. 기획서 업로드 → S3 저장 → report_job 생성 (status: PENDING)
    async def upload(self, user_id: int, file: UploadFile) -> ReportJobResponseDTO:
        # Mac에서 올린 한글 파일 이름(자모가 쪼개진 NFD)을 일반 형태(NFC)로 맞춘다.
        file_name = unicodedata.normalize("NFC", os.path.basename(file.filename or ""))
        file_type = os.path.splitext(file_name)[1].lower().lstrip(".")   # "카페.PDF" → "pdf"

        if file_type not in ALLOWED_FILE_TYPES:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "PDF, DOCX 파일만 업로드할 수 있습니다.")

        content = await file.read()
        if not content:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "빈 파일은 업로드할 수 없습니다.")
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "파일은 10MB 이하만 업로드할 수 있습니다.")

        file_hash = hashlib.sha256(content).hexdigest()
        page_count = count_pdf_pages(content) if file_type == "pdf" else None

        # 위에서 끝까지 읽었으니 처음으로 되돌린 뒤 S3에 올린다.
        await file.seek(0)
        uploaded = await self.s3_service.upload_file(file=file, folder=S3Folder.REPORT.value)

        report_job_id = await self.report_job_repo.create_job({
            "user_id": user_id,
            "report_job_file_name": file_name,
            "report_job_file_type": file_type,
            "report_job_file_size": len(content),
            "report_job_file_path": uploaded.file_key,
            "report_job_page_count": page_count,
            "report_job_file_hash": file_hash,
            "report_job_status": ReportStatus.PENDING,
        })

        job = await self.report_job_repo.get_by_id(report_job_id)
        return ReportJobResponseDTO.model_validate(job)

    # 2. 검토 시작 (PENDING → FILE_CHECK). 실제 검토는 api에서 백그라운드로 실행
    async def start(self, user_id: int, report_job_id: int) -> ReportJobResponseDTO:
        job = await self._get_owned_job(user_id, report_job_id)

        if job.report_job_status != ReportStatus.PENDING:
            raise HTTPException(status.HTTP_409_CONFLICT, "이미 시작했거나 끝난 검토입니다.")

        await self.report_job_repo.update_status(report_job_id, ReportStatus.FILE_CHECK)

        job = await self.report_job_repo.get_by_id(report_job_id)
        return ReportJobResponseDTO.model_validate(job)

    # 2-1. 다시 검토하기 (FAILED → FILE_CHECK). 오류 화면의 '다시 검토하기' 버튼
    async def retry(self, user_id: int, report_job_id: int) -> ReportJobResponseDTO:
        job = await self._get_owned_job(user_id, report_job_id)

        if job.report_job_status != ReportStatus.FAILED:
            raise HTTPException(status.HTTP_409_CONFLICT, "실패한 검토만 다시 시도할 수 있습니다.")

        await self.report_job_repo.reset_for_retry(report_job_id)

        job = await self.report_job_repo.get_by_id(report_job_id)
        return ReportJobResponseDTO.model_validate(job)

    # 3. 검토 상태 조회 (진행 모달이 2~3초마다 호출)
    async def get_job(self, user_id: int, report_job_id: int) -> ReportJobResponseDTO:
        job = await self._get_owned_job(user_id, report_job_id)
        return ReportJobResponseDTO.model_validate(job)

    # 4. 내 검토 요청 목록 (마이페이지)
    async def get_my_jobs(self, user_id: int, page: int, size: int) -> PageResponseDTO[ReportJobResponseDTO]:
        offset = (page - 1) * size
        jobs = await self.report_job_repo.get_by_user(user_id, offset, size)
        total = await self.report_job_repo.count_by_user(user_id)

        return PageResponseDTO(
            total_count=total,
            total_pages=(total + size - 1) // size,
            offset=offset,
            limit=size,
            items=[ReportJobResponseDTO.model_validate(j) for j in jobs]
        )

    # 5. 검토 요청 삭제 (업로드 화면의 '삭제' 버튼)
    async def delete_job(self, user_id: int, report_job_id: int) -> None:
        job = await self._get_owned_job(user_id, report_job_id)

        if job.report_job_status not in DELETABLE_STATUSES:
            raise HTTPException(status.HTTP_409_CONFLICT, "검토가 진행 중이거나 끝난 요청은 삭제할 수 없습니다.")

        try:
            await self.s3_service.delete_file(job.report_job_file_path)
        except Exception:
            pass   # S3에 파일이 없어도 DB 기록은 지운다.

        await self.report_job_repo.delete_job(report_job_id)

    # 본인 요청인지 확인
    async def _get_owned_job(self, user_id: int, report_job_id: int) -> ReportJob:
        job = await self.report_job_repo.get_by_id(report_job_id)

        if job is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "검토 요청을 찾을 수 없습니다.")
        if job.user_id != user_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "본인의 검토 요청만 볼 수 있습니다.")

        return job


# PDF 쪽수 세기 (pypdf가 없거나 읽을 수 없는 파일이면 None)
def count_pdf_pages(content: bytes) -> int | None:
    try:
        from pypdf import PdfReader
        return len(PdfReader(io.BytesIO(content)).pages)
    except Exception:
        return None


# 백그라운드 검토 작업
# 응답을 보낸 뒤에 실행되므로 요청용 DB 세션을 쓰지 않고 새로 연다.
# 1단계 파일 확인 → 2단계 Gemini 검토 → 3단계 검토 보고서 PDF 생성·S3 저장 → 완료
async def run_report_review(report_job_id: int, s3_service: S3Service) -> None:
    async with AsyncSessionLocal() as db:
        repo = ReportJobRepository(db)
        export_repo = ReportExportRepository(db)
        try:
            job = await repo.get_by_id(report_job_id)

            # 1단계: 파일 확인 (FILE_CHECK는 start에서 이미 설정됨)
            # S3에서 원본을 받아 문서 로더로 텍스트를 뽑는다.
            obj = await s3_service.s3_client.get_object(Bucket=AWS_S3_BUCKET, Key=job.report_job_file_path)
            content = await obj["Body"].read()
            text = await asyncio.to_thread(extract_report_text, content, job.report_job_file_type)

            if not has_enough_text(text):
                raise ReviewFailed("글자를 읽을 수 없는 파일입니다. 스캔 이미지가 아닌, 글자가 들어 있는 PDF·DOCX로 다시 올려 주세요.")

            # 2단계: AI 검토 (Gemini)
            await repo.update_status(report_job_id, ReportStatus.AI_REVIEW)
            result = await analyze_report(text)

            if result.llm.status == "UNAVAILABLE":
                raise ReviewFailed(f"{result.llm.unavailable_reason} {result.llm.guide}".strip()
                                   or "사업계획서로 검토할 수 없는 문서입니다.")

            # 3단계: 검토 결과 정리 → 검토 보고서 PDF 만들기 → S3 저장 → report_export 기록
            await repo.update_status(report_job_id, ReportStatus.SUMMARIZING)
            pdf_bytes = await asyncio.to_thread(build_report_pdf, result, job.report_job_file_name)

            stem = os.path.splitext(job.report_job_file_name)[0]
            today = datetime.now().strftime("%Y/%m/%d")
            export_key = f"{S3Folder.REPORT.value}/{today}/export/{uuid.uuid4()}/검토보고서_{stem}.pdf"
            await s3_service.s3_client.put_object(
                Bucket=AWS_S3_BUCKET,
                Key=export_key,
                Body=pdf_bytes,
                ContentType="application/pdf",
            )
            await export_repo.create_export(report_job_id, export_key, result.model_dump(mode="json"))

            await repo.update_status(report_job_id, ReportStatus.COMPLETED)

        except ReviewFailed as e:
            await db.rollback()
            await repo.update_status(report_job_id, ReportStatus.FAILED, str(e))

        except Exception:
            traceback.print_exc()   # 원인은 서버 터미널에서 확인
            await db.rollback()
            await repo.update_status(
                report_job_id,
                ReportStatus.FAILED,
                "AI 응답을 받지 못했습니다. 잠시 후 다시 시도해 주세요."
            )


# 화면에 그대로 보여 줄 실패 사유가 있는 경우
class ReviewFailed(Exception):
    pass


# 레포지토리 주입 팩토리 함수
def get_report_job_service(
        report_job_repo: ReportJobRepository = Depends(get_report_job_repository),
        s3_service: S3Service = Depends(get_s3_service)
    ):
    return ReportJobService(report_job_repo, s3_service)
