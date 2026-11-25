from enum import Enum

class AnnouncementSourceEnum(str, Enum):
    KSTARTUP = "kstartup"  # K-Startup 사업공고 (창업진흥원)
    MSS = "mss"            # 중소벤처기업부 사업공고
    BIZINFO = "bizinfo"    # 기업마당 지원사업공고 (중기부·지자체 통합)

class CategoryGroupEnum(str, Enum):
    """출처마다 다른 공고 분류를 묶은 공통 그룹 (카드 아이콘·색 구분용)"""
    FUNDING = "FUNDING"        # 자금
    BUSINESS = "BUSINESS"      # 사업화
    EDUCATION = "EDUCATION"    # 교육·멘토링
    FACILITY = "FACILITY"      # 공간·시설
    EVENT = "EVENT"            # 행사·네트워크
    MARKET = "MARKET"          # 판로·수출
    TECH_HR = "TECH_HR"        # 기술·인력
    ETC = "ETC"                # 기타 (매핑 안 되는 값)

class AnnouncementSortEnum(str, Enum):
    DEADLINE = "DEADLINE"  # 마감 임박순 (마감일 없는 공고는 뒤로)
    LATEST = "LATEST"      # 최근 수집순
