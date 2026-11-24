import math
from datetime import datetime, timezone
from fastapi import Depends, HTTPException

from app.repository.user_repository import UserRepository, get_user_repository
from app.model.user_model import User
from app.enum.user_enum import UserProvider
from app.schema.user_schema import (
    UserCreateDTO, UserClaimDTO, UserResponseDTO, UserUpdateDTO
)
from app.schema.common_schema import PageResponseDTO
from app.util.security_util import get_password_hash


# 예외처리, 트랜잭션 관리
class UserService:

    def __init__(self, repo: UserRepository):
        self.repo = repo

    # 회원 이메일 중복확인
    async def check_duplicate_user(self, user_email: str, user_provider: str) -> None:
        result = await self.repo.exists_user_email_and_provider(user_email, user_provider)

        if result:
            raise HTTPException(
                status_code=409,
                detail="이미 존재하는 이메일입니다."
            )

    # 회원 가입
    async def join(self, user: UserCreateDTO) -> UserClaimDTO:
        # 필수 약관(서비스 이용약관, 개인정보 수집·이용) 동의 확인
        if not (user.user_agree_terms and user.user_agree_privacy):
            raise HTTPException(
                status_code=400,
                detail="필수 약관에 동의해야 가입할 수 있습니다."
            )

        is_local = user.user_provider == UserProvider.LOCAL

        # 1. 비정상 조합 거절 + 비밀번호 암호화
        #    - 로컬: 비밀번호 필수, 소셜 계정 정보(provider_id) 불가
        #    - 소셜: provider_id 필수, 비밀번호는 저장하지 않음
        encrypted_password = None
        if is_local:
            if not user.user_password:
                raise HTTPException(
                    status_code=400,
                    detail="비밀번호를 입력해주세요."
                )
            if user.user_provider_id:
                raise HTTPException(
                    status_code=400,
                    detail="로컬 회원가입에는 소셜 계정 정보를 보낼 수 없습니다."
                )
            encrypted_password = get_password_hash(user.user_password)
        else:
            if not user.user_provider_id:
                raise HTTPException(
                    status_code=400,
                    detail="소셜 회원가입에는 user_provider_id가 필요합니다."
                )

        # 2. 중복 확인 (이메일+provider, 소셜은 provider_id도)
        await self.check_duplicate_user(user.user_email, user.user_provider)

        if not is_local and await self.repo.exists_user_provider_id(user.user_provider_id):
            raise HTTPException(
                status_code=409,
                detail="이미 가입된 소셜 계정입니다."
            )

        # 암호화된 비밀번호로 교체
        new_user = UserCreateDTO(
            **user.model_dump(exclude={"user_password"}),
            user_password=encrypted_password
        )

        return await self.repo.create_user(new_user)

    # 회원 조회(id)
    async def get_user_by_id(self, user_id: int) -> UserResponseDTO:
        found_user = await self.repo.find_user_by_id(user_id)

        if not found_user:
            raise HTTPException(
                status_code=404,
                detail="회원이 존재하지 않습니다."
            )

        return UserResponseDTO.model_validate(found_user)

    # 회원 조회(email, provider) -> 없으면 None (로그인/소셜로그인에서 사용)
    async def get_user_by_email_and_provider(
        self, user_email: str, user_provider: str
    ) -> User | None:
        return await self.repo.find_user_by_email_and_provider(user_email, user_provider)

    # 회원 조회(email, provider) -> 없으면 404 (API 응답용)
    async def get_user_response_by_email_and_provider(
        self, user_email: str, user_provider: str
    ) -> UserResponseDTO:
        found_user = await self.repo.find_user_by_email_and_provider(user_email, user_provider)

        if not found_user:
            raise HTTPException(
                status_code=404,
                detail="회원이 존재하지 않습니다."
            )

        return UserResponseDTO.model_validate(found_user)

    # 회원 전체 조회 + 페이지네이션
    async def get_users_paging(self, offset: int, limit: int) -> PageResponseDTO:
        current_page = offset
        offset = (offset - 1) * limit

        total_count = await self.repo.count_users()
        users = await self.repo.find_user_by_paging(offset, limit)
        total_pages = math.ceil(total_count / limit)
        items_dto = [UserResponseDTO.model_validate(user) for user in users]

        return PageResponseDTO(
            total_count=total_count,
            total_pages=total_pages,
            offset=current_page,
            limit=limit,
            items=items_dto
        )

    # 회원 정보 수정
    async def update_user(self, user_id: int, user: UserUpdateDTO) -> UserResponseDTO:
        exists_user = await self.repo.exists_user_by_id(user_id)
        if not exists_user:
            raise HTTPException(
                status_code=404,
                detail="회원을 찾을 수 없습니다."
            )

        # dto -> dict
        # exclude_unset=True: 값이 오지 않은 컬럼은 제외
        update_data = user.model_dump(exclude_unset=True)

        if update_data.get("user_password"):
            update_data["user_password"] = get_password_hash(update_data["user_password"])

        # 수정 시간 갱신
        update_data["user_updated_at"] = datetime.now(timezone.utc)

        updated_user = await self.repo.update_user(user_id, update_data)

        # 비밀번호 제거된 응답
        return UserResponseDTO.model_validate(updated_user)

    # 회원 탈퇴
    async def withdraw(self, user_id: int) -> None:
        is_deleted = await self.repo.delete_user(user_id)

        if not is_deleted:
            raise HTTPException(
                status_code=404,
                detail="회원이 존재하지 않습니다."
            )


# 레포지토리 주입 팩토리 함수
def get_user_service(repo: UserRepository = Depends(get_user_repository)):
    return UserService(repo)
