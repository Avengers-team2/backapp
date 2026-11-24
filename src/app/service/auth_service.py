import os
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from jose import jwt, JWTError
from fastapi import Depends, HTTPException, status

from app.repository.redis_repository import get_redis_repository, RedisRepository
from app.service.user_service import get_user_service, UserService
from app.util.security_util import verify_password
from app.util.jwt_token_util import (
    parse_token, generate_access_token, generate_refresh_token, reissue_access_token
)
from app.schema.auth_schema import JwtTokenDTO, LoginRequestDTO, SocialLoginRequestDTO
from app.schema.user_schema import UserClaimDTO, UserCreateDTO
from app.enum.user_enum import UserProvider

load_dotenv()
TOKEN_BLACKLIST_PREFIX = os.getenv("TOKEN_BLACKLIST_PREFIX")
REFRESH_TOKEN_PREFIX = os.getenv("REFRESH_TOKEN_PREFIX")
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM")

# 소셜 가입 전용 토큰 (소셜 인증을 통과한 이메일/provider 정보를 변조 없이 /auth/join까지 전달)
SOCIAL_JOIN_TOKEN_PURPOSE = "social_join"
SOCIAL_JOIN_TOKEN_MINUTES = 10


# 예외처리, 트랜잭션 관리
class AuthService:

    def __init__(
        self,
        redis_repo: RedisRepository,
        user_service: UserService
    ):
        self.redis_repo = redis_repo
        self.user_service = user_service

    # redis에 refresh_token 저장
    # key - 콜론 체이닝
    async def save_refresh_token(self, user_id: int, refresh_token: str) -> None:
        try:
            key = f"{REFRESH_TOKEN_PREFIX}{user_id}"
            ex = 60 * 60 * 24 * 30  # 30일
            await self.redis_repo.set(key, refresh_token, ex=ex)

        except Exception:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="save_refresh_token 오류"
            )

    # redis에 등록된 refresh_token이 유효한지 검사
    async def validate_refresh_token(self, user_id: int, refresh_token: str) -> bool:
        key = f"{REFRESH_TOKEN_PREFIX}{user_id}"
        saved_token = await self.redis_repo.get(key)
        return refresh_token == saved_token

    # redis에 등록된 refresh_token을 삭제
    async def delete_refresh_token(self, user_id: int) -> None:
        key = f"{REFRESH_TOKEN_PREFIX}{user_id}"
        await self.redis_repo.delete(key)

    # redis에 access_token 무효화 -> 블랙리스트로 등록(로그아웃)
    async def save_blacklisted_token(self, access_token: str) -> None:
        try:
            key = f"{TOKEN_BLACKLIST_PREFIX}{access_token}"
            ex = 60 * 60 * 24

            await self.redis_repo.set(key, "blacklisted", ex=ex)

        except Exception:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="save_blacklisted_token 오류"
            )

    # redis에 블랙리스트로 등록되어있는지 확인
    async def is_blacklisted_token(self, access_token: str) -> bool:
        key = f"{TOKEN_BLACKLIST_PREFIX}{access_token}"
        # True -> 블랙리스트, False -> 사용가능
        return await self.redis_repo.exists(key)

    # access/refresh 토큰 발급 + refresh redis 저장 (로그인 공통 로직)
    async def _issue_tokens(self, user_id: int, user_email: str, user_provider) -> JwtTokenDTO:
        # 유저의 정보 중 최소한의 정보만 claim에 담기
        claims = UserClaimDTO(
            user_id=user_id,
            user_email=user_email,
            user_provider=user_provider
        )

        access_token = generate_access_token(claims)
        refresh_token = generate_refresh_token(claims)

        await self.save_refresh_token(user_id, refresh_token)

        return JwtTokenDTO(
            access_token=access_token,
            refresh_token=refresh_token
        )

    # 로컬 로그인
    async def login(self, login_request_dto: LoginRequestDTO) -> JwtTokenDTO:
        # 1. 회원 조회
        user_in_db = await self.user_service.get_user_by_email_and_provider(
            login_request_dto.user_email,
            login_request_dto.user_provider
        )

        if not user_in_db:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="회원이 존재하지 않습니다."
            )

        # 2. 비밀번호 검증(단방향 검사)
        if not login_request_dto.user_password or not user_in_db.user_password or not verify_password(
            login_request_dto.user_password,  # 플레인 비밀번호
            user_in_db.user_password          # 암호화된 비밀번호
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="아이디 또는 비밀번호가 일치하지 않습니다."
            )

        # 3. 토큰 발급 + 4. refresh redis 저장
        return await self._issue_tokens(
            user_in_db.user_id,
            user_in_db.user_email,
            user_in_db.user_provider
        )

    # 소셜 로그인 (가입된 회원이면 토큰, 아니면 None)
    async def social_login_or_none(self, social_user: SocialLoginRequestDTO) -> JwtTokenDTO | None:
        user_in_db = await self.user_service.get_user_by_email_and_provider(
            social_user.user_email,
            social_user.user_provider
        )

        if not user_in_db:
            return None

        return await self._issue_tokens(
            user_in_db.user_id,
            user_in_db.user_email,
            user_in_db.user_provider
        )

    # 소셜 가입 토큰 생성 (소셜 콜백에서 비회원일 때 쿠키에 심는다)
    def generate_social_join_token(self, social_user: SocialLoginRequestDTO) -> str:
        expire = datetime.now(timezone.utc) + timedelta(minutes=SOCIAL_JOIN_TOKEN_MINUTES)
        return jwt.encode(
            {
                "purpose": SOCIAL_JOIN_TOKEN_PURPOSE,
                "user_email": social_user.user_email,
                "user_name": social_user.user_name,
                "user_provider": social_user.user_provider.value,
                "user_provider_id": social_user.user_provider_id,
                "exp": expire
            },
            SECRET_KEY,
            algorithm=ALGORITHM
        )

    # 소셜 가입 요청 검증: 쿠키 토큰의 값으로 email/provider/provider_id를 덮어쓴다.
    # (요청 본문의 값은 신뢰하지 않는다)
    def apply_social_join_token(self, user: UserCreateDTO, token: str | None) -> UserCreateDTO:
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="소셜 인증 정보가 없습니다. 소셜 로그인부터 다시 진행해주세요."
            )

        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        except JWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="소셜 인증이 만료되었거나 유효하지 않습니다. 다시 시도해주세요."
            )

        if payload.get("purpose") != SOCIAL_JOIN_TOKEN_PURPOSE:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="유효하지 않은 소셜 인증 정보입니다."
            )

        update_data = {
            "user_email": payload["user_email"],
            "user_provider": UserProvider(payload["user_provider"]),
            "user_provider_id": payload["user_provider_id"],
        }

        # 소셜 프로필 이름이 있으면 토큰 값으로 고정 (없으면 사용자가 입력한 이름 사용)
        if payload.get("user_name"):
            update_data["user_name"] = payload["user_name"]

        return user.model_copy(update=update_data)

    # 로그아웃
    async def logout(self, user_id: int, tokens: JwtTokenDTO) -> None:
        # 1. 블랙리스트에 access_token 등록
        if tokens.access_token:
            await self.save_blacklisted_token(tokens.access_token)
        # 2. redis에 저장된 refresh_token 삭제
        await self.delete_refresh_token(user_id)

    # refresh -> access 재발급
    async def refresh(self, refresh_token: str) -> str:
        payload = parse_token(refresh_token)
        user_id = payload.user_id

        is_valid: bool = await self.validate_refresh_token(user_id, refresh_token)

        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="유효하지 않은 Refresh Token"
            )

        return reissue_access_token(refresh_token)


# 의존성 주입 팩토리 함수
def get_auth_service(
    redis_repo: RedisRepository = Depends(get_redis_repository),
    user_service: UserService = Depends(get_user_service)
):
    return AuthService(redis_repo, user_service)
