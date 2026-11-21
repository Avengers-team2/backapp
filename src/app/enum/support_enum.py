from enum import Enum

class AnnouncementSourceEnum(str, Enum):
    KSTARTUP = "kstartup"  # K-Startup 사업공고 (창업진흥원)
    MSS = "mss"            # 중소벤처기업부 사업공고
    BIZINFO = "bizinfo"    # 기업마당 지원사업공고 (중기부·지자체 통합)

class AnnouncementSortEnum(str, Enum):
    DEADLINE = "DEADLINE"  # 마감 임박순 (마감일 없는 공고는 뒤로)
    LATEST = "LATEST"      # 최근 수집순
