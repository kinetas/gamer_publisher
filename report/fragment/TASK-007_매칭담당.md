# TASK-007_매칭담당

완료 시각: 2026-08-19

## 배경 요약
TASK-005가 신설한 `game_news` 테이블(게임메카 RSS 기사, `appid`는 매칭 전까지
항상 NULL)에 대해, 기사 제목으로 Steam appid를 매칭해 채우는 작업. 감성분석
섹션(doc/CHANGE_REQUEST.md 항목 3)이 나중에 리뷰를 수집할 대상 게임 목록을
만드는 선행 단계다. `recent_games_pipeline`이 겪었던 "카탈로그 전체 순회" 문제와
무관하게, 게임명 1건당 storesearch 1콜로 끝나는 정상 동작 엔드포인트를 쓴다
(doc/decision-record-2026-08-19-three-section-restructure.md 참고).

## 변경 내역

### 1. `develope/airflow/dags/common/game_matching.py` 신설
`develope/spark-jobs/jobs/`(Spark 분산처리 대상, 이 작업엔 불필요)가 아니라
`develope/airflow/dags/common/`을 택했다 — 가벼운 단발 API 호출이고 Airflow
PythonOperator에서 직접 쓰기 편하다는 매니저 권장 이유를 그대로 채택. 새 모듈로
분리한 이유는 `postgres_load.py`가 이미 gold→postgres upsert/리포트 선정/외부
서비스 알림 등 여러 책임을 지고 있어, "게임명→appid 매칭"이라는 별개 관심사를
더 얹기보다 독립 모듈로 분리하는 편이 낫다고 판단했기 때문이다 (gamemeca_rss.py를
postgres_load.py에 합치지 않고 별도 모듈로 뺀 TASK-005의 선례와 같은 판단).

- `search_steam_appid(query: str) -> dict | None`:
  `https://store.steampowered.com/api/storesearch/?term={query}&cc=kr&l=korean`을
  `requests.get`(timeout=30)으로 호출, `items[0]`만 후보로 본다.
- `match_game_news_appids() -> None`: `SELECT id, title FROM game_news WHERE
  appid IS NULL`로 매칭 대상만 조회(이미 매칭된 행은 재조회 안 함) → 각 행의
  title로 `search_steam_appid` 호출 → 매칭 성공 시
  `UPDATE game_news SET appid = %s WHERE id = %s` → 마지막에 한 번만 commit.
  `PostgresHook(postgres_conn_id="postgres_app")` 사용(postgres_load.py와 동일
  connection id). 매칭 실패 행은 그냥 스킵(다음 6시간 주기에 재시도, appid는
  계속 NULL).

### 2. `develope/airflow/dags/gamemeca_ingest_pipeline.py` 수정
- `from common.game_matching import match_game_news_appids` import 추가.
- `match_game_news_appids` PythonOperator(`task_id="match_game_news_appids"`)
  신규 추가, `upsert_task >> match_task`로 의존관계 설정.
- `ingest_gamemeca_news` 태스크는 그대로 독립 유지 (설정 미변경).
- 모듈 docstring을 "두 태스크가 독립 병렬"에서 "세 태스크 중 두 개는 병렬,
  match_game_news_appids는 upsert_gamemeca_news 뒤에 순차 실행"으로 갱신.

## 오탐 방지 로직 (매우 중요, 상세)
`search_steam_appid`는 storesearch 최상위 결과(`items[0]`)의 `name`이 검색어
(기사 제목, `query`) 문자열 안에 **부분 문자열로 포함될 때만** 채택한다:

```python
if _normalize(candidate_name) not in _normalize(query):
    return None  # 매칭 실패로 처리
```

`_normalize()`는 `strip().lower()` + 연속 공백을 단일 공백으로 정리하는 정도만
적용한다. 특수문자 제거 등 더 느슨한 정규화는 오탐 위험을 키우고, 정규화를 아예
안 하면 사소한 공백/대소문자 차이로 매칭률이 0에 가까워지므로 이 정도가 균형점이라
판단했다. 이 원칙은 매니저가 지정한 대로
`develope/langgraph-server/app/clients/rag.py`(실제 경로 확인함, 지시서의
`app/rag.py`는 오기로 보임)의 `search_relevant_articles`가
`needle in f"{title} {excerpt}".lower()`로 game_name 포함 여부만 보는 것과
동일한 "포함 안 되면 매칭 실패" 보수적 원칙을 독립적으로 재구현한 것이다 —
rag.py는 읽기만 하고 import/수정하지 않았다.

요청 실패/타임아웃(`requests.RequestException`)과 JSON 파싱 실패
(`ValueError`)는 모두 `logging.warning` 후 `None` 반환으로 soft-fail 처리했다
(이 레포의 `gamemeca_rss.fetch_gamemeca_articles`, `postgres_load.
notify_langgraph` 등과 동일한 패턴).

storesearch 요청 사이에는 `_REQUEST_INTERVAL_SECONDS = 0.7`초 sleep을 두었다
(`spark-jobs/jobs/ingest.py`의 `STEAMSPY_REQUEST_INTERVAL_SECONDS` sleep 패턴
참고 — storesearch는 SteamSpy `all`(1req/60s)만큼 엄격한 제한 문서는 없지만,
`match_game_news_appids`가 대상 행을 연속 순회 호출하므로 비공식 API에 매너상
짧은 텀을 두는 게 안전하다는 판단).

## 검증
- `python -m py_compile`로 `game_matching.py`, `gamemeca_ingest_pipeline.py` 구문
  오류 없음 확인 (airflow/psycopg2 미설치 환경이라 실제 import/DAG 파싱 실행
  검증은 못 함, TASK-005와 동일한 제약).
- `game_news` 테이블 스키마(04-create-news-table.sql)는 수정하지 않음 (appid
  컬럼 이미 존재).
- 기존 5개 함수(`select_weekly_report`, `notify_langgraph`,
  `load_gold_to_postgres`, `archive_current_report`, `ingest_gamemeca_news`)와
  `upsert_gamemeca_news`는 전혀 수정하지 않음 — 새 모듈(`game_matching.py`)에만
  신규 함수를 추가했다.
- `develope/langgraph-server/**`, `develope/fastapi-server/**`,
  `develope/frontend/**`는 열람(rag.py)만 하고 일절 수정/import하지 않음.

## 수정/생성 파일 목록 (절대경로)

**생성:**
- `E:\GP\develope\airflow\dags\common\game_matching.py`

**수정:**
- `E:\GP\develope\airflow\dags\gamemeca_ingest_pipeline.py` (import 1줄 추가 +
  `match_game_news_appids` 태스크 추가 + `upsert_task >> match_task` 의존관계 +
  docstring 갱신, 기존 `ingest_gamemeca_news`/`upsert_gamemeca_news` 태스크
  설정은 미변경)

## 예상 토큰 소모량: 중 (medium)
이유: 문서 4개(CHANGE_REQUEST/PRD/decision-record/Coding_Rule) + 선행 코드
4개(04-create-news-table.sql, gamemeca_rss.py, postgres_load.py,
gamemeca_ingest_pipeline.py) + 참고용 2개(rag.py 실제 경로 확인 포함, ingest.py의
sleep 패턴)를 읽어 오탐 방지 원칙과 sleep 패턴 등 기존 컨벤션을 정확히 맞추는
조사 비중이 있었으나, 실제 신규 코드량은 모듈 1개(약 140줄, 함수 2개) + DAG
태스크 1개 추가로 크지 않아 "대" 수준까지는 아니었음. Spark/psycopg2/airflow
미설치 환경이라 `py_compile` 구문 검증 외 실제 실행 테스트는 하지 않아 검증
단계 토큰은 크지 않았음.
