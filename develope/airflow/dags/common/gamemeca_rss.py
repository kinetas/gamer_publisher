"""게임메카(gamemeca.com) 뉴스 RSS를 Postgres 저장용으로 파싱하는 독립 모듈.

develope/langgraph-server/app/clients/gamemeca.py 와는 별개의 독립 구현이다.
그 파일은 ChromaDB(RAG) 색인용으로 langgraph-server(FastAPI, httpx 비동기)
안에서만 쓰이고, 이 레포 규칙상 develope/langgraph-server/** 는 절대
import/수정하면 안 된다. 여기서는 Airflow(동기 실행) 환경에 맞춰 requests +
xml.etree.ElementTree로 RSS를 처음부터 다시 파싱해서, 프론트 RSS 뉴스
섹션에 노출할 구조화 데이터(game_news 테이블)를 만드는 데 쓴다.

파싱 스타일은 langgraph-server 쪽 구현을 참고했다 (개별 기사 페이지를
스크레이핑하지 않고 RSS description 필드를 그대로 저장 - description에
이미 리드 문단이 담겨 있어 전문 스크레이핑이 필요 없고, 법적으로도 짧은
요약 + 원문 링크만 저장하는 편이 안전하다).

robots.txt는 일반 크롤링을 허용하되 Crawl-delay: 30을 명시한다. 하지만
이 함수는 "기사 하나하나 순회"가 아니라 RSS 피드 자체를 한 번만 요청하는
것이므로 요청 사이 sleep이 필요 없다 (gamemeca_ingest_pipeline.py의
ingest_gamemeca_news/langgraph-server 쪽과 동일한 이해).
"""
import logging
import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

import requests

logger = logging.getLogger(__name__)

RSS_URL = "https://www.gamemeca.com/rss.php"
_HEADERS = {"User-Agent": "gamer-publisher-airflow-bot/0.1 (+news ingest)"}
_REQUEST_TIMEOUT = 30

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _clean_text(html: str) -> str:
    text = _TAG_RE.sub(" ", html)
    return _WS_RE.sub(" ", text).strip()


def _parse_pub_date(raw: str) -> datetime | None:
    """RSS pubDate(RFC 822, 예: "Wed, 19 Aug 2026 10:00:00 +0900")를
    timezone-aware datetime으로 변환한다. 형식이 안 맞으면 None
    (game_news.pub_date는 NULL 허용이라 파이프라인을 죽이지 않는다).
    """
    if not raw:
        return None
    try:
        return parsedate_to_datetime(raw)
    except (TypeError, ValueError) as exc:
        logger.warning("게임메카 pubDate 파싱 실패(%r): %s", raw, exc)
        return None


def _parse_item(item: ET.Element) -> dict | None:
    title = (item.findtext("title") or "").strip()
    link = (item.findtext("link") or item.findtext("guid") or "").strip()
    excerpt = _clean_text(item.findtext("description") or "")
    if not title or not link or not excerpt:
        # 셋 중 하나라도 없으면 프론트에 보여줄 만한 기사가 아니라고 보고 skip한다.
        return None

    image_el = item.find("image/url")
    if image_el is None or not (image_el.text or "").strip():
        image_el = item.find("image")
    image_url = (image_el.text or "").strip() if image_el is not None else ""

    return {
        "source": "gamemeca",
        "external_id": link,
        "title": title,
        "excerpt": excerpt,
        "link": link,
        "image_url": image_url or None,
        "pub_date": _parse_pub_date((item.findtext("pubDate") or "").strip()),
    }


def fetch_gamemeca_articles() -> list[dict]:
    """게임메카 RSS를 동기 requests로 가져와 파싱한다.

    네트워크 오류/XML 파싱 오류가 나도 이 함수는 예외를 올리지 않고 빈
    리스트를 반환한다 - 이 레포의 다른 soft-fail 패턴(ingest_gamemeca_news,
    notify_langgraph 등)과 동일하게, RSS 하나 실패했다고 파이프라인 전체를
    죽이지 않기 위함이다. 호출부(upsert_gamemeca_news)가 빈 리스트를
    "이번 주기엔 저장할 게 없다"로 취급해 upsert를 스킵한다.
    """
    try:
        response = requests.get(RSS_URL, headers=_HEADERS, timeout=_REQUEST_TIMEOUT)
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("게임메카 RSS 조회 실패: %s", exc)
        return []

    try:
        root = ET.fromstring(response.text)
    except ET.ParseError as exc:
        logger.warning("게임메카 RSS 파싱 실패: %s", exc)
        return []

    articles = [_parse_item(item) for item in root.iterfind("./channel/item")]
    return [a for a in articles if a is not None]
