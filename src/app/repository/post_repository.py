from sqlalchemy.ext.asyncio import AsyncSession
from app.infrastructure.postgresql import get_postgresql_db
from fastapi import Depends
from sqlalchemy import insert, select, update, delete, func, exists, desc, asc, or_, and_
from sqlalchemy.orm import joinedload, selectinload

from app.schema.post_schema import PostCreateDTO
from app.model.post_model import Post
from app.model.post_comment_model import PostComment
from app.enum.post_enum import PostSortEnum

# 게시글별 "삭제 안 된 댓글 수"를 세는 서브쿼리 (목록 조회에서 같이 사용)
def comment_count_subquery():
    return (
        select(func.count(PostComment.comment_id))
            .where(PostComment.post_id == Post.post_id, PostComment.comment_deleted_at.is_(None))
            .correlate(Post)
            .scalar_subquery()
    )


class PostRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_post(self, user_id: int, post: PostCreateDTO) -> int:
        query = (
            insert(Post)
            .values(
                **post.model_dump(),
                user_id=user_id
            )
            .returning(
                Post.post_id
            )
        )
        result = await self.db.execute(query)
        await self.db.commit()
        new_post_id = result.scalar_one()
        return new_post_id


    async def get_by_id(self, post_id: int) -> Post | None:
        query = (
            select(Post)
                .options(joinedload(Post.user), selectinload(Post.comments.and_(PostComment.comment_deleted_at.is_(None)))
                    .joinedload(PostComment.user))
                .where(Post.post_id == post_id, Post.post_deleted_at.is_(None))
        )
        
        result = await self.db.execute(query)
        return result.scalar_one_or_none()


    async def find_post_by_paging(
        self,
        offset: int,
        limit: int,
        sort_by: PostSortEnum = PostSortEnum.LATEST,
        search: str | None = None,
        category: str | None = None
    ):
        query = (
            select(Post, comment_count_subquery().label("comment_count"))
                .options(joinedload(Post.user))
                .where(Post.post_deleted_at.is_(None))
        )
        if search:
            query = query.where(or_(Post.post_title.ilike(f"%{search}%"), Post.post_content.ilike(f"%{search}%")))
        
        if category:
            query = query.where(Post.post_category == category)
        
        count_query = select(func.count(Post.post_id)).where(Post.post_deleted_at.is_(None))
        
        if search:
            count_query = count_query.where(or_(Post.post_title.ilike(f"%{search}%"), Post.post_content.ilike(f"%{search}%")))
        
        if category:
            count_query = count_query.where(Post.post_category == category)
        
        if sort_by == PostSortEnum.OLDEST:
            query = query.order_by(asc(Post.post_id))
        
        elif sort_by == PostSortEnum.VIEWS:
            query = query.order_by(desc(Post.post_view_count), desc(Post.post_id))
        
        elif sort_by == PostSortEnum.LIKES:
            query = query.order_by(desc(Post.post_like_count), desc(Post.post_id))
        
        elif sort_by == PostSortEnum.LATEST:
            query = query.order_by(desc(Post.post_id))
        
        # 정렬된 상태에서 offset, limit
        query = query.offset(offset).limit(limit)

        count_result = await self.db.execute(count_query)
        total = count_result.scalar_one()
        result = await self.db.execute(query)
        return list(result.tuples().all()), total


    async def update_post(self, post_id: int, update_data: dict) -> int:
        query = (
            update(Post)
            .values(
                **update_data,
                post_updated_at = func.now()
            )
            .where(Post.post_id == post_id,Post.post_deleted_at.is_(None))
            .returning(Post.post_id)
        )

        result = await self.db.execute(query)
        await self.db.commit()
        updated_post_id = result.scalar_one_or_none()
        return updated_post_id


    async def delete_post(self, post_id: int) -> bool:
        query = (
            update(Post)
                .where(Post.post_id == post_id, Post.post_deleted_at.is_(None))
                .values(post_deleted_at = func.now())
        )

        result = await self.db.execute(query)
        await self.db.commit()
        return result.rowcount > 0


    async def increase_view_count(self, post_id: int) -> int:
        query = (
            update(Post)
                .where(Post.post_id == post_id, Post.post_deleted_at.is_(None))
                .values(post_view_count = Post.post_view_count + 1)
                .returning(Post.post_view_count)
        )

        result = await self.db.execute(query)
        await self.db.commit()
        view_count = result.scalar_one_or_none()
        return view_count


    async def increase_like_count(self, post_id: int) -> int | None:
        query = (
            update(Post)
                .where(Post.post_id == post_id, Post.post_deleted_at.is_(None))
                .values(post_like_count = Post.post_like_count + 1)
                .returning(Post.post_like_count)
        )

        result = await self.db.execute(query)
        like_count = result.scalar_one_or_none()
        return like_count


    async def decrease_like_count(self, post_id: int) -> int | None:
        query = (
            update(Post)
                .where(
                    Post.post_id == post_id,
                    Post.post_deleted_at.is_(None),
                    Post.post_like_count > 0
                )
                .values(post_like_count = Post.post_like_count - 1)
                .returning(Post.post_like_count)
        )

        result = await self.db.execute(query)
        like_count = result.scalar_one_or_none()
        return like_count


    async def find_my_posts(self, user_id: int, offset: int, limit: int):
        query = (
            select(Post, comment_count_subquery().label("comment_count"))
                .options(joinedload(Post.user))
                .where(Post.user_id == user_id, Post.post_deleted_at.is_(None))
                .order_by(desc(Post.post_id))
                .offset(offset)
                .limit(limit)
        )

        count_query = (
            select(func.count(Post.post_id))
                .where(Post.user_id == user_id, Post.post_deleted_at.is_(None))
        )

        count_result = await self.db.execute(count_query)
        total = count_result.scalar_one()
        result = await self.db.execute(query)
        return list(result.tuples().all()), total


    async def exists_post(self, post_id: int) -> bool:
        query = select(exists().where(Post.post_id == post_id, Post.post_deleted_at.is_(None)))
        result = await self.db.execute(query)
        return result.scalar()


def get_post_repository(db: AsyncSession = Depends(get_postgresql_db)):
    return PostRepository(db)