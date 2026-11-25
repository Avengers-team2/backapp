from datetime import date

from pydantic import BaseModel, Field

from app.enum.support_enum import CategoryGroupEnum


class SupportProgramDTO(BaseModel):
    source: str
    source_id: str
    title: str
    organization: str | None = None
    category: str | None = None
    category_group: CategoryGroupEnum
    summary: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    period_text: str | None = None
    tags: list[str] = []
    regions: list[str] = []
    detail_url: str | None = None


class MyAnalysisOptionDTO(BaseModel):
    input_id: int
    label: str
    summary: str


class SupportBookmarkRequestDTO(BaseModel):
    source: str = Field(min_length=1, max_length=30)
    source_id: str = Field(min_length=1, max_length=100)


class SupportBookmarkStatusDTO(BaseModel):
    source: str
    source_id: str
    is_bookmarked: bool


class MySupportBookmarkDTO(BaseModel):
    bookmark_id: int
    source: str
    source_id: str
    title: str
    organization: str | None = None
    category: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    dday: int | None = None
    detail_url: str | None = None
    is_available: bool
