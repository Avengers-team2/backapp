from enum import Enum

class ReportStatus(str, Enum):
    PENDING = "PENDING"        # 요청 접수, 대기 중
    PROCESSING = "PROCESSING"  # 검토 진행 중
    COMPLETED = "COMPLETED"    # 검토 완료
    FAILED = "FAILED"          # 실패 (error_message에 사유 저장)