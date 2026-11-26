"""
상권 안의 현재 점포 조회 (소상공인 상가정보) + 같은 업종 / 프랜차이즈 분류

흐름
  1) 상권 중심 + 반지름(폴리곤 가장 먼 꼭짓점 거리)으로 반경 조회  -> 폴리곤 안에 있는 점포만 남김
  2) 상권별로 12시간 캐시 (메모리 + 파일). 상가정보는 월 단위로 갱신되는 데이터라 자주 부를 필요가 없다
  3) 선택한 업종과 같은 점포만 골라 프랜차이즈 / 일반 점포로 나눔 (프론트가 다른 모양으로 그릴 수 있게)

프랜차이즈 판별: 공정위 브랜드 목록(app/data/analysis_input/brand_cache.json)의 이름과 점포 상호명을 비교한다.
  - 상호명이 브랜드명으로 시작하면 (3글자 이상) 프랜차이즈 후보
  - 2글자 브랜드는 상호명이 정확히 같거나 '브랜드명+...점' 형태일 때만
  * 이름 비교라서 오탐/누락이 있을 수 있다 (is_franchise 는 '추정'). 화면에 단정하지 말 것.
"""
import asyncio
import json
import math
import re
import time
from pathlib import Path

from shapely.geometry import Point

from app.infrastructure.external.franchise_api import load_brands
from app.infrastructure.external.store_api import fetch_stores_in_radius
from app.util.store_industry_map import is_same_industry
from app.util.trdar_geo_util import _load as _load_geo

CACHE_DIR = Path(__file__).resolve().parents[1] / "data" / "store_cache"
CACHE_TTL_SECONDS = 12 * 60 * 60
MIN_RADIUS_M, MAX_RADIUS_M = 150, 1500

_memory: dict[str, tuple[float, dict]] = {}
_locks: dict[str, asyncio.Lock] = {}
_brand_index: dict[str, str] | None = None


def _norm(text: str) -> str:
    return re.sub(r"[^0-9a-z가-힣]", "", (text or "").lower())


def _area(code: str):
    """(feature, shapely 도형) 또는 None"""
    loaded = _load_geo()
    if loaded is None or code not in loaded[3]:
        return None
    i = loaded[3][code]
    return loaded[0][i], loaded[1][i]


def _radius_m(feature: dict, geom) -> int:
    """중심에서 폴리곤 가장 먼 꼭짓점까지 거리(m) + 여유"""
    p = feature["properties"]
    lat0, lng0 = p["center_lat"], p["center_lng"]
    kx = 111_000 * math.cos(math.radians(lat0))
    far = 0.0
    polys = geom.geoms if geom.geom_type == "MultiPolygon" else [geom]
    for poly in polys:
        for lng, lat in poly.exterior.coords:
            far = max(far, math.hypot((lng - lng0) * kx, (lat - lat0) * 111_000))
    return int(min(max(far + 30, MIN_RADIUS_M), MAX_RADIUS_M))


def _slim(item: dict) -> dict:
    """프론트/분석에 필요한 필드만 남김 (캐시 용량 절약)"""
    return {
        "id": item.get("bizesId"),
        "name": (item.get("bizesNm") or "").strip(),
        "branch": (item.get("brchNm") or "").strip(),
        "indsSclsCd": item.get("indsSclsCd"),
        "indsSclsNm": (item.get("indsSclsNm") or "").strip(),
        "indsMclsNm": (item.get("indsMclsNm") or "").strip(),
        "indsLclsNm": (item.get("indsLclsNm") or "").strip(),
        "floor": (item.get("flrNo") or "").strip(),
        "address": item.get("rdnmAdr") or item.get("lnoAdr") or "",
        "lat": item.get("lat"),
        "lng": item.get("lon"),
    }


def _read_disk(code: str) -> dict | None:
    f = CACHE_DIR / f"{code}.json"
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        return data if time.time() - data["saved_at"] < CACHE_TTL_SECONDS else None
    except (OSError, ValueError, KeyError):
        return None


def _write_disk(code: str, data: dict) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        (CACHE_DIR / f"{code}.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass  # 캐시 저장 실패는 무시 (다음 요청에서 다시 조회)


async def get_area_stores(code: str) -> dict | None:
    """상권 안 모든 점포 {stdr_ym, stores:[...]} 또는 상권이 없으면 None. 상권 단위로 캐시"""
    area = _area(code)
    if area is None:
        return None
    hit = _memory.get(code)
    if hit and time.time() - hit[0] < CACHE_TTL_SECONDS:
        return hit[1]

    async with _locks.setdefault(code, asyncio.Lock()):  # 같은 상권을 동시에 여러 번 부르지 않게
        hit = _memory.get(code)
        if hit and time.time() - hit[0] < CACHE_TTL_SECONDS:
            return hit[1]
        data = _read_disk(code)
        if data is None:
            feature, geom = area
            p = feature["properties"]
            items, stdr_ym = await fetch_stores_in_radius(p["center_lat"], p["center_lng"], _radius_m(feature, geom))
            stores = [
                _slim(i) for i in items
                if i.get("lat") is not None and i.get("lon") is not None and geom.contains(Point(i["lon"], i["lat"]))
            ]
            data = {"saved_at": time.time(), "stdr_ym": stdr_ym, "stores": stores}
            _write_disk(code, data)
        _memory[code] = (data["saved_at"], data)
        return data


async def _brands() -> dict[str, str]:
    """정규화한 브랜드명 -> 원래 이름"""
    global _brand_index
    if _brand_index is None:
        brands = await load_brands()
        _brand_index = {}
        for b in brands:
            n = _norm(b["name"])
            if len(n) >= 2:
                _brand_index.setdefault(n, b["name"])
    return _brand_index


def _match_brand(store: dict, index: dict[str, str]) -> str | None:
    name = _norm(store["name"])
    if len(name) < 2 or name == _norm(store["indsSclsNm"]):  # '카페' 같은 일반 명칭은 브랜드로 보지 않음
        return None
    for end in range(len(name), 1, -1):  # 긴 이름부터
        brand = name[:end]
        if brand in index:
            rest = name[end:]
            if end >= 3 or rest == "" or (rest.endswith("점") and len(rest) <= 8):
                return index[brand]
    return None


def _to_view(s: dict, brand: str | None, my_brand_norm: str) -> dict:
    return {
        "id": s["id"],
        "name": s["name"],
        "branch": s["branch"],
        "category": s["indsSclsNm"],
        "floor": s["floor"],
        "address": s["address"],
        "lat": s["lat"],
        "lng": s["lng"],
        "is_franchise": brand is not None,
        "brand": brand,
        "is_my_brand": bool(brand and my_brand_norm and _norm(brand) == my_brand_norm),
    }


async def classify_stores(stores: list[dict], industry_code: str, my_brand: str | None) -> dict:
    """같은 업종 점포를 일반 / 프랜차이즈로 나눈다"""
    index = await _brands()
    my_norm = _norm(my_brand or "")
    independent, franchise = [], []
    for s in stores:
        if not is_same_industry(s, industry_code):
            continue
        brand = _match_brand(s, index)
        (franchise if brand else independent).append(_to_view(s, brand, my_norm))
    return {"same_industry_stores": independent, "franchise_stores": franchise}
