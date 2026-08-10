"""편집국장: 요청 payload(3개 카테고리 리스트)를 정규화해서 각 게임에 category/
order_index를 부여하고, 3개 데스크로 fan-out한다. LLM 호출 없음.
"""
import time

from langgraph.types import Send

from ..state import Category, GameRef, ReportState

_DESK_NAMES: dict[Category, str] = {
    "old_introductions": "옛 작품 데스크",
    "recent_replays": "다시 추천 데스크",
    "recent_new": "신규 추천 데스크",
}


def _to_game_refs(raw_games: list[dict], category: Category) -> list[GameRef]:
    refs: list[GameRef] = []
    for idx, game in enumerate(raw_games):
        refs.append(
            {
                "appid": game["appid"],
                "name": game["name"],
                "developer": game.get("developer"),
                "publisher": game.get("publisher"),
                "ccu": game.get("ccu"),
                "positive": game.get("positive"),
                "negative": game.get("negative"),
                "category": category,
                "order_index": idx,
            }
        )
    return refs


async def editor_in_chief(state: ReportState) -> dict:
    old_refs = _to_game_refs(state.get("old_introductions") or [], "old_introductions")
    replay_refs = _to_game_refs(state.get("recent_replays") or [], "recent_replays")
    new_refs = _to_game_refs(state.get("recent_new") or [], "recent_new")

    total = len(old_refs) + len(replay_refs) + len(new_refs)
    return {
        "old_introductions": old_refs,
        "recent_replays": replay_refs,
        "recent_new": new_refs,
        "started_at": time.monotonic(),
        "logs": [f"[editor_in_chief] 총 {total}개 게임 접수"],
    }


def dispatch_desks(state: ReportState) -> list[Send]:
    """편집국장 직후 실행되는 conditional edge. 카테고리별로 desk 노드를 Send."""
    sends: list[Send] = []
    for category, desk_name in _DESK_NAMES.items():
        games = state.get(category) or []
        if not games:
            continue
        sends.append(
            Send(
                "desk",
                {
                    "desk_name": desk_name,
                    "category": category,
                    "games": games,
                    "report_date": state["report_date"],
                    "started_at": state["started_at"],
                },
            )
        )
    return sends
