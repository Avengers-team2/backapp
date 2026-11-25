import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()

# 기획서분석용 함수
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL")

if GEMINI_API_KEY is None:
    raise RuntimeError("GEMINI_API_KEY가 없습니다")
if GEMINI_MODEL is None:
    raise RuntimeError("GEMINI_MODEL 없습니다")

llm = ChatGoogleGenerativeAI(
    model=GEMINI_MODEL,
    temperature=0,
    google_api_key=GEMINI_API_KEY,
    max_retries=3
)
def get_llm():
    return llm

# 상권분석용 함수
GEMINI_AREA_API_KEY = os.getenv("GEMINI_AREA_API_KEY")
GEMINI_AREA_MODEL = os.getenv("GEMINI_AREA_MODEL")

area_llm = None

def get_area_llm():
    global area_llm

    if area_llm is None:
        if GEMINI_AREA_API_KEY is None:
            raise RuntimeError("GEMINI_AREA_API_KEY가 없습니다")
        if GEMINI_AREA_MODEL is None:
            raise RuntimeError("GEMINI_AREA_MODEL이 없습니다")

        area_llm = ChatGoogleGenerativeAI(
            model=GEMINI_AREA_MODEL,
            temperature=0,
            google_api_key=GEMINI_AREA_API_KEY,
            max_retries=3
        )

    return area_llm