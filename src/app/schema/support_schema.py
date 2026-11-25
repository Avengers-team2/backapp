from datetime import date

from pydantic import BaseModel

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
