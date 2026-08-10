"""FastAPI 엔드포인트. 실제 리포트 생성 로직(편집국장->데스크->기자->교열부->
편집부 병렬 파이프라인)은 전부 graph.py의 LangGraph 그래프에 있다 — 이 파일은
얇게 유지한다.
"""
import logging
from contextlib import asynccontextmanager
from datetime import date

from fastapi import FastAPI, HTTPException

from .clients.http import close_http_client, init_http_client
from .graph import GRAPH
from .schemas import WeeklyReportRequest

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_http_client()
    try:
        yield
    finally:
        await close_http_client()


app = FastAPI(title="gamer_publisher LangGraph Report Service", lifespan=lifespan)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/graph")
def graph_mermaid() -> dict:
    """디버그용: 현재 컴파일된 그래프 구조를 mermaid로 반환한다."""
    return {"mermaid": GRAPH.get_graph().draw_mermaid()}


@app.post("/reports/weekly")
async def weekly_report(payload: WeeklyReportRequest, dry_run: bool = False) -> dict:
    """recent_games_pipeline의 select_weekly_report가 선정한 후보로 게임별 소개
    글을 병렬 생성하고, 완성된 리포트를 postgres(weekly_reports)에 저장한다.

    dry_run=true면 postgres/chromadb에 아무것도 쓰지 않고 content를 그대로
    응답에 담아 돌려준다 (로컬 검증용).
    """
    initial_state = {
        "old_introductions": [g.model_dump() for g in payload.old_introductions],
        "recent_replays": [g.model_dump() for g in payload.recent_replays],
        "recent_new": [g.model_dump() for g in payload.recent_new],
        "report_date": date.today().isoformat(),
        "dry_run": dry_run,
    }

    try:
        result = await GRAPH.ainvoke(initial_state)
    except Exception:
        logger.exception("리포트 생성 그래프 실행 실패")
        raise HTTPException(status_code=500, detail="report generation failed")

    for line in result.get("logs", []):
        logger.info(line)

    response = {
        "status": "dry_run" if dry_run else "created",
        "report_date": initial_state["report_date"],
        "timings": result.get("timings"),
    }
    if dry_run:
        response["content"] = result.get("content")
    return response
