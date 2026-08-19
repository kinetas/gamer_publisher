"""감성분석 파이프라인: select_sentiment_targets >> sentiment_ingest >> sentiment_classify >> summarize_and_save.

TASK-006, doc/CHANGE_REQUEST.md 항목 3 ("감성분석 섹션 신설"). 명작 아카이브
(old_games) + 다시 추천된 적 있는 게임(recent_games recommend_count>=1) + RSS
뉴스에서 매칭된 게임(game_news.appid, TASK-007) 전체를 대상으로, Steam 공식
appreviews API에서 리뷰 원문을 수집하고 로컬 경량 다국어 감성분석 라이브러리
(HuggingFace transformers, cardiffnlp/twitter-xlm-roberta-base-sentiment)로
1차 분류한 뒤, 집계+대표 샘플만 langgraph-server(POST /sentiment/summarize,
확정 계약이라 develope/langgraph-server/**는 건드리지 않았다)에 보내 "왜 그런
평가인지" 요약을 받아 sentiment_reports에 저장한다.

doc/decision-record-2026-08-19-three-section-restructure.md "설계가 중간에 바뀐
부분: 감성분석" 참고 - 리뷰 전량을 LLM에 넣지 않고 로컬 라이브러리로 1차 분류 후
집계+샘플만 LLM에 넣어, LLM 호출량을 "리뷰 개수"가 아니라 "게임 개수" 수준으로
줄인 이유가 설명돼 있다.

## 단계별 실행 방식과 근거

1. select_sentiment_targets (PythonOperator, Airflow, common/sentiment_targets.py)
   - PostgresHook으로 old_games/recent_games/game_news를 조회해야 하므로 Airflow
     쪽에 둔다(spark-jobs pod에는 postgres 접근 관례가 없다는 이 레포의 기존
     패턴, common/postgres_load.py 모듈 docstring: "postgres 접근은 항상
     airflow-scheduler 컨테이너의 common/postgres_load.py 쪽에서만 처리"). 대상
     appid+name 목록을 MinIO 고정 키(s3a://datalake/interim/sentiment/
     targets.json)에 써 둔다.
2. sentiment_ingest (KubernetesPodOperator, spark-submit, common/spark_stage.py의
   기존 make_stage_task 재사용) - spark-jobs/jobs/ingest.py의 write_raw_json이
   SparkSession을 필요로 하므로 Spark 단계로 만든다. pool="sentiment"를 주지만
   sentiment_ingest.py는 POOL 환경변수를 전혀 읽지 않는다 - make_stage_task의
   기존 시그니처를 그대로 재사용해도 문제없는지 먼저 확인했고(POOL을 안 쓰면
   그만이라는 매니저 지시사항 그대로) 문제가 없어 make_stage_task를 수정하지
   않고 그대로 썼다.
3. sentiment_classify (KubernetesPodOperator, plain python, common/spark_stage.py에
   새로 추가한 make_python_stage_task 전용 빌더) - HuggingFace transformers 로컬
   추론은 분산처리가 필요한 규모가 아니고(대상 appid 수백 개 x 리뷰 최대
   100개), Spark UDF로 감싸면 executor마다 모델을 중복 로드하는 오버헤드만
   생긴다는 매니저 지시("Spark UDF로 넣지 말고 별도 단계로 분리")에 따라 별도
   단계로 분리했다. 같은 spark-jobs 이미지를 그대로 재사용한다
   (develope/spark-jobs/requirements.txt에 transformers/sentencepiece/boto3를,
   Dockerfile에 torch(CPU 전용 wheel)를 추가했다 - spark-jobs가 이미 이 레포의
   "무거운 python 실행 환경" 담당이고, airflow 컨테이너(스케줄러)는 가벼운
   상태를 유지해야 한다는 common/postgres_load.py 모듈 docstring의 설계 원칙과
   일치시켰다).
4. summarize_and_save (PythonOperator, Airflow, common/sentiment_load.py) -
   requests로 langgraph-server를 호출하고 PostgresHook으로 sentiment_reports에
   upsert해야 하므로 Airflow 쪽에 둔다. postgres_load.py에 합치지 않고 새
   모듈(sentiment_load.py)로 분리했다 - TASK-007이 game_matching.py를 분리한
   것과 같은 판단(이미 여러 책임을 지고 있는 postgres_load.py에 새 관심사를 더
   얹지 않기 위함).

## 단계 간 데이터 전달을 MinIO 고정 키로 한 이유 (XCom/pod env var 대신)

- 대상 목록(수백 개 appid) 자체는 XCom(Airflow 메타데이터 DB) 용량으로는 크지
  않지만, KubernetesPodOperator(sentiment_ingest)가 이를 받으려면 env_vars에
  Jinja(XCom pull) 문자열을 담아야 한다. 그런데 common/spark_stage.py의
  make_stage_task(수정 금지)는 env_vars 딕셔너리를 DAG 파싱 시점에 곧바로
  k8s.V1EnvVar 객체 리스트로 변환해 버리므로, 그 안에 담긴 Jinja 문자열이
  Airflow의 템플릿 렌더링 단계에서 실제로 치환되는지 이 환경(Airflow 미설치,
  실행 검증 불가)에서 확인할 수 없었다. 검증 안 된 방식에 기대는 대신, 안전하게
  확정 동작하는 방식(고정 MinIO 키 s3a://datalake/interim/sentiment/*.json을 각
  단계가 직접 읽고 씀)을 택했다. max_active_runs=1로 동시 실행을 막아 "고정 키"가
  서로 다른 실행끼리 섞이지 않게 한다(주간 스케줄이라 동시 실행이 필요하지도 않음).
- classify 결과(appid별 집계 + 샘플 최대 15개, 수백 게임분)는 XCom(메타데이터
  DB) 용량으로 넣기에는 부담스러울 수 있다고 판단해 같은 이유로 MinIO에 둔다.

## raw 리뷰 재수집 시 중복 문제

sentiment_ingest.py는 기존 ingest.py의 write_raw_json(append 전용)을 그대로
재사용해 s3a://datalake/raw/steam/reviews/ 에 계속 쌓는다(이 레포 raw 영역의
기존 컨벤션과 동일 - steamspy_all 등 다른 raw 소스도 append 전용). 매주 같은
게임의 "최신 리뷰"를 다시 수집하면 리뷰가 중복으로 쌓일 수 있는데,
sentiment_classify.py가 recommendationid 기준으로 dedup해서 해소한다
(old_games_pipeline의 silver.py가 appid 기준 dropDuplicates로 bronze 중복을
해소하는 것과 동일한 원칙).

이 DAG이 스케줄러에 반영되려면:
  1. scripts/push_code_to_minio.sh 로 MinIO code 버킷(code/dags)에 업로드
  2. `docker compose run --rm dags-sync` 로 dags 볼륨에 반영
(Jenkins CI/CD가 구성되면 위 두 단계는 파이프라인이 자동으로 수행한다.)
"""
from datetime import datetime

from airflow import DAG
from airflow.operators.python import PythonOperator

from common.sentiment_load import summarize_and_save
from common.sentiment_targets import select_sentiment_targets
from common.spark_stage import make_python_stage_task, make_stage_task

with DAG(
    dag_id="sentiment_pipeline",
    schedule="@weekly",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    # 단계 간 핸드오프를 고정 MinIO 키(interim/sentiment/*)로 하기 때문에, 동시
    # 실행이 생기면 서로 다른 실행의 대상 목록/결과가 뒤섞일 수 있다. 주간
    # 스케줄에 동시 실행이 필요하지도 않아 1로 고정한다(모듈 docstring
    # "단계 간 데이터 전달을 MinIO 고정 키로 한 이유" 참고).
    max_active_runs=1,
    tags=["sentiment", "ml", "kubernetes"],
) as dag:
    select_targets = PythonOperator(
        task_id="select_sentiment_targets",
        python_callable=select_sentiment_targets,
    )

    ingest = make_stage_task("sentiment_ingest", pool="sentiment")

    classify = make_python_stage_task("sentiment_classify")

    save = PythonOperator(
        task_id="summarize_and_save",
        python_callable=summarize_and_save,
    )

    select_targets >> ingest >> classify >> save
