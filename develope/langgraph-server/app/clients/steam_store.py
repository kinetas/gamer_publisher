"""Steam Store 공식 appdetails API (한국어). 공개 API라 키가 필요 없다.

한 번에 게임 하나만 상세 데이터를 돌려준다(여러 appid를 한 번에 넘기면 가격
정보만 옴) — 매주 선정된 15개에만 붙이므로 15번 호출로 충분하다. Steam이 기본
User-Agent를 차단한 이력이 있어(발신 요청 다수가 python-requests 기본 UA로
막힌 사례) 명시적으로 지정한다.
"""
import logging

import httpx

from ..config import STEAM_SEM
from ..state import SteamDetail
from ._retry import retry_async
from .http import get_http_client

logger = logging.getLogger(__name__)

STEAM_APPDETAILS_URL = "https://store.steampowered.com/api/appdetails"
_HEADERS = {"User-Agent": "gamer-publisher-report-bot/0.1 (+weekly game report)"}


async def fetch_appdetails_kr(appid: int) -> SteamDetail | None:
    """한국어 장르/짧은 설명을 가져온다. 실패하거나 success:false면 None."""

    async def _call() -> httpx.Response:
        client = get_http_client()
        response = await client.get(
            STEAM_APPDETAILS_URL,
            params={"appids": appid, "l": "korean", "cc": "kr"},
            headers=_HEADERS,
        )
        response.raise_for_status()
        return response

    try:
        async with STEAM_SEM:
            response = await retry_async(_call, label=f"steam_appdetails({appid})")
    except Exception as exc:  # noqa: BLE001 - steam 실패가 그래프를 죽이면 안 됨
        logger.warning("steam appdetails 실패 appid=%s: %s", appid, exc)
        return None

    payload = response.json().get(str(appid))
    if not payload or not payload.get("success"):
        return None

    data = payload.get("data") or {}
    genres = [g.get("description", "") for g in data.get("genres", []) if g.get("description")]

    detail: SteamDetail = {}
    if data.get("short_description"):
        detail["short_description"] = data["short_description"]
    if genres:
        detail["genres"] = genres
    release = data.get("release_date") or {}
    if release.get("date"):
        detail["release_date"] = release["date"]
    if "is_free" in data:
        detail["is_free"] = bool(data["is_free"])

    return detail or None
