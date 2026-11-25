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
