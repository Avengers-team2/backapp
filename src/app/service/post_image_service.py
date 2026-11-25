from fastapi import Depends
from app.repository.post_image_repository import PostImageRepository, get_post_image_repository
from app.schema.post_image_schema import PostImageResponseDTO


# 게시글 사진 처리 (PostService가 글 작성·수정·상세 조회 때 불러서 씀)
class PostImageService:
    def __init__(self, image_repo: PostImageRepository):
        self.image_repo = image_repo


    # 글 작성 후 사진 저장
    async def save_images(self, post_id: int, image_urls: list[str]) -> None:
        try:
            await self.image_repo.create_images(post_id, image_urls)
            await self.image_repo.db.commit()

        except Exception:
            await self.image_repo.db.rollback()
            raise


    # 글 수정 시 사진 교체 (기존 사진 전부 지우고 새로 저장)
    async def replace_images(self, post_id: int, image_urls: list[str]) -> None:
        try:
            await self.image_repo.delete_images_by_post_id(post_id)
            await self.image_repo.create_images(post_id, image_urls)
            await self.image_repo.db.commit()
        except Exception:
            await self.image_repo.db.rollback()
            raise
        

    # 상세 조회용 사진 목록
    async def get_images(self, post_id: int) -> list[PostImageResponseDTO]:
        imgs = await self.image_repo.find_images_by_post_id(post_id)
        result = [PostImageResponseDTO.model_validate(img) for img in imgs]
        return result


def get_post_image_service(
        image_repository: PostImageRepository = Depends(get_post_image_repository)
    ):
    return PostImageService(image_repository)
