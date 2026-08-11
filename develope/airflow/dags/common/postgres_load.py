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

# 주간 리포트 슬롯 개수 (총 15개 = 프론트 1행 5열 그리드 x 3섹션에 맞춤).
# old/신규/다시추천 세 카테고리는 서로 다른 테이블/기준에서 뽑는다.
OLD_SLOT_COUNT = 5
RECENT_NEW_SLOT_COUNT = 5
RECENT_REPLAY_SLOT_COUNT = 5

LANGGRAPH_REPORT_URL = "http://langgraph-server:8100/reports/weekly"
LANGGRAPH_INGEST_GAMEMECA_URL = "http://langgraph-server:8100/ingest/gamemeca"
FASTAPI_ARCHIVE_URL = "http://fastapi-server:8000/reports/archive-current"


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
            # name이 빈 게 섞여 들어오면(SteamSpy가 아직 못 채운 신작 등, ingest.py의
            # Steam 공식 API 보강으로 대부분 막히지만 방어적으로 한 번 더 거른다)
            # 리포트에 이름 없는 게임이 나가버리므로 여기서 확실히 배제한다.
            cur.execute(
                """
                SELECT appid, name, developer, publisher, ccu, positive, negative, last_recommended_at
                FROM old_games
                WHERE name IS NOT NULL AND name != ''
                ORDER BY last_recommended_at ASC NULLS FIRST, ccu ASC
                LIMIT %s
                """,
                (OLD_SLOT_COUNT,),
            )
            old_picks = cur.fetchall()

            # 두 쿼리 다 공통으로 recent_games 풀 자체를 "1년 이내 수집된 것"으로
            # 제한하고(1년 넘으면 old_games 영역과 개념이 겹치므로 recent 후보에서
            # 아예 배제), 그 안에서 positive=0(리뷰 하나도 못 받은 것)인 것도 뺀다.
            recent_pool_filter = "ingested_at >= now() - interval '1 year' AND positive != 0"

            # 다시 추천: 한 번이라도 추천된 것 중, 적게 추천된 것부터 우선 (recommend_count
            # ASC). 신규 추천을 먼저 정하지 않고 이걸 먼저 뽑는 이유는 아래 신규 추천이
            # 이 결과와 안 겹치게 걸러야 하기 때문.
            cur.execute(
                f"""
                SELECT appid, name, developer, publisher, ccu, positive, negative, last_recommended_at
                FROM recent_games
                WHERE first_recommended_at IS NOT NULL AND name IS NOT NULL AND name != ''
                  AND {recent_pool_filter}
                ORDER BY recommend_count ASC, last_recommended_at ASC NULLS FIRST
                LIMIT %s
                """,
                (RECENT_REPLAY_SLOT_COUNT,),
            )
            recent_replay_picks = cur.fetchall()
            replay_appids = {r["appid"] for r in recent_replay_picks}

            # 신규 추천: 추천 안 한 것(first_recommended_at IS NULL) 우선, 모자라면
            # 추천 적게 한 것으로 채운다 - 단 다시 추천에 이미 뽑힌 appid와는 겹치면
            # 안 되므로, 여유 있게 뽑은 뒤 파이썬에서 걸러낸다. ccu는 여전히 인기
            # 많은 신작 우선(DESC) - old_games와 달리 "묻힌 걸 찾는다"는 취지가 아니다.
            cur.execute(
                f"""
                SELECT appid, name, developer, publisher, ccu, positive, negative,
                       first_recommended_at, recommend_count
                FROM recent_games
                WHERE name IS NOT NULL AND name != '' AND {recent_pool_filter}
                ORDER BY (first_recommended_at IS NOT NULL), recommend_count ASC, ccu DESC
                LIMIT %s
                """,
                (RECENT_NEW_SLOT_COUNT + len(replay_appids) + 10,),
            )
            recent_new_candidates = cur.fetchall()
            recent_new_picks = [
                r for r in recent_new_candidates if r["appid"] not in replay_appids
            ][:RECENT_NEW_SLOT_COUNT]

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
    """선정된 리포트 후보를 langgraph-server로 넘겨 게임별 소개 글을 생성하고
    weekly_reports에 저장하도록 요청한다.

    langgraph-server 쪽 문제(OPENAI_API_KEY 미설정 등)로 실패해도 이 task 때문에
    파이프라인 전체가 죽지 않도록 로그만 남기고 넘어간다 (리포트 생성은 매주 갱신되는
    부가 산출물이라, 이거 하나 실패했다고 postgres upsert까지 롤백할 이유는 없음).
    """
    report = context["ti"].xcom_pull(task_ids="select_weekly_report", key="weekly_report")

    try:
        # langgraph-server가 편집국장->데스크->기자->교열부->편집부 병렬 그래프로
        # 바뀌면서 정상 케이스도 Steam/Reddit 취재 + LLM 호출 30건이 걸린다
        # (실측 45~60초). Reddit/OpenAI 쪽 백오프가 겹치면 꼬리가 길어질 수 있어
        # 여유를 크게 둔다 — 실패해도 soft-fail이라 DAG은 안 죽지만, 타임아웃이
        # 너무 짧으면 "리포트는 잘 만들어졌는데 경고 로그만 뜨는" 상황이 반복된다.
        response = requests.post(LANGGRAPH_REPORT_URL, json=report, timeout=600)
    except requests.RequestException as exc:
        logger.warning("langgraph-server 호출 실패: %s", exc)
        return

    if response.ok:
        logger.info("langgraph-server 리포트 생성 성공: %s", response.text[:300])
    else:
        logger.warning(
            "langgraph-server 예상 밖 응답: %s %s", response.status_code, response.text[:500]
        )


def ingest_gamemeca_news() -> None:
    """게임메카 RSS를 langgraph-server가 chromadb(game_news_refs)에 색인하도록 요청한다.

    실패해도(예: 게임메카 일시 장애) 다음 주기에 다시 시도하면 되므로 warning만 남긴다.
    """
    try:
        response = requests.post(LANGGRAPH_INGEST_GAMEMECA_URL, timeout=60)
    except requests.RequestException as exc:
        logger.warning("게임메카 RSS 색인 요청 실패: %s", exc)
        return

    if response.ok:
        logger.info("게임메카 RSS 색인 결과: %s", response.text[:300])
    else:
        logger.warning(
            "게임메카 RSS 색인 예상 밖 응답: %s %s", response.status_code, response.text[:500]
        )


def archive_current_report() -> None:
    """새 리포트를 만들기 전에, 지금까지 '최신'이던 리포트를 PDF로 archive하도록
    fastapi-server에 요청한다 (recent_games_pipeline의 맨 앞 task).

    헤드리스 브라우저 구동 + 페이지 로드가 걸리는 작업이라 timeout을 넉넉히 준다.
    archive가 실패해도(예: 아직 리포트가 하나도 없음) 이번 주 파이프라인은 계속 진행한다.
    """
    try:
        response = requests.post(FASTAPI_ARCHIVE_URL, timeout=120)
    except requests.RequestException as exc:
        logger.warning("fastapi-server 리포트 archive 호출 실패: %s", exc)
        return

    if response.ok:
        logger.info("리포트 archive 요청 결과: %s", response.text[:300])
    else:
        logger.warning(
            "리포트 archive 예상 밖 응답: %s %s", response.status_code, response.text[:500]
        )
