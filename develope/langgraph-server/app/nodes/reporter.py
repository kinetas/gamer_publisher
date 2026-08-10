"""기자: 취재(Steam/Reddit/RAG 동시 조회) + 초고 작성(LLM 1회).

절대 예외를 밖으로 던지지 않는다 — 게임 하나의 취재/작성이 실패해도 나머지 14개와
그래프 전체 실행은 계속되어야 한다. 실패 시 기존 main.py와 동일한 placeholder
문구로 대체한다.
"""
import asyncio
import logging
import time

from .. import prompts
from ..clients import llm, rag, reddit, steam_store
from ..config import REPORTER_MODEL
from ..state import Draft, ReporterState, Research

logger = logging.getLogger(__name__)


async def reporter(payload: ReporterState) -> dict:
    game = payload["game"]
    t_start = time.monotonic() - payload["started_at"]

    steam_detail, reddit_buzz, past_writeups = await asyncio.gather(
        steam_store.fetch_appdetails_kr(game["appid"]),
        reddit.fetch_buzz(game["name"]),
        rag.lookup_by_appid(game["appid"]),
    )
    research: Research = {
        "steam": steam_detail,
        "reddit": reddit_buzz,
        "past_writeups": past_writeups,
    }

    prompt = prompts.reporter_prompt(game, research)
    draft_text = await llm.complete(prompt, model=REPORTER_MODEL, label=f"reporter({game['appid']})")
    error = None
    if draft_text is None:
        draft_text = prompts.placeholder_description(game["name"])
        error = "llm_unavailable"

    draft: Draft = {"game": game, "research": research, "draft_text": draft_text, "error": error}
    t_end = time.monotonic() - payload["started_at"]
    return {
        "drafts": [draft],
        "logs": [
            f"[reporter] appid={game['appid']} name={game['name']} "
            f"steam={'O' if steam_detail else 'X'} reddit={'O' if reddit_buzz else 'X'} "
            f"past={len(past_writeups)} t_start=+{t_start:.2f}s t_end=+{t_end:.2f}s"
        ],
    }
