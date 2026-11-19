import enum

class PaymentStatus(str, enum.Enum):
    READY = "READY"          # 결제 요청 생성, 아직 결제 전
    PAID = "PAID"            # 결제 완료
    FAILED = "FAILED"        # 결제 실패
    CANCELED = "CANCELED"    # 결제 취소 (환불 포함)