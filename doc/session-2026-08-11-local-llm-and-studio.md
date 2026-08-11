# 세션 요약 — 2026-08-11 (전체)

랭그래프 리포트 파이프라인 이어작업 → 로컬 LLM/Studio/LangSmith 세팅 → RAG 재설계 →
데이터 파이프라인 버그 수정 → **layout_desk barrier 동시성 버그 발견(미해결)**.

## 1. 어제 하던 작업 이어서 완료

`develope/langgraph-server`에서 교열부(copy_editor) 반려→재작성 루프 기능이 코드는 완성돼 있었으나 검증이 중단된 상태였음.

- `graph.py` / `state.py` / `nodes/copy_desk.py` / `nodes/reporter.py` / `prompts.py`: 교열부가 "근거 없이 지어낸 초고"라고 판단하면(LLM이 `REWRITE_NEEDED` 응답) 기자에게 되돌려 재작성시키는 루프 (최대 1회, `_MAX_REWRITES = 1`).
- `.venv_check3`(로컬 가상환경)에 의존성 설치 완료, 그래프 컴파일 + dry-run 검증 완료.
- **(주의) 이 반려/재작성 루프의 barrier 로직이 나중에(§12) 치명적 버그로 드러남.**

## 2. 게임 이미지 파이프라인 연결

프론트가 게임 카드에 이미지를 전혀 안 가져오고 있었음.

- `clients/steam_store.py`: Steam appdetails 응답에서 `header_image` 파싱 추가.
- `state.py`: `SteamDetail.image`, `CheckedDraft.image` 필드 추가.
- `nodes/copy_desk.py`/`nodes/layout_desk.py`: image를 최종 content까지 실어나름.
- 프론트: `types.ts`/`PlaceholderImage.tsx`/`GameGrid.tsx`/`GameDetailRow.tsx` 연결.

## 3. PDF 다운로드 폴백

MinIO에 아직 archive 안 된(=이번 주처럼 최신) 리포트는 다운로드 버튼이 막혀있었음.

- `Sidebar.tsx`: `pdfUrl` 없으면 `/print/{id}?print=1`을 새 탭으로 열어 브라우저 인쇄 다이얼로그 사용.
- `PrintReport.tsx`: `?print=1`이면 리포트 로드 후 `window.print()` 자동 호출.
- `global.css`: 다크 테마 인쇄 시 배경 날아가는 문제 → `print-color-adjust: exact`, `PageSheet` 단위 페이지 분할.

## 4. 도커 스택 전체 기동 + 버그 수정

- `frontend` 컨테이너가 죽어있던 버그 발견/수정: nginx가 부팅 시 `fastapi-server`를 resolve하는데 `depends_on` 없어서 race 발생 → `depends_on` + `restart: unless-stopped` 추가.

## 5. LM Studio 시도 → 실패 → Ollama로 전환

- 이 컴퓨터는 GPU 없음(Intel UHD 630 내장그래픽만) → CPU 추론만 가능.
- `lmstudio/llmster-preview:cpu`(LM Studio 공식 헤드리스 이미지) 테스트 → **한국어 출력이 깨짐**(짝 없는 UTF-16 surrogate, 서로 다른 모델 2종에서 재현) → 이미지의 CPU 백엔드 버그로 판단, 폐기.
- **Ollama로 전환**: `docker-compose.yml`에 `ollama`(공식 이미지) + `ollama-init`(모델 pull) + `open-webui`(채팅 테스트 UI, :3001) 추가. 모델: `qwen2.5:3b`(채팅), `nomic-embed-text`(임베딩).
- `config.py`/`llm.py`에 `LLM_BASE_URL`/`LLM_API_KEY`/`LLM_CONCURRENCY` 추가해 OpenAI ↔ 로컬 서버 전환 가능하게 함.
- **사고**: 첫 모델 로드(CPU repack) 중 Docker Desktop 백엔드 전체가 응답 불능(모든 API 500) → 사용자가 Docker Desktop 직접 재시작. 재기동 시 k3s가 cgroup 에러로 한 번 실패했으나 재시도로 복구(일시적 문제였음).
- 이후 OpenAI 크레딧 만료로 실제 Ollama 한국어 응답 품질은 미검증 상태 — `.env`에 Ollama 설정 6줄은 주석 처리만 해둠(나중에 주석만 풀면 복귀).

## 6. LangGraph Studio

- Studio(웹 UI)는 항상 smith.langchain.com에서 로드되지만, 실행은 로컬 `langgraph dev` 서버(`http://127.0.0.1:2024`)에서 전부 처리 — 코드/데이터는 이 컴퓨터를 안 벗어남.
- `.venv_check3`에 `langgraph-cli[inmem]` 설치. `langgraph-server/langgraph.json` 생성(`"app.graph:GRAPH"` — 모듈 경로로 써야 상대 import 안 깨짐). `langgraph-server/.env.studio` 생성(호스트에서 도니까 `localhost:포트`로 접속, `.env`와 값 같고 접속 방식만 다름).
- **의존성 충돌**: `langgraph-cli` 설치가 chromadb 필요 opentelemetry 버전을 다운그레이드시켜 그래프 로드가 깨짐 → `opentelemetry-*==1.44.0`로 재설치해서 해결.
- 접속: https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024
- **주의**: `baseUrl=127.0.0.1`은 "요청 보내는 브라우저가 있는 컴퓨터 자신"이라 **다른 컴퓨터에서 열면 UI만 뜨고 실행은 안 됨**. 다른 컴퓨터에서 쓰려면 `0.0.0.0` 바인딩 + 실제 네트워크 주소로 baseUrl 교체 + 인증 설정 필요(미설정).
- **미결**: 로컬 프로세스 대신 docker-compose 서비스로 옮길지 여부 — 답변 대기 중.

## 7. LangSmith

- 사용자가 본인 API 키를 직접 `.env`에 추가. `docker-compose.yml`의 `langgraph-server`에 `LANGCHAIN_TRACING_V2`/`LANGCHAIN_API_KEY`/`LANGCHAIN_PROJECT`(`gamer-publisher`) 추가 — `langchain-core`가 이미 의존성이라 이 env만 채우면 코드 변경 없이 자동 추적.
- 확인: smith.langchain.com → Tracing Projects → `gamer-publisher`.
- **현재 상태: `LANGCHAIN_TRACING_V2=true`로 켜져 있음** (Studio에서 이것저것 만지느라 한 번 껐다가 실전 테스트 시작하며 다시 켬).

## 8. RAG 재설계

사용자가 기존 chromadb 설계를 지적: "예전 소개 여부는 postgres로 충분한데 왜 임베딩을 쓰냐" + "RAG는 원래 PRD상 '근거 기반 보고서 작성'이 목적인데 좁게 구현됐다".

- **postgres 직접 조회로 교체**: `db.py`에 `lookup_past_writeups(appid)` 추가(weekly_reports.content JSONB를 LATERAL jsonb_array_elements로 조회). `rag.py`의 구 `lookup_by_appid`/`upsert_writeups`(chromadb `weekly_writeups` 컬렉션) 제거. `reporter.py`/`layout_desk.py` 갱신.
- **실제 근거자료 RAG 신설**: 게임메카(gamemeca.com) RSS(`rss.php`)를 소스로 채택 — robots.txt 크롤링 허용, RSS description이 실제로 짧음(600~900자, 본문 전체 아님) 확인해서 저작권 안전. 인벤은 RSS 못 찾아서 보류.
  - `clients/gamemeca.py` 신설: RSS 파싱, id/title/excerpt/link/pub_date/image_url 반환.
  - `rag.py` 재작성: `game_news_refs` 컬렉션(id=링크, document=제목+요약, metadata에 link/source/pub_date). `search_relevant_articles`(의미 검색), `upsert_articles`.
  - `state.py`: `Research.news_refs` 추가.
  - `reporter.py`: steam_detail의 genres까지 받은 뒤 게임이름+장르로 뉴스 검색, research에 포함.
  - `prompts.py`: 뉴스 요약을 참고자료로 프롬프트에 포함하고, 실제로 참고했으면 글 끝에 `출처: <링크>` 붙이게 지시(안 쓰면 안 붙임 — "라우터 방식", 본문 무단 복제 방지).
  - `main.py`: `POST /ingest/gamemeca` 엔드포인트 신설.
  - `airflow/dags/gamemeca_ingest_pipeline.py` 신설(6시간마다), `postgres_load.py`에 `ingest_gamemeca_news()` 추가.

## 9. 데이터 파이프라인 버그 수정 (spark-jobs)

실제 Airflow DAG(`recent_games_pipeline`)를 처음 돌려보고 발견한 문제들.

- **SteamSpy 이름 공백 버그**: `recent_games`의 21/23행이 name 등 필드가 빈 채로 들어옴. 원인: SteamSpy가 출시 2개월 시점(신작)의 데이터를 아직 못 채운 것(appid는 알지만 나머지 필드가 빈 "껍데기" 응답 — SteamSpy 자체의 데이터 공백, 우리 코드 버그 아님). Steam 공식 API(`store.steampowered.com/api/appdetails`, 키 불필요)로 확인하니 정상 데이터 있음 → `ingest.py`에 `fetch_steam_official_name` 폴백 추가.
- **ccu 필터가 old/recent 둘 다에 적용되던 버그**: `silver.py`의 "ccu 평균 이하만 남기기"(옛 명작 발굴용 "묻힌 게임 찾기" 필터)가 `recent` pool에도 걸려있었음 → `recent`는 이 필터 제거(평점 좋음 필터는 유지).
- **postgres 낡은 데이터**: `load_gold_to_postgres`가 upsert만 하고 삭제를 안 해서, 고치기 전 첫 실행의 빈 이름 데이터가 그대로 남아있었음 → 수동 정리 + `select_weekly_report`에도 `name IS NOT NULL AND name != ''` 방어 필터 추가.
- **DLC가 후보에 섞여 들어감**: 예시로 발견한 appid 하나가 실제로는 게임이 아니라 DLC("Clan and Crown - Supporter Pack")였음 — 별도 조치 아직 안 함(§14 참고).
- `scripts/push_code_to_minio.sh` + `docker compose run --rm dags-sync` + `scripts/load-image-to-k3s.sh`로 반영. **Git Bash에서 이 스크립트들 실행 시 `/bin/sh` 같은 유닉스 경로가 윈도우 경로로 잘못 변환되는 문제 있음 → `MSYS_NO_PATHCONV=1` 접두사로 우회.**

## 10. Spark 유지 결정 (포트폴리오 목적)

- 데이터 실측: `recent_games`는 애초에 설계상 소량(주간 몇십 개), `old_games`(SteamSpy 전체)도 4만~9만 개 수준이라 사실 Spark가 꼭 필요한 규모는 아님 — 게다가 이 인프라 전체가 물리적으로 컴퓨터 한 대라 "분산처리"의 이점도 제한적. **처음엔 Spark/k3s를 걷어내고 plain Python으로 가자고 제안했으나, 사용자가 "취업 포트폴리오 용도라 Spark는 어떻게든 써야 한다"고 명확히 함 — 이후 그 방향 존중.**
- **대안 제시**: 지금 있는 ingest 파이프라인(병목이 SteamSpy 요청 제한이라 Spark 정당화가 약함)보다, **리뷰 크롤링 + 감정분석**이 Spark를 훨씬 설득력 있게 쓸 자리 (인기 게임 하나가 리뷰 500만 개 확인함, 텍스트별 NLP 추론은 진짜 로컬 CPU 병렬화 이득이 있음).
- 사용자 결정: 매주 선정된 15개 게임 범위로(다만 신규 추천의 ccu 필터를 없애 인기 신작도 포함되게 해서 리뷰량 자체를 늘림), 감정분석은 voted_up 재활용이 아니라 **진짜 다국어 NLP 모델**(예: cardiffnlp/twitter-xlm-roberta-base-sentiment)을 Spark로 분산 추론하는 방향으로 확정. **아직 구현 시작 전(설계만 확정).**

## 11. select_weekly_report 재설계

- `recent_new`(신규 추천) 정렬을 `ccu ASC`(옛 명작 발굴과 같은 "묻힌 것 찾기" 기준)에서 `ccu DESC`(인기 신작 우선 — 리뷰도 많아짐)로 변경.
- `old_games` 수집량 확대: `OLD_SLOT_COUNT`(최종 선정 5개, 프론트 그리드 고정이라 안 건드림)가 아니라 **`steamspy_max_pages` Airflow Variable을 3→10으로 증가** (수집 단계 자체를 넓힘).
- **1년 규칙**(여러 번 정정 끝에 확정): `recent_games` 후보 풀을 `ingested_at >= now() - interval '1 year'`로 제한(1년 넘으면 old_games 영역과 개념이 겹치므로 recent 후보에서 아예 배제) + 그 안에서 `positive != 0`(리뷰 하나도 못 받은 것 배제).
- **다시 추천/신규 추천 우선순위 재설계**: 다시 추천은 `recommend_count ASC`(적게 추천된 것 우선)로 먼저 뽑고, 신규 추천은 `(first_recommended_at IS NOT NULL), recommend_count ASC, ccu DESC` 순으로 뽑되 다시 추천에 이미 뽑힌 appid는 파이썬에서 제외(여유 있게 뽑은 뒤 필터링). 코드/dags-sync 반영 완료.

## 12. ⚠️ 치명적 버그 발견 (미해결) — layout_desk barrier 동시성

실제 12개 게임(옛작품5+다시추천2+신규추천5)으로 처음 실전 테스트 → `notify_langgraph`는 200 OK로 응답하지만 **postgres에 리포트가 저장 안 됨**. 추적 결과:

- langgraph-server 로그: reporter/copy_editor 12개 전부 정상 완료(`"교열 완료"` 12번), 그런데 **`[layout_desk]` 로그가 한 번도 안 찍힘**, 응답의 `timings`도 `null`. postgres 시퀀스가 번호를 건너뛴 걸 보면 저장 시도는 있었는데 실패.
- `.venv_check3`로 LLM 없이 재현하는 격리 테스트 작성(`app.clients.llm.complete` 등을 mock) → **100% 재현 성공** (LLM 문제 아님, 순수 그래프 구조 버그).
- **버그 1 확인**: `dispatch_layout_desk`(copy_editor에서 나가는 조건부 edge)가 보는 `state`에는 `old_introductions`/`recent_replays`/`recent_new`가 전부 `None`으로 보임 → `expected`가 항상 0으로 계산됨. `checked`도 그 노드 자신의 기여분(=1)만 보이는 것으로 추정.
- **버그 2 확인**: 반려/재작성(REWRITE_NEEDED) 경로를 강제로 하나 트리거하는 테스트 → **그래프가 완전히 멈춤(5분+ 무응답)**. 실제 운영 실패도 12개 중 하나 이상이 진짜로 반려됐기 때문일 가능성이 높음.
- 결론: 어제 설계한 반려/재작성 루프의 barrier(`dispatch_layout_desk`)가 구조적으로 잘못됐다 — 패치가 아니라 재설계가 필요해 보임. **다음 세션에서 이어서 고쳐야 함.**

## 13. 현재 접속 가능한 것들

| 항목 | 주소 | 상태 |
|---|---|---|
| 프론트엔드 | http://localhost:3000 | 정상 |
| fastapi-server | http://localhost:8000 | 정상 |
| langgraph-server (도커) | http://localhost:8100 | 정상, 단 §12 버그로 실제 리포트 생성은 실패 |
| Ollama API | http://localhost:11434 | 떠있음, `.env`에서 현재 비활성(OpenAI 크레딧 만료로 스위치 필요) |
| Open WebUI | http://localhost:3001 | 정상 |
| LangGraph Studio | https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024 | 로컬 `langgraph dev`(venv) 떠 있어야 동작 |
| LangSmith | smith.langchain.com → gamer-publisher 프로젝트 | 트레이싱 켜짐 |
| Airflow | http://localhost:8080 | 정상, DAG 여러 번 실행 확인 |

## 14. 다음에 이어서 할 것 (우선순위 순)

1. **§12 layout_desk barrier 버그 수정** — 가장 시급. 반려/재작성 루프 재설계 필요.
2. 버그 수정 후 `recent_games_pipeline` 재실행해서 진짜 리포트 저장까지 확인.
3. DLC 등 게임이 아닌 항목이 후보 풀에 섞이는 문제(§9 마지막) 처리 여부 결정.
4. 리뷰 크롤링 + Spark 감정분석 파이프라인 구현 (§10에서 방향만 확정, 코드 없음).
5. OpenAI 크레딧 확보 또는 Ollama로 복귀해서 실제 텍스트 생성 품질 검증 (다른 컴퓨터 GPU로 하겠다고 하셨음).
6. LangGraph Studio를 docker-compose로 옮길지 결정 (§6 미결).
7. 인벤(Inven) RAG 소스 추가 여부 — RSS 못 찾아서 스크레이핑 방식 조사 필요.
