import asyncio
import sys

sys.path.insert(0, r"C:\Users\Administrator\GP\develope\langgraph-server")

from unittest.mock import AsyncMock, patch


async def main():
    with patch("app.clients.llm.complete", new=AsyncMock(return_value="테스트 소개 문구입니다.")), \
         patch("app.clients.steam_store.fetch_appdetails_kr", new=AsyncMock(return_value=None)), \
         patch("app.clients.reddit.fetch_buzz", new=AsyncMock(return_value=None)), \
         patch("app.clients.db.lookup_past_writeups", return_value=[]), \
         patch("app.clients.rag.search_relevant_articles", new=AsyncMock(return_value=[])), \
         patch("app.clients.db.save_weekly_report") as mock_save:

        import app.graph as graph_module

        original_dispatch = graph_module.dispatch_layout_desk

        def instrumented_dispatch(state):
            checked = state.get("checked") or []
            expected = (
                len(state.get("old_introductions") or [])
                + len(state.get("recent_replays") or [])
                + len(state.get("recent_new") or [])
            )
            result = original_dispatch(state)
            print(f"[DISPATCH] checked={len(checked)} expected={expected} result={result}")
            return result

        graph_module.dispatch_layout_desk = instrumented_dispatch

        graph = graph_module.build_graph()

        def game(appid, cat, idx):
            return {
                "appid": appid, "name": f"Game{appid}", "developer": "dev",
                "publisher": "pub", "ccu": 0, "positive": 0, "negative": 0,
            }

        state = {
            "old_introductions": [game(i, "old_introductions", i) for i in range(5)],
            "recent_replays": [game(100 + i, "recent_replays", i) for i in range(2)],
            "recent_new": [game(200 + i, "recent_new", i) for i in range(5)],
            "report_date": "2099-01-01",
            "dry_run": False,
        }

        result = await graph.ainvoke(state)
        print("=== logs ===")
        for line in result.get("logs", []):
            print(line)
        print("=== content is None?", result.get("content") is None)
        print("=== timings:", result.get("timings"))
        print("=== save_weekly_report called:", mock_save.called, mock_save.call_args)


asyncio.run(main())
