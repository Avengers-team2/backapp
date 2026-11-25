from datetime import datetime
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel  # JS 카멜 -> Snake로 변경해서 받기

# VO
class ReportExportVO(BaseModel):
    export_id: int
    report_job_id: int
    export_file_path: str
    export_created_at: datetime | None = None

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


# DTO
# 검토 보고서 PDF 다운로드 링크 응답
class ReportExportDownloadDTO(BaseModel):
    download_url: str       # S3 임시 다운로드 주소
    file_name: str          # 내려받을 파일 이름
    expires_in: int         # 링크 유효 시간(초)

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)
