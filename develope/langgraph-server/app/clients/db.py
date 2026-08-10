"""weekly_reports upsert. 기존 main.py에 있던 SQL을 그대로 옮겼다 (동작 변경 없음)."""
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
