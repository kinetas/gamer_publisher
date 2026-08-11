import asyncio
import random
import sys

sys.path.insert(0, r"C:\Users\Administrator\GP\develope\langgraph-server")

from unittest.mock import AsyncMock, patch


async def jittery_complete(*args, **kwargs):
    await asyncio.sleep(random.uniform(0.01, 0.2))
    label = kwargs.get("label", "")
    if "copy_editor(0)" in label:
        return "REWRITE_NEEDED: 테스트 사유"
    return "테스트 소개 문구입니다."

# app.graph를 임포트하기 전에 dispatch_layout_desk를 계측판으로 바꿔치기 -
# graph.py의 "from .nodes.copy_desk import ... dispatch_layout_desk"가
# 이 계측판을 가져가게 만들어서, 실제 앱과 동일하게 모듈 임포트 시 1회만
# build_graph()가 실행되는 조건을 그대로 맞춘다.
import app.nodes.copy_desk as copy_desk_module

_original_dispatch = copy_desk_module.dispatch_layout_desk
_call_log = []


def instrumented_dispatch(state):
    checked = state.get("checked") or []
    old = state.get("old_introductions")
    replay = state.get("recent_replays")
    new = state.get("recent_new")
    result = _original_dispatch(state)
    _call_log.append(
        f"checked={len(checked)} old={old if old is None else len(old)} "
        f"replay={replay if replay is None else len(replay)} "
        f"new={new if new is None else len(new)} result={result}"
    )
    return result


copy_desk_module.dispatch_layout_desk = instrumented_dispatch


async def main():
    with patch("app.clients.llm.complete", new=jittery_complete), \
         patch("app.clients.steam_store.fetch_appdetails_kr", new=AsyncMock(return_value=None)), \
         patch("app.clients.reddit.fetch_buzz", new=AsyncMock(return_value=None)), \
         patch("app.clients.db.lookup_past_writeups", return_value=[]), \
         patch("app.clients.rag.search_relevant_articles", new=AsyncMock(return_value=[])), \
         patch("app.clients.db.save_weekly_report") as mock_save:

        from app.graph import GRAPH  # 모듈 임포트 시 1회 빌드된 실제 앱과 동일한 싱글턴

        def game(appid):
            return {
                "appid": appid, "name": f"Game{appid}", "developer": "dev",
                "publisher": "pub", "ccu": 0, "positive": 0, "negative": 0,
            }

        state = {
            "old_introductions": [game(i) for i in range(5)],
            "recent_replays": [game(100 + i) for i in range(2)],
            "recent_new": [game(200 + i) for i in range(5)],
            "report_date": "2099-01-01",
            "dry_run": False,
        }

        result = await GRAPH.ainvoke(state)
        print("=== dispatch calls ===")
        for line in _call_log:
            print(line)
        print("=== content is None?", result.get("content") is None)
        print("=== save_weekly_report called:", mock_save.called)


asyncio.run(main())
