"""주간 리포트 파이프라인: archive_current_report >> select_weekly_report >> notify_langgraph.

예전에는 "최근작 발굴"(recent_games_pipeline: Steam 비공식 검색 API로 신작을
능동 탐색)이 이 DAG 앞단에 ingest/bronze/silver/gold(Spark, pool="recent") +
load_to_postgres를 붙여서 매주 recent_games 풀을 새로 채웠다. 하지만 Steam
비공식 검색 API의 `released` 날짜 필터가 서버에서 완전히 무시되는 구조적
한계로 느리고(수십 분) 히트율이 낮아(수십 개 중 1~2개) 폐기됐다 (상세 경위:
`doc/recent-games-discovery-investigation.md`, `doc/decision-record-2026-08-19-three-section-restructure.md`).
"신규 추천"은 RSS 뉴스 섹션(`gamemeca_ingest_pipeline`)으로 대체되었고,
"다시 추천"은 "명작 아카이브"에 흡수 통합됐다. recent_games 테이블과 기존
행(recommend_count>=1)은 유지되어 계속 주간 리포트 후보 풀로 쓰인다 — 다만
이 DAG은 더 이상 recent_games에 새 appid를 채우지 않는다(그 역할이던
Spark 단계 전체가 사라짐).

이제 이 DAG은 매주 다음 3단계만 수행하는 가벼운 파이프라인이다:

1. `archive_current_report`: 이번 주 새 리포트로 덮어쓰기 전에, 지금까지
   '최신'이었던 리포트를 fastapi-server가 헤드리스 브라우저로 프론트
   /print/:id를 캡처해 PDF로 MinIO에 저장하도록 요청한다 (과거 리포트는
   프론트에 다시 안 띄우고 다운로드 전용으로만 제공하는 설계라, 여기서
   미리 PDF로 얼려둬야 함).
2. `select_weekly_report`: old_games(명작 아카이브)/recent_games(다시 추천으로
   흡수 통합된 옛 최근작 풀) 두 테이블을 대조해 이번 주 리포트에 실을 게임
   목록을 선정한다.
3. `notify_langgraph`: 선정된 목록을 langgraph-server에 넘겨 게임별 소개 글
   생성 + weekly_reports 저장을 요청한다.

이 DAG이 스케줄러에 반영되려면:
  1. scripts/push_code_to_minio.sh 로 MinIO code 버킷(code/dags)에 업로드
  2. `docker compose run --rm dags-sync` 로 dags 볼륨에 반영
(Jenkins CI/CD가 구성되면 위 두 단계는 파이프라인이 자동으로 수행한다.)
"""
from datetime import datetime

from airflow import DAG
from airflow.operators.python import PythonOperator

from common.postgres_load import (
    archive_current_report,
    notify_langgraph,
    select_weekly_report,
)

with DAG(
    dag_id="weekly_report_pipeline",
    schedule="@weekly",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["report", "weekly"],
) as dag:
    archive = PythonOperator(
        task_id="archive_current_report",
        python_callable=archive_current_report,
    )

    select_report = PythonOperator(
        task_id="select_weekly_report",
        python_callable=select_weekly_report,
    )

    notify = PythonOperator(
        task_id="notify_langgraph",
        python_callable=notify_langgraph,
    )

    archive >> select_report >> notify
