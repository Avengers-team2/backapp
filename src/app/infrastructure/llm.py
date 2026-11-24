import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL")

if GEMINI_API_KEY is None:
    raise RuntimeError("GEMINI_API_KEY가 없습니다")
if GEMINI_MODEL is None:
    raise RuntimeError("GEMINI_MODEL 없습니다")

llm = ChatGoogleGenerativeAI(
    model=GEMINI_MODEL,
    temperature=0,
    google_api_key=GEMINI_API_KEY
)
def get_llm():
    return llm