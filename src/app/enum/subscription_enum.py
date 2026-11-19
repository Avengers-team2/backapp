# app/enums/subscription_enum.py
import enum

class SubscriptionStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"      # 이용 중
    CANCELED = "CANCELED"  # 해지되어 이용 종료
    EXPIRED = "EXPIRED"    # 이용 기간이 끝나서 종료