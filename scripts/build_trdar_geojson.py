"""
서울시 상권분석서비스(영역-상권) shapefile -> GeoJSON 변환 스크립트

원본: 서울 열린데이터광장 OA-15560 (.shp .shx .dbf .prj .cpg)
결과: src/app/data/geo/seoul_trdar.geojson  (WGS84 위경도, 경계선 단순화)

처리 내용
  1. .prj 의 좌표계(Korea 2000 중부원점 TM, 단위 m)를 WGS84(EPSG:4326)로 변환
  2. 미터 단위인 TM 좌표에서 경계선을 단순화 (기본 3m, 위상 유지)
  3. 소수점 6자리(약 0.1m)로 반올림, RFC 7946 방향(바깥 반시계)으로 정렬
  4. 속성 이름을 영문 snake_case 로 정리

실행 (서버 환경에는 필요 없고, 이 스크립트를 다시 돌릴 때만 아래 패키지가 필요)
  pip install pyshp pyproj shapely
  python scripts/build_trdar_geojson.py [shapefile 경로(확장자 제외)] [단순화 허용오차(m)]
"""

import json
import sys
from pathlib import Path

import numpy as np
import shapefile
import shapely
from pyproj import CRS, Transformer
from shapely.geometry import mapping, shape
from shapely.geometry.polygon import orient

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SRC = ROOT / "서울시 상권분석서비스(영역-상권)"
OUT_PATH = ROOT / "src" / "app" / "data" / "geo" / "seoul_trdar.geojson"
DEFAULT_TOLERANCE_M = 3.0
COORD_DIGITS = 6

# shapefile 속성(dbf) -> GeoJSON 속성
FIELD_MAP = {
    "TRDAR_CD": "code",
    "TRDAR_CD_N": "name",
    "TRDAR_SE_C": "type_code",
    "TRDAR_SE_1": "type_name",
    "SIGNGU_CD": "gu_code",
    "SIGNGU_CD_": "gu",
    "ADSTRD_CD": "dong_code",
    "ADSTRD_CD_": "dong",
    "RELM_AR": "area_m2",
}


def _round_coords(geom_dict: dict) -> dict:
    def walk(c):
        if isinstance(c[0], (int, float)):
            return [round(v, COORD_DIGITS) for v in c]
        return [walk(x) for x in c]

    return {"type": geom_dict["type"], "coordinates": walk(geom_dict["coordinates"])}


def build(src: Path, tolerance_m: float) -> dict:
    reader = shapefile.Reader(str(src), encoding="utf-8")
    src_crs = CRS.from_wkt(Path(f"{src}.prj").read_text(encoding="utf-8"))
    to_wgs84 = Transformer.from_crs(src_crs, CRS.from_epsg(4326), always_xy=True).transform

    features = []
    for sr in reader.iterShapeRecords():
        rec = sr.record.as_dict()
        geom = shape(sr.shape.__geo_interface__)
        if not geom.is_valid:
            geom = geom.buffer(0)  # 자기교차 등 깨진 도형 복구
        geom = geom.simplify(tolerance_m, preserve_topology=True)
        geom = shapely.transform(geom, lambda c: np.column_stack(to_wgs84(c[:, 0], c[:, 1])))
        # 소수점 반올림을 도형 유효성을 유지하는 방식으로 (단순 반올림은 좁은 구간에서 선이 꼬일 수 있음)
        geom = shapely.set_precision(geom, 10 ** -COORD_DIGITS)
        if geom.geom_type == "Polygon":
            geom = orient(geom, sign=1.0)
        else:
            geom = type(geom)([orient(p, sign=1.0) for p in geom.geoms])

        props = {out: rec[k] for k, out in FIELD_MAP.items()}
        for key in ("code", "gu_code", "dong_code"):
            props[key] = str(props[key]).strip()
        # 상권 중심점도 위경도로
        lng, lat = to_wgs84(rec["XCNTS_VALU"], rec["YDNTS_VALU"])
        props["center_lng"] = round(lng, COORD_DIGITS)
        props["center_lat"] = round(lat, COORD_DIGITS)

        features.append({
            "type": "Feature",
            "properties": props,
            "geometry": _round_coords(mapping(geom)),
        })

    return {"type": "FeatureCollection", "features": features}


def main() -> None:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SRC
    tolerance = float(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_TOLERANCE_M

    collection = build(src, tolerance)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps(collection, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    size_kb = OUT_PATH.stat().st_size / 1024
    print(f"{len(collection['features'])}개 상권 -> {OUT_PATH} ({size_kb:,.0f}KB, 허용오차 {tolerance}m)")


if __name__ == "__main__":
    main()
