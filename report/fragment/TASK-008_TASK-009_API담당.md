# TASK-008_TASK-009_API담당

완료 시각: 2026-08-19

## 배경 요약
사이트를 3섹션(명작 아카이브 / RSS 뉴스 / 감성분석) 체제로 재구성하는 작업의 일환으로,
이전 세그먼트(data_pipelines)가 DB 스키마(`game_news`, `sentiment_reports`)와
파이프라인(뉴스 수집, appid 매칭, 감성분석 집계)을 이미 끝냈다. 이번 세그먼트는 그
데이터를 프론트엔드가 소비할 수 있는 REST API로 노출하는 차례다. 같은 파일
(`main.py`)을 다루는 두 태스크를 지시받은 순서대로 진행했다:
- TASK-009(refactor, 선행): `weekly_reports.content`가 이제 `old_introductions` 키
  하나만 갖도록 파이프라인 쪽에서 스키마가 바뀌었으므로, API의 `_row_to_report`가
  참조하던 옛 키(`recent_replays`, `recent_new`)를 제거.
- TASK-008(feature, 후행): `game_news`/`sentiment_reports` 테이블을 노출하는
  `/news`, `/news/{id}`, `/sentiment`, `/sentiment/{appid}` 4개 엔드포인트 신규 추가.

## 변경 내역

### TASK-009 — `_row_to_report` 리팩터
`E:\GP\develope\fastapi-server\app\main.py`의 `_row_to_report` 함수에서
`recentReplays`(`content.get("recent_replays", [])`)와
`recentNew`(`content.get("recent_new", [])`) 키/소스 참조를 완전히 삭제했다.
현재:
```python
def _row_to_report(row: dict) -> dict:
    content = row["content"]
    return {
        "date": row["report_date"].isoformat(),
        "oldIntroductions": content.get("old_introductions", []),
    }
```
이 함수는 `/reports/latest`, `/reports/{report_id}` 두 라우트에서만 호출되므로 이
수정 하나로 두 라우트 모두 새 스키마를 반영한다. `archive_current_report`,
`list_reports`, `download_report`는 `_row_to_report`를 쓰지 않음을 재확인했다 —
`list_reports`는 `id`/`report_date`/`pdf_path`만 별도 SELECT하고,
`download_report`/`archive_current_report`는 `pdf_path`만 다루므로 이번 수정으로
인한 영향이 없다.

### TASK-008 — `/news`, `/sentiment` 엔드포인트 4종 추가
기존 `/reports/*` 라우트와 동일한 패턴(`_db_conn()` + `psycopg2.extras.RealDictCursor`,
함수형 라우트, 404는 `HTTPException(status_code=404, detail=...)`)으로 작성했다.
배치 위치는 `/health` 바로 다음, `/reports/*` 라우트들 앞이다(파일 상단에 신규
섹션을 모아 두는 편이 `/reports/*` 블록의 응집도를 해치지 않는다고 판단).

- `_row_to_news(row)` / `_row_to_sentiment(row)` 헬퍼를 `_row_to_report`와 같은
  패턴(행 dict → camelCase 응답 dict 변환)으로 신설.
- `GET /news`: `SELECT * FROM game_news ORDER BY pub_date DESC LIMIT %s OFFSET %s`,
  쿼리 파라미터 `limit`(기본 20)/`offset`(기본 0)을 FastAPI 함수 시그니처 기본값으로
  받아 그대로 바인딩.
- `GET /news/{news_id}`: `id`로 단건 조회, 없으면 404 `detail="news not found"`.
- `GET /sentiment`: `SELECT * FROM sentiment_reports ORDER BY generated_at DESC`
  (페이지네이션 없이 전체 반환, 지시서 요구사항 그대로).
- `GET /sentiment/{appid}`: `appid`로 단건 조회, 없으면 404
  `detail="sentiment report not found"`.
- `pub_date`는 NULL 가능 컬럼이므로 `row["pub_date"].isoformat() if row["pub_date"] else None`으로
  방어 처리. `generated_at`은 스키마상 `NOT NULL`이라 무조건 `.isoformat()`.
- `appid`(news 테이블 쪽)는 매칭 전 NULL 가능(04-create-news-table.sql 참고)이라
  그대로 `row["appid"]`를 반환(정수 또는 None, 별도 캐스팅 불필요 — psycopg2가 이미
  int/None으로 반환).

## 검증
- `python -m py_compile E:\GP\develope\fastapi-server\app\main.py` — TASK-009
  단독 반영 시점, TASK-008 반영 후 시점 각각 실행, 둘 다 구문 오류 없이 통과.
- `fastapi`, `psycopg2`, `boto3`, `playwright` 모듈이 로컬 환경에 설치돼 있지 않아
  `python -c "import fastapi"` 등은 `ModuleNotFoundError`로 실패 — 실제 서버 기동/런타임
  import 검증은 불가능했다. TASK-007 사례와 동일한 환경 제약이며, 해당 사실만 보고한다.
- `archive_current_report`, `list_reports`, `download_report` 등 이번 두 태스크
  범위 밖 함수는 코드를 건드리지 않았고, 최종 파일을 다시 읽어 diff가 지시받은
  범위(TASK-009: `_row_to_report` 본문, TASK-008: 신규 헬퍼 2개 + 라우트 4개)에만
  한정됨을 확인했다.
- DB 스키마 파일(`04-create-news-table.sql`, `05-create-sentiment-table.sql`)은
  읽기만 하고 수정하지 않았다.

## 최종 확정 엔드포인트 응답 스키마 (frontend 팀 계약용)

### `GET /news`, `GET /news/{news_id}`
단건은 아래 객체 그대로, 목록(`GET /news`)은 이 객체의 배열.
| 필드 | 타입 | 비고 |
|---|---|---|
| `id` | number (int) | |
| `source` | string | |
| `title` | string | |
| `excerpt` | string \| null | |
| `link` | string \| null | |
| `imageUrl` | string \| null | |
| `pubDate` | string (ISO 8601) \| null | NULL 가능 컬럼, `.isoformat()` 또는 null |
| `appid` | number (int) \| null | 매칭 전이면 null |

`GET /news`는 쿼리 파라미터 `limit`(기본 20), `offset`(기본 0)을 지원. 404 시
`{"detail": "news not found"}` (status 404).

### `GET /sentiment`, `GET /sentiment/{appid}`
단건은 아래 객체 그대로, 목록(`GET /sentiment`)은 이 객체의 배열(페이지네이션 없음).
| 필드 | 타입 | 비고 |
|---|---|---|
| `appid` | number (int) | PK |
| `name` | string | |
| `positiveCount` | number (int) | |
| `negativeCount` | number (int) | |
| `neutralCount` | number (int) | |
| `reviewCount` | number (int) | |
| `summary` | string \| null | |
| `generatedAt` | string (ISO 8601) | NOT NULL 컬럼, 항상 값 있음 |

404 시 `{"detail": "sentiment report not found"}` (status 404).

### `GET /reports/latest`, `GET /reports/{report_id}` (TASK-009로 변경됨)
| 필드 | 타입 | 비고 |
|---|---|---|
| `date` | string (ISO 8601, date) | `report_date.isoformat()` |
| `oldIntroductions` | array (GamePick[]) | `content.old_introductions`, 각 원소 필드: `appid`(int), `name`(string), `developer`(string), `publisher`(string), `ccu`(int), `positive`(int), `negative`(int), `lastRecommendedAt`(string, 파이프라인이 저장한 그대로 — API는 키 자체를 재가공하지 않고 JSONB 값을 그대로 통과시킴) |

주의: `recentReplays`, `recentNew` 키는 완전히 삭제되어 더 이상 응답에 포함되지 않는다
(이전 세그먼트까지는 있었으나 이번 리팩터로 제거됨). frontend 타입 정의 시 이 두 키를
쓰지 말 것.

404 시 `{"detail": "no reports yet"}`(`/reports/latest`) 또는
`{"detail": "report not found"}`(`/reports/{report_id}`).

## 발견한 이슈/제약사항
- 로컬 환경에 `fastapi`/`psycopg2`/`boto3`/`playwright`가 설치돼 있지 않아 실제
  서버 기동, DB 접속, 엔드포인트 응답 실측 검증은 하지 못했다. `py_compile`
  구문 검증만 수행했다(TASK-007과 동일한 환경 제약, 신규 이슈 아님).
- `GamePick.lastRecommendedAt`(및 다른 GamePick 필드)의 정확한 타입/포맷은
  `_row_to_report`가 JSONB 컬럼 값을 가공 없이 그대로 통과시키므로, 실제 값의
  형태(문자열 포맷 등)는 이전 세그먼트(data_pipelines)가 `old_introductions`를
  적재할 때 쓴 포맷을 따른다 — API 레이어에서는 이를 별도로 검증/변환하지 않는다.
  frontend 팀이 정확한 값 예시가 필요하면 실제 `weekly_reports.content` row나
  data_pipelines 세그먼트 보고서를 참고해야 한다.
- `/sentiment`는 지시서에 페이지네이션 요구사항이 없어 전체 목록을 반환하도록
  구현했다 — `sentiment_reports`는 `appid` PK 기준 게임 수만큼만 있어 `/news`보다
  행 수가 훨씬 적을 것으로 예상되지만, 향후 게임 수가 크게 늘면 페이지네이션
  추가를 고려할 필요가 있다(지시서 범위 밖이라 이번엔 추가하지 않음).

## 수정/생성 파일 목록 (절대경로)

**수정:**
- `E:\GP\develope\fastapi-server\app\main.py`
  - TASK-009: `_row_to_report` 함수 본문에서 `recentReplays`/`recentNew` 키 제거
  - TASK-008: `_row_to_news`, `_row_to_sentiment` 헬퍼 함수 신설 +
    `GET /news`, `GET /news/{news_id}`, `GET /sentiment`, `GET /sentiment/{appid}`
    라우트 4개 신설 (`/health`와 `/reports/latest` 사이에 배치)

**생성:**
- `E:\GP\report\fragment\TASK-008_TASK-009_API담당.md` (본 보고서)

## 예상 토큰 소모량: 소 (small)
이유: 문서 4개(CHANGE_REQUEST/PRD/decision-record/Coding_Rule) + 대상 파일
1개(main.py) + 참고용 스키마 2개(04-create-news-table.sql,
05-create-sentiment-table.sql) + 형식 참고용 보고서 1개(TASK-007)만 읽으면 됐고,
지시서에 두 태스크의 정확한 코드 스니펫(TASK-009)과 상세 필드 스펙(TASK-008)이
이미 명시돼 있어 별도 설계 판단 없이 그대로 반영하는 작업이었다. 신규 코드량도
헬퍼 2개 + 라우트 4개로 크지 않았고, 실행 환경(psycopg2/fastapi) 부재로
`py_compile` 구문 검증만 수행해 검증 단계 토큰도 크지 않았다.
