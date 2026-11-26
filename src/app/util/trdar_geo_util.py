"""
상권 폴리곤(GeoJSON) 조회

파일: app/data/geo/seoul_trdar.geojson
      (scripts/build_trdar_geojson.py 로 서울시 상권분석서비스 shapefile 을 변환한 것)

서버가 켜진 뒤 처음 쓸 때 한 번만 읽어서 메모리에 올려 둔다. (1.5MB, 상권 1,650개)
파일을 새로 만들었다면 서버를 재시작해야 반영된다.

좌표 순서 주의: GeoJSON 은 [경도(lng), 위도(lat)] 순서다.
"""

import json
import math
from functools import lru_cache
from pathlib import Path

from shapely import STRtree
from shapely.geometry import Point, shape
from shapely.ops import nearest_points

GEOJSON_PATH = Path(__file__).resolve().parents[1] / "data" / "geo" / "seoul_trdar.geojson"

METERS_PER_DEG_LAT = 111_000  # 위도 1도 ≈ 111km


@lru_cache(maxsize=1)
def _load() -> tuple[list[dict], list, STRtree, dict[str, int]] | None:
    """(features, shapely 도형들, 공간 인덱스, 상권코드→순번). 파일이 없으면 None"""
    if not GEOJSON_PATH.exists():
        return None
    features = json.loads(GEOJSON_PATH.read_text(encoding="utf-8"))["features"]
    geoms = [shape(f["geometry"]) for f in features]
    by_code = {f["properties"]["code"]: i for i, f in enumerate(features)}
    return features, geoms, STRtree(geoms), by_code


def is_geo_data_loaded() -> bool:
    return _load() is not None


def _to_kakao_polygons(geometry: dict) -> list[list[list[dict]]]:
    """
    GeoJSON 도형 -> 카카오지도용 좌표.  [폴리곤][고리][점{lat, lng}] 3단 구조

    - 고리(ring): 첫 번째가 바깥 경계, 두 번째부터는 구멍
    - Polygon 이면 폴리곤 1개, MultiPolygon 이면 조각 수만큼
    - GeoJSON 의 [경도, 위도] 를 {lat: 위도, lng: 경도} 로 이름을 붙여 순서 실수를 막는다
    """
    polygons = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
    return [[[{"lat": lat, "lng": lng} for lng, lat in ring] for ring in polygon] for polygon in polygons]


def _to_item(feature: dict, distance_m: float) -> dict:
    p = feature["properties"]
    return {
        "code": p["code"],
        "name": p["name"],
        "type_name": p["type_name"],
        "gu": p["gu"],
        "dong": p["dong"],
        "area_m2": p["area_m2"],
        "center_lat": p["center_lat"],
        "center_lng": p["center_lng"],
        "distance_m": round(distance_m),
        "geometry": feature["geometry"],  # 표준 GeoJSON (Polygon 또는 MultiPolygon), [경도, 위도]
        "kakao_polygons": _to_kakao_polygons(feature["geometry"]),  # 카카오지도에 바로 쓰는 좌표
    }


def find_trdar_by_point(lat: float, lng: float, nearby_m: int = 300) -> dict:
    """
    좌표가 속한 상권을 찾는다.

    - 어떤 상권 안에 있으면  matched="inside"  (겹치는 상권이 여럿이면 작은 상권부터)
    - 안에 없으면 nearby_m 미터 이내의 가까운 상권을  matched="nearby"  (가까운 순)
    - 그것도 없으면  matched="none"
    """
    data = _load()
    if data is None:
        raise FileNotFoundError(str(GEOJSON_PATH))
    features, geoms, tree, _ = data
    point = Point(lng, lat)

    inside = [int(i) for i in tree.query(point, predicate="intersects")]
    if inside:
        inside.sort(key=lambda i: features[i]["properties"]["area_m2"])
        return {"matched": "inside", "items": [_to_item(features[i], 0) for i in inside]}

    # 위경도(도) 기준 검색 반경: 경도 1도가 위도 1도보다 짧으므로 넉넉하게 잡고, 아래에서 미터로 다시 거른다
    meters_per_deg_lng = METERS_PER_DEG_LAT * math.cos(math.radians(lat))
    search_deg = nearby_m / meters_per_deg_lng
    near = []
    for i in tree.query(point.buffer(search_deg)):
        i = int(i)
        on_edge, _ = nearest_points(geoms[i], point)
        dx = (on_edge.x - lng) * meters_per_deg_lng
        dy = (on_edge.y - lat) * METERS_PER_DEG_LAT
        dist = math.hypot(dx, dy)
        if dist <= nearby_m:
            near.append((dist, i))
    near.sort()
    if near:
        return {"matched": "nearby", "items": [_to_item(features[i], d) for d, i in near]}
    return {"matched": "none", "items": []}


def get_trdar_center(code: str) -> tuple[float, float] | None:
    """상권 중심 좌표 (위도, 경도). 폴리곤 파일이 없거나 없는 코드면 None (오류를 내지 않는다)"""
    data = _load()
    if data is None:
        return None
    features, _, _, by_code = data
    idx = by_code.get(code)
    if idx is None:
        return None
    p = features[idx]["properties"]
    return p["center_lat"], p["center_lng"]


def get_trdar_polygon(code: str) -> dict | None:
    data = _load()
    if data is None:
        raise FileNotFoundError(str(GEOJSON_PATH))
    features, _, _, by_code = data
    idx = by_code.get(code)
    return None if idx is None else _to_item(features[idx], 0)
