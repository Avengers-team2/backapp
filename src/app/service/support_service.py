import asyncio
import logging
import time
from datetime import date
from enum import Enum

from fastapi import Depends, HTTPException, status

from app.infrastructure.external.public_data_api import CollectError, collect_all
from app.repository.analysis_input_repository import AnalysisInputRepository, get_analysis_input_repository
from app.schema.support_schema import SupportProgramDTO
from app.util.support_util import NATIONWIDE, clip, to_category_group

log = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 30 * 60
RETRY_AFTER_SECONDS = 60
RESULT_LIMIT = 60
SUMMARY_LENGTH = 120

STATUS_WORDS: dict[str, list[str]] = {
    "예비 창업자": ["예비"],
    "운영 중": ["소상공인", "기창업", "운영"],
    "폐업 예정": ["재기", "재창업", "폐업"],
    "가게 이전": ["이전", "확장"],
}


class SearchScope(str, Enum):
    ALL = "all"
    TITLE = "title"
    ORGANIZATION = "organization"


_rows: list[dict] = []
_fetched_at = 0.0
_failed_at = 0.0
_lock = asyncio.Lock()


async def load_programs() -> list[dict]:
    global _rows, _fetched_at, _failed_at
    if _rows and time.monotonic() - _fetched_at < CACHE_TTL_SECONDS:
        return _rows
    async with _lock:
        if _rows and time.monotonic() - _fetched_at < CACHE_TTL_SECONDS:
            return _rows
        if not _rows and _failed_at and time.monotonic() - _failed_at < RETRY_AFTER_SECONDS:
            raise CollectError("지원사업 공고를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.")
        try:
            results = await collect_all()
        except CollectError:
            _failed_at = time.monotonic()
            raise
        rows = [row for source_rows in results.values() for row in source_rows]
        if not rows:
            _failed_at = time.monotonic()
            if _rows:
                return _rows
            raise CollectError("지원사업 공고를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.")
        _rows = rows
        _fetched_at = time.monotonic()
        log.info("지원사업 공고 %d건 로드", len(rows))
        return _rows


async def preload_programs() -> None:
    try:
        await load_programs()
    except CollectError:
        pass


def _normalize(text: str | None) -> str:
    return "".join((text or "").split()).lower()


def _match_keyword(row: dict, keyword: str, scope: SearchScope) -> bool:
    if not keyword:
        return True
    if scope == SearchScope.TITLE:
        fields = [row["title"]]
    elif scope == SearchScope.ORGANIZATION:
        fields = [row["organization"]]
    else:
        fields = [row["title"], row["organization"], row["summary"], row["category"]]
    return any(keyword in _normalize(f) for f in fields)


def _in_seoul(row: dict) -> bool:
    regions = row["regions"]
    return not regions or NATIONWIDE in regions or "서울" in regions


def _relevance(row: dict, status_words: list[str], industry_words: list[str]) -> int:
    conditions = _normalize(" ".join(row["targets"] + row["career"]))
    text = _normalize(" ".join(filter(None, [row["title"], row["summary"]])))
    score = 0
    if any(w in conditions or w in text for w in status_words):
        score += 2
    if any(w in text for w in industry_words):
        score += 1
    return score


def _deadline_key(row: dict) -> tuple[bool, date]:
    end = row["end_date"]
    return (end is None, end or date.max)


def _tags(row: dict) -> list[str]:
    tags: list[str] = []
    for value in [*row["targets"], *row["career"], *row["regions"]]:
        value = value.strip()
        if value and value not in tags and len(value) <= 10:
            tags.append(value)
        if len(tags) == 3:
            break
    return tags


def _to_dto(row: dict) -> SupportProgramDTO:
    return SupportProgramDTO(
        source=row["source"],
        source_id=row["source_id"],
        title=row["title"],
        organization=row["organization"],
        category=row["category"],
        category_group=to_category_group(row["category"]),
        summary=clip(row["summary"], SUMMARY_LENGTH),
        start_date=row["start_date"],
        end_date=row["end_date"],
        period_text=row["period_text"],
        tags=_tags(row),
        regions=row["regions"],
        detail_url=row["detail_url"] or row["apply_url"],
    )


class SupportService:
    def __init__(self, input_repo: AnalysisInputRepository):
        self.input_repo = input_repo

    async def search(self, keyword: str, scope: SearchScope, input_id: int | None, user_id: int | None) -> list[SupportProgramDTO]:
        try:
            rows = await load_programs()
        except CollectError as e:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e))

        today = date.today()
        word = _normalize(keyword)
        rows = [r for r in rows if (r["end_date"] is None or r["end_date"] >= today) and _match_keyword(r, word, scope)]
        rows.sort(key=_deadline_key)

        if input_id is not None:
            rows = await self._filter_by_analysis(rows, input_id, user_id)

        return [_to_dto(r) for r in rows[:RESULT_LIMIT]]

    async def _filter_by_analysis(self, rows: list[dict], input_id: int, user_id: int | None) -> list[dict]:
        if user_id is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "로그인이 필요합니다.")
        analysis = await self.input_repo.get_input(input_id, user_id)
        if analysis is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "분석 조건을 찾을 수 없습니다.")

        status_words = [_normalize(w) for w in STATUS_WORDS.get(analysis.input_use_purpose or "", [])]
        industry_words = [
            _normalize(w)
            for value in (analysis.input_industry_mid, analysis.input_industry_small)
            for w in value.replace("·", " ").split()
            if len(w.strip()) >= 2
        ]

        seoul = [r for r in rows if _in_seoul(r)]
        scored = [(r, _relevance(r, status_words, industry_words)) for r in seoul]
        matched = [(r, s) for r, s in scored if s > 0]
        if not matched:
            return seoul
        matched.sort(key=lambda item: (-item[1], _deadline_key(item[0])))
        return [r for r, _ in matched]


def get_support_service(
        input_repository: AnalysisInputRepository = Depends(get_analysis_input_repository)
    ):
    return SupportService(input_repository)
