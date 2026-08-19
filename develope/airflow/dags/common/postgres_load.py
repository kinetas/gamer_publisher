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

from common.gamemeca_rss import fetch_gamemeca_articles

logger = logging.getLogger(__name__)

GOLD_COLUMNS = [
    "appid", "name", "developer", "publisher",
    "positive", "negative", "owners", "ccu", "ingested_at",
]

# 주간 리포트 슬롯 개수 (총 15개 유지 = 기존 3섹션 x 5개 그리드와 동일한 총량).
# "신규 추천"(recent_games_pipeline의 Spark 발굴) 폐기로 RECENT_NEW_SLOT_COUNT는 제거하고,
# 남은 두 카테고리(old_games 명작 아카이브 / recent_games 다시추천)에 15개를 재분배한다.
# old_games_pipeline은 앞으로도 계속 새 appid를 발굴해 풀이 꾸준히 늘어나는 반면,
# recent_games_pipeline DAG 자체가 없어져 recent_games 풀은 더 이상 새 appid가 유입되지
# 않는 고정된(오히려 시간이 지나며 줄어들 수 있는) 풀이다. 그래서 계속 성장하는 old 쪽에
# 더 큰 비중(8)을, 고정된 recent 쪽에 더 작은 비중(7)을 준다.
OLD_SLOT_COUNT = 8
RECENT_REPLAY_SLOT_COUNT = 7

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

    if not rows:
        # recent pool은 이번 실행에서 RECENT_MIN_POSITIVE_REVIEWS(ingest.py) 기준을
        # 통과한 후보가 0개일 수 있다 - 정상 상황이니 upsert만 스킵하고 넘어간다.
        logger.info("%s: 이번 gold 스냅샷에 upsert할 행 없음, 스킵", table)
        return

    conn = PostgresHook(postgres_conn_id="postgres_app").get_conn()
    try:
        with conn.cursor() as cur:
            # ingested_at은 UPDATE 대상에서 뺀다 — gold.py가 매 실행마다
            # withColumn("ingested_at", current_timestamp())로 전체 스냅샷에
            # "지금"을 찍는데다, raw/bronze/silver가 append 전용(정리 없음)이라
            # 몇 주 전에 처음 본 appid도 매번 gold 재처리 대상에 그대로 들어있다.
            # 여기서 EXCLUDED.ingested_at으로 덮어쓰면 이미 알고 있던 appid의
            # "최초 수집 시각"이 재실행할 때마다 "지금"으로 리셋되어, select_weekly_report의
            # "1년 이내" 신선도 필터가 사실상 절대 만료 안 되는 것처럼 무력화된다.
            # appid가 처음 INSERT될 때만 실제 최초 수집 시각이 박히게 둔다.
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
                    ccu = EXCLUDED.ccu
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
    """postgres 이력 대조 후 2그룹(옛작품/다시추천)을 선정하고 이력을 갱신한다.

    langgraph-server의 WeeklyReportRequest 계약이 old_introductions 단일 리스트만
    받으므로(schemas.py), old_games에서 뽑은 옛작품과 recent_games에서 뽑은 다시추천을
    하나의 리스트로 합쳐서 xcom에 싣는다. "신규 추천"(recommend_count=0 발굴)은
    recent_games_pipeline 폐기와 함께 완전히 제거됐다.
    """
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

            # 두 쿼리 다 공통으로 recent_games 풀 자체를 "오늘 기준 1년 이내 수집된 것"으로
            # 제한하고(1년 넘으면 old_games 영역과 개념이 겹치므로 recent 후보에서
            # 아예 배제), 그 안에서 positive=0(리뷰 하나도 못 받은 것)인 것도 뺀다.
            # old_games에서 이미 고른 옛작품 결과(old_picks)와 겹치는 게 없어야 하므로
            # (기획 요구사항), old_appids를 먼저 구해서 아래 recent 쿼리들에서
            # 전부 미리 제외한다 — appid 전역 유일성상 이론적으로만 가능한 케이스지만
            # 방어적으로 막아둔다.
            old_appids = {r["appid"] for r in old_picks}
            # positive < 100은 후보에서 아예 제외한다 - 리뷰가 그 정도로 적으면
            # "추천"이라는 형식 자체가 안 맞는다는 사용자 피드백. 100~999는 후보에는
            # 들어가되 langgraph-server 쪽(prompts.py _tone_guidance/copy_desk_prompt)이
            # "숨겨진 맛집" 톤으로 담백하게 쓰고, 과장하면 교열 단계에서 반려한다.
            recent_pool_filter = "ingested_at >= now() - interval '1 year' AND positive >= 100"

            # 다시 추천: recommend_count > 1(두 번 이상 추천된 적 있는 것)을 주 후보로
            # 삼아 적게 추천된 것부터 우선(ASC)으로 RECENT_REPLAY_SLOT_COUNT개를 채운다.
            # 그것만으로 부족하면 recommend_count = 1(한 번만 추천된 것)에서 나머지를 보충한다.
            cur.execute(
                f"""
                SELECT appid, name, developer, publisher, ccu, positive, negative,
                       last_recommended_at, recommend_count
                FROM recent_games
                WHERE recommend_count > 1 AND name IS NOT NULL AND name != ''
                  AND {recent_pool_filter} AND appid != ALL(%s::int[])
                ORDER BY recommend_count ASC, last_recommended_at ASC NULLS FIRST
                LIMIT %s
                """,
                (list(old_appids), RECENT_REPLAY_SLOT_COUNT),
            )
            recent_replay_picks = cur.fetchall()

            if len(recent_replay_picks) < RECENT_REPLAY_SLOT_COUNT:
                exclude = old_appids | {r["appid"] for r in recent_replay_picks}
                cur.execute(
                    f"""
                    SELECT appid, name, developer, publisher, ccu, positive, negative,
                           last_recommended_at, recommend_count
                    FROM recent_games
                    WHERE recommend_count = 1 AND name IS NOT NULL AND name != ''
                      AND {recent_pool_filter} AND appid != ALL(%s::int[])
                    ORDER BY last_recommended_at ASC NULLS FIRST
                    LIMIT %s
                    """,
                    (list(exclude), RECENT_REPLAY_SLOT_COUNT - len(recent_replay_picks)),
                )
                recent_replay_picks += cur.fetchall()

            old_appids = list(old_appids)
            recent_appids = [r["appid"] for r in recent_replay_picks]

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

    # langgraph-server의 WeeklyReportRequest는 old_introductions 하나뿐이므로
    # (develope/langgraph-server/app/schemas.py), 옛작품과 다시추천을 한 리스트로 합친다.
    # 다른 키를 붙이면 pydantic validation이 422로 거부한다.
    report = {
        "old_introductions": _jsonable_rows(old_picks) + _jsonable_rows(recent_replay_picks),
    }
    logger.info(
        "주간 리포트 선정: 옛작품 %d / 다시추천 %d (합계 %d)",
        len(old_picks), len(recent_replay_picks), len(old_picks) + len(recent_replay_picks),
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


def upsert_gamemeca_news() -> None:
    """게임메카 RSS를 독립 파싱해 game_news 테이블에 upsert한다 (link=external_id 기준).

    langgraph-server의 ChromaDB 색인(ingest_gamemeca_news)과는 별개의 파이프라인 -
    이 함수는 RAG용이 아니라 프론트 RSS 뉴스 섹션에 표시할 구조화 데이터를 Postgres에
    저장한다. gamemeca_rss.py가 langgraph-server/app/clients/gamemeca.py를 import하지
    않고 완전히 독립적으로 RSS를 다시 파싱하듯, 이 함수도 ingest_gamemeca_news와 별개로
    동작한다 (같은 RSS를 각자 목적에 맞게 따로 가져옴).
    """
    articles = fetch_gamemeca_articles()

    if not articles:
        # fetch_gamemeca_articles는 네트워크/파싱 오류를 이미 warning으로 남기고 []를
        # 반환한다 - 여기서는 "이번 주기엔 upsert할 기사 없음"만 info로 남기고 스킵한다
        # (load_gold_to_postgres의 "rows 없으면 스킵" 패턴과 동일).
        logger.info("게임메카 RSS: 이번 조회에서 upsert할 기사 없음, 스킵")
        return

    rows = [
        (
            a["source"],
            a["external_id"],
            a["title"],
            a["excerpt"],
            a["link"],
            a["image_url"],
            a["pub_date"],
        )
        for a in articles
    ]

    conn = PostgresHook(postgres_conn_id="postgres_app").get_conn()
    try:
        with conn.cursor() as cur:
            # appid는 UPDATE 대상에서 뺀다 - TASK-007(게임명 -> appid 매칭)이 채운 값을
            # 이 함수가 재실행될 때마다 EXCLUDED.appid(NULL)로 덮어써서 지우면 안 된다.
            # load_gold_to_postgres가 ingested_at을 EXCLUDED 대상에서 뺀 것과 같은 이유.
            psycopg2.extras.execute_values(
                cur,
                """
                INSERT INTO game_news
                    (source, external_id, title, excerpt, link, image_url, pub_date)
                VALUES %s
                ON CONFLICT (external_id) DO UPDATE SET
                    source = EXCLUDED.source,
                    title = EXCLUDED.title,
                    excerpt = EXCLUDED.excerpt,
                    link = EXCLUDED.link,
                    image_url = EXCLUDED.image_url,
                    pub_date = EXCLUDED.pub_date
                """,
                rows,
            )
        conn.commit()
    finally:
        conn.close()

    logger.info("게임메카 뉴스: %d행 upsert 완료", len(rows))


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
