import os
import tempfile

from langchain_community.document_loaders import Docx2txtLoader, PyPDFLoader

MIN_TEXT_LENGTH = 200   # 이보다 글자가 적으면 스캔 이미지 PDF 등으로 보고 검토하지 않음


# 업로드한 기획서(pdf/docx) 내용 → AI에 넘길 텍스트
# 프롬프트 규칙에 맞춰 PDF는 페이지마다 [p.숫자] 표시를 붙인다.
def extract_report_text(content: bytes, file_type: str) -> str:
    suffix = f".{file_type}"

    # LangChain 문서 로더는 파일 경로를 받으므로 임시 파일에 저장해서 읽는다.
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        if file_type == "pdf":
            docs = PyPDFLoader(tmp_path).load()
            pages = [
                f"[p.{doc.metadata.get('page', i) + 1}]\n{doc.page_content.strip()}"
                for i, doc in enumerate(docs)
            ]
            return "\n\n".join(pages)

        if file_type == "docx":
            docs = Docx2txtLoader(tmp_path).load()
            return "\n\n".join(doc.page_content.strip() for doc in docs)

        raise ValueError(f"지원하지 않는 파일 형식입니다: {file_type}")

    finally:
        os.remove(tmp_path)


# 페이지 표시를 뺀 실제 글자 수가 충분한지
def has_enough_text(text: str) -> bool:
    body = "".join(line for line in text.splitlines() if not line.startswith("[p."))
    return len(body.strip()) >= MIN_TEXT_LENGTH
