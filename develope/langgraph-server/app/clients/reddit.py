"""Reddit(praw) 기반 게임 반응(취재자료) 수집.

praw.Reddit 인스턴스는 내부적으로 requests.Session을 감싸고 있어 스레드-세이프하지
않다. asyncio.to_thread로 여러 스레드에서 동시에 호출하므로, 스레드별 인스턴스를
두기 위해 threading.local을 쓴다. REDDIT_SEM이 동시 실행 스레드 수를 제한하므로
실제로 만들어지는 인스턴스 수도 그만큼으로 제한된다.

REDDIT_CLIENT_ID/SECRET이 없으면 조용히 None을 돌려준다 — main.py의 기존
`openai_client is None` degrade 패턴과 동일한 사상. 이 함수는 어떤 예외도 밖으로
내보내지 않는다: 하나의 게임에서 Reddit 조회가 실패해도 그래프 전체 실행이
죽으면 안 되기 때문.
"""
import asyncio
import logging
import threading

import praw

from ..config import REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_SEM, REDDIT_USER_AGENT
from ..state import RedditBuzz

logger = logging.getLogger(__name__)

_SUBREDDITS = "Games+gaming+pcgaming+patientgamers+ShouldIbuythisgame"
_MAX_COMMENT_CHARS = 300
_MAX_SUBMISSIONS = 5
_MAX_COMMENTS = 5

_thread_local = threading.local()


def _get_thread_client() -> "praw.Reddit | None":
    if not REDDIT_CLIENT_ID or not REDDIT_CLIENT_SECRET:
        return None
    client = getattr(_thread_local, "reddit", None)
    if client is None:
        client = praw.Reddit(
            client_id=REDDIT_CLIENT_ID,
            client_secret=REDDIT_CLIENT_SECRET,
            user_agent=REDDIT_USER_AGENT,
        )
        _thread_local.reddit = client
    return client


def _fetch_sync(name: str) -> RedditBuzz | None:
    reddit = _get_thread_client()
    if reddit is None:
        return None

    try:
        subreddit = reddit.subreddit(_SUBREDDITS)
        submissions = list(
            subreddit.search(f'"{name}"', sort="top", time_filter="year", limit=_MAX_SUBMISSIONS)
        )
        if not submissions:
            return None

        titles = [s.title for s in submissions]
        comments: list[str] = []
        top = submissions[0]
        top.comments.replace_more(limit=0)
        for comment in top.comments[:_MAX_COMMENTS]:
            body = getattr(comment, "body", "")
            if body:
                comments.append(body[:_MAX_COMMENT_CHARS])
        return {"titles": titles, "comments": comments}
    except Exception as exc:  # noqa: BLE001 - reddit 실패가 그래프를 죽이면 안 됨
        logger.warning("reddit 조회 실패 name=%s: %s", name, exc)
        return None


async def fetch_buzz(name: str) -> RedditBuzz | None:
    if not REDDIT_CLIENT_ID or not REDDIT_CLIENT_SECRET:
        return None
    async with REDDIT_SEM:
        return await asyncio.to_thread(_fetch_sync, name)
