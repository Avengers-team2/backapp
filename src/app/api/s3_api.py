import os
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, status
from app.service.s3_service import get_s3_service, S3Service
from app.enum.s3_enum import S3Folder
from app.schema.common_schema import ApiResponseDTO
from app.schema.s3_schema import ImageUploadResponseDTO, FileUploadResponseDTO
from app.schema.user_schema import UserClaimDTO
from app.dependencie.auth_dependency import get_current_user

router = APIRouter()

MAX_IMAGE_SIZE = 5 * 1024 * 1024    # 이미지 최대 5MB
MAX_FILE_SIZE = 10 * 1024 * 1024    # 파일 최대 10MB
ALLOWED_FILE_EXTS = {".hwp", ".docx", ".pdf"}  # 기획서 허용 확장자 (한글, 워드, PDF)

# 1. 이미지 업로드 (게시글 사진 등) — 원본 + 썸네일
@router.post(
    "/images",
    summary="이미지 업로드 (원본 + 썸네일)",
    response_model=ApiResponseDTO
)
async def upload_image(
    file: UploadFile = File(...),
    folder: S3Folder = Form(...),
    user_claims: UserClaimDTO = Depends(get_current_user),
    s3_service: S3Service = Depends(get_s3_service)
):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="이미지 파일만 업로드할 수 있습니다."
        )

    if file.size is not None and file.size > MAX_IMAGE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="이미지는 5MB 이하만 업로드할 수 있습니다."
        )

    dto = await s3_service.upload_image_with_thumbnail(file=file, folder=folder.value)
    return ApiResponseDTO(
        success=True,
        message="이미지 업로드 성공",
        data=dto
    )


# 2. 일반 파일 업로드 (기획서 등)
@router.post(
    "/files",
    summary="파일 업로드",
    response_model=ApiResponseDTO
)
async def upload_file(
    file: UploadFile = File(...),
    folder: S3Folder = Form(...),
    user_claims: UserClaimDTO = Depends(get_current_user),
    s3_service: S3Service = Depends(get_s3_service)
):
    filename = (file.filename or "").lower()
    ext = os.path.splitext(filename)[1]   # "카페.PDF" → ".pdf"
    if ext not in ALLOWED_FILE_EXTS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="hwp, docx, PDF 파일만 업로드할 수 있습니다."
        )

    if file.size is not None and file.size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="파일은 10MB 이하만 업로드할 수 있습니다."
        )
    
    dto = await s3_service.upload_file(file=file, folder=folder.value)
    return ApiResponseDTO(
        success=True,
        message="파일 업로드 성공",
        data=dto
    )


# 3. 파일 다운로드 URL 발급 (기한 있는 링크)
@router.get(
    "/download-url",
    summary="파일 다운로드 URL 발급",
    response_model=ApiResponseDTO
)
async def get_download_url(
    key: str,
    user_claims: UserClaimDTO = Depends(get_current_user),
    s3_service: S3Service = Depends(get_s3_service)
):
    url = await s3_service.get_download_url(key)
    return ApiResponseDTO(
        success=True,
        message="다운로드 성공",
        data={"download_url": url}
    )


# 4. 파일 삭제
@router.delete(
    "",
    summary="파일 삭제",
    response_model=ApiResponseDTO
)
async def delete_file(
    key: str,
    user_claims: UserClaimDTO = Depends(get_current_user),
    s3_service: S3Service = Depends(get_s3_service)
):
    await s3_service.delete_file(key)
    return ApiResponseDTO(
        success=True,
        message="파일 삭제 성공"
    )
