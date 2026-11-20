from fastapi import Depends, HTTPException, status
from app.repository.post_repository import PostRepository, get_post_repository
from app.schema.post_schema import PostCreateDTO, PostUpdateDTO, PostListResponseDTO, PostDetailResponseDTO
from app.schema.common_schema import PageResponseDTO
from app.enum.post_enum import PostSortEnum, PostCategoryEnum
from app.schema.post_comment_schema import CommentResponseDTO
from app.schema.user_schema import UserSummaryDTO


class PostService:
    def __init__(self, post_repo: PostRepository):
        self.post_repo = post_repo

    async def create_post(self, user_id: int, post: PostCreateDTO) -> int:
        new_post_id = await self.post_repo.create_post(user_id, post)
        return new_post_id


    async def get_post_list(
            self, 
            page: int, 
            size: int = 10, 
            sort_by: PostSortEnum = PostSortEnum.LATEST,
            keyword: str | None = None,
            category: PostCategoryEnum | None = None
            ) -> PageResponseDTO[PostListResponseDTO]:
        
        if page < 1:
            page = 1

        offset = (page - 1) * size

        if keyword:
            keyword = keyword.strip() or None

        posts, total = await self.post_repo.find_post_by_paging(
            offset=offset, 
            limit=size, 
            sort_by=sort_by, 
            search=keyword, 
            category=category
        )
        
        total_pages = (total + size - 1) // size
        items = [PostListResponseDTO.model_validate(p) for p in posts]

        return PageResponseDTO(
            total_count=total,
            total_pages=total_pages,
            offset=offset,
            limit=size,
            items=items
            )


    async def get_post_detail(self, post_id: int) -> PostDetailResponseDTO:
        post = await self.post_repo.get_by_id(post_id)
        
        if post is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="게시글이 없거나 삭제되었습니다."
            )
        view_count = await self.post_repo.increase_view_count(post_id)

        comments = sorted(post.comments, key=lambda c: c.comment_id)
        comments_map: dict[int, CommentResponseDTO] = {}
        for c in comments:
            comments_map[c.comment_id] = CommentResponseDTO(
                comment_id=c.comment_id,
                comment_content=c.comment_content,
                parent_comment_id=c.parent_comment_id,
                comment_created_at=c.comment_created_at,
                comment_updated_at=c.comment_updated_at,
                comment_deleted_at=c.comment_deleted_at,
                user=UserSummaryDTO.model_validate(c.user),
                children=[]
          )
        root_comments = []
        for dto in comments_map.values():
            if dto.parent_comment_id is None:
                root_comments.append(dto)
            else:
                parent = comments_map.get(dto.parent_comment_id)
                if parent:
                    parent.children.append(dto)

        return PostDetailResponseDTO(
            post_id=post.post_id,
            post_category=post.post_category,
            post_title=post.post_title,
            post_content=post.post_content,
            post_image_url=post.post_image_url,
            post_view_count=view_count,
            post_like_count=post.post_like_count,
            post_created_at=post.post_created_at,
            post_updated_at=post.post_updated_at,
            post_deleted_at=post.post_deleted_at,
            user=UserSummaryDTO.model_validate(post.user),
            comments=root_comments
        )


    async def update_post(self, post_id: int, user_id: int, update_dto: PostUpdateDTO) -> int:
        post = await self.post_repo.get_by_id(post_id)

        if post is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="게시글이 없거나 삭제되었습니다."
            )

        if post.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="본인 글만 수정할 수 있습니다"
            )

        update_data = update_dto.model_dump()
        updated_id = await self.post_repo.update_post(post_id, update_data)

        if updated_id is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="게시글이 없거나 삭제되었습니다."
            )

        return updated_id


    async def delete_post(self, post_id: int, user_id: int) -> bool:
        post = await self.post_repo.get_by_id(post_id)
        
        if post is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="게시글이 없거나 삭제되었습니다."
            )

        if post.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="본인 글만 삭제할 수 있습니다"
            )

        deleted = await self.post_repo.delete_post(post_id)

        if deleted is False:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="게시글이 없거나 삭제되었습니다."
            )

        return True


    async def get_my_posts(
            self,
            user_id: int, 
            page: int, 
            size: int = 10
        )-> PageResponseDTO[PostListResponseDTO]:

        if page < 1:
            page = 1
        
        offset = (page - 1) * size
        posts, total = await self.post_repo.find_my_posts(user_id, offset, size)

        total_pages = (total + size - 1) // size
        items = [PostListResponseDTO.model_validate(p) for p in posts]

        return PageResponseDTO(
            total_count=total,
            total_pages=total_pages,
            offset=offset,
            limit=size,
            items=items
        )


def get_post_service(
        post_repository: PostRepository = Depends(get_post_repository)
    ):
    return PostService(post_repository)