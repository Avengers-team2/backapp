"""
서울시 상권분석서비스(영역-상권) CSV 를 읽어서 상권 검색에 쓴다.
파일: app/data/analysis_input/seoul_trdar.csv  (서울 열린데이터광장 OA-15560 에서 CSV 내려받기)
"""

import csv
from functools import lru_cache
from pathlib import Path

TRDAR_CSV_PATH = Path(__file__).resolve().parents[1] / "data" / "analysis_input" / "seoul_trdar.csv"

COL_CODE = "상권_코드"
COL_NAME = "상권_코드_명"
COL_GU = "자치구_코드_명"
COL_DONG = "행정동_코드_명"


def _read_rows(path: Path) -> list[dict]:
    for encoding in ("utf-8-sig", "cp949"):
        try:
            with path.open(encoding=encoding, newline="") as f:
                return list(csv.DictReader(f))
        except UnicodeDecodeError:
            continue
    raise ValueError("상권 CSV 인코딩을 읽을 수 없습니다.")


@lru_cache(maxsize=1)
def load_trdar_list() -> tuple[dict, ...]:
    if not TRDAR_CSV_PATH.exists():
        return tuple()

    areas = []
    for row in _read_rows(TRDAR_CSV_PATH):
        code = (row.get(COL_CODE) or "").strip()
        name = (row.get(COL_NAME) or "").strip()
        if not code or not name:
            continue
        areas.append({
            "code": code,
            "name": name,
            "gu": (row.get(COL_GU) or "").strip(),
            "dong": (row.get(COL_DONG) or "").strip(),
        })
    return tuple(areas)


def normalize(text: str) -> str:
    return "".join(text.split()).lower()


def search_trdar(keyword: str, limit: int = 8) -> list[dict]:
    tokens = [normalize(t) for t in keyword.split() if t.strip()]
    if not tokens:
        return []

    starts, contains = [], []
    for area in load_trdar_list():
        name = normalize(area["name"])
        haystack = name + normalize(area["gu"] + area["dong"])
        if not all(t in haystack for t in tokens):
            continue
        (starts if name.startswith(tokens[0]) else contains).append(area)
    return (starts + contains)[:limit]


def exists_trdar(code: str) -> bool:
    areas = load_trdar_list()
    if not areas:
        return True
    return any(a["code"] == code for a in areas)
