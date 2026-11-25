from datetime import date

from fastapi import Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError

from app.infrastructure.external.public_data_api import CollectError
from app.repository.support_bookmark_repository import SupportBookmarkRepository, get_support_bookmark_repository
from app.schema.support_schema import MySupportBookmarkDTO, SupportBookmarkStatusDTO
from app.service.support_service import load_programs

KSTARTUP_DETAIL_URL = "https://www.k-startup.go.kr/web/contents/bizpbanc-ongoing.do?schM=view&pbancSn="


async def _program_index() -> dict[tuple[str, str], dict]:
    try:
        rows = await load_programs()
    except CollectError:
        return {}
    return {(r["source"], r["source_id"]): r for r in rows}


def _fallback_url(source: str, source_id: str) -> str | None:
    if source == "kstartup" and source_id.isdigit():
        return KSTARTUP_DETAIL_URL + source_id
    return None


class SupportBookmarkService:
    def __init__(self, repo: SupportBookmarkRepository):
        self.repo = repo

    async def toggle(self, user_id: int, source: str, source_id: str) -> SupportBookmarkStatusDTO:
        if await self.repo.exists_bookmark(user_id, source, source_id):
            await self.repo.delete_bookmark(user_id, source, source_id)
            return SupportBookmarkStatusDTO(source=source, source_id=source_id, is_bookmarked=False)

        program = (await _program_index()).get((source, source_id))
        deadline = program["end_date"] if program else None
        try:
            await self.repo.create_bookmark(user_id, source, source_id, deadline)
        except IntegrityError:
            await self.repo.db.rollback()
        return SupportBookmarkStatusDTO(source=source, source_id=source_id, is_bookmarked=True)

    async def list_keys(self, user_id: int) -> list[str]:
        bookmarks = await self.repo.list_bookmarks(user_id)
        return [f"{b.bookmark_program_source}:{b.bookmark_program_id}" for b in bookmarks]

    async def list_my_bookmarks(self, user_id: int, keyword: str) -> list[MySupportBookmarkDTO]:
        bookmarks = await self.repo.list_bookmarks(user_id)
        index = await _program_index()
        today = date.today()
        word = "".join(keyword.split()).lower()
        items: list[MySupportBookmarkDTO] = []

        for b in bookmarks:
            source, source_id = b.bookmark_program_source, b.bookmark_program_id
            program = index.get((source, source_id))
            end_date = program["end_date"] if program else b.bookmark_deadline_date
            item = MySupportBookmarkDTO(
                bookmark_id=b.bookmark_id,
                source=source,
                source_id=source_id,
                title=program["title"] if program else "공고 정보를 불러올 수 없어요",
                organization=program["organization"] if program else None,
                category=program["category"] if program else None,
                start_date=program["start_date"] if program else None,
                end_date=end_date,
                dday=(end_date - today).days if end_date else None,
                detail_url=(program["detail_url"] or program["apply_url"]) if program else _fallback_url(source, source_id),
                is_available=program is not None,
            )
            if word and word not in "".join(f"{item.title}{item.organization or ''}".split()).lower():
                continue
            items.append(item)

        return items


def get_support_bookmark_service(
        repo: SupportBookmarkRepository = Depends(get_support_bookmark_repository)
    ):
    return SupportBookmarkService(repo)
