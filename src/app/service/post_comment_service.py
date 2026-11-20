from fastapi import Depends, HTTPException, status
from app.repository.post_comment_repository import CommentRepository, get_comment_repository
from app.repository.post_repository import PostRepository, get_post_repository
from app.schema.post_comment_schema import CommentCreateDTO, CommentUpdateDTO


class CommentService:
    def __init__(self, comment_repo: CommentRepository, post_repo: PostRepository):
        self.comment_repo = comment_repo
        self.post_repo = post_repo


    async def create_comment(self, post_id: int, user_id: int, comment_dto: CommentCreateDTO) -> int:
        content = _clean_comment_content(comment_dto.comment_content)

        # 게시글이 있는지 확인
        if not await self.post_repo.exists_post(post_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="게시글이 없거나 삭제되었습니다."
            )

        # 답글이면 답글 대상 확인 + 단계 처리
        parent_comment_id = await _resolve_parent_comment_id(
            self.comment_repo, post_id, comment_dto.parent_comment_id
        )

        new_comment_id = await self.comment_repo.create_comment(
            user_id=user_id,
            post_id=post_id,
            comment_content=content,
            parent_comment_id=parent_comment_id
        )
        return new_comment_id


    async def update_comment(self, comment_id: int, user_id: int, update_dto: CommentUpdateDTO) -> int:
        content = _clean_comment_content(update_dto.comment_content)

        await _get_owned_comment(self.comment_repo, comment_id, user_id, "본인 댓글만 수정할 수 있습니다.")

        updated_id = await self.comment_repo.update_comment(comment_id, content)

        if updated_id is None:
            raise _comment_not_found_error()

        return updated_id


    async def delete_comment(self, comment_id: int, user_id: int) -> bool:
        await _get_owned_comment(self.comment_repo, comment_id, user_id, "본인 댓글만 삭제할 수 있습니다.")

        deleted = await self.comment_repo.delete_comment(comment_id)

        if not deleted:
            raise _comment_not_found_error()

        return True


def get_comment_service(
        comment_repository: CommentRepository = Depends(get_comment_repository),
        post_repository: PostRepository = Depends(get_post_repository)
    ):
    return CommentService(comment_repository, post_repository)


# ===== 공통 함수 =====

# 댓글 내용 앞뒤 공백을 제거하고, 비어 있으면 400
def _clean_comment_content(raw: str) -> str:
    content = raw.strip()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="댓글 내용을 입력하세요."
        )
    return content


# 댓글이 없거나 삭제된 경우의 404 에러 생성
def _comment_not_found_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="댓글이 없거나 삭제되었습니다."
    )


# 답글 대상 댓글이 없거나 삭제된 경우의 404 에러 생성
def _parent_comment_not_found_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="답글을 달 댓글이 없거나 삭제되었습니다."
    )


# 댓글을 찾고, 없으면 404 / 본인 댓글이 아니면 forbidden_detail 메시지로 403
async def _get_owned_comment(comment_repo: CommentRepository, comment_id: int, user_id: int, forbidden_detail: str):
    comment = await comment_repo.get_by_id(comment_id)

    if comment is None:
        raise _comment_not_found_error()

    if comment.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=forbidden_detail
        )

    return comment


# 답글 대상 확인 후 실제로 저장할 parent_comment_id 반환 (3단계 이상이면 부모를 한 칸 위로)
async def _resolve_parent_comment_id(comment_repo: CommentRepository, post_id: int, parent_comment_id: int | None) -> int | None:
    if parent_comment_id is None:
        return None

    parent = await comment_repo.get_by_id(parent_comment_id)

    if parent is None:
        raise _parent_comment_not_found_error()

    if parent.post_id != post_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="다른 게시글의 댓글에는 답글을 달 수 없습니다."
        )

    # 대상이 2단계 이상이면, 대상이 몇 단계인지 확인
    if parent.parent_comment_id is not None:
        grand_parent = await comment_repo.get_by_id(parent.parent_comment_id)

        if grand_parent is None:
            raise _parent_comment_not_found_error()

        # 대상이 3단계(자식 댓글2)면 → 같은 단계에 붙도록 부모를 한 칸 위로
        if grand_parent.parent_comment_id is not None:
            parent_comment_id = parent.parent_comment_id

    return parent_comment_id
