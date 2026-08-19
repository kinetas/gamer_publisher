# TASK-004_Airflow담당

완료 시각: 2026-08-19 (UTC 13:04경)

## 배경 요약
"신규 추천"(recent_games_pipeline의 Spark 신작 발굴)을 완전 폐기하고 RSS 뉴스로 대체,
"다시 추천"은 "명작 아카이브"에 흡수 통합 — ingest/bronze/silver/gold(pool="recent")
경로 자체가 더 이상 돌 필요가 없어져 관련 DAG/코드를 정리했다.

## 변경 내역

### 1. DAG 파일 이름 변경 + 재구성
- `develope/airflow/dags/recent_games_pipeline.py` 삭제.
- `develope/airflow/dags/weekly_report_pipeline.py` 신규 생성.
  - `dag_id`: `"recent_games_pipeline"` → `"weekly_report_pipeline"`
  - `tags`: `["spark", "kubernetes", "medallion", "recent-games", "report"]` → `["report", "weekly"]`
    (spark/kubernetes 태스크가 이 DAG에서 전부 사라졌으므로 관련 태그 전부 제거)
  - `make_stage_task`(ingest/bronze/silver/gold, pool="recent") 4개 태스크와
    `load_gold_to_postgres(pool="recent")` 태스크 전부 제거.
  - `from common.spark_stage import make_stage_task` import 제거, `recent_max_candidates =
    Variable.get(...)` 관련 코드 제거.
  - import를 `from common.postgres_load import archive_current_report, notify_langgraph,
    select_weekly_report`로 축소 (`load_gold_to_postgres` import 제거).
  - 남은 흐름: `archive_current_report >> select_weekly_report >> notify_langgraph` (3 태스크).
  - 모듈 docstring을 새 흐름에 맞게 새로 작성 — "최근작 발굴"/"Spark"/"medallion"/"3슬롯" 등
    옛 개념 언급을 없애고, 폐기 경위(문서 링크 포함)와 recent_games 테이블이 여전히
    "다시 추천" 풀로 유지된다는 점을 명시.
- 부수 수정: `develope/airflow/dags/gamemeca_ingest_pipeline.py`의 주석에서
  `recent_games_pipeline(주간)` 언급을 `weekly_report_pipeline(주간)`으로 수정
  (DAG 이름이 바뀌었으므로 주석 정확성 유지 목적, 로직 변경 없음).

### 2. `develope/spark-jobs/jobs/ingest.py` 정리
POOL="recent"로만 도달하던 죽은 코드를 전부 제거. 삭제 전 repo 전체 grep으로
old pool 경로/다른 파일에서 참조가 없음을 확인함 (실제로 발견된 참조는 전부
문서(doc/*.md)나 주석뿐이었고, 코드 레벨 참조는 없었음).

**제거한 것:**
- 함수: `discover_recent_game_appids`, `_fetch_release_search_page`,
  `_parse_steam_release_date`, `fetch_steamspy_appdetails`,
  `fetch_steam_official_appdetails`, `fetch_steam_official_name`
  (뒤 두 함수는 `discover_recent_game_appids`/`fetch_steamspy_appdetails`에서만
  호출되고 old pool 경로에서는 전혀 안 쓰이는 것을 확인 후 제거)
- 상수: `STEAM_SEARCH_URL`, `STEAM_APPDETAILS_URL`, `RECENT_WINDOW_SPAN_DAYS`,
  `RECENT_MIN_POSITIVE_REVIEWS`, `STEAM_SEARCH_PAGE_SIZE`, `STEAM_SEARCH_MAX_PAGES`,
  `STEAM_SEARCH_REQUEST_INTERVAL_SECONDS`, `APPID_FROM_LOGO_RE`,
  `STEAMSPY_APPDETAILS_INTERVAL_SECONDS`
- import: `re` (APPID_FROM_LOGO_RE 제거로 미사용), `from datetime import date, datetime,
  timedelta` (recent 전용 날짜 계산에서만 쓰였고, old pool 경로는 datetime을 전혀 안 씀)
- `main()`의 `if pool == "recent": ...` 분기 전체 제거. `pool = os.environ.get("POOL",
  "old")` 판단 로직 자체도 제거하고 old pool 로직을 무조건 실행하도록 단순화
  (POOL env var는 spark_stage.py가 여전히 주입하지만 ingest.py는 더 이상 읽지 않음 — 무해).
- 모듈 docstring을 old pool 전용 설명으로 재작성, 폐기된 recent 경로에 대한 설명은
  "과거에는 ~했으나 폐기했다" 요약 + 문서 링크로 대체.

**보수적으로 남긴 것 (old pool 소유, 절대 안 건드림):**
- `fetch_steam_official_app_list`, `STEAM_APP_LIST_URL`, `STEAM_APP_LIST_MAX_RESULTS` —
  `main()`의 old pool 분기 안에서 주석 처리된 상태로 남아있는 코드가 참조하므로 유지
  (old_games_pipeline.py와 동일하게 유지해야 하는 부분, recent 전용 아님)
- `fetch_all_steamspy_pages`, `STEAMSPY_URL`, `STEAMSPY_REQUEST_INTERVAL_SECONDS`,
  `STEAMSPY_MAX_PAGES` 처리 로직 — old pool 핵심 로직, 전혀 수정 안 함
- `write_raw_json`, `import json/os/time/requests`, `from pyspark.sql import SparkSession` —
  old pool도 그대로 쓰므로 유지

수정 후 `develope/spark-jobs/jobs/ingest.py`의 `main()`은 `old_games_pipeline.py`가
기대하는 계약(`STEAMSPY_MAX_PAGES` env var 읽어 `fetch_all_steamspy_pages` 호출 →
`steamspy_all` raw 경로에 적재)과 정확히 동일하게 동작함을 코드 대조로 확인.

### 3. `bronze.py` / `silver.py` / `gold.py` 확인 (수정 안 함)
전체를 읽고 pool="recent" 관련 분기를 검토했으나, 요청대로 **삭제하지 않고 현행 유지**.

- `bronze.py`: `source = "steamspy_recent" if pool == "recent" else "steamspy_all"`
  분기와 `clean()`의 "raw_path가 없으면 빈 스키마로 대체" 로직(recent pool이 이번 주
  후보 0개일 수 있다는 전제로 작성된 방어 코드)이 있음. `STEAMSPY_ALL_SCHEMA`는
  이름과 달리 recent pool의 `appdetails` 응답 스키마와도 호환되게 공유되는 구조.
  → **판단: 그대로 둠.** pool="recent" 인자로 호출될 일 자체가 없어져 이 분기는
  자연히 죽은 코드가 되지만, `clean()`의 방어 로직(`PATH_NOT_FOUND` 폴백)은 old
  pool에서도 이론상 유효하고(빈 raw 디렉토리 방어) old pool 가독성을 해치지 않으므로
  제거할 이유가 없음.
- `silver.py`: `if pool == "recent": filtered = rated_well / else: ccu 평균 이하 필터`
  분기가 있음. 모듈 docstring에 recent pool의 필터 정책(ccu 필터 없음, 감성분석
  원본으로 쓰기 위함)에 대한 설명도 남아있음.
  → **판단: 그대로 둠.** `if/else` 자체가 매우 짧고(3줄) old pool(else 분기) 로직을
  전혀 가리지 않으며, 오히려 "왜 old만 ccu 필터를 쓰는지"를 대조 설명하는 docstring이
  old pool 로직 이해에 도움이 됨. 제거하면 "recent pool은 왜 없는가"에 대한 맥락이
  사라져 이후 다른 개발자가 old pool의 ccu 필터 존재 이유를 오해할 여지가 있다고 판단.
- `gold.py`: `source`/`table` 변수를 pool 값으로 분기하는 2줄뿐. old pool 로직과
  완전히 얽혀있어 분리 자체가 무의미함.
  → **판단: 그대로 둠.** 수정할 대상이 없음.

세 파일 모두 pool="old" 로직은 전혀 건드리지 않았음 (애초에 읽기만 하고 아무 것도
쓰지 않음).

### 4. `develope/scripts/` 확인 (수정 안 함, 확인만)
`push_code_to_minio.sh`, `load-image-to-k3s.sh`, `spark-driver-ui.sh` 3개 파일 전체를
grep(`recent`, 대소문자 무시)했으나 매치 없음. `push_code_to_minio.sh`는 이미 알려진 대로
`mc mirror`로 `airflow/dags` 디렉토리 전체를 통째로 미러링하는 방식이라 개별 DAG
파일명을 참조하지 않음 — 수정 불필요.

## file_ownership 밖이라 못 고친 파일 (다른 세그먼트가 고쳐야 함)
- `doc/langgraph-report-pipeline.md`
  - L44: `` Airflow DAG(`recent_games_pipeline`)이 15개 게임을 선정해 `POST
    /reports/weekly`로 넘기는 계약은 그대로 유지 `` → DAG 이름이 `weekly_report_pipeline`로
    바뀌었으므로 갱신 필요. 같은 문단의 `old_introductions/recent_replays/recent_new`
    키 설명도 TASK-003의 `select_weekly_report` 리팩터(단일 `old_introductions` 리스트로
    통합) 완료 후 함께 갱신 필요.
  - L187: `` `airflow tasks test recent_games_pipeline notify_langgraph` `` → DAG 이름
    변경 반영 필요.
  - L207: `` `airflow dags trigger recent_games_pipeline` `` → DAG 이름 변경 반영 필요.
  - 사유: doc/langgraph-report-pipeline.md는 이번 태스크의 file_ownership 밖 (LangGraph
    담당 세그먼트 소유로 추정).
- (참고, 수정 요구는 아님) `develope/airflow/dags/common/spark_stage.py`의 모듈 docstring
  1행이 `"old_games_pipeline / recent_games_pipeline DAG이 공유하는..."`라고 옛 이름을
  언급하나, 이 파일은 이번 태스크 지침상 명시적으로 "건드리지 마라" 대상이라 그대로 둠.
  (old_games_pipeline.py 자체도 주석에 `recent_games_pipeline`을 언급하지만 역시
  "절대 건드리지 마라" 대상이라 그대로 둠.)

## 수정/삭제/생성 파일 목록 (절대경로)

**생성:**
- `E:\GP\develope\airflow\dags\weekly_report_pipeline.py`

**삭제:**
- `E:\GP\develope\airflow\dags\recent_games_pipeline.py`

**수정:**
- `E:\GP\develope\spark-jobs\jobs\ingest.py`
- `E:\GP\develope\airflow\dags\gamemeca_ingest_pipeline.py` (주석 1곳: DAG 이름 갱신)

**확인만 하고 수정 안 함:**
- `E:\GP\develope\spark-jobs\jobs\bronze.py`
- `E:\GP\develope\spark-jobs\jobs\silver.py`
- `E:\GP\develope\spark-jobs\jobs\gold.py`
- `E:\GP\develope\scripts\push_code_to_minio.sh`
- `E:\GP\develope\scripts\load-image-to-k3s.sh`
- `E:\GP\develope\scripts\spark-driver-ui.sh`
- `E:\GP\develope\airflow\dags\common\postgres_load.py` (TASK-003 동시 작업 중이라 미터치)
- `E:\GP\develope\airflow\dags\common\spark_stage.py` (지침상 미터치)
- `E:\GP\develope\airflow\dags\old_games_pipeline.py` (지침상 미터치)

## 검증
- `python -m py_compile` 로 `ingest.py`, `weekly_report_pipeline.py` 구문 오류 없음 확인
  (airflow/pyspark 미설치 환경이라 실제 import/실행 검증은 못 함 — 구문 검증만).
- `ingest.py`의 `main()`이 `old_games_pipeline.py`가 기대하는 계약(env_vars=
  `{"STEAMSPY_MAX_PAGES": steamspy_max_pages}`, pool="old")과 정확히 일치하는지
  코드 대조로 확인함.

## 예상 토큰 소모량: 중 (medium)
이유: 문서 5개(CHANGE_REQUEST/PRD/decision-record/Coding_Rule/investigation) 선독 +
DAG 2개, ingest/bronze/silver/gold 4개, postgres_load.py, spark_stage.py, scripts 3개
등 다수 파일을 읽어 교차 검증(특히 ingest.py의 함수/상수가 정말 recent 전용인지 grep
재확인)하는 조사 비중이 컸음. 반면 실제 코드 변경량은 DAG 1개 재작성 + ingest.py 축소
+ 주석 1곳 수정으로 크지 않아 "대" 수준까지는 아니었음.
