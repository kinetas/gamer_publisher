"""옛 명작 발굴 파이프라인: ingest >> bronze >> silver >> gold >> load_to_postgres.

SteamSpy `all`(전체 게임) 기준으로 ccu 낮고 평점 좋은 "옛 명작"을 발굴한다.
이 풀은 순위가 주 단위로 거의 안 바뀌므로 월간으로만 갱신한다
(recent_games_pipeline은 최근작 풀을 주간으로 갱신 — 둘은 완전히 별개 파이프라인).

이 DAG이 스케줄러에 반영되려면:
  1. scripts/push_code_to_minio.sh 로 MinIO code 버킷(code/dags)에 업로드
  2. `docker compose run --rm dags-sync` 로 dags 볼륨에 반영
(Jenkins CI/CD가 구성되면 위 두 단계는 파이프라인이 자동으로 수행한다.)
"""
from datetime import datetime

from airflow import DAG
from airflow.models import Variable
from airflow.operators.python import PythonOperator

from common.postgres_load import load_gold_to_postgres
from common.spark_stage import make_stage_task

# SteamSpy `all`은 페이지당 1000개, 요청 제한 1req/60s라 전체 수집에 50분+ 걸린다.
# Airflow Variable "steamspy_max_pages"로 페이지 수를 제한할 수 있다 (기본값 3 = 몇 분 내 완료,
# 개발/파이프라인 동작 확인용). 실제 전체 배치 수집을 돌리려면 Airflow UI에서 이 Variable을
# 빈 문자열로 비우거나 지우면 된다 (ingest.py: 미설정 시 전체 수집).
steamspy_max_pages = Variable.get("steamspy_max_pages", default_var="3")

with DAG(
    dag_id="old_games_pipeline",
    schedule="@monthly",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["spark", "kubernetes", "medallion", "old-games"],
) as dag:
    ingest = make_stage_task(
        "ingest", pool="old", env_vars={"STEAMSPY_MAX_PAGES": steamspy_max_pages}
    )
    bronze = make_stage_task("bronze", pool="old")
    silver = make_stage_task("silver", pool="old")
    gold = make_stage_task("gold", pool="old")

    load_to_postgres = PythonOperator(
        task_id="load_to_postgres",
        python_callable=load_gold_to_postgres,
        op_kwargs={"pool": "old"},
    )

    ingest >> bronze >> silver >> gold >> load_to_postgres
