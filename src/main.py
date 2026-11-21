from fastapi import FastAPI
from app.security.cors import setup_cors
from app.security.security_headers import set_up_security
from contextlib import asynccontextmanager
from app.infrastructure.postgresql import engine, Base
from app.infrastructure.redis import start_redis_client
from app.infrastructure.s3 import start_s3_client
import app.model

from app.api import (
    user_api,
    analysis_api,
    report_api,
    bookmark_api,
    subscription_api,
    payment_api,
    ai_api,
    mypage_api,
    post_api,
    support_api,
    auth_api,
    s3_api
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 비동기 연결
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        print("PostgreSQL 연결 성공!")

    async with start_redis_client(app):
        print("Redis 연결 성공!")

        async with start_s3_client(app):
            print("S3 연결 성공!")

            # 4. 전이학습 모델 로드
            yield

app = FastAPI(
    lifespan=lifespan,
    title="Fast API Service",
    description="파이썬 백엔드 구축!😎",
    version="1.0.0",
    docs_url="/docs", # Swagger
    redoc_url="/redoc"
)

setup_cors(app) 
set_up_security(app)

@app.get("/")
def health_check():
    return {"message": "Hello World"}


app.include_router(user_api.router, prefix="/users", tags=["users"])
app.include_router(analysis_api.router, prefix="/analyses", tags=["analysis"])
app.include_router(report_api.router, prefix="/reports", tags=["report"])
app.include_router(bookmark_api.router, prefix="/bookmarks", tags=["bookmarks"])
app.include_router(subscription_api.router, prefix="/subscriptions", tags=["subscriptions"])
app.include_router(payment_api.router, prefix="/payments", tags=["payments"])
app.include_router(post_api.router, prefix="/post", tags=["posts"])
app.include_router(mypage_api.router, prefix="/mypage", tags=["mypage"])
app.include_router(auth_api.router, prefix="/auth", tags=["auth"])
app.include_router(support_api.router, prefix="/support", tags=["support"])
app.include_router(ai_api.router, prefix="/ai", tags=["ai"])
app.include_router(s3_api.router, prefix="/upload", tags=["upload"])