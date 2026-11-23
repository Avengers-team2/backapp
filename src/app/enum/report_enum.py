from enum import Enum

class ReportStatus(str, Enum):
    PENDING = "PENDING"        # 요청 접수, 대기 중
    PROCESSING = "PROCESSING"  # 검토 진행 중
    FILE_CHECK = "FILE_CHECK"    # 진행 1단계: 파일 확인 중
    AI_REVIEW = "AI_REVIEW"      # 진행 2단계: AI 검토 중
    SUMMARIZING = "SUMMARIZING"  # 진행 3단계: 검토 결과 정리 중
    COMPLETED = "COMPLETED"    # 검토 완료
    FAILED = "FAILED"          # 실패 (error_message에 사유 저장)