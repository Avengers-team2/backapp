from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import insert, select, delete
from fastapi import Depends
from app.infrastructure.postgresql import get_postgresql_db
from app.model.post_image_model import PostImage


# commit은 하지 않는다 (좋아요처럼 서비스에서 commit / rollback)
class PostImageRepository:
    def __init__(self, db: AsyncSession):
        self.db = db


    # 사진 여러 장 저장
    async def create_images(self, post_id: int, image_urls: list[str]) -> None:
        if image_urls is None:
            return
        
        if not image_urls:
            return

        rows = [
            {"post_id": post_id, "image_url": url, "image_sort_order": order}
            for order, url in enumerate(image_urls)
        ]
        query = insert(PostImage).values(rows)
        await self.db.execute(query)


    # 게시글의 사진 전부 삭제 (글 수정 시 교체용)
    async def delete_images_by_post_id(self, post_id: int) -> None:
        query = delete(PostImage).where(PostImage.post_id == post_id)
        await self.db.execute(query)


    # 게시글의 사진 목록 조회 (순서대로)
    async def find_images_by_post_id(self, post_id: int) -> list[PostImage]:
        query = (
            select(PostImage)
            .where(PostImage.post_id == post_id)
            .order_by(PostImage.image_sort_order)
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())


def get_post_image_repository(db: AsyncSession = Depends(get_postgresql_db)):
    return PostImageRepository(db)
