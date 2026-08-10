"""최근작 발굴 + 주간 리포트 파이프라인.

ingest >> bronze >> silver >> gold >> load_to_postgres >> select_weekly_report >> notify_langgraph

Steam Store 검색으로 "2개월 전 ~ 2개월 전+1주"에 출시된 게임의 appid를 뽑고,
SteamSpy appdetails로 지표를 채워 ccu 낮고 평점 좋은 최근작을 발굴한다. 이 창은
매주 실행 시점 기준으로 한 칸씩 뒤로 밀리므로, 별도 dedup 없이도 주차별로
겹치지 않는 게임이 자연스럽게 나온다 (ingest.py 참고).

gold까지 끝나면 postgres(recent_games)로 upsert하고, old_games/recent_games 두
테이블을 대조해 주간 리포트 3슬롯(옛 작품 소개/신규 추천/다시 추천)을 선정한 뒤
langgraph-server에 리포트 작성을 요청한다. langgraph-server는 아직 미구현이라
notify_langgraph는 실패해도 DAG 전체를 실패시키지 않는다 (postgres_load.py 참고).

이 DAG이 스케줄러에 반영되려면:
  1. scripts/push_code_to_minio.sh 로 MinIO code 버킷(code/dags)에 업로드
  2. `docker compose run --rm dags-sync` 로 dags 볼륨에 반영
(Jenkins CI/CD가 구성되면 위 두 단계는 파이프라인이 자동으로 수행한다.)
"""
from datetime import datetime

from airflow import DAG
from airflow.models import Variable
from airflow.operators.python import PythonOperator

from common.postgres_load import (
    load_gold_to_postgres,
    notify_langgraph,
    select_weekly_report,
)
from common.spark_stage import make_stage_task

# appid당 SteamSpy appdetails 호출이 1초씩이라, 창 안 후보가 많으면(수백 개) 오래 걸린다.
# Airflow Variable "recent_max_candidates"로 개수를 제한할 수 있다 (기본값 20 = 개발/테스트용).
# 실제 운영 배치는 Airflow UI에서 이 Variable을 빈 문자열로 비우거나 지우면 된다.
recent_max_candidates = Variable.get("recent_max_candidates", default_var="20")

with DAG(
    dag_id="recent_games_pipeline",
    schedule="@weekly",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["spark", "kubernetes", "medallion", "recent-games", "report"],
) as dag:
    ingest = make_stage_task(
        "ingest",
        pool="recent",
        env_vars={"RECENT_MAX_CANDIDATES": recent_max_candidates},
    )
    bronze = make_stage_task("bronze", pool="recent")
    silver = make_stage_task("silver", pool="recent")
    gold = make_stage_task("gold", pool="recent")

    load_to_postgres = PythonOperator(
        task_id="load_to_postgres",
        python_callable=load_gold_to_postgres,
        op_kwargs={"pool": "recent"},
    )

    select_report = PythonOperator(
        task_id="select_weekly_report",
        python_callable=select_weekly_report,
    )

    notify = PythonOperator(
        task_id="notify_langgraph",
        python_callable=notify_langgraph,
    )

    ingest >> bronze >> silver >> gold >> load_to_postgres >> select_report >> notify
