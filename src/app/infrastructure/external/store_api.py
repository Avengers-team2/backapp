"""
소상공인시장진흥공단 상가(상권)정보 API - 반경 내 상가업소 조회

키: .env 의 STORE_INFO_KEY (값은 로그/응답에 절대 남기지 않는다)
주의: 초당 호출 횟수 제한이 있다 (동시에 여러 건 보내면 LIMITED_NUMBER_OF_SERVICE_REQUESTS_PER_SECOND 오류).
      그래서 모든 호출을 한 줄로 세우고 사이에 간격을 둔다.
"""
import asyncio
import logging
import os
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[4] / ".env")

STORE_INFO_KEY = os.getenv("STORE_INFO_KEY", "")
RADIUS_URL = "https://apis.data.go.kr/B553077/api/open/sdsc2/storeListInRadius"
PAGE_SIZE = 1000
MAX_PAGES = 5
MIN_INTERVAL = 0.4  # 호출 사이 최소 간격(초)
MAX_RETRY = 5

log = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)

_gate = asyncio.Lock()
_last_call = 0.0


class StoreApiError(Exception):
    pass


async def _get(client: httpx.AsyncClient, params: dict) -> dict:
    """한 줄로 세워서 호출. 초당 제한 오류가 나오면 잠깐 쉬고 다시 시도"""
    global _last_call
    for attempt in range(MAX_RETRY):
        async with _gate:
            wait = MIN_INTERVAL - (time.monotonic() - _last_call)
            if wait > 0:
                await asyncio.sleep(wait)
            res = await client.get(RADIUS_URL, params=params)
            _last_call = time.monotonic()
        res.raise_for_status()
        body = res.json()
        if "body" in body:
            return body
        if "LIMITED_NUMBER" in str(body):
            await asyncio.sleep(1.5 * (attempt + 1))
            continue
        raise StoreApiError("상가정보 API 응답이 올바르지 않습니다.")
    raise StoreApiError("상가정보 API 호출 한도를 초과했습니다. 잠시 후 다시 시도해 주세요.")


async def fetch_stores_in_radius(lat: float, lng: float, radius_m: int) -> tuple[list[dict], str]:
    """(점포 목록, 데이터 기준월 'YYYYMM'). 반경 안 전체를 페이지 넘기며 모은다"""
    if not STORE_INFO_KEY:
        raise StoreApiError("STORE_INFO_KEY 가 .env 에 없습니다.")

    items: list[dict] = []
    stdr_ym = ""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            for page in range(1, MAX_PAGES + 1):
                body = await _get(client, {
                    "serviceKey": STORE_INFO_KEY,
                    "radius": radius_m,
                    "cx": lng,
                    "cy": lat,
                    "type": "json",
                    "numOfRows": PAGE_SIZE,
                    "pageNo": page,
                })
                header = body.get("header", {})
                if str(header.get("resultCode", "00")) != "00":
                    raise StoreApiError(f"상가정보 API 오류: {header.get('resultMsg', '')}")
                stdr_ym = header.get("stdrYm", stdr_ym)
                data = body["body"]
                items += data.get("items") or []
                if len(items) >= int(data.get("totalCount") or 0):
                    break
    except httpx.HTTPError as e:
        # 요청 주소에 키가 들어 있어서 예외 문구를 그대로 내보내지 않는다
        raise StoreApiError(f"상가정보 API 연결 실패 ({type(e).__name__})") from None
    return items, stdr_ym
