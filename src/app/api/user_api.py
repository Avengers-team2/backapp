from fastapi import APIRouter, Query, Depends, HTTPException
from app.service.user_service import get_user_service, UserService
from app.schema.user_schema import (
    UserCreateDTO, UserClaimDTO, UserUpdateDTO
)
from app.schema.common_schema import ApiResponseDTO
from app.dependencie.auth_dependency import get_current_user


router = APIRouter()


@router.post(
    "/check-user",
    summary="회원 중복 확인",
    response_model=ApiResponseDTO
)
async def check_user(
    user_email: str,
    user_provider: str,
    user_service: UserService = Depends(get_user_service)
):
    await user_service.check_duplicate_user(user_email, user_provider)
    return ApiResponseDTO(
        success=True,
        message="중복되지 않은 사용자",
    )


@router.post(
    "/join",
    summary="회원 가입",
    response_model=ApiResponseDTO,
    responses={
        409: {
            "description": "중복된 이메일로 회원가입 시도",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "이미 존재하는 이메일입니다."
                    }
                }
            }
        }
    }
)
async def join(
    user: UserCreateDTO,
    user_service: UserService = Depends(get_user_service)
):
    user_claim: UserClaimDTO = await user_service.join(user)

    return ApiResponseDTO(
        success=True,
        message="회원가입 성공",
        data=user_claim
    )


# access_token -> 로그인한 사용자 정보 조회
# (/{user_id} 보다 먼저 선언해야 "me"가 id로 해석되지 않는다)
@router.post(
    "/me",
    response_model=ApiResponseDTO,
    summary="Access Token으로 회원정보 조회"
)
async def me(
    current_user: UserClaimDTO = Depends(get_current_user),
    user_service: UserService = Depends(get_user_service)
):
    found_user = await user_service.get_user_by_id(current_user.user_id)

    return ApiResponseDTO(
        success=True,
        message="회원 정보 조회 완료",
        data=found_user
    )


# Query(...): 쿼리스트링으로 데이터를 받기, (...): 필수
# get방식 값을 전송하는 방법 -> ?key=value&key=value
@router.get(
    "/",
    summary="회원 정보 조회(email, provider)",
    response_model=ApiResponseDTO
)
async def get_user_by_email_and_provider(
    user_email: str = Query(...),
    user_provider: str = Query(...),
    user_service: UserService = Depends(get_user_service)
):
    found_user = await user_service.get_user_response_by_email_and_provider(user_email, user_provider)
    return ApiResponseDTO(
        success=True,
        message="회원 조회 성공",
        data=found_user
    )


@router.get(
    "/{user_id}",
    summary="회원 정보 조회(id)",
    response_model=ApiResponseDTO,
)
async def get_user_by_id(
    user_id: int,
    user_service: UserService = Depends(get_user_service)
):
    found_user = await user_service.get_user_by_id(user_id)
    return ApiResponseDTO(
        success=True,
        message="회원 조회 성공",
        data=found_user
    )


@router.get(
    "",
    summary="회원 전체 정보 조회",
    response_model=ApiResponseDTO
)
async def get_users(
    offset: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    user_service: UserService = Depends(get_user_service)
):
    page_result = await user_service.get_users_paging(offset, limit)

    return ApiResponseDTO(
        success=True,
        message="회원 전체 조회 성공",
        data=page_result
    )


# 본인 정보만 수정/탈퇴할 수 있도록 로그인한 사용자와 id를 비교한다.
@router.put(
    "/{user_id}",
    summary="회원 정보 수정",
    response_model=ApiResponseDTO
)
async def update_user(
    user_id: int,
    user: UserUpdateDTO,
    current_user: UserClaimDTO = Depends(get_current_user),
    user_service: UserService = Depends(get_user_service)
):
    if current_user.user_id != user_id:
        raise HTTPException(status_code=403, detail="본인 정보만 수정할 수 있습니다.")

    updated_user = await user_service.update_user(user_id, user)

    return ApiResponseDTO(
        success=True,
        message="회원 정보 업데이트 완료",
        data=updated_user
    )


@router.delete(
    "/{user_id}",
    summary="회원 탈퇴",
    response_model=ApiResponseDTO
)
async def withdraw(
    user_id: int,
    current_user: UserClaimDTO = Depends(get_current_user),
    user_service: UserService = Depends(get_user_service)
):
    if current_user.user_id != user_id:
        raise HTTPException(status_code=403, detail="본인 계정만 탈퇴할 수 있습니다.")

    await user_service.withdraw(user_id)

    return ApiResponseDTO(
        success=True,
        message="회원 탈퇴 완료"
    )
