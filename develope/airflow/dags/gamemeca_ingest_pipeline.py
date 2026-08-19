"""게임메카 뉴스 RSS를 주기적으로 색인/저장/매칭하는 파이프라인.

Spark/medallion 단계가 필요 없다 - RSS 하나 가져와서 처리하는 가벼운 태스크들뿐이다.
세 태스크 중 앞의 둘은 서로 완전히 독립된 부작용을 갖는 별개 파이프라인을 각자
수행하고, 세 번째는 그중 하나(postgres 저장)에 이어서 실행된다:

  - ingest_gamemeca_news: langgraph-server에 색인을 요청해 chromadb(game_news_refs)에
    RAG용으로 저장한다 (실제 파싱/임베딩/upsert는 langgraph-server의
    POST /ingest/gamemeca, app/clients/gamemeca.py + rag.py 참고. 이 DAG 파일에서는
    건드리지 않는다).
  - upsert_gamemeca_news: common/gamemeca_rss.py(langgraph-server와 독립된 구현)로
    RSS를 동기 파싱해 postgres game_news 테이블에 upsert한다 - 프론트 RSS 뉴스
    섹션이 표시할 구조화 데이터용 (TASK-005, doc/CHANGE_REQUEST.md 항목 1).
  - match_game_news_appids: common/game_matching.py로 game_news 중 appid가 아직
    NULL인 행을 Steam storesearch API로 매칭해 채운다 - 감성분석 섹션이 나중에
    리뷰를 수집할 대상 목록을 만드는 선행 작업 (TASK-007, doc/CHANGE_REQUEST.md
    항목 3).

ingest_gamemeca_news와 upsert_gamemeca_news는 서로 다른 대상(chromadb vs
postgres)에 쓰고 서로의 결과를 읽지 않으므로 의존관계 없이 DAG 루트로 병렬
실행한다. 한쪽이 실패해도(둘 다 내부에서 soft-fail 처리) 다른 쪽 저장을 막을
이유가 없다. 반면 match_game_news_appids는 game_news에 매칭할 행이 이미 있어야
의미가 있으므로 upsert_gamemeca_news 뒤에 이어서 실행한다
(upsert_gamemeca_news >> match_game_news_appids).

하루 여러 번 새 기사가 나오는 소스라 weekly_report_pipeline(주간)보다 훨씬
자주(6시간마다) 돌린다. robots.txt의 Crawl-delay: 30은 "기사 하나하나 순회"가
아니라 피드 자체를 한 번 가져오는 것뿐이라 이 주기로도 전혀 부담 없다
(RSS 파싱 태스크들은 RSS 피드 자체를 각자 한 번씩만 요청. match_game_news_appids는
storesearch를 게임명 1건당 1콜로만 호출하는 별개의 API라 이 제약과 무관하다).

이 DAG이 스케줄러에 반영되려면:
  1. scripts/push_code_to_minio.sh 로 MinIO code 버킷(code/dags)에 업로드
  2. `docker compose run --rm dags-sync` 로 dags 볼륨에 반영
(Jenkins CI/CD가 구성되면 위 두 단계는 파이프라인이 자동으로 수행한다.)
"""
from datetime import datetime

from airflow import DAG
from airflow.operators.python import PythonOperator

from common.game_matching import match_game_news_appids
from common.postgres_load import ingest_gamemeca_news, upsert_gamemeca_news

with DAG(
    dag_id="gamemeca_ingest_pipeline",
    schedule="0 */6 * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["rag", "gamemeca", "news"],
) as dag:
    PythonOperator(
        task_id="ingest_gamemeca_news",
        python_callable=ingest_gamemeca_news,
    )

    upsert_task = PythonOperator(
        task_id="upsert_gamemeca_news",
        python_callable=upsert_gamemeca_news,
    )

    match_task = PythonOperator(
        task_id="match_game_news_appids",
        python_callable=match_game_news_appids,
    )

    # game_news에 행이 이미 있어야 매칭이 의미가 있으므로 upsert 이후에 실행한다.
    # ingest_gamemeca_news(chromadb 색인)는 이 의존관계와 무관하게 그대로 병렬 유지.
    upsert_task >> match_task
