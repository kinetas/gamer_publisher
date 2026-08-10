import json
import os
from datetime import date
from typing import Any

import psycopg2
from fastapi import FastAPI, HTTPException
from openai import OpenAI
from pydantic import BaseModel

app = FastAPI(title="gamer_publisher LangGraph Report Service")

DATABASE_URL = os.environ.get("DATABASE_URL")
_openai_api_key = os.environ.get("OPENAI_API_KEY")
openai_client = OpenAI(api_key=_openai_api_key) if _openai_api_key else None


class GamePick(BaseModel):
    appid: int
    name: str
    developer: str | None = None
    publisher: str | None = None
    ccu: int | None = None
    positive: int | None = None
    negative: int | None = None
    last_recommended_at: str | None = None


class WeeklyReportRequest(BaseModel):
    old_introductions: list[GamePick]
    recent_new: list[GamePick]
    recent_replays: list[GamePick]


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


def _describe(game: GamePick, category: str) -> str:
    """게임 소개 문구를 LLM으로 생성한다. API 키가 없으면(로컬 개발 등) placeholder로 대체."""
    if openai_client is None:
        return f"{game.name} 소개 글 (OPENAI_API_KEY 미설정으로 자동 생성 안 됨)"

    prompt = (
        "다음 스팀 게임을 한국어로 2~3문장 소개하는 글을 써줘. "
        "게임 리포트 큐레이터 말투로, 과장 없이 담백하게.\n"
        f"카테고리: {category}\n"
        f"이름: {game.name}\n"
        f"개발사: {game.developer or '알 수 없음'}\n"
        f"현재 동시접속자(ccu): {game.ccu}\n"
        f"긍정 리뷰 {game.positive} / 부정 리뷰 {game.negative}\n"
    )
    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=200,
    )
    return (response.choices[0].message.content or "").strip()


def _build_section(games: list[GamePick], category: str) -> list[dict[str, Any]]:
    return [
        {
            "appid": game.appid,
            "name": game.name,
            "developer": game.developer or "",
            "publisher": game.publisher or game.developer or "",
            "positive": game.positive or 0,
            "negative": game.negative or 0,
            "ccu": game.ccu or 0,
            "description": _describe(game, category),
        }
        for game in games
    ]


@app.post("/reports/weekly")
def weekly_report(payload: WeeklyReportRequest) -> dict:
    """recent_games_pipeline의 select_weekly_report가 선정한 후보로 게임별 소개 글을
    생성하고, 완성된 리포트를 postgres(weekly_reports)에 저장한다.
    PDF 생성/저장은 여기서 하지 않는다 (fastapi-server가 헤드리스 브라우저로 프론트
    /print/:id 페이지를 캡처하는 방식으로 별도 처리).
    """
    if DATABASE_URL is None:
        raise HTTPException(status_code=500, detail="DATABASE_URL not configured")

    content = {
        "old_introductions": _build_section(payload.old_introductions, "옛 게임 소개"),
        "recent_replays": _build_section(payload.recent_replays, "다시 추천"),
        "recent_new": _build_section(payload.recent_new, "신규 추천"),
    }
    report_date = date.today().isoformat()

    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO weekly_reports (report_date, content)
                VALUES (%s, %s)
                ON CONFLICT (report_date) DO UPDATE SET content = EXCLUDED.content
                """,
                (report_date, json.dumps(content)),
            )
        conn.commit()
    finally:
        conn.close()

    return {"status": "created", "report_date": report_date}
