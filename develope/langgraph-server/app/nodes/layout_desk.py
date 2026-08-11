"""편집부: 교열 완료된 15개 글을 카테고리별로 재정렬해 최종 content를 만들고,
(dry_run이 아니면) postgres에 저장한다.

LLM 호출 없음 — 프론트(GameEntry, ReportDocument.tsx 등)에 헤드라인/총평을
보여줄 자리가 없어서, 아무도 안 볼 텍스트를 LLM으로 쓰는 건 토큰 낭비라고 보고
순수 취합/영속화 역할로만 둔다.

drafts/checked는 병렬 브랜치가 operator.add로 모은 리스트라 도착 순서가
비결정적이다. 프론트는 카테고리당 고정 5칸 그리드라, 여기서 반드시
(category, order_index) 기준으로 재정렬한다.

예전엔 여기서 chromadb(weekly_writeups)에도 같은 글을 인덱싱해서 "같은 게임
과거 소개글 조회"에 썼는데, 그건 완전일치(appid) 질문이라 postgres 하나로
충분해서(reporter.py가 db.lookup_past_writeups로 weekly_reports.content를
직접 조회) 제거했다 — 저장은 여기 save_weekly_report 한 곳만 하면 된다.
chromadb는 이제 game_news_refs(게임메카 등 실제 근거자료) 컬렉션 전용이다.
"""
import asyncio
import logging
import time

from ..clients import db
from ..state import CheckedDraft, ReportState

logger = logging.getLogger(__name__)

_CATEGORIES = ("old_introductions", "recent_replays", "recent_new")


def _game_dict(checked_item: CheckedDraft) -> dict:
    game = checked_item["game"]
    return {
        "appid": game["appid"],
        "name": game["name"],
        "developer": game.get("developer") or "",
        "publisher": game.get("publisher") or game.get("developer") or "",
        "positive": game.get("positive") or 0,
        "negative": game.get("negative") or 0,
        "ccu": game.get("ccu") or 0,
        "description": checked_item["final_text"],
        "image": checked_item.get("image") or "",
    }


async def layout_desk(state: ReportState) -> dict:
    checked = state.get("checked") or []
    by_category: dict[str, list[CheckedDraft]] = {c: [] for c in _CATEGORIES}
    for item in checked:
        by_category.setdefault(item["game"]["category"], []).append(item)
    for items in by_category.values():
        items.sort(key=lambda item: item["game"]["order_index"])

    content: dict = {
        category: [_game_dict(item) for item in by_category[category]] for category in _CATEGORIES
    }

    # 논설위원실(총평)이 활성화되면 이 값이 채워진다. 지금은 그래프에 미등록이라
    # 항상 비어있고, fastapi-server의 _row_to_report는 알려진 3개 키만 읽으므로
    # 여분 키가 있어도 프론트는 영향받지 않는다.
    commentary = state.get("commentary")
    if commentary:
        content["commentary"] = commentary

    elapsed = time.monotonic() - state["started_at"]
    timings = {"total_seconds": round(elapsed, 2)}
    counts = {category: len(by_category[category]) for category in _CATEGORIES}
    logs = [f"[layout_desk] 취합 완료: {counts}, t=+{elapsed:.2f}s"]

    if state.get("dry_run"):
        logs.append("[layout_desk] dry_run=True, postgres 저장 스킵")
        return {"content": content, "timings": timings, "logs": logs}

    report_date = state["report_date"]
    await asyncio.to_thread(db.save_weekly_report, report_date, content)

    return {"content": content, "timings": timings, "logs": logs}
