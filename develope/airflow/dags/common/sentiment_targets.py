"""감성분석 대상 appid+name 목록을 확보해 MinIO에 써 두는 모듈
(TASK-006, doc/CHANGE_REQUEST.md 항목 3 / 감성분석 섹션의 "대상 게임 appid 확보" 단계).

세 집합의 합집합(중복 제거)을 대상으로 삼는다:
  - old_games 전체 (명작 아카이브 풀, old_games_pipeline이 채움)
  - recent_games WHERE recommend_count >= 1 (weekly_report_pipeline이 "다시 추천"으로
    한 번이라도 실제 노출한 적 있는 것만 - 한 번도 추천 안 된 recent_games 행은
    사이트에 노출된 적이 없으므로 감성분석 대상에서 제외한다. doc/CHANGE_REQUEST.md의
    "분석 대상은 명작 아카이브 + RSS 뉴스에 노출되는 게임들로 한정" 요구사항에 맞춘 판단)
  - game_news WHERE appid IS NOT NULL (TASK-007 game_matching.py가 채운 것)

old_games/recent_games에 이미 있는 appid는 그쪽 name을 그대로 쓴다. game_news에만
있는 appid(뉴스에서만 언급되고 old/recent 풀에는 없는 게임)는 name을
game_news.title에서 유추하지 않는다 - 기사 제목은 "○○ 신작 발표" 같은 문장이라
게임명만 깔끔하게 뽑아내기 어렵고, sentiment_reports.name이 부정확하면 프론트에
그대로 노출되기 때문이다. 대신 Steam 공식 appdetails API(appid로 게임명을 직접
조회하는 1콜짜리 정상 동작 엔드포인트 - storesearch/appreviews와 같은 "식별자 1건당
API 콜 1번" 부류라, recent_games_pipeline이 겪었던 "카탈로그 전체를 순회해야 하는"
구조적 문제와 무관하다. doc/decision-record-2026-08-19-three-section-restructure.md
참고)로 appid -> name을 다시 조회한다. appreviews 응답 자체(query_summary)에는
게임 이름이 없어서 이 방법을 택했다.

PostgresHook을 쓰므로 Airflow 쪽에 둔다 - spark-jobs pod에는 postgres 접근 관례가
없다는 이 레포의 기존 패턴(postgres_load.py 모듈 docstring: "postgres 접근은 항상
airflow-scheduler 컨테이너의 common/postgres_load.py 쪽에서만 처리") 유지.
postgres_load.py에 함수를 더 얹지 않고 새 모듈로 분리한 이유는 sentiment_load.py와
동일 - TASK-007이 게임명->appid 매칭을 postgres_load.py에 합치지 않고
game_matching.py로 분리한 선례를 그대로 따른다(이미 여러 책임을 지고 있는 파일에
새 관심사를 더 얹지 않는다는 판단).

확보한 목록은 XCom이 아니라 MinIO 고정 키(s3a://datalake/interim/sentiment/
targets.json)에 쓴다 - develope/airflow/dags/sentiment_pipeline.py 모듈 docstring의
"단계 간 데이터 전달을 MinIO 고정 키로 한 이유" 참고.
"""
import json
import logging
import time

import boto3
import psycopg2.extras
import requests
from airflow.hooks.base import BaseHook
from airflow.providers.postgres.hooks.postgres import PostgresHook

logger = logging.getLogger(__name__)

APPDETAILS_URL = "https://store.steampowered.com/api/appdetails"
_REQUEST_TIMEOUT = 30
# appdetails도 storesearch와 마찬가지로 공식 문서상 엄격한 요청 제한은 없지만,
# game_news에서만 발견된 appid를 순회 호출하므로 매너상 sleep을 둔다
# (game_matching.py의 _REQUEST_INTERVAL_SECONDS=0.7과 동일한 판단).
_REQUEST_INTERVAL_SECONDS = 0.7

_BUCKET = "datalake"
TARGETS_KEY = "interim/sentiment/targets.json"


def _minio_client():
    """postgres_load.py의 _minio_storage_options()와 같은 minio_default connection을
    쓰지만, 여기서는 pandas/s3fs가 아니라 boto3로 직접 JSON 오브젝트를 쓰기 위해
    boto3 client를 구성한다 (spark_stage.py의 minio_conn 사용 패턴과 동일).
    """
    conn = BaseHook.get_connection("minio_default")
    return boto3.client(
        "s3",
        endpoint_url="http://minio:9000",
        aws_access_key_id=conn.login,
        aws_secret_access_key=conn.password,
    )


def _fetch_name_via_appdetails(appid: int) -> str | None:
    """appdetails(appid -> 상세정보)로 게임명을 조회한다. 실패/비공개·삭제된
    앱이면 None으로 soft-fail 처리한다 - 이 레포의 다른 외부 API 호출
    (game_matching.search_steam_appid, gamemeca_rss.fetch_gamemeca_articles 등)과
    동일한 패턴.
    """
    try:
        response = requests.get(
            APPDETAILS_URL,
            params={"appids": appid, "cc": "kr", "l": "korean"},
            timeout=_REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("appdetails 이름 조회 실패(appid=%s): %s", appid, exc)
        return None

    entry = data.get(str(appid)) or {}
    if not entry.get("success"):
        return None
    name = (entry.get("data") or {}).get("name")
    return name or None


def select_sentiment_targets(**context) -> None:
    """old_games 전체 + recent_games(recommend_count>=1) + game_news(appid 매칭됨)의
    합집합을 대상 appid+name 목록으로 확보해 MinIO(TARGETS_KEY)에 JSON으로 쓴다.

    sentiment_ingest.py(Spark, KubernetesPodOperator)가 이 키를 직접 읽는다.
    """
    conn = PostgresHook(postgres_conn_id="postgres_app").get_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT appid, name FROM old_games WHERE name IS NOT NULL AND name != ''"
            )
            old_rows = cur.fetchall()

            cur.execute(
                "SELECT appid, name FROM recent_games "
                "WHERE recommend_count >= 1 AND name IS NOT NULL AND name != ''"
            )
            recent_rows = cur.fetchall()

            cur.execute("SELECT DISTINCT appid FROM game_news WHERE appid IS NOT NULL")
            news_appids = [row["appid"] for row in cur.fetchall()]
    finally:
        conn.close()

    targets: dict[int, str] = {}
    for row in old_rows + recent_rows:
        targets[row["appid"]] = row["name"]

    # old_games/recent_games에 이미 있는 game_news appid는 재조회할 필요가 없다.
    missing = [appid for appid in news_appids if appid not in targets]
    resolved = 0
    for i, appid in enumerate(missing):
        name = _fetch_name_via_appdetails(appid)
        if name:
            targets[appid] = name
            resolved += 1
        if i < len(missing) - 1:
            time.sleep(_REQUEST_INTERVAL_SECONDS)

    target_list = [{"appid": appid, "name": name} for appid, name in targets.items()]

    client = _minio_client()
    client.put_object(
        Bucket=_BUCKET,
        Key=TARGETS_KEY,
        Body=json.dumps(target_list, ensure_ascii=False).encode("utf-8"),
    )

    logger.info(
        "감성분석 대상 확보: old=%d recent=%d news전용=%d/%d(이름조회성공) 합계=%d",
        len(old_rows), len(recent_rows), resolved, len(missing), len(target_list),
    )
