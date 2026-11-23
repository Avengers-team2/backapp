from fastapi import APIRouter, Query, Depends
from app.service.default_service import get_default_service, DefaultService
from app.schema.common_schema import ApiResponseDTO

router = APIRouter()

from fastapi import BackgroundTasks, File, UploadFile, status
from app.service.report_job_service import ReportJobService, get_report_job_service, run_report_review
from app.schema.user_schema import UserClaimDTO
from app.dependencie.auth_dependency import get_current_user


# 1. 기획서 업로드 (검토 요청 생성, status: PENDING)
@router.post(
    "/jobs",
    summary="기획서 업로드",
    response_model=ApiResponseDTO,
    status_code=status.HTTP_201_CREATED
)
async def upload_report_file(
    file: UploadFile = File(...),
    user_claims: UserClaimDTO = Depends(get_current_user),
    report_job_service: ReportJobService = Depends(get_report_job_service)
):
    job = await report_job_service.upload(user_claims.user_id, file)

    return ApiResponseDTO(
        success=True,
        message="기획서 업로드 성공",
        data=job
    )


# 2. 내 검토 요청 목록 (마이페이지, "/jobs/{report_job_id}"보다 위에 있어야 함)
@router.get(
    "/jobs",
    summary="내 검토 요청 목록 조회",
    response_model=ApiResponseDTO
)
async def get_my_report_jobs(
    page: int = Query(1, ge=1, description="페이지 번호"),
    size: int = Query(10, ge=1, le=50, description="페이지당 개수"),
    user_claims: UserClaimDTO = Depends(get_current_user),
    report_job_service: ReportJobService = Depends(get_report_job_service)
):
    paged_jobs = await report_job_service.get_my_jobs(user_claims.user_id, page, size)

    return ApiResponseDTO(
        success=True,
        message="검토 요청 목록 조회 성공",
        data=paged_jobs
    )


# 3. 검토 시작 (분석 시작하기 버튼, 검토는 백그라운드에서 진행)
@router.post(
    "/jobs/{report_job_id}/start",
    summary="기획서 검토 시작",
    response_model=ApiResponseDTO,
    status_code=status.HTTP_202_ACCEPTED
)
async def start_report_job(
    report_job_id: int,
    background_tasks: BackgroundTasks,
    user_claims: UserClaimDTO = Depends(get_current_user),
    report_job_service: ReportJobService = Depends(get_report_job_service)
):
    job = await report_job_service.start(user_claims.user_id, report_job_id)
    background_tasks.add_task(run_report_review, report_job_id)

    return ApiResponseDTO(
        success=True,
        message="기획서 검토 시작",
        data=job
    )


# 4. 검토 상태 조회 (진행 모달이 2~3초마다 호출)
@router.get(
    "/jobs/{report_job_id}",
    summary="검토 상태 조회",
    response_model=ApiResponseDTO
)
async def get_report_job(
    report_job_id: int,
    user_claims: UserClaimDTO = Depends(get_current_user),
    report_job_service: ReportJobService = Depends(get_report_job_service)
):
    job = await report_job_service.get_job(user_claims.user_id, report_job_id)

    return ApiResponseDTO(
        success=True,
        message="검토 상태 조회 성공",
        data=job
    )


# 5. 검토 요청 삭제 (업로드 화면의 '삭제' 버튼)
@router.delete(
    "/jobs/{report_job_id}",
    summary="검토 요청 삭제",
    response_model=ApiResponseDTO
)
async def delete_report_job(
    report_job_id: int,
    user_claims: UserClaimDTO = Depends(get_current_user),
    report_job_service: ReportJobService = Depends(get_report_job_service)
):
    await report_job_service.delete_job(user_claims.user_id, report_job_id)

    return ApiResponseDTO(
        success=True,
        message="검토 요청 삭제 성공"
    )
