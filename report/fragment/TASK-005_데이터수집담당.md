# TASK-005_데이터수집담당

완료 시각: 2026-08-19

## 배경 요약
"신규 추천"(recent_games_pipeline의 Spark 신작 발굴, 폐기됨)을 RSS 뉴스 섹션으로
대체하는 작업의 일부. 게임메카(gamemeca.com) RSS 기사를 프론트 RSS 뉴스 섹션에
노출할 수 있도록 Postgres(`game_news` 테이블)에 저장하는 파이프라인을 신설했다.
langgraph-server의 기존 `POST /ingest/gamemeca`(ChromaDB RAG 색인)는 기사 목록을
응답으로 안 돌려줘서 재사용할 수 없었고, 지침상 `develope/langgraph-server/**`는
import/수정이 전면 금지라 Airflow 쪽에 완전히 독립적인 경량 RSS 파서를 새로 작성했다.

## 변경 내역

### 1. `develope/postgres/init/04-create-news-table.sql` 신설
`game_news` 테이블 생성. 기존 02/03번 SQL의 "파일 상단에 테이블 용도 설명 주석"
스타일을 따랐다. `appid`는 NULL 허용 + FK 없음(old_games/recent_games 어디에도
속하지 않을 수 있고, TASK-007이 매칭 전까지는 항상 NULL이므로).

### 2. `develope/airflow/dags/common/gamemeca_rss.py` 신설
`develope/langgraph-server/app/clients/gamemeca.py`를 import/수정하지 않고,
그 파일의 파싱 스타일(RSS description을 그대로 저장, 전문 스크레이핑 금지)만
참고해 Airflow(동기 requests) 환경에 맞게 완전히 새로 작성했다.
- `fetch_gamemeca_articles() -> list[dict]`: `RSS_URL = "https://www.gamemeca.com/rss.php"`를
  `requests.get`(User-Agent 헤더 포함, timeout=30)으로 가져와
  `xml.etree.ElementTree`로 `channel/item`을 순회 파싱.
- 각 item에서 title/link(또는 guid)/description(HTML 태그 제거 + 공백 정리)을
  추출하고 셋 중 하나라도 없으면 skip. `image/url` 또는 `image` 태그에서
  image_url 추출.
- `pubDate`는 `email.utils.parsedate_to_datetime`으로 timezone-aware datetime
  변환을 시도하고, 실패 시 None(컬럼이 NULL 허용).
- 네트워크 오류/XML 파싱 오류 시 `logging.warning` 후 빈 리스트 반환 (파이프라인을
  죽이지 않는 soft-fail 패턴).
- robots.txt Crawl-delay: 30 관련 주석 포함 (피드 자체를 한 번만 가져오므로
  개별 요청 sleep 불필요, 기존 gamemeca.py/gamemeca_ingest_pipeline.py와 동일한 근거).

### 3. `develope/airflow/dags/common/postgres_load.py`에 `upsert_gamemeca_news()` 추가
- 파일 상단에 `from common.gamemeca_rss import fetch_gamemeca_articles` 추가
  (이 레포의 DAG 파일들이 전부 `from common.xxx import yyy` 절대 import를 쓰는
  것을 `weekly_report_pipeline.py`/`old_games_pipeline.py`/`gamemeca_ingest_pipeline.py`
  에서 확인 후 동일한 스타일로 맞춤 — 상대 import 아님).
- 함수는 `ingest_gamemeca_news` 바로 다음, `archive_current_report` 바로 앞에 추가
  (요청받은 위치, 기존 함수 5개는 전혀 수정하지 않음).
- `fetch_gamemeca_articles()`가 빈 리스트를 반환하면(피드 실패) upsert를 스킵하고
  info 로그만 남기고 리턴 (`load_gold_to_postgres`의 "rows 없으면 스킵" 패턴 재사용).
- `psycopg2.extras.execute_values` + `ON CONFLICT (external_id) DO UPDATE`로
  source/title/excerpt/link/image_url/pub_date를 갱신. `appid`와 `ingested_at`은
  UPDATE 대상에서 제외 — `appid`는 TASK-007이 매칭한 값을 이 함수 재실행 시마다
  지우지 않기 위함(`load_gold_to_postgres`가 `ingested_at`을 뺀 것과 동일한 이유의
  패턴), `ingested_at`은 DEFAULT now()로 최초 삽입 시각만 유지.

### 4. `develope/airflow/dags/gamemeca_ingest_pipeline.py`에 태스크 추가
`upsert_gamemeca_news` PythonOperator를 새로 추가. 기존 `ingest_gamemeca_news`
태스크(설정 변경 없이 그대로 유지)와 함께 **의존관계 없이 DAG 루트로 병렬 배치**했다.

**판단 근거**: 두 태스크는 서로 다른 저장소(ChromaDB vs Postgres)에 쓰고 서로의
출력을 전혀 읽지 않는 완전히 독립적인 부작용을 갖는다. 순차로 두면 한쪽이 오래
걸리거나 soft-fail 재시도 대기에 걸릴 때 다른 쪽까지 불필요하게 지연되므로,
순서를 강제할 이유가 없다고 판단해 병렬로 뒀다. 두 태스크 모두 내부적으로
RSS 조회 실패를 삼키는 soft-fail이라, 병렬로 둬도 한쪽 실패가 다른 쪽을 막지 않는다.
모듈 docstring도 이 병렬 구조와 판단 근거를 설명하도록 갱신했다(로직 자체는
`ingest_gamemeca_news` 함수 미변경, DAG 스케줄/태그도 그대로 유지).

## game_news 테이블 최종 컬럼/타입
| 컬럼 | 타입 | 제약 |
|---|---|---|
| id | SERIAL | PRIMARY KEY |
| source | TEXT | NOT NULL |
| external_id | TEXT | UNIQUE NOT NULL (RSS link, upsert 기준) |
| title | TEXT | NOT NULL |
| excerpt | TEXT | |
| link | TEXT | |
| image_url | TEXT | |
| pub_date | TIMESTAMPTZ | |
| appid | INTEGER | NULL 허용, FK 없음 (TASK-007이 UPDATE로 채움) |
| ingested_at | TIMESTAMPTZ | NOT NULL DEFAULT now() |

## 검증
- `ast.parse`로 `postgres_load.py`, `gamemeca_rss.py`, `gamemeca_ingest_pipeline.py`
  3개 파일 구문 오류 없음 확인 (airflow/psycopg2 미설치 환경이라 실제
  import/실행 검증은 못 함).
- `weekly_report_pipeline.py`, `old_games_pipeline.py`, `gamemeca_ingest_pipeline.py`
  grep으로 `from common.xxx import yyy` 절대 import 컨벤션임을 확인 후 동일 스타일 적용.
- 기존 함수(`select_weekly_report`, `notify_langgraph`, `load_gold_to_postgres`,
  `archive_current_report`, `ingest_gamemeca_news`)와 `develope/langgraph-server/**`는
  일절 열람만 하고 수정/import하지 않음.

## 수정/생성 파일 목록 (절대경로)

**생성:**
- `E:\GP\develope\postgres\init\04-create-news-table.sql`
- `E:\GP\develope\airflow\dags\common\gamemeca_rss.py`

**수정:**
- `E:\GP\develope\airflow\dags\common\postgres_load.py` (import 1줄 추가 +
  `upsert_gamemeca_news()` 함수 추가, 기존 함수 미변경)
- `E:\GP\develope\airflow\dags\gamemeca_ingest_pipeline.py` (태스크 1개 추가 +
  docstring 갱신, 기존 `ingest_gamemeca_news` 태스크 설정 미변경)

## 예상 토큰 소모량: 중 (medium)
이유: 문서 4개(CHANGE_REQUEST/PRD/decision-record/Coding_Rule) + 기존 코드 6개
(gamemeca_ingest_pipeline.py, postgres_load.py, langgraph-server의 gamemeca.py 참고용,
02/03번 SQL, old_games_pipeline.py, weekly_report_pipeline.py, spark_stage.py,
common/__init__.py)를 읽어 컨벤션(import 스타일, upsert 패턴, soft-fail 패턴)을
정확히 맞추는 조사 비중이 있었으나, 실제 신규 코드량은 SQL 1개 + 모듈 1개(약 100줄)
+ 함수 1개 추가 + DAG 태스크 1개 추가로 크지 않아 "대" 수준까지는 아니었음.
