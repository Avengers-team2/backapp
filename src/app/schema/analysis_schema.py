from datetime import datetime
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel  # JS 카멜 -> Snake로 변경해서 받기

# VO
class AnalysisVO(BaseModel):
    analysis_id: int
    input_id: int
    analysis_total_score: float | None = None
    analysis_grade: str | None = None
    analysis_sales_score: float | None = None
    analysis_competition_score: float | None = None
    analysis_customer_score: float | None = None
    analysis_time_score: float | None = None
    analysis_closure_score: float | None = None
    analysis_stability_score: float | None = None
    analysis_closure_grade: str | None = None
    analysis_predicted_sales: int | None = None
    analysis_predict_quarter: str | None = None
    analysis_model_version: str | None = None
    analysis_data_quarter: str
    analysis_result_detail: dict | None = None
    analysis_is_saved: bool = False
    analysis_created_at: datetime | None = None

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)
        