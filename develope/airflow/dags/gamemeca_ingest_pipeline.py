"""게임메카 뉴스 RSS를 주기적으로 chromadb(game_news_refs)에 색인하는 파이프라인.

Spark/medallion 단계가 필요 없다 - RSS 하나 가져와서 langgraph-server에 색인
요청하는 가벼운 태스크 하나뿐이다 (실제 파싱/임베딩/upsert는
langgraph-server의 POST /ingest/gamemeca, app/clients/gamemeca.py + rag.py 참고).

하루 여러 번 새 기사가 나오는 소스라 recent_games_pipeline(주간)보다 훨씬
자주(6시간마다) 돌린다. robots.txt의 Crawl-delay: 30은 "기사 하나하나 순회"가
아니라 피드 자체를 한 번 가져오는 것뿐이라 이 주기로도 전혀 부담 없다.

이 DAG이 스케줄러에 반영되려면:
  1. scripts/push_code_to_minio.sh 로 MinIO code 버킷(code/dags)에 업로드
  2. `docker compose run --rm dags-sync` 로 dags 볼륨에 반영
(Jenkins CI/CD가 구성되면 위 두 단계는 파이프라인이 자동으로 수행한다.)
"""
from datetime import datetime

from airflow import DAG
from airflow.operators.python import PythonOperator

from common.postgres_load import ingest_gamemeca_news

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
