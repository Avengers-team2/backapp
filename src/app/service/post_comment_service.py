from fastapi import Depends, HTTPException, status
from app.repository.post_comment_repository import CommentRepository, get_comment_repository
from app.repository.post_repository import PostRepository, get_post_repository
from app.schema.post_comment_schema import CommentCreateDTO, CommentUpdateDTO


class CommentService:
    def __init__(self, comment_repo: CommentRepository, post_repo: PostRepository):
        self.comment_repo = comment_repo
        self.post_repo = post_repo


    async def create_comment(self, post_id: int, user_id: int, comment_dto: CommentCreateDTO) -> int:
        content = comment_dto.comment_content.strip()
        if not content:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="댓글 내용을 입력하세요."
            )

        # 게시글이 있는지 확인
        if not await self.post_repo.exists_post(post_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="게시글이 없거나 삭제되었습니다."
            )

        parent_comment_id = comment_dto.parent_comment_id

        # 답글이면 답글 대상 확인 + 단계 처리
        if parent_comment_id is not None:
            parent = await self.comment_repo.get_by_id(parent_comment_id)

            if parent is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="답글을 달 댓글이 없거나 삭제되었습니다."
                )

            if parent.post_id != post_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="다른 게시글의 댓글에는 답글을 달 수 없습니다."
                )

            # 대상이 2단계 이상이면, 대상이 몇 단계인지 확인
            if parent.parent_comment_id is not None:
                grand_parent = await self.comment_repo.get_by_id(parent.parent_comment_id)

                if grand_parent is None:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="답글을 달 댓글이 없거나 삭제되었습니다."
                    )

                # 대상이 3단계(자식 댓글2)면 → 같은 단계에 붙도록 부모를 한 칸 위로
                if grand_parent.parent_comment_id is not None:
                    parent_comment_id = parent.parent_comment_id

        new_comment_id = await self.comment_repo.create_comment(
            user_id=user_id,
            post_id=post_id,
            comment_content=content,
            parent_comment_id=parent_comment_id
        )
        return new_comment_id


    async def update_comment(self, comment_id: int, user_id: int, update_dto: CommentUpdateDTO) -> int:
        content = update_dto.comment_content.strip()
        if not content:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="댓글 내용을 입력하세요."
            )

        comment = await self.comment_repo.get_by_id(comment_id)

        if comment is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="댓글이 없거나 삭제되었습니다."
            )

        if comment.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="본인 댓글만 수정할 수 있습니다."
            )

        updated_id = await self.comment_repo.update_comment(comment_id, content)

        if updated_id is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="댓글이 없거나 삭제되었습니다."
            )

        return updated_id


    async def delete_comment(self, comment_id: int, user_id: int) -> bool:
        comment = await self.comment_repo.get_by_id(comment_id)

        if comment is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="댓글이 없거나 삭제되었습니다."
            )

        if comment.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="본인 댓글만 삭제할 수 있습니다."
            )

        deleted = await self.comment_repo.delete_comment(comment_id)

        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="댓글이 없거나 삭제되었습니다."
            )

        return True


def get_comment_service(
        comment_repository: CommentRepository = Depends(get_comment_repository),
        post_repository: PostRepository = Depends(get_post_repository)
    ):
    return CommentService(comment_repository, post_repository)