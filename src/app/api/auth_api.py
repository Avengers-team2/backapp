import os
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, Query, Request, Response, HTTPException
from app.schema.common_schema import ApiResponseDTO
from app.schema.user_schema import UserClaimDTO
from app.enum.user_enum import UserProvider
from app.schema.auth_schema import JwtTokenDTO, LoginRequestDTO, SocialLoginRequestDTO
from app.schema.user_schema import UserCreateDTO
from app.service.auth_service import AuthService, get_auth_service
from app.service.user_service import UserService, get_user_service
from app.dependencie.auth_dependency import get_current_user, get_tokens

# 소셜 로그인용
import httpx  # 추가 요청
from fastapi.responses import RedirectResponse  # 페이지 전환
from urllib.parse import urlencode  # 요청주소를 조합하기 위한 라이브러리


load_dotenv()
router = APIRouter()

FRONT_END_URL = os.getenv("FRONT_END_URL")

# 소셜 가입용 쿠키 이름 / 유효시간(10분)
SOCIAL_JOIN_COOKIE = "social_join_token"
SOCIAL_JOIN_COOKIE_MAX_AGE = 60 * 10

# 소셜 로그인 후 되돌아갈 프론트 경로를 잠깐 보관하는 쿠키 / 유효시간(10분)
LOGIN_REDIRECT_COOKIE = "login_redirect_path"
LOGIN_REDIRECT_COOKIE_MAX_AGE = 60 * 10
LOGIN_REDIRECT_MAX_LENGTH = 500
# 로그인 후에 다시 로그인/가입 화면으로 돌아가면 반복되므로 제외
LOGIN_REDIRECT_BLOCKED_PREFIXES = ("/login", "/join", "/find-account")


# 되돌아갈 경로 검사: 우리 사이트 안의 경로만 허용 (다른 사이트로 보내는 오픈 리다이렉트 방지)
#   OK : /analysis, /analysis?area=3120197#result
#   NO : https://evil.com, //evil.com, /\evil.com, 제어문자 포함, 너무 긴 값, /login
def _safe_redirect_path(path: str | None) -> str | None:
    if not path or len(path) > LOGIN_REDIRECT_MAX_LENGTH:
        return None
    if not path.startswith("/") or path.startswith("//"):
        return None
    if "\\" in path or any(ord(ch) < 32 or ord(ch) == 127 for ch in path):
        return None
    only_path = path.split("?")[0].split("#")[0]
    if any(only_path == p or only_path.startswith(f"{p}/") for p in LOGIN_REDIRECT_BLOCKED_PREFIXES):
        return None  # /login, /join, /find-account 와 그 하위 (/loginx 같은 다른 경로는 허용)
    return path


# 소셜 로그인 시작 때 호출: 안전한 경로면 쿠키에 저장, 아니면 이전 값을 지움
def _remember_redirect_path(response: Response, redirect: str | None) -> None:
    safe_path = _safe_redirect_path(redirect)
    if safe_path is None:
        response.delete_cookie(LOGIN_REDIRECT_COOKIE)
        return
    response.set_cookie(
        key=LOGIN_REDIRECT_COOKIE,
        value=safe_path,
        httponly=True,
        secure=False,
        samesite="lax",  # 소셜 사이트에서 돌아오는 이동(GET)에는 lax 쿠키도 같이 전달된다
        max_age=LOGIN_REDIRECT_COOKIE_MAX_AGE
    )


# 쿠키 값은 다시 검사해서 사용 (쿠키는 사용자가 바꿀 수 있으므로)
def _read_redirect_path(request: Request) -> str | None:
    return _safe_redirect_path(request.cookies.get(LOGIN_REDIRECT_COOKIE))


# 쿠키에 토큰 저장 (로그인/소셜로그인 공통)
def _set_auth_cookies(response: Response, tokens: JwtTokenDTO) -> None:
    response.set_cookie(
        key="access_token",
        value=tokens.access_token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=60 * 60 * 24
    )

    response.set_cookie(
        key="refresh_token",
        value=tokens.refresh_token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=60 * 60 * 24 * 30
    )


# 프론트(signUpApi, checkEmailApi)가 /auth 아래로 호출한다.
# 이메일 중복 확인: data=True면 사용 가능, False면 이미 가입된 이메일
@router.get(
    "/check-email",
    response_model=ApiResponseDTO,
    summary="이메일 중복 확인(로컬)"
)
async def check_email(
    user_email: str,
    user_service: UserService = Depends(get_user_service)
):
    found_user = await user_service.get_user_by_email_and_provider(
        user_email, UserProvider.LOCAL
    )
    is_available = found_user is None

    return ApiResponseDTO(
        success=True,
        message="사용 가능한 이메일" if is_available else "이미 가입된 이메일",
        data=is_available
    )


@router.post(
    "/join",
    response_model=ApiResponseDTO,
    summary="회원 가입",
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
    request: Request,
    response: Response,
    user_service: UserService = Depends(get_user_service),
    auth_service: AuthService = Depends(get_auth_service)
):
    # 소셜 가입: 소셜 콜백에서 심어준 쿠키 토큰으로 email/provider/provider_id를 검증(본문 값 무시)
    is_social = user.user_provider != UserProvider.LOCAL
    if is_social:
        user = auth_service.apply_social_join_token(
            user, request.cookies.get(SOCIAL_JOIN_COOKIE)
        )

    user_claim = await user_service.join(user)

    # 가입이 끝났으니 가입용 토큰 쿠키는 삭제
    if is_social:
        response.delete_cookie(SOCIAL_JOIN_COOKIE)

    return ApiResponseDTO(
        success=True,
        message="회원가입 성공",
        data=user_claim
    )


@router.post(
    "/login",
    response_model=ApiResponseDTO,
    summary="로컬 로그인",
    responses={
        200: {
            "description": "로그인 성공"
        },
        401: {
            "description": "비밀번호 불일치",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "아이디 또는 비밀번호가 일치하지 않습니다."
                    }
                }
            }
        },
        404: {
            "description": "존재하지 않는 회원",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "회원이 존재하지 않습니다."
                    }
                }
            }
        }
    }
)
async def login(
    login_user: LoginRequestDTO,
    response: Response,
    auth_service: AuthService = Depends(get_auth_service)
):
    login_user.user_provider = UserProvider.LOCAL
    tokens = await auth_service.login(login_user)

    _set_auth_cookies(response, tokens)

    return ApiResponseDTO(
        success=True,
        message="로그인 성공"
    )


# ---------------- 구글 로그인 ----------------
GOOGLE_AUTH_URL = os.getenv("GOOGLE_AUTH_URL")
GOOGLE_TOKEN_URL = os.getenv("GOOGLE_TOKEN_URL")
GOOGLE_USERINFO_URL = os.getenv("GOOGLE_USERINFO_URL")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI")


# /auth/google
@router.get(
    "/google",
    summary="구글 로그인"
)
async def google_login(
    next: str | None = Query(None, description="로그인 후 돌아갈 프론트 경로 (예: /analysis?area=1). 프론트 /login?next= 와 같은 이름"),
    redirect: str | None = Query(None, description="next 의 옛 이름 (둘 다 오면 next 우선)")
):
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "consent"
    }

    url = f"{GOOGLE_AUTH_URL}?{urlencode(params)}"
    response = RedirectResponse(url)
    _remember_redirect_path(response, next or redirect)
    return response


# /auth/google/callback
@router.get(
    "/google/callback",
    summary="구글 로그인 콜백"
)
async def google_login_callback(
    code: str,
    request: Request,
    auth_service: AuthService = Depends(get_auth_service)
):
    async with httpx.AsyncClient() as client:
        token_res = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code"
            }
        )

        token_data = token_res.json()
        access_token = token_data.get("access_token")

        if not access_token:
            raise HTTPException(status_code=400, detail="구글 토큰 발급 실패")

        user_res = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"}
        )

    user = user_res.json()
    user_params = {
        "user_email": user.get("email"),
        "user_name": user.get("name"),
        "user_provider": UserProvider.GOOGLE.value,
        "user_provider_id": user.get("sub")
    }

    return await _handle_social_login(user_params, auth_service, request)


# ---------------- 카카오 로그인 ----------------
KAKAO_CLIENT_ID = os.getenv("KAKAO_CLIENT_ID")
KAKAO_CLIENT_SECRET = os.getenv("KAKAO_CLIENT_SECRET")
KAKAO_REDIRECT_URI = os.getenv("KAKAO_REDIRECT_URI")
KAKAO_AUTH_URL = os.getenv("KAKAO_AUTH_URL")
KAKAO_TOKEN_URL = os.getenv("KAKAO_TOKEN_URL")
KAKAO_USERINFO_URL = os.getenv("KAKAO_USERINFO_URL")


@router.get("/kakao", summary="카카오 로그인 리다이렉트")
async def kakao_login(
    next: str | None = Query(None, description="로그인 후 돌아갈 프론트 경로 (예: /analysis?area=1). 프론트 /login?next= 와 같은 이름"),
    redirect: str | None = Query(None, description="next 의 옛 이름 (둘 다 오면 next 우선)")
):
    params = {
        "client_id": KAKAO_CLIENT_ID,
        "redirect_uri": KAKAO_REDIRECT_URI,
        "response_type": "code",
    }

    url = f"{KAKAO_AUTH_URL}?{urlencode(params)}"
    response = RedirectResponse(url)
    _remember_redirect_path(response, next or redirect)
    return response


@router.get("/kakao/callback", summary="카카오 로그인 콜백")
async def kakao_login_callback(
    code: str,
    request: Request,
    auth_service: AuthService = Depends(get_auth_service)
):
    async with httpx.AsyncClient() as client:
        token_res = await client.post(
            KAKAO_TOKEN_URL,
            data={
                "code": code,
                "client_id": KAKAO_CLIENT_ID,
                "client_secret": KAKAO_CLIENT_SECRET,
                "redirect_uri": KAKAO_REDIRECT_URI,
                "grant_type": "authorization_code"
            }
        )

        token_data = token_res.json()
        access_token = token_data.get("access_token")

        if not access_token:
            raise HTTPException(status_code=400, detail="카카오 토큰 발급 실패")

        user_res = await client.get(
            KAKAO_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"}
        )

    user = user_res.json()
    kakao_account = user.get("kakao_account") or {}
    user_email = kakao_account.get("email")
    user_provider_id = str(user.get("id"))
    # 이름: 이름 동의항목(name)이 있으면 사용, 없으면 프로필 닉네임
    kakao_name = kakao_account.get("name") or (kakao_account.get("profile") or {}).get("nickname")

    user_params = {
        "user_email": user_email,
        "user_name": kakao_name,
        "user_provider": UserProvider.KAKAO.value,
        "user_provider_id": user_provider_id
    }

    return await _handle_social_login(user_params, auth_service, request)


# ---------------- 네이버 로그인 ----------------
NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET")
NAVER_REDIRECT_URI = os.getenv("NAVER_REDIRECT_URI")
NAVER_AUTH_URL = os.getenv("NAVER_AUTH_URL")
NAVER_TOKEN_URL = os.getenv("NAVER_TOKEN_URL")
NAVER_USERINFO_URL = os.getenv("NAVER_USERINFO_URL")


@router.get("/naver", summary="네이버 로그인 리다이렉트")
async def naver_login(
    next: str | None = Query(None, description="로그인 후 돌아갈 프론트 경로 (예: /analysis?area=1). 프론트 /login?next= 와 같은 이름"),
    redirect: str | None = Query(None, description="next 의 옛 이름 (둘 다 오면 next 우선)")
):
    params = {
        "client_id": NAVER_CLIENT_ID,
        "redirect_uri": NAVER_REDIRECT_URI,
        "response_type": "code",
    }

    url = f"{NAVER_AUTH_URL}?{urlencode(params)}"
    response = RedirectResponse(url)
    _remember_redirect_path(response, next or redirect)
    return response


@router.get("/naver/callback", summary="네이버 로그인 콜백")
async def naver_login_callback(
    code: str,
    request: Request,
    auth_service: AuthService = Depends(get_auth_service)
):
    async with httpx.AsyncClient() as client:
        token_res = await client.post(
            NAVER_TOKEN_URL,
            data={
                "code": code,
                "client_id": NAVER_CLIENT_ID,
                "client_secret": NAVER_CLIENT_SECRET,
                "redirect_uri": NAVER_REDIRECT_URI,
                "grant_type": "authorization_code"
            }
        )

        token_data = token_res.json()
        access_token = token_data.get("access_token")

        if not access_token:
            raise HTTPException(status_code=400, detail="네이버 토큰 발급 실패")

        user_res = await client.get(
            NAVER_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"}
        )

    user = user_res.json()
    naver_user = user.get("response") or {}

    user_params = {
        "user_email": naver_user.get("email"),
        "user_name": naver_user.get("name"),
        "user_provider": UserProvider.NAVER.value,
        "user_provider_id": str(naver_user.get("id"))
    }

    return await _handle_social_login(user_params, auth_service, request)


# 로그아웃
@router.post(
    "/logout",
    summary="로그아웃",
    response_model=ApiResponseDTO,
)
async def logout(
    response: Response,
    user_claims: UserClaimDTO = Depends(get_current_user),
    tokens: JwtTokenDTO = Depends(get_tokens),
    auth_service: AuthService = Depends(get_auth_service)
):
    await auth_service.logout(user_claims.user_id, tokens)

    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")

    return ApiResponseDTO(
        success=True,
        message="로그아웃 성공"
    )


@router.get(
    "/refresh",
    response_model=ApiResponseDTO,
    summary="토큰 재발급"
)
async def refresh(
    response: Response,
    tokens: JwtTokenDTO = Depends(get_tokens),
    auth_service: AuthService = Depends(get_auth_service)
):
    refresh_token = tokens.refresh_token
    try:
        access_token = await auth_service.refresh(refresh_token)

        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,
            secure=False,
            samesite="lax",
            max_age=60 * 60 * 24
        )

        return ApiResponseDTO(
            success=True,
            message="Access Token 재발급 성공"
        )

    except Exception:
        response.delete_cookie("access_token")
        response.delete_cookie("refresh_token")

        return ApiResponseDTO(
            success=False,
            message="Refresh Token 만료"
        )


# 소셜 로그인 공통 처리
# - 비회원: 프론트 /join(소셜 가입 모드)으로 이동 -> 프론트가 /auth/join 호출
# - 회원: 쿠키에 토큰 저장 후, 로그인 전에 보던 페이지(없으면 프론트 메인)로 이동
async def _handle_social_login(user_params: dict, auth_service: AuthService, request: Request):
    social_user = SocialLoginRequestDTO.model_validate(user_params)
    tokens = await auth_service.social_login_or_none(social_user)

    # 비회원 -> 프론트 /join 폼이 쿼리를 보고 소셜 가입 모드로 동작
    if not tokens:
        # 값이 없는 항목(예: 이름 동의 안 함)은 쿼리에서 생략 -> 프론트가 직접 입력받음
        query = {key: value for key, value in user_params.items() if value}
        # 가입을 마친 뒤 원래 페이지로 돌아갈 수 있게 next 를 같이 넘긴다 (검사를 통과한 경로만)
        return_path = _read_redirect_path(request)
        if return_path:
            query["next"] = return_path
        url = f"{FRONT_END_URL}/join?{urlencode(query)}"
        redirect_response = RedirectResponse(url)
        redirect_response.delete_cookie(LOGIN_REDIRECT_COOKIE)

        # 쿼리는 화면 표시용. 실제 가입 때는 이 쿠키 값만 신뢰한다.
        redirect_response.set_cookie(
            key=SOCIAL_JOIN_COOKIE,
            value=auth_service.generate_social_join_token(social_user),
            httponly=True,
            secure=False,
            samesite="lax",
            max_age=SOCIAL_JOIN_COOKIE_MAX_AGE
        )
        return redirect_response

    # 기존 회원: 로그인 전에 보던 페이지로 (저장된 경로가 없거나 안전하지 않으면 메인)
    return_path = _read_redirect_path(request) or ""
    redirect_response = RedirectResponse(url=f"{FRONT_END_URL.rstrip('/')}{return_path}")
    _set_auth_cookies(redirect_response, tokens)
    redirect_response.delete_cookie(LOGIN_REDIRECT_COOKIE)  # 한 번 쓰면 지움

    return redirect_response
