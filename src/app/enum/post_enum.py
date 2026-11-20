import enum


class PostCategoryEnum(str, enum.Enum):
    REVIEW = "REVIEW"            # 창업후기
    MARKET_INFO = "MARKET_INFO"  # 상권정보
    SUPPORT_QNA = "SUPPORT_QNA"  # 지원사업Q&A
    FREE = "FREE"                # 자유