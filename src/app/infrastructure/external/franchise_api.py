import asyncio
import json
import logging
import os
import time
from datetime import date
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[4] / ".env")

BRAND_API_KEY = os.getenv("FTC_BRAND_API_KEY") or os.getenv("DATA_GO_KR_API_KEY", "")
BRAND_URL = "https://apis.data.go.kr/1130000/FftcBrandRlsInfo2_Service/getBrandinfo"
PAGE_SIZE = 1000
MAX_PAGES = 50

log = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)

RETRY_AFTER_SECONDS = 60
CONCURRENCY = 5
CACHE_FILE = Path(__file__).resolve().parents[2] / "data" / "brand_cache.json"
CACHE_MAX_AGE_SECONDS = 7 * 24 * 60 * 60

_brands: list[dict] | None = None
_lock = asyncio.Lock()
_last_error: tuple[float, str] | None = None


class BrandApiError(Exception):
    pass


def _extract_items(body: dict) -> tuple[list[dict], int]:
    root = body.get("response", body)
    header = root.get("header", root)
    code = str(header.get("resultCode", "00"))
    if code not in ("00", "0", "000"):
        raise BrandApiError(f"{code} {header.get('resultMsg', '')}")

    data = root.get("body", root)
    items = data.get("items") or []
    if isinstance(items, dict):
        items = items.get("item") or []
    if isinstance(items, dict):
        items = [items]
    total = int(data.get("totalCount") or 0)
    return items, total


def _to_brand(item: dict) -> dict | None:
    name = (item.get("brandNm") or item.get("brndNm") or "").strip()
    if not name:
        return None
    large = (item.get("indutyLclasNm") or "").strip()
    mid = (item.get("indutyMlsfcNm") or "").strip()
    return {
        "id": str(item.get("brandMnno") or item.get("brndMnno") or name),
        "name": name,
        "category": " · ".join(x for x in (large, mid) if x),
        "alias_of": None,
        "disclosure_url": "https://franchise.ftc.go.kr",
    }


async def _fetch_page(client: httpx.AsyncClient, year: int, page: int) -> tuple[list[dict], int]:
    res = await client.get(BRAND_URL, params={
        "serviceKey": BRAND_API_KEY,
        "pageNo": page,
        "numOfRows": PAGE_SIZE,
        "resultType": "json",
        "jngBizCrtraYr": year,
    })
    res.raise_for_status()
    return _extract_items(res.json())


async def _fetch_year(client: httpx.AsyncClient, year: int) -> list[dict]:
    first_items, total = await _fetch_page(client, year, 1)
    if not first_items:
        return []

    last_page = min(MAX_PAGES, -(-total // PAGE_SIZE))
    semaphore = asyncio.Semaphore(CONCURRENCY)

    async def fetch(page: int) -> list[dict]:
        async with semaphore:
            items, _ = await _fetch_page(client, year, page)
            return items

    rest = await asyncio.gather(*(fetch(page) for page in range(2, last_page + 1)))

    brands: dict[str, dict] = {}
    for items in [first_items, *rest]:
        for item in items:
            brand = _to_brand(item)
            if brand:
                brands.setdefault(brand["name"], brand)
    return list(brands.values())


def _read_cache() -> list[dict] | None:
    try:
        if time.time() - CACHE_FILE.stat().st_mtime > CACHE_MAX_AGE_SECONDS:
            return None
        brands = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        return brands if isinstance(brands, list) and brands else None
    except (OSError, ValueError):
        return None


def _write_cache(brands: list[dict]) -> None:
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(json.dumps(brands, ensure_ascii=False), encoding="utf-8")
    except OSError as e:
        log.warning("가맹 브랜드 캐시 저장 실패: %s", e)


def _safe_message(e: Exception) -> str:
    if isinstance(e, httpx.HTTPStatusError):
        code = e.response.status_code
        if code in (401, 403):
            return "공공데이터포털에서 '가맹정보 브랜드 목록' API 활용신청(승인)이 필요합니다."
        return f"공공데이터 API 응답 오류입니다. (HTTP {code})"
    if isinstance(e, httpx.RequestError):
        return "공공데이터 API 서버에 연결할 수 없습니다."
    if isinstance(e, BrandApiError):
        return str(e)
    return "브랜드 목록 응답을 처리하지 못했습니다."


async def load_brands() -> list[dict]:
    global _brands, _last_error
    if _brands is not None:
        return _brands

    async with _lock:
        if _brands is not None:
            return _brands
        cached = _read_cache()
        if cached:
            _brands = cached
            log.info("가맹 브랜드 %d개 로드 (캐시 파일)", len(cached))
            return _brands
        if _last_error and time.monotonic() - _last_error[0] < RETRY_AFTER_SECONDS:
            raise BrandApiError(_last_error[1])
        if not BRAND_API_KEY:
            raise BrandApiError("FTC_BRAND_API_KEY 또는 DATA_GO_KR_API_KEY 가 .env 에 없습니다.")

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                this_year = date.today().year
                for year in (this_year - 1, this_year - 2):
                    brands = await _fetch_year(client, year)
                    if brands:
                        _brands = brands
                        _write_cache(brands)
                        _last_error = None
                        log.info("가맹 브랜드 %d개 로드 (%d년 기준)", len(brands), year)
                        return _brands
            raise BrandApiError("브랜드 목록이 비어 있습니다.")
        except Exception as e:
            message = _safe_message(e)
            log.warning("가맹 브랜드 로드 실패: %s", message)
            _last_error = (time.monotonic(), message)
            raise BrandApiError(message) from None


async def preload_brands() -> None:
    try:
        await load_brands()
    except BrandApiError:
        pass
