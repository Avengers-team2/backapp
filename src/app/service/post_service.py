from fastapi import Depends, HTTPException, status
from app.repository.post_repository import PostRepository, get_post_repository
from app.enum.post_enum import PostSortEnum, PostCategoryEnum
from app.schema.post_schema import PostCreateDTO, PostUpdateDTO, PostListResponseDTO, PostDetailResponseDTO
from app.schema.common_schema import PageResponseDTO
from app.schema.post_comment_schema import CommentResponseDTO
from app.schema.post_like_schema import PostLikeStatusResponseDTO
from app.schema.user_schema import UserSummaryDTO
from app.repository.post_like_repository import PostLikeRepository, get_post_like_repository
from app.repository.post_bookmark_repository import PostBookmarkRepository, get_post_bookmark_repository
from app.schema.post_bookmark_schema import PostBookmarkStatusResponseDTO


class PostService:
    # (게시글, 댓글 수) → 목록 DTO
    @staticmethod
    def _to_list_dto(post, comment_count: int) -> PostListResponseDTO:
        dto = PostListResponseDTO.model_validate(post)
        dto.post_comment_count = comment_count
        return dto

    def __init__(self, post_repo: PostRepository, like_repo: PostLikeRepository, bookmark_repo: PostBookmarkRepository):
        self.post_repo = post_repo
        self.like_repo = like_repo
        self.bookmark_repo = bookmark_repo

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
        items = [self._to_list_dto(p, c) for p, c in posts]

        return PageResponseDTO(
            total_count=total,
            total_pages=total_pages,
            offset=offset,
            limit=size,
            items=items
            )


    async def get_post_detail(self, post_id: int, user_id: int | None = None) -> PostDetailResponseDTO:
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

        # 화면에 실제로 보이는 댓글 수 (부모가 삭제돼 숨겨진 답글은 제외)
        def count_tree(nodes) -> int:
            return sum(1 + count_tree(n.children) for n in nodes)

        comment_count = count_tree(root_comments)

        # 로그인한 경우에만 좋아요·북마크 여부 확인
        is_liked = False
        is_bookmarked = False
        if user_id is not None:
            is_liked = await self.like_repo.exists_like(user_id, post_id)
            is_bookmarked = await self.bookmark_repo.exists_bookmark(user_id, post_id) 

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
            comments=root_comments,
            post_comment_count=comment_count,
            is_liked=is_liked,
            is_bookmarked=is_bookmarked
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
        items = [self._to_list_dto(p, c) for p, c in posts]

        return PageResponseDTO(
            total_count=total,
            total_pages=total_pages,
            offset=offset,
            limit=size,
            items=items
        )


    async def toggle_like(self, post_id: int, user_id: int) -> PostLikeStatusResponseDTO:
        try:
            liked = await self.like_repo.exists_like(user_id, post_id)
            if not liked:
                like_count = await self.post_repo.increase_like_count(post_id)
                if like_count is None:
                    await self.post_repo.db.rollback()
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="게시글이 없거나 삭제되었습니다."
                    )
                await self.like_repo.create_like(user_id, post_id)
                is_liked = True
            else:
                await self.like_repo.delete_like(user_id, post_id)
                like_count = await self.post_repo.decrease_like_count(post_id)
                if like_count is None:
                    await self.post_repo.db.rollback()
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="게시글이 없거나 삭제되었습니다."
                    )
                is_liked = False
            await self.post_repo.db.commit()
        except HTTPException:
            raise
        except Exception:
            await self.post_repo.db.rollback()
            raise
        return PostLikeStatusResponseDTO(is_liked=is_liked, post_like_count=like_count)


    async def toggle_bookmark(self, post_id: int, user_id: int) -> PostBookmarkStatusResponseDTO:
        try:
            bookmarked = await self.bookmark_repo.exists_bookmark(user_id, post_id)

            if not bookmarked:
                # 북마크: 삭제 안 된 글인지 먼저 확인
                if not await self.post_repo.exists_post(post_id):
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="게시글이 없거나 삭제되었습니다."
                    )
                await self.bookmark_repo.create_bookmark(user_id, post_id)
                is_bookmarked = True

            else:
                # 북마크 취소 (글이 삭제됐어도 취소는 가능)
                await self.bookmark_repo.delete_bookmark(user_id, post_id)
                is_bookmarked = False

            await self.post_repo.db.commit()

        except HTTPException:
            raise
        except Exception:
            await self.post_repo.db.rollback()
            raise

        return PostBookmarkStatusResponseDTO(is_bookmarked=is_bookmarked)


    async def get_my_bookmarks(
            self,
            user_id: int,
            page: int,
            size: int = 10
        ) -> PageResponseDTO[PostListResponseDTO]:

        if page < 1:
            page = 1

        offset = (page - 1) * size
        posts, total = await self.bookmark_repo.find_my_bookmarks(user_id, offset, size)

        total_pages = (total + size - 1) // size
        items = [self._to_list_dto(p, c) for p, c in posts]

        return PageResponseDTO(
            total_count=total,
            total_pages=total_pages,
            offset=offset,
            limit=size,
            items=items
        )


def get_post_service(
        post_repository: PostRepository = Depends(get_post_repository),
        like_repository: PostLikeRepository = Depends(get_post_like_repository),
        bookmark_repository: PostBookmarkRepository = Depends(get_post_bookmark_repository)
    ):
    return PostService(post_repository, like_repository, bookmark_repository)