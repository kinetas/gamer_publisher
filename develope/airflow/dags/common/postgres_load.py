"""gold 스냅샷 -> postgres upsert, 주간 리포트 선정, langgraph-server 호출.

old_games_pipeline / recent_games_pipeline DAG의 Spark 단계(gold) 다음에 붙는
가벼운 Python task들이 여기서 온다. 데이터 규모가 작아서(수천 row) Spark 없이
pandas + psycopg2로 처리한다.

k3s pod(Spark)와 달리 이 코드는 airflow-scheduler 컨테이너 안에서 직접 실행되므로
"minio"/"postgres" 호스트가 docker-compose backend-net의 기본 DNS로 바로 resolve된다
(Spark executor에서 겪었던 k3s coredns 이슈와 무관).
"""
import logging
from datetime import datetime

import pandas as pd
import psycopg2.extras
import requests
from airflow.hooks.base import BaseHook
from airflow.providers.postgres.hooks.postgres import PostgresHook

logger = logging.getLogger(__name__)

GOLD_COLUMNS = [
    "appid", "name", "developer", "publisher",
    "positive", "negative", "owners", "ccu", "ingested_at",
]

# 주간 리포트 슬롯 개수. old/신규/다시추천 세 카테고리는 서로 다른 테이블/기준에서 뽑는다.
OLD_SLOT_COUNT = 3
RECENT_NEW_SLOT_COUNT = 3
RECENT_REPLAY_SLOT_COUNT = 2

LANGGRAPH_REPORT_URL = "http://langgraph-server:8100/reports/weekly"


def _minio_storage_options() -> dict:
    minio_conn = BaseHook.get_connection("minio_default")
    return {
        "key": minio_conn.login,
        "secret": minio_conn.password,
        "client_kwargs": {"endpoint_url": "http://minio:9000"},
    }


def _to_native(value):
    """pandas/numpy 스칼라를 psycopg2가 바로 바인딩할 수 있는 python 기본 타입으로 변환."""
    if pd.isna(value):
        return None
    return value.item() if hasattr(value, "item") else value


def load_gold_to_postgres(pool: str) -> None:
    """gold parquet(S3)을 읽어 postgres(old_games/recent_games)로 upsert한다.

    Spark의 JDBC writer는 진짜 upsert(ON CONFLICT)를 지원하지 않아서,
    여기서는 Spark 밖에서 psycopg2로 직접 upsert한다.
    """
    table = "recent_games" if pool == "recent" else "old_games"
    df = pd.read_parquet(
        f"s3://datalake/gold/{table}/", storage_options=_minio_storage_options()
    )

    rows = [
        tuple(_to_native(v) for v in row)
        for row in df[GOLD_COLUMNS].itertuples(index=False, name=None)
    ]

    conn = PostgresHook(postgres_conn_id="postgres_app").get_conn()
    try:
        with conn.cursor() as cur:
            psycopg2.extras.execute_values(
                cur,
                f"""
                INSERT INTO {table}
                    (appid, name, developer, publisher, positive, negative, owners, ccu, ingested_at)
                VALUES %s
                ON CONFLICT (appid) DO UPDATE SET
                    name = EXCLUDED.name,
                    developer = EXCLUDED.developer,
                    publisher = EXCLUDED.publisher,
                    positive = EXCLUDED.positive,
                    negative = EXCLUDED.negative,
                    owners = EXCLUDED.owners,
                    ccu = EXCLUDED.ccu,
                    ingested_at = EXCLUDED.ingested_at
                """,
                rows,
            )
        conn.commit()
    finally:
        conn.close()

    logger.info("%s: %d행 upsert 완료", table, len(rows))


def _jsonable_rows(rows: list[dict]) -> list[dict]:
    clean_rows = []
    for row in rows:
        clean = {}
        for key, value in row.items():
            clean[key] = value.isoformat() if isinstance(value, datetime) else value
        clean_rows.append(clean)
    return clean_rows


def select_weekly_report(**context) -> None:
    """postgres 이력 대조 후 3슬롯(옛작품/신규/다시추천) 선정하고 이력을 갱신한다."""
    conn = PostgresHook(postgres_conn_id="postgres_app").get_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # 옛 작품 소개: 한번도 추천 안 된 것 우선, 부족하면 오래전에 추천된 것으로 채움
            # (NULL이 ASC 정렬에서 뒤로 가는 postgres 기본 동작을 NULLS FIRST로 뒤집는다).
            cur.execute(
                """
                SELECT appid, name, ccu, positive, negative, last_recommended_at
                FROM old_games
                ORDER BY last_recommended_at ASC NULLS FIRST, ccu ASC
                LIMIT %s
                """,
                (OLD_SLOT_COUNT,),
            )
            old_picks = cur.fetchall()

            # 신규 추천: 이번 풀 자체가 시간 윈도우로 이미 새 게임만 들어오지만,
            # 혹시 모를 재실행 대비로 "진짜 처음"인 것만 추가로 거른다.
            cur.execute(
                """
                SELECT appid, name, ccu, positive, negative
                FROM recent_games
                WHERE first_recommended_at IS NULL
                ORDER BY ccu ASC
                LIMIT %s
                """,
                (RECENT_NEW_SLOT_COUNT,),
            )
            recent_new_picks = cur.fetchall()

            # 다시 추천: 새 후보 풀이 아니라 "신규 추천" 이력 자체에서 오래된 것을 재소환.
            cur.execute(
                """
                SELECT appid, name, ccu, positive, negative, last_recommended_at
                FROM recent_games
                WHERE first_recommended_at IS NOT NULL
                ORDER BY last_recommended_at ASC NULLS FIRST
                LIMIT %s
                """,
                (RECENT_REPLAY_SLOT_COUNT,),
            )
            recent_replay_picks = cur.fetchall()

            old_appids = [r["appid"] for r in old_picks]
            recent_appids = [r["appid"] for r in recent_new_picks + recent_replay_picks]

            if old_appids:
                cur.execute(
                    """
                    UPDATE old_games SET
                        first_recommended_at = COALESCE(first_recommended_at, now()),
                        last_recommended_at = now(),
                        recommend_count = recommend_count + 1
                    WHERE appid = ANY(%s)
                    """,
                    (old_appids,),
                )
            if recent_appids:
                cur.execute(
                    """
                    UPDATE recent_games SET
                        first_recommended_at = COALESCE(first_recommended_at, now()),
                        last_recommended_at = now(),
                        recommend_count = recommend_count + 1
                    WHERE appid = ANY(%s)
                    """,
                    (recent_appids,),
                )
        conn.commit()
    finally:
        conn.close()

    report = {
        "old_introductions": _jsonable_rows(old_picks),
        "recent_new": _jsonable_rows(recent_new_picks),
        "recent_replays": _jsonable_rows(recent_replay_picks),
    }
    logger.info(
        "주간 리포트 선정: 옛작품 %d / 신규 %d / 다시추천 %d",
        len(old_picks), len(recent_new_picks), len(recent_replay_picks),
    )
    context["ti"].xcom_push(key="weekly_report", value=report)


def notify_langgraph(**context) -> None:
    """선정된 리포트 후보를 langgraph-server로 넘겨 실제 리포트 글 생성을 요청한다.

    langgraph-server는 아직 구현 전(스텁만 존재)이라, 실패/501 응답이어도
    파이프라인 전체를 실패시키지 않고 로그만 남기고 넘어간다.
    """
    report = context["ti"].xcom_pull(task_ids="select_weekly_report", key="weekly_report")

    try:
        response = requests.post(LANGGRAPH_REPORT_URL, json=report, timeout=30)
    except requests.RequestException as exc:
        logger.warning("langgraph-server 호출 실패 (아직 미구현일 수 있음): %s", exc)
        return

    if response.status_code == 501:
        logger.info("langgraph-server: 리포트 생성 아직 미구현(501) - 이번 주는 skip")
    elif response.ok:
        logger.info("langgraph-server 리포트 생성 요청 성공: %s", response.status_code)
    else:
        logger.warning(
            "langgraph-server 예상 밖 응답: %s %s", response.status_code, response.text[:500]
        )
