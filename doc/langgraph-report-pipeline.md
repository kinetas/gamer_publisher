# LangGraph 뉴스룸 병렬 파이프라인

`langgraph-server`(주간 게임 리포트 게임별 소개글 생성)를 언론사 편집국 조직도에
대응시켜 실제로 LangGraph `Send`/`Command` 기반 병렬 그래프로 재작성한 작업 기록.
2026-08-10 작업. 원본 계획서: `C:\Users\Administrator\.claude\plans\deep-crunching-leaf.md`.

---

## 배경 / 이전 상태

`develope/langgraph-server`는 이름과 달리 LangGraph를 전혀 쓰지 않았다.
`app/main.py` 하나뿐이었고, 15개 게임(옛 작품5/다시추천5/신규5)을 `for` 루프로
순회하며 OpenAI를 순차 호출하는 평범한 FastAPI 엔드포인트였다. `langgraph`/
`langchain`/`chromadb`는 `requirements.txt`에 있었지만 실제로는 어디서도
import되지 않는 죽은 의존성이었고, Reddit(`praw`)도 `.env.example`에 자리만
있을 뿐 코드가 없었다.

---

## 설계: 조직도 → LangGraph 매핑

```
편집국장 (진입점, 15개 게임을 3개 카테고리로 분배)
  ├─ 옛 작품 데스크(5)   ─┐
  ├─ 다시 추천 데스크(5) ─┼─ 3개 데스크 병렬
  └─ 신규 추천 데스크(5) ─┘
       └─ 각 데스크 내부: 기자 5명 병렬 (취재+초고)
  (차장 스킵)
  ── 15개 초고 fan-in ──
  교열부 — 게임별 병렬로 Reddit 반응 대조(사실체크)
  ── fan-in ──
  편집부 — 최종 취합 + 저장 + RAG 인덱싱 (LLM 호출 없음)
  (논설위원실 — 노드 코드는 작성, 그래프 등록은 주석 처리: 토큰 비용 때문에 비활성)
```

**스코프 결정 두 가지:**
- Steam 장르/설명은 postgres에 저장하지 않음 — 선정된 15개에만 매주 라이브로
  fetch(무료, 키 불필요). 과거 Steam Store 호출 429 이력(`doc/error.md` #13)이
  있어 대량 확장은 피함.
- 편집부는 LLM 호출 없이 취합+저장만 함 — 프론트(`GameEntry` 타입,
  `ReportDocument.tsx`)에 헤드라인/총평을 보여줄 자리가 아예 없어서, 안 보여줄
  텍스트를 LLM으로 쓰는 건 토큰 낭비.

Airflow DAG(`recent_games_pipeline`)이 15개 게임을 선정해 `POST /reports/weekly`로
넘기는 계약은 그대로 유지 — `weekly_reports.content`의 `old_introductions/
recent_replays/recent_new` 키, 게임당 8개 필드(`appid,name,developer,publisher,
positive,negative,ccu,description`)가 `fastapi-server`(`_row_to_report`)와
프론트 타입까지 이어지는 하드 컨트랙트라서.

---

## 그래프 토폴로지

```python
from langgraph.graph import StateGraph, START, END
from langgraph.types import Send, Command   # langgraph>=1.2,<2
```

```
START → editor_in_chief
           │ add_conditional_edges(dispatch_desks, ["desk"]) → 3×Send
           ▼
         desk (×3)
           │ Command(update={"logs":[...]}, goto=[Send("reporter", …)×5])
           ▼
       reporter (×15, 한 superstep에 전부 착지)
           │ add_edge("reporter", "copy_desk")   ← barrier
           ▼
      copy_desk (barrier)
           │ add_conditional_edges(dispatch_copy_editors, ["copy_editor"]) → 15×Send
           ▼
     copy_editor (×15 병렬)
           │ add_edge("copy_editor", "layout_desk")
           ▼
      layout_desk → END
```

`editor_in_chief`/`copy_desk`는 일반 edge로 도달해 표준 `add_conditional_edges`를
쓰고, `desk → reporter`(Send로 도달한 노드가 다시 Send로 fan-out하는 유일한
구간)만 `Command(goto=[Send, ...])`를 쓴다. 신형 API 표면을 이 한 군데로
최소화했다.

`drafts`/`checked`/`logs` state 채널은 `Annotated[list[X], operator.add]`로
병렬 브랜치의 결과를 누적한다 — 도착 순서가 비결정적이라, 각 `GameRef`에
`order_index`를 부여해 `layout_desk`가 `(category, order_index)` 기준으로
재정렬한다 (프론트는 카테고리당 고정 5칸 그리드라 순서가 틀어지면 바로 티가 남).

---

## 모듈 구조

```
develope/langgraph-server/app/
  main.py            # FastAPI만. /health, /graph(디버그 mermaid), /reports/weekly
  config.py          # env, 세마포어, 모델명
  schemas.py         # GamePick / WeeklyReportRequest
  state.py           # TypedDict + reducer
  graph.py           # build_graph() -> 컴파일된 그래프 싱글턴(GRAPH)
  prompts.py         # 한국어 프롬프트 조립 함수
  nodes/
    editor_in_chief.py   # 편집국장 + dispatch_desks
    desk.py               # 데스크 (Command(goto=[Send]))
    reporter.py           # 기자 (취재 3종 동시 조회 + 초고 LLM 1회)
    copy_desk.py           # 교열부 barrier + copy_editor
    layout_desk.py          # 편집부 (LLM 없음)
    editorial_board.py      # 논설위원실 (그래프 미등록)
  clients/
    _retry.py          # 429/5xx 지수 백오프
    http.py             # 공유 httpx.AsyncClient (lifespan 관리)
    steam_store.py       # Steam Store 공식 appdetails(KR)
    reddit.py             # praw, 스레드로컬 인스턴스
    rag.py                 # chromadb, appid 메타데이터 필터 조회 + 배치 임베딩 upsert
    llm.py                  # AsyncOpenAI 래퍼, 키 없으면 None
    db.py                    # weekly_reports upsert
```

### 노드별 책임

| 노드 | LLM | 역할 |
|---|---|---|
| `editor_in_chief` | ✗ | 3리스트 정규화, category+order_index 부여 |
| `desk` (×3) | ✗ | 데스크 배정 로그, 기자 5명에게 Send |
| `reporter` (×15) | ✓1회 | 취재(Steam/Reddit/RAG 동시 조회, 각각 실패 시 degrade) + 초고 |
| `copy_desk` (barrier) | ✗ | 15개 draft 확인 후 15-way Send |
| `copy_editor` (×15) | ✓1회 | reporter가 가져온 자료 재사용해 사실체크(재수집 없음) |
| `layout_desk` | ✗ | 재정렬, content 조립, postgres 저장, chromadb 인덱싱 |
| `editorial_board` | ✓1회 | 총평 — 그래프 미등록 |

### 외부 클라이언트 핵심 결정

- **Steam Store**: 공식 `appdetails?l=korean&cc=kr`, 공개 API(키 불필요), 앱당 1콜.
- **Reddit(praw)**: read-only script app. praw는 스레드 비안전이라
  `threading.local()`로 스레드별 인스턴스. 크레덴셜 없으면 조용히 `None`.
- **chromadb RAG**: "같은 게임 과거 글 조회"는 벡터 검색이 아니라
  `collection.get(where={"appid": appid})` 메타데이터 필터(exact match가 맞는
  질문이라). 임베딩은 chroma 내장 EF(동기, onnx 모델 필요) 대신
  `AsyncOpenAI().embeddings.create(...)`로 15개를 배치 1콜로 직접 계산해서 upsert.
  의존성은 풀버전 `chromadb` 대신 경량 `chromadb-client==1.0.21` +
  서버 이미지 `chromadb/chroma:1.0.21`로 버전 고정(레포 전체가 버전 미고정
  관례인데 이 두 패키지만 예외 — 메이저 업이 조용히 빌드를 깨는 케이스라서).
- **동시성 안전장치**: `STEAM_SEM=4`, `REDDIT_SEM=3`, `LLM_SEM=8`,
  `CHROMA_SEM=4` (`doc/error.md` #13의 Steam 429 재발 방지).

---

## 변경 파일

**신규**: `app/config.py`, `state.py`, `schemas.py`, `graph.py`, `prompts.py`,
`nodes/*.py`(6개), `clients/*.py`(6개)

**수정**:
- `app/main.py` — 얇게 재작성, `async def`, `?dry_run=true` 지원
- `requirements.txt` — `langgraph>=1.2,<2`, `chromadb-client==1.0.21` 고정,
  `praw`/`httpx` 추가, 미사용 `langchain` 제거
- `develope/docker-compose.yml` — `chromadb` 이미지 태그 고정, `langgraph-server`에
  `REDDIT_CLIENT_ID/SECRET/USER_AGENT` 추가
- `develope/.env.example` — `REDDIT_USER_AGENT` 추가
- `develope/airflow/dags/common/postgres_load.py` — `notify_langgraph` 타임아웃
  120→600초 (새 파이프라인 정상 케이스가 45~60초로 늘어나서)
- `develope/.gitignore` — `__pycache__/`, `*.pyc` 추가

**out of scope**: Spark job/postgres 스키마 변경 없음, 프론트엔드 변경 없음,
Airflow DAG 태스크 구조/payload 변경 없음(타임아웃 한 줄 제외).

---

## 검증 결과

로컬 venv + 실제 docker compose 스택으로 직접 실행해서 확인:

1. **Send/Command 스모크 테스트** — 장난감 그래프로 `Command(goto=[Send, Send])`
   fan-out이 langgraph 1.2.10에서 기대대로 동작 확인 (3×2=6개 도착).
2. **Docker 빌드** 성공 — onnxruntime/torch 없이 경량 이미지.
3. **`/graph` mermaid** — 설계와 정확히 일치하는 토폴로지, `editorial_board`
   노드 없음 확인.
4. **chromadb 클라이언트/서버(1.0.21) 호환** 확인 (`heartbeat`, 컬렉션 생성).
5. **실제 게임 15개 dry-run** — Steam Store 실제 API 15콜 포함 총 0.93초.
   15개 `reporter`의 시작 시각이 전부 `t_start=+0.00s`로 클러스터링 → 순차가
   아니라 진짜 병렬 확인 (순차였다면 최소 몇 배 소요).
6. **계약 회귀 없음** — `weekly_reports.content` 최상위 키 정확히 3개
   (`old_introductions/recent_replays/recent_new`), 게임 객체 정확히 8개 필드.
   `fastapi-server` → 프론트 camelCase(`oldIntroductions` 등) 왕복까지 확인.
7. **Degrade 경로** — `OPENAI_API_KEY`/`REDDIT_CLIENT_ID`/`SECRET` 비어있는
   실제 `.env` 상태에서 500이 아니라 200 + placeholder 텍스트로 정상 응답,
   chroma upsert는 "임베딩 생성 불가"로 로그만 남기고 조용히 스킵.
8. **Airflow 통합** — DAG 코드를 MinIO에 재업로드(`push_code_to_minio.sh` +
   `dags-sync`) 후 `airflow tasks test recent_games_pipeline notify_langgraph`로
   실제 HTTP 호출 확인. soft-fail 계약(태스크 자체는 SUCCESS 유지) 그대로 동작.

### 환경상 못 돌려본 것

`.env`에 `OPENAI_API_KEY`/`REDDIT_CLIENT_ID`/`SECRET`이 비어 있어서:
- 실제 LLM이 쓴 소개글, 실제 Reddit 반응이 반영된 결과물은 미확인 (키 채우면
  바로 확인 가능 — 그 전까지는 전부 placeholder로 정상 degrade됨)
- RAG 2회차("같은 게임 이전 글 재사용, 표현 안 겹치게") 효과는 임베딩이 있어야
  검증 가능
- `select_weekly_report`를 포함한 전체 DAG 트리거는 의도적으로 안 돌림 — 이
  태스크가 postgres의 실제 추천 이력(`first/last_recommended_at`,
  `recommend_count`)을 진짜로 갱신하기 때문에, 필요하면 별도로 요청해서 돌릴 것.

---

## 다음에 할 일 (필요 시)

- `.env`에 `OPENAI_API_KEY`, `REDDIT_CLIENT_ID`/`SECRET` 채우고 실제 LLM
  결과물 + Reddit 반응 반영 확인
- 원하면 `airflow dags trigger recent_games_pipeline`로 진짜 주간 파이프라인
  end-to-end 실행
- 논설위원실(총평) 필요해지면 `graph.py`의 주석 3줄만 풀면 됨(4줄 변경)
