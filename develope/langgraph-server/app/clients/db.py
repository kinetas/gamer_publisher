"""weekly_reports 읽기/쓰기. 기존 main.py에 있던 SQL을 그대로 옮겼다 (동작 변경 없음)."""
import json
import logging

import psycopg2

from ..config import DATABASE_URL

logger = logging.getLogger(__name__)


def save_weekly_report(report_date: str, content: dict) -> None:
    if DATABASE_URL is None:
        raise RuntimeError("DATABASE_URL not configured")

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


def lookup_past_writeups(appid: int, *, limit: int = 3) -> list[str]:
    """같은 게임의 과거 소개글(최신순)을 최대 limit개 돌려준다. 실패/이력없음이면 [].

    weekly_reports.content(JSONB)의 세 카테고리 배열을 합쳐서 appid로 직접 찾는다.
    예전엔 chromadb에 임베딩까지 만들어서 같은 걸 조회했는데, "같은 appid"는
    유사도가 아니라 완전일치 질문이라 애초에 벡터 검색이 필요 없었다 — 임베딩
    API 호출(비용/키 의존성) 없이 postgres 쿼리 하나로 대체한다.
    """
    if DATABASE_URL is None:
        return []

    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT report_date, elem->>'description' AS description
                FROM weekly_reports,
                     LATERAL jsonb_array_elements(
                         COALESCE(content->'old_introductions', '[]'::jsonb)
                         || COALESCE(content->'recent_replays', '[]'::jsonb)
                         || COALESCE(content->'recent_new', '[]'::jsonb)
                     ) AS elem
                WHERE (elem->>'appid')::int = %s
                ORDER BY report_date DESC
                LIMIT %s
                """,
                (appid, limit),
            )
            return [row[1] for row in cur.fetchall()]
    except Exception as exc:  # noqa: BLE001 - DB 실패가 그래프를 죽이면 안 됨
        logger.warning("과거 소개글 조회 실패 appid=%s: %s", appid, exc)
        return []
    finally:
        conn.close()
