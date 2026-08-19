# TASK-006_감성분석담당

완료 시각: 2026-08-19

## 배경 요약
사이트 3섹션 재구성(doc/CHANGE_REQUEST.md 항목 3)의 마지막 신규 기능. Steam
리뷰 원문을 수집해 로컬 경량 다국어 감성분석 라이브러리(HuggingFace
transformers, cardiffnlp/twitter-xlm-roberta-base-sentiment)로 1차 분류하고,
집계+대표 샘플만 langgraph-server(POST /sentiment/summarize, 이미 구현
완료·확정 계약)에 보내 "왜 그런 평가인지" 요약을 받아 `sentiment_reports`에
저장한다. 리뷰 전량을 LLM에 넣지 않는 이유는
doc/decision-record-2026-08-19-three-section-restructure.md "설계가 중간에
바뀐 부분: 감성분석"에 설명된 대로 - LLM 호출량을 리뷰 개수가 아니라 게임
개수 수준으로 줄여 `recent_games_pipeline`이 겪었던 병목 재발을 막기 위함.

## 전체 아키텍처: 4단계

```
select_sentiment_targets (Airflow, PythonOperator)
    -> sentiment_ingest (Spark, KubernetesPodOperator, spark-submit)
    -> sentiment_classify (plain python, KubernetesPodOperator)
    -> summarize_and_save (Airflow, PythonOperator)
```

### 1. select_sentiment_targets — PythonOperator (Airflow)
- **왜 Airflow인가**: `old_games`/`recent_games`/`game_news`를 PostgresHook으로
  조회해야 한다. "postgres 접근은 항상 airflow-scheduler 컨테이너의
  common/postgres_load.py 쪽에서만 psycopg2/PostgresHook으로 처리한다"는 이
  레포의 기존 패턴(postgres_load.py 모듈 docstring)을 그대로 지켰다.
- 대상: `old_games` 전체 + `recent_games WHERE recommend_count >= 1` +
  `game_news WHERE appid IS NOT NULL`의 합집합(중복 제거).
  `recommend_count >= 1` 조건을 둔 이유: weekly_report_pipeline이 실제로
  한 번이라도 "다시 추천"으로 뽑아 사이트에 노출한 적 있는 게임만 대상으로
  삼기 위함(CHANGE_REQUEST의 "분석 대상은 명작 아카이브 + RSS 뉴스에 노출되는
  게임들로 한정" 요구사항과 정합).
- **game_news 전용 appid의 name 확보**: appreviews 응답(query_summary)에는
  게임 이름이 없다. game_news.title에서 이름을 유추하지 않고(기사 제목은
  "○○ 신작 발표" 같은 문장이라 게임명만 정확히 뽑기 어려움), Steam 공식
  `appdetails?appids={appid}` API로 appid -> name을 직접 조회했다.
  storesearch(이름->appid, 이미 game_matching.py가 반대 방향으로 씀)와 달리
  appdetails는 appid->이름을 바로 주는 "식별자 1건당 API 콜 1번"짜리 정상
  동작 엔드포인트라 recent_games_pipeline이 겪었던 카탈로그 전체 순회
  문제와 무관하다.
- 결과(appid+name 목록)는 XCom이 아니라 MinIO 고정 키
  `s3a://datalake/interim/sentiment/targets.json`에 boto3로 직접 쓴다 (이유는
  "설계 결정: 단계 간 전달 방식" 섹션 참고).

### 2. sentiment_ingest — Spark, KubernetesPodOperator (spark-submit)
- **왜 Spark인가**: 지시받은 대로 기존 `ingest.py`의 `write_raw_json`
  함수(SparkSession 필요)를 그대로 재사용해 raw JSON을 MinIO에 저장하기
  때문. `common/spark_stage.py`의 기존 `make_stage_task(stage, pool,
  env_vars)`를 **수정 없이 그대로** 재사용했다 - `pool="sentiment"`을 주지만
  `sentiment_ingest.py`는 `POOL` 환경변수를 전혀 읽지 않아 문제가 없음을
  확인했다(매니저 지시사항의 "문제 없으면 기존 함수를 그대로 재사용해라"에
  해당).
- targets.json을 `spark.read.json()`으로 읽고, appid마다 Steam 공식
  `appreviews/{appid}?json=1&filter=recent&language=all&num_per_page=100&
  purchase_type=all`을 호출(요청 사이 1초 sleep, timeout=30, soft-fail)해
  리뷰 원문 최대 100개를 가져온 뒤, `write_raw_json`으로
  `s3a://datalake/raw/steam/reviews/`에 append 저장한다.
- 1콜/appid로 호출량을 예측 가능하게 유지하기 위해 cursor 페이지네이션은
  쓰지 않았다(1페이지만).

### 3. sentiment_classify — plain python, KubernetesPodOperator (신규 실행 방식)
- **왜 spark-submit이 아닌가**: transformers/torch 로컬 추론은 분산처리가
  필요 없는 단일 프로세스 작업이고, Spark UDF로 감싸면 executor마다 모델을
  중복 로드하는 오버헤드만 생긴다는 매니저 지시("Spark UDF로 넣지 말고 별도
  단계로 분리")를 그대로 따랐다.
- **`make_stage_task`를 고치지 않고 새 빌더 `make_python_stage_task(stage,
  env_vars)`를 `common/spark_stage.py`에 추가**했다(기존 함수는 원칙적으로
  건드리지 말라는 지시). spark-submit 전용 설정(COMMON_SPARK_CONF,
  dynamicAllocation, driver.host, spark 서비스어카운트 등)을 전부 빼고, 같은
  spark-jobs 이미지를 `cmds=["python"]`으로 plain 실행한다. MinIO
  자격증명(`MINIO_ENDPOINT/ACCESS_KEY/SECRET_KEY`)은 DAG 파싱 시점에
  `BaseHook.get_connection("minio_default")`로 읽어 고정 값으로 주입한다
  (COMMON_SPARK_CONF의 `--conf`와 같은 원리).
- MinIO에서 `raw/steam/reviews/` 전체를 boto3로 직접 읽고(SparkSession 없이),
  `recommendationid` 기준으로 dedup(같은 리뷰가 매주 재수집되며 raw에 중복
  쌓이는 문제 해소 - silver.py가 appid 기준 dropDuplicates로 bronze 중복을
  없애는 것과 동일한 원칙), 리뷰 텍스트를
  `cardiffnlp/twitter-xlm-roberta-base-sentiment`로 분류(긍정/중립/부정
  3-way)해 appid별 positive/negative/neutral/review_count를 집계하고, 대표
  샘플(긍정/부정 우선 혼합, 최대 15개)을 뽑는다.
- 결과를 `s3a://datalake/interim/sentiment/results.json`에 boto3로 쓴다.
- 라이브러리(`transformers`, `sentencepiece`, `boto3`)는
  `develope/spark-jobs/requirements.txt`에 추가했고, `torch`는 CPU 전용
  wheel(`--index-url https://download.pytorch.org/whl/cpu`)로 Dockerfile에서
  별도 설치해 이미지 용량을 줄였다(GPU 빌드 CUDA 종속성을 피함). airflow
  컨테이너(스케줄러)가 아니라 spark-jobs 이미지에 넣은 이유는
  `postgres_load.py` 모듈 docstring의 "스케줄러는 가벼운 상태를 유지해야
  한다"는 설계 원칙과, spark-jobs가 이미 이 레포의 "무거운 python 실행
  환경" 담당이라는 지시를 그대로 따랐다.

### 4. summarize_and_save — PythonOperator (Airflow)
- **왜 Airflow인가**: `requests`로 langgraph-server를 호출하고
  `PostgresHook`으로 `sentiment_reports`에 upsert해야 하므로.
- `postgres_load.py`에 함수를 더 얹지 않고 **새 모듈 `common/
  sentiment_load.py`로 분리**했다 - postgres_load.py는 이미 gold->postgres
  upsert / 주간 리포트 선정 / 외부 서비스 알림 등 여러 책임을 지고 있어서,
  TASK-007이 game_matching.py를 분리한 선례와 동일한 판단을 적용했다.
- `results.json`을 읽어 appid마다 `SentimentSummaryRequest` 계약대로
  payload를 구성해 `POST http://langgraph-server:8100/sentiment/summarize`를
  호출한다(timeout=120). 계약상 LLM이 실패해도 이 엔드포인트는 항상 200 +
  폴백 문구를 반환하므로 soft-fail로 관대하게 처리하되, 완전히 응답을 못
  받으면(네트워크 오류/타임아웃) summary를 로컬 폴백 문구
  ("리뷰 요약을 생성하지 못했습니다 (LLM 서버 응답 없음).")로 채우고 이미
  계산된 카운트는 그대로 upsert한다(지시사항 그대로 - 로컬 집계는 LLM
  실패로 날리지 않음).
- `sentiment_reports`에 `appid` 기준 `ON CONFLICT DO UPDATE`로 upsert하며,
  appid 하나 처리할 때마다 즉시 commit해 중간에 실패해도 앞서 처리한
  게임들의 저장이 롤백되지 않게 했다.

## 설계 결정: 단계 간 데이터 전달을 MinIO 고정 키로 한 이유 (지시된 XCom/pod env var 대신)
지시서는 대상 appid 목록을 pod env var로(JSON 문자열 직렬화), classify
결과는 MinIO 또는 XCom 중 판단해서 넘기라고 했다. 실제로는 **두 핸드오프
모두 MinIO 고정 키**(`s3a://datalake/interim/sentiment/targets.json`,
`.../results.json`)로 통일했다:

- `sentiment_ingest`는 **수정 금지인 기존 `make_stage_task`**를 그대로
  써야 한다. 이 함수는 `env_vars` 딕셔너리를 **DAG 파싱 시점**에 곧바로
  `k8s.V1EnvVar` 객체 리스트로 변환해 `KubernetesPodOperator(env_vars=...)`에
  넘긴다. 만약 여기 `{"SENTIMENT_TARGETS": "{{ ti.xcom_pull(...) }}"}` 같은
  Jinja 문자열을 넣는다면, Airflow의 템플릿 렌더링 단계가 `V1EnvVar` 객체
  내부의 `.value`까지 재귀적으로 렌더링해 주는지가 관건인데, 이 환경에는
  Airflow가 설치돼 있지 않아 실제 렌더링 여부를 실행 검증할 수 없었다.
  검증 안 된 방식에 파이프라인 정합성을 걸기보다, **DAG 파싱 시점에 이미
  확정된 값만 V1EnvVar로 넘기고(MinIO 자격증명 등 기존 COMMON_SPARK_CONF
  방식과 동일), 런타임에 달라지는 값은 각 pod가 고정 MinIO 키를 직접
  읽고/쓰는 방식**으로 우회했다. `max_active_runs=1`로 동시 실행을 막아
  고정 키가 서로 다른 실행 사이에서 섞이지 않게 했다(주간 스케줄이라
  동시 실행이 필요하지도 않음).
- classify 결과(appid 수백 개 x 샘플 최대 15개)는 Airflow 기본 XCom
  backend가 메타데이터 DB라는 점을 고려해, 규모가 커질 여지가 있는 이
  데이터도 같은 이유로 MinIO에 뒀다(대상 목록만 있는 targets.json은 XCom
  으로도 충분히 작지만, 파이프라인 앞뒤 두 핸드오프의 방식을 통일해 두는
  편이 유지보수 관점에서 더 낫다고 판단).

## 검증
- `python -m py_compile`로 신규/수정 파일 6개(sentiment_targets.py,
  sentiment_load.py, spark_stage.py, sentiment_pipeline.py,
  sentiment_ingest.py, sentiment_classify.py) 구문 오류 없음 확인. 이
  환경에는 airflow/pyspark/psycopg2/boto3/transformers가 설치돼 있지 않아
  실제 import/DAG 파싱/모델 로딩 실행 검증은 하지 못했다(TASK-005/007과
  동일한 제약).
- `develope/langgraph-server/**`, `develope/fastapi-server/**`,
  `develope/frontend/**`는 계약 확인을 위해 `schemas.py`/`main.py`만
  열람했고 일절 수정/import하지 않았다.
- 기존 함수(`make_stage_task`, `postgres_load.py`의 5개 함수,
  `game_matching.py`, `gamemeca_rss.py`, `ingest.py`의 pool="old" 로직,
  `old_games_pipeline.py`/`weekly_report_pipeline.py`/
  `gamemeca_ingest_pipeline.py`)는 전혀 수정하지 않음 - 새 파일 추가 또는
  `spark_stage.py`에 새 함수 추가만 수행.

## sentiment_reports 최종 스키마
```sql
CREATE TABLE IF NOT EXISTS sentiment_reports (
    appid           INTEGER PRIMARY KEY,
    name            TEXT NOT NULL,
    positive_count  INTEGER NOT NULL DEFAULT 0,
    negative_count  INTEGER NOT NULL DEFAULT 0,
    neutral_count   INTEGER NOT NULL DEFAULT 0,
    review_count    INTEGER NOT NULL DEFAULT 0,
    summary         TEXT,
    generated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
```
FK 없음(old_games/recent_games/game_news 중 어디서 유래했든 섞여 들어올 수
있고, 대상 게임이 나중에 그 테이블들에서 사라져도 독립적으로 남는 별도
요약 테이블이므로 - game_news.appid가 FK 없이 독립적인 것과 같은 이유).

## 생성/수정 파일 목록 (절대경로)

**생성:**
- `E:\GP\develope\postgres\init\05-create-sentiment-table.sql`
- `E:\GP\develope\airflow\dags\common\sentiment_targets.py`
- `E:\GP\develope\airflow\dags\common\sentiment_load.py`
- `E:\GP\develope\airflow\dags\sentiment_pipeline.py`
- `E:\GP\develope\spark-jobs\jobs\sentiment_ingest.py`
- `E:\GP\develope\spark-jobs\jobs\sentiment_classify.py`
- `E:\GP\report\fragment\TASK-006_감성분석담당.md` (본 파일)

**수정:**
- `E:\GP\develope\airflow\dags\common\spark_stage.py` (기존 `make_stage_task`는
  전혀 건드리지 않음 - 파일 맨 끝에 새 함수 `make_python_stage_task` 추가만)
- `E:\GP\develope\spark-jobs\requirements.txt` (`transformers`,
  `sentencepiece`, `boto3` 추가. 기존 `pyspark`/`requests`/`praw` 3줄은 미변경)
- `E:\GP\develope\spark-jobs\Dockerfile` (torch CPU 전용 wheel 설치 RUN 구문
  1줄 추가, 기존 `COPY`/`WORKDIR`/`pip install -r requirements.txt` 구조는
  그대로 유지)

## 예상 토큰 소모량: 대 (large)
이유: 선행 문서 4개(CHANGE_REQUEST/PRD/decision-record/Coding_Rule) + 선행
완료 코드 6개(04-create-news-table.sql, 02-create-recommendation-tables.sql,
game_matching.py, postgres_load.py, gamemeca_rss.py) + 참고용 8개
(ingest.py/bronze.py/silver.py/gold.py, spark_stage.py,
old_games_pipeline.py/weekly_report_pipeline.py/gamemeca_ingest_pipeline.py,
langgraph-server schemas.py/main.py, requirements.txt/Dockerfile,
TASK-007 report)를 정독해 기존 컨벤션(soft-fail 패턴, sleep 간격, raw append
철학, silver dedup 원칙, upsert 패턴)을 정확히 맞춰야 했고, 신규 기능 자체가
4단계 파이프라인(6개 신규 파일 + 1개 파일에 함수 추가)으로 이 세그먼트에서
가장 큰 신규 기능이었다. 특히 "KubernetesPodOperator의 env_vars가 런타임
Jinja 값을 실제로 렌더링해 주는지" 문제를 Airflow 미설치 환경에서 검증할
수 없어, 이를 우회하는 대안 설계(MinIO 고정 키 핸드오프 + max_active_runs=1)를
스스로 판단하고 근거를 정리하는 데 추가 사고 비용이 들었다. Spark/psycopg2/
airflow/boto3/transformers 미설치 환경이라 `py_compile` 구문 검증 외 실제
실행/모델 로딩 테스트는 하지 못했다.
