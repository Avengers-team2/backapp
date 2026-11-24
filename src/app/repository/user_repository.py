from sqlalchemy.ext.asyncio import AsyncSession
from app.infrastructure.postgresql import get_postgresql_db
from fastapi import Depends

# 모델, ORM 가져오기
from app.model.user_model import User
from app.schema.user_schema import UserCreateDTO, UserClaimDTO
from sqlalchemy import insert, select, update, delete, func, exists


class UserRepository:

    # 생성자 주입
    def __init__(self, db: AsyncSession):
        self.db = db

    # 순수 함수

    # 1. 중복 확인
    async def exists_user_by_id(self, user_id: int) -> bool:
        query = (
            select(exists().where(User.user_id == user_id))
        )
        result = await self.db.execute(query)
        return result.scalar()

    async def exists_user_email_and_provider(self, user_email: str, user_provider: str) -> bool:
        query = select(User).where(
            User.user_email == user_email,
            User.user_provider == user_provider
        )

        result = await self.db.execute(query)
        found_user = result.scalar_one_or_none()
        return found_user is not None


    # 소셜 계정 중복 확인 (user_provider_id는 DB에서 unique)
    async def exists_user_provider_id(self, user_provider_id: str) -> bool:
        query = (
            select(exists().where(User.user_provider_id == user_provider_id))
        )
        result = await self.db.execute(query)
        return result.scalar()


    # 2. 회원가입
    async def create_user(self, user: UserCreateDTO) -> UserClaimDTO:
        # pydantic -> dict
        # model_dump: 키 벨류를 딕셔너리로 리턴
        new_user = user.model_dump()
        query = (
            insert(User)
            .values(**new_user)
        ).returning(
            User.user_id,
            User.user_email,
            User.user_provider
        )

        result = await self.db.execute(query)

        # 필요한 값만 리턴(id, email, provider)
        user_id, user_email, user_provider = result.first()

        await self.db.commit()

        payload = {
            "user_id": user_id,
            "user_email": user_email,
            "user_provider": user_provider
        }

        # dict -> pydantic
        claim_dto = UserClaimDTO.model_validate(payload)
        return claim_dto


    # 3. 회원 정보 조회(id)
    async def find_user_by_id(self, user_id: int) -> User | None:
        query = select(User).where(User.user_id == user_id)
        result = await self.db.execute(query)
        found_user = result.scalar_one_or_none()
        return found_user


    # 4. 회원 정보 조회(email, provider)
    async def find_user_by_email_and_provider(self, user_email: str, user_provider: str) -> User | None:
        query = select(User).where(
            User.user_email == user_email,
            User.user_provider == user_provider,
        )
        result = await self.db.execute(query)
        found_user = result.scalar_one_or_none()
        return found_user


    # 5. 회원 전체 정보 조회 - 페이지네이션
    # offset, limit 방식
    async def find_user_by_paging(self, offset: int, limit: int) -> list[User]:
        query = (
            select(User)
            .order_by(User.user_id)
            .offset(offset)
            .limit(limit)
        )
        result = await self.db.execute(query)
        users = result.scalars().all()
        return users

    async def count_users(self) -> int:
        query = (
            select(func.count()).select_from(User)
        )
        result = await self.db.execute(query)
        count = result.scalar_one()
        return count


    # 6. 회원 정보 수정
    async def update_user(self, user_id: int, update_data: dict) -> User | None:
        if not update_data:
            return None

        query = (
            update(User)
            .where(User.user_id == user_id)
            .values(**update_data)
            .returning(User)
        )

        result = await self.db.execute(query)
        await self.db.commit()

        updated_user = result.scalar_one_or_none()
        return updated_user


    # 7. 회원 삭제
    async def delete_user(self, user_id: int) -> bool:
        query = (
            delete(User)
            .where(User.user_id == user_id)
        )

        result = await self.db.execute(query)
        await self.db.commit()
        return result.rowcount > 0


# 주입 팩토리 메서드
def get_user_repository(db: AsyncSession = Depends(get_postgresql_db)):
    return UserRepository(db)
