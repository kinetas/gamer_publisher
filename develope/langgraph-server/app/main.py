from typing import Any

from fastapi import FastAPI, Response

app = FastAPI(title="gamer_publisher LangGraph Report Service")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/reports/weekly")
def weekly_report(payload: dict[str, Any]) -> Response:
    """recent_games_pipeline이 선정한 주간 후보(옛작품/신규/다시추천)를 받아
    실제 리포트 글을 생성하는 자리. LangGraph 리포트 생성 로직은 아직 구현 전이라
    501을 반환한다 - 호출하는 Airflow 쪽(common/postgres_load.notify_langgraph)은
    이 응답을 실패로 취급하지 않고 로그만 남기고 넘어간다.
    """
    return Response(status_code=501, content="report generation not implemented yet")
