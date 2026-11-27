from datetime import datetime
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel  # JS 카멜 -> Snake로 변경해서 받기

# VO
class ReportExportVO(BaseModel):
    export_id: int
    report_job_id: int
    export_file_path: str
    export_created_at: datetime | None = None
    export_result_json: dict | None = None

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


# DTO
# 검토 보고서 PDF 다운로드 링크 응답
class ReportExportDownloadDTO(BaseModel):
    download_url: str       # S3 임시 다운로드 주소
    file_name: str          # 내려받을 파일 이름
    expires_in: int         # 링크 유효 시간(초)

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


# 결과 화면용 항목 점수 한 줄
class ReportResultItemDTO(BaseModel):
    item_key: str
    label: str              # 평가 항목 이름 (예: 시장성 및 고객 분석)
    short_label: str        # 카드용 짧은 이름 (예: 시장·고객)
    score: int              # 100점 환산 (1~5단계 × 20)
    grade: str              # 우수 / 보통 / 미흡 / 매우 미흡
    judgment: str
    strengths: list[str] = []
    gaps: list[str] = []

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ReportResultSuggestionDTO(BaseModel):
    priority: str           # 높음 / 보통 / 낮음
    problem: str
    action: str

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ReportResultFinanceDTO(BaseModel):
    label: str
    original: str | None = None
    formula: str | None = None
    result: str             # 일치 / 불일치 / 근거 누락

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


# 결과 화면 응답 (GET /reports/jobs/{id}/result)
class ReportResultDTO(BaseModel):
    report_job_id: int
    file_name: str                  # 원본 기획서 이름
    file_type: str                  # pdf / docx
    business_item: str              # 사업 아이템 한 줄 요약 (화면 제목용)
    reviewed_at: datetime | None    # 검토 완료 일시
    total_score: int | None         # 종합 점수 (100점)
    total_grade: str | None = None  # 종합 등급 (우수 / 보통 / 미흡 / 매우 미흡)
    summary: str
    key_strengths: list[str] = []
    items: list[ReportResultItemDTO] = []
    suggestions: list[ReportResultSuggestionDTO] = []
    finance_checks: list[ReportResultFinanceDTO] = []
    final_opinion: str = ""
    pdf_file_name: str              # 검토 보고서 PDF 이름
    pdf_size: int | None = None     # 검토 보고서 PDF 용량(바이트)
    original_url: str | None = None # 원본 미리보기 주소 (PDF만, 1시간 유효)

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

