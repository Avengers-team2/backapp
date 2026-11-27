import re

MIN_TEXT_LEN = 20  # make_split.py 와 같은 기준

# 목록 기호로 시작하는 줄은 각각 따로 한 문단으로 본다
BULLET_PATTERN = re.compile(r"^\s*([◾•·▪■□○●◦※\-\*]|\d+[.)]|[①-⑳])\s*")


def split_text(text: str) -> list[str]:
    # 4) 줄바꿈을 \n 으로 통일하고, 빈 줄(공백만 있는 줄 포함) 기준으로 덩어리를 나눈다
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    blocks = re.split(r"\n\s*\n", text)

    paragraphs = []
    for block in blocks:
        lines = [line.strip() for line in block.split("\n") if line.strip()]
        if not lines:
            continue
        # 5) 덩어리 안에 목록 기호로 시작하는 줄이 있으면 줄마다 따로 문단으로 나눈다
        if sum(bool(BULLET_PATTERN.match(line)) for line in lines) >= 2:
            current = ""
            for line in lines:
                if BULLET_PATTERN.match(line) and current:
                    paragraphs.append(current)
                    current = line
                else:
                    current = f"{current} {line}".strip()
            if current:
                paragraphs.append(current)
        # 6) 아니면 덩어리 안의 줄을 한 칸 띄어 이어서 한 문단으로 만든다
        else:
            paragraphs.append(" ".join(lines))

    # 7) 앞뒤 공백을 지우고 MIN_TEXT_LEN 미만인 문단(제목 등)은 뺀다
    return [p.strip() for p in paragraphs if len(p.strip()) >= MIN_TEXT_LEN]


MIN_PDF_ITEM_LEN = 5  # PDF 의 불릿·표 행은 이 글자 수 미만이면 제외
# "1. 사업 개요", "3-1. 목표 고객" 같은 번호 제목 (짧은 줄만, 문장은 제외)
HEADING_PATTERN = re.compile(r"^\d+(?:-\d+)*[.)]\s*\S.{0,38}$")
# 표 머리글 줄: "항목 내용", "구분 금액" 처럼 짧고 첫 낱말이 열 이름인 줄
TABLE_HEADER_PATTERN = re.compile(r"^(항목|구분|품목|분류|내용|단계|기간)\s+\S+(\s+\S+)?$")
FULL_LINE_RATIO = 0.75  # 이 비율 이상 긴 줄은 "줄바꿈으로 잘린 줄"로 본다


def is_heading(line: str) -> bool:
    return bool(HEADING_PATTERN.match(line)) and not line.endswith(("다.", "."))


def split_pdf_text(text: str) -> list[tuple[str, str]]:
    """PDF 글자를 (section, 문단) 목록으로 자른다. 제목 줄은 문단에 넣지 않고 section 으로만 쓴다."""
    lines = [ln.strip() for ln in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    max_len = max((len(ln) for ln in lines), default=0)
    full_len = max_len * FULL_LINE_RATIO

    result: list[tuple[str, str]] = []
    section = ""
    current = ""      # 이어 붙이는 중인 문단
    cur_kind = ""     # "bullet" 또는 "prose"
    prev_full = False  # 직전 줄이 꽉 찬 줄이었는지
    in_table = False

    def flush() -> None:
        nonlocal current, cur_kind
        min_len = MIN_PDF_ITEM_LEN if cur_kind == "bullet" else MIN_TEXT_LEN
        if current and len(current) >= min_len:
            result.append((section, current))
        current, cur_kind = "", ""

    for line in lines:
        if not line:  # 빈 줄(쪽 바뀜 등): 문단은 끝내되 표 상태는 유지
            flush()
            prev_full = False
            continue
        if is_heading(line):
            flush()
            section = line
            in_table = False
            prev_full = False
            continue
        if TABLE_HEADER_PATTERN.match(line) and len(line) <= 15:
            flush()
            in_table = True
            prev_full = False
            continue
        if in_table:
            if line.endswith(("다.", ".")) or BULLET_PATTERN.match(line):
                in_table = False  # 표가 끝나고 일반 문장이 시작됨
            else:
                flush()
                if len(line) >= MIN_PDF_ITEM_LEN:
                    result.append((section, line))
                continue
        if BULLET_PATTERN.match(line):
            flush()
            current, cur_kind = line, "bullet"
        elif current and prev_full:
            current = f"{current} {line}"  # 줄바꿈으로 잘린 문장 이어 붙이기
        else:
            flush()
            current, cur_kind = line, "prose"
        prev_full = len(line) >= full_len and not line.endswith(("다.", "."))
    flush()
    return result


PAGE_PATTERN = re.compile(r"\[p\.(\d+)\]\n?")

def split_report_paragraphs(text: str) -> list[tuple[int | None, str, str]]:
    if not text.startswith("[p."): 
        result = []
        for p in split_text(text):
            result.append((None, "", p))
        return result

    parts = PAGE_PATTERN.split(text)
    pages = []

    for i, p in zip(parts[1::2], parts[2::2]):
        pages.append((int(i), p))

    clean = "\n\n".join(p for _, p in pages)
    pairs = split_pdf_text(clean)

    page_keys = []
    for num, page_text in pages:
        page_keys.append((num, re.sub(r"\s", "", page_text)))

    result = []
    for section, para in pairs:
        key = re.sub(r"\s", "", para)[:15]

        page = None
        for num, flat in page_keys:
            if key in flat:
                page = num
                break

        result.append((page, section, para))

    return result
