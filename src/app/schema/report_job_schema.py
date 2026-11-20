from datetime import datetime
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel  # JS 카멜 -> Snake로 변경해서 받기

from app.enum.report_enum import ReportStatus


# VO
class ReportJobVO(BaseModel):
    report_job_id: int
    user_id: int
    report_job_file_name: str
    report_job_file_type: str
    report_job_file_size: int
    report_job_file_path: str
    report_job_created_at: datetime | None = None
    report_job_completed_at: datetime | None = None
    report_job_status: ReportStatus = ReportStatus.PENDING
    report_job_error_message: str | None = None

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)
            