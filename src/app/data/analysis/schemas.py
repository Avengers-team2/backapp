"""ML 결과를 백엔드/화면에 넘기는 출력 형식 (백엔드와 합의하는 '계약').

규칙
- 파이썬 안에서는 snake_case, JSON(API)으로 내보낼 때는 camelCase (model_dump(by_alias=True))
- 값이 없으면 키를 빼지 말고 null 로 보낸다. 숫자는 숫자 타입, 코드는 항상 문자열(앞자리 0 보존)
- 결과는 등급(A~D) 없이 '점수'로만 보여준다 (사용자 결정). DB 의 analysis_grade 컬럼은 null 로 둔다.

실행 확인: ml/ 폴더에서  python -m schemas
"""
import json
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

QUARTER = r"^\d{5}$"  # 예: "20254" (CHAR(5))


class CamelModel(BaseModel):
    # protected_namespaces=(): model_version 이 pydantic 예약 접두어(model_)와 겹쳐서 나는 경고를 끈다 (이름은 ERD 와 맞춤)
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid", protected_namespaces=())


class Indicator(CamelModel):
    score: Optional[float] = Field(default=None, ge=0, le=100)  # 0~100, 자료가 없으면 null
    detail: Optional[str] = None  # 점수가 있을 때의 근거 문장
    reason: Optional[str] = None  # 점수가 null 일 때의 이유 (예: "자료 없음")


class Indicators(CamelModel):
    sales: Indicator
    competition: Indicator
    customer: Indicator
    time: Indicator
    closure: Indicator
    stability: Indicator


class Prediction(CamelModel):
    base_quarter: str = Field(pattern=QUARTER)
    predict_quarter: str = Field(pattern=QUARTER)
    predicted_sales: Optional[int] = None  # 원 단위, 없으면 null
    scope: str = "상권·업종 단위 예측입니다"


class AnalysisResult(CamelModel):
    analysis_id: Optional[int] = None  # 백엔드가 저장한 뒤 채움
    area_code: str = Field(min_length=1)  # 상권 코드 (문자열)
    industry_code: str = Field(min_length=1)  # 업종 코드 (문자열)
    total_score: Optional[float] = Field(default=None, ge=0, le=100)
    reliability: Literal["높음", "보통", "낮음"]
    indicators: Indicators
    prediction: Prediction
    risks: list[str] = Field(default_factory=list)  # 위험 요인 문장
    improvements: list[str] = Field(default_factory=list)  # 개선 방향 문장
    model_version: str  # 예측 모델 버전
    scoring_version: str  # 점수 계산 규칙(가중치·기준값·문장 규칙) 버전. 규칙을 바꾸면 올린다


def to_analysis_row(r: AnalysisResult) -> dict:
    """ERD 의 analysis 테이블 컬럼 이름에 맞춘 한 행.
    (analysis_id, 입력값 컬럼 input_* 은 백엔드가 채운다)
    """
    ind = r.indicators
    detail = {  # analysis_result_detail (JSON): 근거 문장, 위험 요인, 개선 방향, 신뢰도
        "reliability": r.reliability,
        "scoringVersion": r.scoring_version,  # ERD 에 전용 컬럼이 없어 detail JSON 안에 저장
        "indicators": {k: v for k, v in ind.model_dump(by_alias=True, exclude_none=True).items()},
        "risks": r.risks,
        "improvements": r.improvements,
        "scope": r.prediction.scope,
    }
    return {
        "analysis_total_score": r.total_score,
        "analysis_grade": None,  # 등급은 쓰지 않음 (점수로 표시)
        "analysis_sales_score": ind.sales.score,
        "analysis_competition_score": ind.competition.score,
        "analysis_customer_score": ind.customer.score,
        "analysis_time_score": ind.time.score,
        "analysis_closure_score": ind.closure.score,
        "analysis_stability_score": ind.stability.score,
        "analysis_predicted_sales": r.prediction.predicted_sales,
        "analysis_predict_quarter": r.prediction.predict_quarter,  # CHAR(5)
        "analysis_model_version": r.model_version,
        "analysis_result_detail": json.dumps(detail, ensure_ascii=False),
    }

