"""기자: 취재(Steam/Reddit/RAG 동시 조회) + 초고 작성(LLM 1회).

절대 예외를 밖으로 던지지 않는다 — 게임 하나의 취재/작성이 실패해도 나머지 14개와
그래프 전체 실행은 계속되어야 한다. 실패 시 기존 main.py와 동일한 placeholder
문구로 대체한다.

교열부(copy_editor)가 초고를 반려하면 이 노드가 재작성 모드(is_revision=True)로
다시 호출된다. 이때는 Steam/Reddit/RAG를 재취재하지 않고(payload["research"]에
이미 있는 자료를 재사용) 반려 사유 + 이전 초고를 반영해서 다시 쓴다. 완성되면
공유 barrier(copy_desk)를 거치지 않고 Command로 곧장 copy_editor 한 명에게만
돌아간다 — barrier로 다시 보내면 이미 끝난 다른 게임들까지 재실행돼버리기
때문(자세한 이유는 graph.py/copy_desk.py 주석 참고).
"""
import asyncio
import logging
import time
from typing import Literal

from langgraph.types import Command, Send

from .. import prompts
from ..clients import db, llm, rag, reddit, steam_store
from ..config import REPORTER_MODEL
from ..state import Draft, ReporterState, Research

logger = logging.getLogger(__name__)


async def reporter(payload: ReporterState) -> dict | Command[Literal["copy_editor"]]:
    game = payload["game"]
    t_start = time.monotonic() - payload["started_at"]
    is_revision = payload.get("is_revision", False)
    retry_count = payload.get("retry_count", 0)

    reused_research = payload.get("research") if is_revision else None
    if reused_research is not None:
        steam_detail = reused_research.get("steam")
        reddit_buzz = reused_research.get("reddit")
        past_writeups = reused_research.get("past_writeups") or []
        research: Research = reused_research
    else:
        steam_detail, reddit_buzz, past_writeups = await asyncio.gather(
            steam_store.fetch_appdetails_kr(game["appid"]),
            reddit.fetch_buzz(game["name"]),
            asyncio.to_thread(db.lookup_past_writeups, game["appid"]),
        )
        # 장르는 steam_detail에서 나오므로(위 gather 완료 후에만 앎) 뉴스 검색은
        # 따로 이어서 한다 - 게임 이름만으로 검색하는 것보다 장르까지 있으면
        # 관련 기사가 더 잘 걸린다.
        genres = (steam_detail or {}).get("genres") or []
        news_query = " ".join([game["name"], *genres])
        news_refs = await rag.search_relevant_articles(news_query)
        research = {
            "steam": steam_detail,
            "reddit": reddit_buzz,
            "past_writeups": past_writeups,
            "news_refs": news_refs,
        }

    if is_revision:
        prompt = prompts.reporter_revision_prompt(
            game,
            research,
            payload.get("previous_draft_text") or "",
            payload.get("revision_feedback") or "",
        )
        label = f"reporter-revision({game['appid']})"
    else:
        prompt = prompts.reporter_prompt(game, research)
        label = f"reporter({game['appid']})"

    draft_text = await llm.complete(prompt, model=REPORTER_MODEL, label=label)
    error = None
    if draft_text is None:
        draft_text = prompts.placeholder_description(game["name"])
        error = "llm_unavailable"

    draft: Draft = {
        "game": game,
        "research": research,
        "draft_text": draft_text,
        "error": error,
        "retry_count": retry_count,
        "started_at": payload["started_at"],
    }
    t_end = time.monotonic() - payload["started_at"]
    news_refs = research.get("news_refs") or []
    log_line = (
        f"[reporter{'(재작성)' if is_revision else ''}] appid={game['appid']} name={game['name']} "
        f"steam={'O' if steam_detail else 'X'} reddit={'O' if reddit_buzz else 'X'} "
        f"past={len(past_writeups)} news={len(news_refs)} t_start=+{t_start:.2f}s t_end=+{t_end:.2f}s"
    )

    if is_revision:
        # barrier(copy_desk)를 우회해서 이 게임 하나만 다시 교열로 보낸다.
        return Command(
            update={"drafts": [draft], "logs": [log_line]},
            goto=[Send("copy_editor", {"draft": draft})],
        )

    return {"drafts": [draft], "logs": [log_line]}
