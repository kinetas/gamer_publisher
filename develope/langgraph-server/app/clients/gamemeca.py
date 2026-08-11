"""게임메카(gamemeca.com) 뉴스 RSS 수집.

robots.txt가 일반 크롤링을 허용하고(Crawl-delay: 30, 이 피드 하나만 가끔
호출하는 우리 쓰임에는 문제 없음) 개별 기사 페이지를 안 들어가도 RSS
description 필드에 리드 문단(600~900자 정도, 기사 본문 전체가 아님)이 그대로
온다 — 그래서 개별 기사 스크레이핑이 아예 필요 없다.

법적으로 안전하게 쓰기 위해 이 짧은 요약 + 원문 링크만 저장한다(전문 무단
복제 금지). RAG에 넣을 때도 이 요약을 "참고자료"로만 쓰고, 실제 사용 시
reporter가 글 끝에 원문 링크를 달아 트래픽을 돌려준다.
"""
import logging
import re
import xml.etree.ElementTree as ET

from ._retry import retry_async
from .http import get_http_client

logger = logging.getLogger(__name__)

RSS_URL = "https://www.gamemeca.com/rss.php"
_HEADERS = {"User-Agent": "gamer-publisher-report-bot/0.1 (+weekly game report)"}

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _clean_text(html: str) -> str:
    text = _TAG_RE.sub(" ", html)
    return _WS_RE.sub(" ", text).strip()


def _parse_item(item: ET.Element) -> dict | None:
    title = (item.findtext("title") or "").strip()
    link = (item.findtext("link") or item.findtext("guid") or "").strip()
    description = _clean_text(item.findtext("description") or "")
    if not title or not link or not description:
        return None

    image_el = item.find("image/url")
    if image_el is None or not (image_el.text or "").strip():
        image_el = item.find("image")

    return {
        "id": link,
        "title": title,
        "excerpt": description,
        "link": link,
        "pub_date": (item.findtext("pubDate") or "").strip(),
        "image_url": (image_el.text or "").strip() if image_el is not None else "",
        "source": "gamemeca",
    }


async def fetch_latest_articles() -> list[dict]:
    """게임메카 RSS의 전체 기사 목록을 가져온다. 실패하면 []."""

    async def _call():
        client = get_http_client()
        response = await client.get(RSS_URL, headers=_HEADERS)
        response.raise_for_status()
        return response

    try:
        response = await retry_async(_call, label="gamemeca_rss")
    except Exception as exc:  # noqa: BLE001 - 수집 실패가 그래프/스케줄러를 죽이면 안 됨
        logger.warning("게임메카 RSS 조회 실패: %s", exc)
        return []

    try:
        root = ET.fromstring(response.text)
    except ET.ParseError as exc:
        logger.warning("게임메카 RSS 파싱 실패: %s", exc)
        return []

    articles = [_parse_item(item) for item in root.iterfind("./channel/item")]
    return [a for a in articles if a is not None]
