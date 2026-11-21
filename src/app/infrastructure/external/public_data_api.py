"""
지원사업 공고 수집기

세 API 에서 '접수 중' 공고를 받아 Announcement 테이블 형태(dict)로 바꿔 돌려준다.
DB 저장은 하지 않음 → AnnouncementRepository.upsert_announcements 에서 처리.

  출처       API                                         형식   비고
  kstartup  K-Startup 사업공고                           JSON   조건 필드(대상·업력·나이·지역) 있음
  mss       중소벤처기업부 사업공고                       XML    조건 필드 없음, 최신순
  bizinfo   기업마당 지원사업공고 (중기부·지자체 통합)     JSON   분야·대상·해시태그(지역) 있음
"""

import logging
import xml.etree.ElementTree as ET
from datetime import date
from typing import Any

import httpx

from app.util.support_util import (
    clip,
    parse_date,
    parse_period,
    split_csv,
    strip_html,
    to_regions,
)
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[4] / ".env")  # backapp/.env

# 공공데이터포털 인증키 (Decoding 키) — K-Startup / 중기부 / 기업마당 공용
DATA_GO_KR_API_KEY = os.getenv("DATA_GO_KR_API_KEY", "")

log = logging.getLogger(__name__)
# httpx 는 INFO 레벨에서 요청 URL 을 찍는데, URL 에 인증키(serviceKey)가 들어 있으므로 숨김
logging.getLogger("httpx").setLevel(logging.WARNING)

KSTARTUP_URL = "https://apis.data.go.kr/B552735/kisedKstartupService01/getAnnouncementInformation01"
MSS_URL = "https://apis.data.go.kr/1421000/mssBizService_v2/getbizList_v2"
BIZINFO_URL = "https://apis.data.go.kr/1421000/bizinfo/pblancBsnsService"

Row = dict[str, Any]


class CollectError(Exception):
    """API 가 오류 응답을 준 경우"""


def _row(**fields: Any) -> Row:
    """Announcement 컬럼 기본값을 채운 dict (빠진 키가 없도록)"""
    base: Row = {
        "summary": None, "organization": None, "category": None,
        "targets": [], "career": [], "ages": [], "regions": [],
        "start_date": None, "end_date": None, "period_text": None,
        "detail_url": None, "apply_url": None, "contact": None,
    }
    base.update(fields)
    # 컬럼 길이 제한
    base["title"] = clip(base["title"], 500) or "(제목 없음)"
    base["organization"] = clip(base["organization"], 200)
    base["category"] = clip(base["category"], 100)
    base["period_text"] = clip(base["period_text"], 200)
    base["detail_url"] = clip(base["detail_url"], 1000)
    base["apply_url"] = clip(base["apply_url"], 1000)
    base["contact"] = clip(base["contact"], 500)
    return base


def _is_ended(row: Row, today: date) -> bool:
    return row["end_date"] is not None and row["end_date"] < today


def _with_scheme(url: str | None) -> str | None:
    """'www.example.com' 처럼 http 가 빠진 주소 보정"""
    if not url:
        return None
    url = url.strip()
    if url.startswith(("http://", "https://")):
        return url
    if url.startswith("ttps://"):  # 실제 응답에 있는 오타
        return "h" + url
    return "https://" + url


# ---------------------------------------------------------------------------
# K-Startup
# ---------------------------------------------------------------------------
async def fetch_kstartup(client: httpx.AsyncClient) -> list[Row]:
    """모집 진행 중(rcrt_prgs_yn=Y) 공고 전체"""
    items: list[dict] = []
    page = 1
    while True:
        res = await client.get(KSTARTUP_URL, params={
            "serviceKey": DATA_GO_KR_API_KEY,
            "page": page, "perPage": 100, "returnType": "json",
            "cond[rcrt_prgs_yn::EQ]": "Y",
        })
        data = _json_or_raise(res, "kstartup")
        batch = data.get("data") or []
        items.extend(batch)
        if not batch or len(items) >= data.get("matchCount", 0):
            break
        page += 1

    today = date.today()
    rows = [_normalize_kstartup(i) for i in items]
    return [r for r in rows if not _is_ended(r, today)]


def _normalize_kstartup(i: dict) -> Row:
    apply_url = i.get("biz_aply_url") or i.get("aply_mthd_onli_rcpt_istc")
    return _row(
        source="kstartup",
        source_id=str(i["pbanc_sn"]),
        title=i.get("biz_pbanc_nm") or i.get("intg_pbanc_biz_nm"),
        summary=strip_html(i.get("pbanc_ctnt")),
        organization=i.get("pbanc_ntrp_nm"),
        category=i.get("supt_biz_clsfc"),
        targets=split_csv(i.get("aply_trgt")),
        career=split_csv(i.get("biz_enyy")),
        ages=split_csv(i.get("biz_trgt_age")),
        regions=to_regions(i.get("supt_regin")),
        start_date=parse_date(i.get("pbanc_rcpt_bgng_dt")),
        end_date=parse_date(i.get("pbanc_rcpt_end_dt")),
        detail_url=i.get("detl_pg_url"),
        apply_url=_with_scheme(apply_url) if apply_url and "." in apply_url else None,
        contact=" / ".join(filter(None, [i.get("biz_prch_dprt_nm"), i.get("prch_cnpl_no")])) or None,
        raw=i,
    )


# ---------------------------------------------------------------------------
# 중소벤처기업부
# ---------------------------------------------------------------------------
async def fetch_mss(client: httpx.AsyncClient, max_pages: int = 30) -> list[Row]:
    """
    최신순으로 받다가, 한 페이지의 마감일 있는 공고가 전부 마감이면 중단.
    접수 기간이 없는 글(결과 발표·안내 등)은 매칭 대상이 아니므로 제외.
    """
    today = date.today()
    rows: list[Row] = []
    for page in range(1, max_pages + 1):
        res = await client.get(MSS_URL, params={
            "serviceKey": DATA_GO_KR_API_KEY,
            "pageNo": page, "numOfRows": 100,
        })
        items = _xml_items_or_raise(res, "mss")
        if not items:
            break
        page_rows = [_normalize_mss(i) for i in items]
        dated = [r for r in page_rows if r["end_date"]]
        rows.extend(r for r in dated if not _is_ended(r, today))
        if dated and all(_is_ended(r, today) for r in dated):
            break
    return rows


def _normalize_mss(item: ET.Element) -> Row:
    raw: dict[str, Any] = {}
    files: list[dict] = []
    for child in item:
        if child.tag == "fileName":
            files.append({"name": (child.text or "").strip()})
        elif child.tag == "fileUrl" and files:
            files[-1]["url"] = (child.text or "").strip()
        else:
            raw[child.tag] = (child.text or "").strip()
    raw["files"] = files

    contact = " / ".join(filter(None, [raw.get("writerPosition"), raw.get("writerName"), raw.get("writerPhone")]))
    return _row(
        source="mss",
        source_id=raw["itemId"],
        title=raw.get("title"),
        summary=strip_html(raw.get("dataContents")),
        organization="중소벤처기업부",
        start_date=parse_date(raw.get("applicationStartDate")),
        end_date=parse_date(raw.get("applicationEndDate")),
        detail_url=raw.get("viewUrl"),
        contact=contact or None,
        raw=raw,
    )


# ---------------------------------------------------------------------------
# 기업마당
# ---------------------------------------------------------------------------
async def fetch_bizinfo(client: httpx.AsyncClient) -> list[Row]:
    """게시 중인 지원사업 공고 전체"""
    items: list[dict] = []
    page = 1
    while True:
        res = await client.get(BIZINFO_URL, params={
            "serviceKey": DATA_GO_KR_API_KEY,
            "dataType": "json", "pageNo": page, "numOfRows": 500,
        })
        body = _json_or_raise(res, "bizinfo")["response"]["body"]
        batch = (body.get("items") or {}).get("item") or []
        if isinstance(batch, dict):  # 1건이면 리스트가 아닐 수 있음
            batch = [batch]
        items.extend(batch)
        if not batch or len(items) >= int(body.get("totalCount", 0)):
            break
        page += 1

    today = date.today()
    rows = [_normalize_bizinfo(i) for i in items]
    return [r for r in rows if not _is_ended(r, today)]


def _normalize_bizinfo(i: dict) -> Row:
    period = i.get("reqstBeginEndDe")
    start, end = parse_period(period)
    title = i.get("pblancNm")
    return _row(
        source="bizinfo",
        source_id=i["pblancId"],
        title=title,
        summary=strip_html(i.get("bsnsSumryCn")),
        organization=i.get("jrsdInsttNm"),
        category=i.get("pldirSportRealmLclasCodeNm"),
        targets=split_csv(i.get("trgetNm")),
        # 지역: 해시태그 + 소관기관(경상북도 등) + 공고명 앞 [경북]
        # 중앙부처 공고처럼 지역이 안 잡히면 전국으로 본다
        regions=to_regions(i.get("hashtags"), i.get("jrsdInsttNm"), (title or "")[:10]) or ["전국"],
        start_date=start,
        end_date=end,
        period_text=None if end else period,
        detail_url=i.get("pblancUrl"),
        apply_url=i.get("rceptEngnHmpgUrl"),
        contact=i.get("refrncNm"),
        raw=i,
    )


# ---------------------------------------------------------------------------
# 공통: 응답 검사
# ---------------------------------------------------------------------------
def _json_or_raise(res: httpx.Response, name: str) -> dict:
    res.encoding = "utf-8"
    if res.status_code != 200:
        raise CollectError(f"[{name}] HTTP {res.status_code}: {res.text[:300]}")
    try:
        data = res.json()
    except ValueError:
        # 인증키 오류 등은 200 + XML 로 오는 경우가 있음
        raise CollectError(f"[{name}] JSON 아님: {res.text[:300]}") from None
    header = (data.get("response") or {}).get("header")
    if header and header.get("resultCode") not in ("00", "03"):  # 03 = 데이터 없음
        raise CollectError(f"[{name}] API 오류 {header}")
    return data


def _xml_items_or_raise(res: httpx.Response, name: str) -> list[ET.Element]:
    if res.status_code != 200:
        raise CollectError(f"[{name}] HTTP {res.status_code}: {res.text[:300]}")
    try:
        root = ET.fromstring(res.content)
    except ET.ParseError:
        raise CollectError(f"[{name}] XML 파싱 실패: {res.text[:300]}") from None
    code = root.findtext("header/resultCode")
    if code not in ("00", "03"):
        raise CollectError(f"[{name}] API 오류: {res.text[:300]}")
    return root.findall("body/items/item")


# ---------------------------------------------------------------------------
# 전체 수집
# ---------------------------------------------------------------------------
COLLECTORS = {
    "kstartup": fetch_kstartup,
    "mss": fetch_mss,
    "bizinfo": fetch_bizinfo,
}


async def collect_all(sources: list[str] | None = None) -> dict[str, list[Row]]:
    """
    출처별로 수집. 한 곳이 실패해도 나머지는 계속한다.
    반환: {"kstartup": [...], "mss": [...], "bizinfo": [...]}  (실패한 출처는 빠짐)
    """
    if not DATA_GO_KR_API_KEY:
        raise CollectError("DATA_GO_KR_API_KEY 가 backapp/.env 에 없습니다.")

    results: dict[str, list[Row]] = {}
    async with httpx.AsyncClient(timeout=60) as client:
        for name in sources or list(COLLECTORS):
            try:
                results[name] = await COLLECTORS[name](client)
                log.info("[%s] %d건 수집", name, len(results[name]))
            except (CollectError, httpx.HTTPError) as e:
                log.error("[%s] 수집 실패: %s", name, e)
    return results
