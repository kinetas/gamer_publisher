"""RSS 뉴스 기사 제목에서 게임명을 추출해 Steam 공식 storesearch API로 appid를
매칭하는 모듈 (TASK-007, doc/CHANGE_REQUEST.md 항목 3 / 감성분석 섹션의 appid 확보 단계).

정교한 NLP로 게임명을 따로 추출하지 않고 game_news.title을 그대로 검색어로 쓴다
(기사 제목이 대개 게임명을 포함한다는 전제 - 매니저 지시).

storesearch는 recent_games_pipeline이 겪었던 "카탈로그 전체를 순회해야 하는" 문제
(released 날짜 필터가 서버에서 무시되는 store search)와는 다른 종류의 호출이다 -
게임명 1건당 API 콜 1번으로 끝나는 정상 동작 엔드포인트라 그 병목이 재발하지 않는다
(doc/decision-record-2026-08-19-three-section-restructure.md 참고).

오탐 방지 원칙(매우 중요, 매니저 지시 - langgraph-server의 app/clients/rag.py
search_relevant_articles가 game_name 문자열이 기사 제목/요약에 실제로 등장하는지로
필터링하는 것과 동일한 보수적 원칙. 이 파일은 그 파일을 import하지 않고 같은 원칙만
독립적으로 재구현한다): storesearch 최상위 결과(items[0])의 이름이 검색어(기사
제목) 문자열 안에 부분 문자열로 실제 포함될 때만 채택한다. "무관한 게임을 잘못
매칭하느니 매칭 안 되는 게 낫다" - 포함되지 않으면 None(매칭 실패)으로 처리한다.
"""
import logging
import re
import time

import psycopg2.extras
import requests
from airflow.providers.postgres.hooks.postgres import PostgresHook

logger = logging.getLogger(__name__)

STORESEARCH_URL = "https://store.steampowered.com/api/storesearch/"
_REQUEST_TIMEOUT = 30

# storesearch 요청 사이 매너 sleep. 이름 검색 1콜짜리라 SteamSpy `all`(1req/60s,
# spark-jobs/jobs/ingest.py STEAMSPY_REQUEST_INTERVAL_SECONDS 참고)처럼 엄격한 rate
# limit 문서는 없지만, match_game_news_appids가 game_news를 순회하며 연속 호출하니
# 비공식 API에 짧게라도 텀을 두는 게 안전하다는 판단으로 매 요청 사이 0.7초를 둔다.
_REQUEST_INTERVAL_SECONDS = 0.7

_WS_RE = re.compile(r"\s+")


def _normalize(text: str) -> str:
    """대소문자 무시 + 공백 정규화만 적용한다.

    특수문자까지 제거하는 등 더 느슨한 정규화를 하면 무관한 게임도 부분 문자열로
    걸려 오탐 위험이 커지고, 반대로 정규화를 아예 안 하면(대소문자/공백 차이) 매칭률이
    0에 가까워진다. 대소문자 무시 + 공백 정규화 정도가 그 사이 합리적인 균형점이다.
    """
    return _WS_RE.sub(" ", text.strip().lower())


def search_steam_appid(query: str) -> dict | None:
    """Steam storesearch로 query(기사 제목)와 매칭되는 게임을 찾는다.

    최상위 결과(items[0])만 후보로 보고, 그 이름이 query 문자열 안에 부분 문자열로
    실제 포함될 때만 {"appid": int, "name": str}를 반환한다. 포함되지 않으면(무관한
    게임일 가능성) None을 반환해 매칭 실패로 처리한다(오탐 방지 원칙).

    요청 실패/타임아웃/예상 밖 응답도 None + logging.warning으로 soft-fail 처리한다
    - 이 레포의 다른 외부 API 호출(gamemeca_rss.fetch_gamemeca_articles,
    postgres_load.notify_langgraph 등)과 같은 패턴.
    """
    if not query or not query.strip():
        return None

    try:
        response = requests.get(
            STORESEARCH_URL,
            params={"term": query, "cc": "kr", "l": "korean"},
            timeout=_REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("storesearch 조회 실패(query=%r): %s", query, exc)
        return None

    items = data.get("items") or []
    if not items:
        return None

    candidate = items[0]
    candidate_name = candidate.get("name") or ""
    candidate_appid = candidate.get("id")
    if not candidate_name or candidate_appid is None:
        return None

    if _normalize(candidate_name) not in _normalize(query):
        # 후보 이름이 기사 제목에 실제로 포함되지 않음 -> 무관한 게임일 가능성이
        # 높다고 보고 보수적으로 매칭 실패 처리한다 (오탐 방지 원칙, 매니저 지시).
        logger.info(
            "storesearch 후보 '%s'(appid=%s)가 검색어 %r에 포함되지 않아 매칭 스킵",
            candidate_name, candidate_appid, query,
        )
        return None

    return {"appid": int(candidate_appid), "name": candidate_name}


def match_game_news_appids() -> None:
    """appid가 NULL인 game_news 행을 순회하며 title로 storesearch 매칭을 시도하고,
    성공하면 `UPDATE game_news SET appid = %s WHERE id = %s`로 채운다.

    매칭 대상은 appid IS NULL인 행만 조회한다 - 이미 매칭된 행까지 매번 전체
    재검색하면 storesearch 호출이 주기마다 계속 쌓이기 때문이다. 매칭 실패한 행은
    그냥 넘어가고(appid는 계속 NULL), 다음 DAG 실행 주기(gamemeca_ingest_pipeline,
    6시간마다)에 재시도된다.

    postgres_load.py의 다른 함수들과 동일하게 PostgresHook(postgres_conn_id=
    "postgres_app")을 사용한다. 새 커넥션(연결 문자열)이 아니라 같은 conn_id를
    재사용해 game_news가 있는 app_db에 붙는다.
    """
    conn = PostgresHook(postgres_conn_id="postgres_app").get_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT id, title FROM game_news WHERE appid IS NULL")
            targets = cur.fetchall()

        if not targets:
            logger.info("game_news: appid 매칭 대상 없음, 스킵")
            return

        matched_count = 0
        with conn.cursor() as cur:
            for i, row in enumerate(targets):
                match = search_steam_appid(row["title"])
                if match is not None:
                    cur.execute(
                        "UPDATE game_news SET appid = %s WHERE id = %s",
                        (match["appid"], row["id"]),
                    )
                    matched_count += 1
                if i < len(targets) - 1:
                    time.sleep(_REQUEST_INTERVAL_SECONDS)
        conn.commit()
    finally:
        conn.close()

    logger.info("game_news appid 매칭: %d/%d행 매칭 성공", matched_count, len(targets))
