import enum

class PostCategoryEnum(str, enum.Enum):
    REVIEW = "REVIEW"            # 창업후기
    MARKET_INFO = "MARKET_INFO"  # 상권정보
    SUPPORT_QNA = "SUPPORT_QNA"  # 지원사업Q&A
    FREE = "FREE"                # 자유
    NOTICE = "NOTICE"            # 공지

class PostSortEnum(str, enum.Enum):
    LATEST = "LATEST" # 최신순
    OLDEST = "OLDEST" # 오래된순
    VIEWS = "VIEWS" # 조회수순
    LIKES = "LIKES" # 좋아요순

class PostSearchEnum(str, enum.Enum):
    TITLE = "TITLE" # 제목
    CONTENT = "CONTENT" # 내용