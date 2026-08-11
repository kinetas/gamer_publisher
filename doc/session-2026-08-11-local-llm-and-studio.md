# 세션 요약 — 2026-08-11

랭그래프 리포트 파이프라인 이어작업 + 로컬 LLM(Ollama) 연결 + LangGraph Studio/LangSmith 세팅.

## 1. 어제 하던 작업 이어서 완료

`develope/langgraph-server`에서 교열부(copy_editor) 반려→재작성 루프 기능이 코드는 완성돼 있었으나 검증이 중단된 상태였음.

- `graph.py` / `state.py` / `nodes/copy_desk.py` / `nodes/reporter.py` / `prompts.py`: 교열부가 "근거 없이 지어낸 초고"라고 판단하면(LLM이 `REWRITE_NEEDED` 응답) 기자에게 되돌려 재작성시키는 루프 (최대 1회). 재작성 루프 때문에 게임마다 완료 시점이 달라져서 `copy_editor → layout_desk`를 고정 edge 대신 `dispatch_layout_desk` 조건부 barrier로 구현.
- `.venv_check3`(로컬 가상환경)에 `pip install -r requirements.txt` 마저 완료 (한글 주석 때문에 pip이 cp949로 깨지던 문제는 `PYTHONUTF8=1`로 우회).
- `build_graph()` 컴파일 성공, mermaid 다이어그램으로 구조 확인.
- 더미 게임으로 엔드투엔드 dry-run 성공 (OPENAI_API_KEY 없어서 LLM은 placeholder로 폴백, 구조 자체는 정상).

## 2. 게임 이미지 파이프라인 연결

프론트가 게임 카드에 이미지를 전혀 안 가져오고 있었음 (`PlaceholderImage`가 순수 CSS 회색 박스였음, `GameEntry` 타입에 image 필드 자체가 없었음).

- `clients/steam_store.py`: Steam appdetails 응답에서 `header_image` 파싱 추가.
- `state.py`: `SteamDetail.image`, `CheckedDraft.image` 필드 추가.
- `nodes/copy_desk.py`: `copy_editor`가 `CheckedDraft` 만들 때 `research.steam.image` 실어나름.
- `nodes/layout_desk.py`: 최종 `content` JSON의 게임별 dict에 `"image"` 키 추가 (postgres에 그대로 저장 → fastapi-server가 필드 그대로 통과 → 프론트까지 자동으로 흐름, fastapi-server 코드 변경 불필요).
- 프론트: `types.ts`에 `image: string` 추가, `PlaceholderImage.tsx`가 `src` prop 받아 실제 `<img>` 렌더 (없거나 로드 실패시 기존 placeholder 박스로 폴백), `GameGrid.tsx`/`GameDetailRow.tsx` 연결.
- 검증: dry-run 결과 `content.old_introductions[0].image`에 실제 Steam CDN URL 확인. 프론트 `npx tsc -b` 통과.

## 3. PDF 다운로드 폴백

MinIO에 아직 archive 안 된(=이번 주처럼 최신) 리포트는 다운로드 버튼이 그냥 막혀있었음.

- `Sidebar.tsx`: `pdfUrl` 없으면 `/print/{id}?print=1`을 새 탭으로 열도록 변경 (버튼 비활성화 제거).
- `PrintReport.tsx`: `?print=1`이면 리포트 로드 후 `window.print()` 자동 호출.
- `global.css`: 다크 테마라 브라우저 기본 인쇄는 배경을 날리고 거의 흰 배경에 거의 흰 글씨가 찍히는 문제 → `print-color-adjust: exact`로 강제, `PageSheet` 단위로 페이지 나누기(`break-after: page`) 추가.
- 참고: `airflow/dags/common/postgres_load.py`의 `archive_current_report()`가 실패해도 예외를 삼키고 경고 로그만 남긴 채 파이프라인이 계속 진행되도록 설계돼 있어서, MinIO 아카이브가 조용히 실패해도 아무도 못 알아챌 수 있음 — 이번 세션에서는 실제로 재현은 안 됐음(기존 리포트 1건 PDF 다운로드 정상 확인).

## 4. 도커 스택 전체 기동 + 버그 수정

`docker compose up -d --build`로 전체 스택(postgres/minio/chromadb/fastapi-server/langgraph-server/frontend/airflow/k3s/spark) 기동.

- **버그 발견 및 수정**: `frontend` 컨테이너가 계속 죽어있었음. nginx가 부팅 시 `proxy_pass http://fastapi-server:8000/`을 한 번 resolve하는데, `docker-compose.yml`에 `depends_on`이 없어서 fastapi-server보다 먼저(또는 동시에) 뜨면 `host not found in upstream`으로 즉시 죽고, 재시작 정책도 없어서 그대로 멈춰있었음. `frontend` 서비스에 `depends_on: fastapi-server(service_started)` + `restart: unless-stopped` 추가.

## 5. LM Studio 시도 → 실패 → Ollama로 전환

**LM Studio (실패)**

- 이 컴퓨터 GPU 확인: 내장그래픽(Intel UHD 630)만 있고 별도 GPU 없음 (Device Manager 레벨에서 확인, `nvidia-smi` PATH에 없음). CPU 추론만 가능.
- `lmstudio/llmster-preview:cpu`(공식 LM Studio 헤드리스 이미지)를 임시 컨테이너에서 테스트.
- Qwen2.5-Coder 0.5B/1.5B, Llama 3.2 3B 전부 **한국어 출력이 깨짐** (짝 없는 UTF-16 low surrogate가 섞여나옴 — 모델 문제가 아니라 이미지의 CPU 백엔드 멀티바이트 디토크나이징 버그로 판단, 완전히 다른 모델 두 계열에서 동일 패턴 재현). 영어는 정상 동작.
- "Technical Preview" 딱지가 붙은 이미지라 신뢰성 판단하고 폐기, 사용자가 직접 컨테이너 삭제.

**Ollama (채택)**

- `docker-compose.yml`에 `ollama`(공식 이미지, CPU), `ollama-init`(모델 최초 1회 pull), `open-webui`(채팅 테스트용 웹 UI, 포트 3001) 서비스 추가.
- 모델: 채팅용 `qwen2.5:3b`, 임베딩용 `nomic-embed-text`.
- `.env`에 `LLM_BASE_URL=http://ollama:11434/v1`, `REPORTER_MODEL`/`COPY_DESK_MODEL`/`EDITORIAL_MODEL=qwen2.5:3b`, `EMBEDDING_MODEL=nomic-embed-text`, `LLM_CONCURRENCY=2` 설정.
- `langgraph-server/app/config.py`, `app/clients/llm.py`: `LLM_BASE_URL`/`LLM_API_KEY`로 OpenAI 대신 로컬 OpenAI 호환 서버(Ollama)에 붙을 수 있게 수정. `LLM_CONCURRENCY` env로 동시 호출 수 조절 가능하게 함 (CPU 로컬 서버는 컨테이너 하나가 사실상 순차 처리라 기본값 8 대신 2 권장).
- **사고 및 복구**: 첫 모델 로드(CPU repack 단계)가 매우 오래 걸려서(디스크 I/O 비정상적으로 큼) Docker Desktop 백엔드 전체가 응답 불능 상태에 빠짐 (`docker stop`/`kill`조차 500 에러). 사용자가 Docker Desktop을 직접 종료 후 재시작. 재기동 시 k3s 컨테이너가 cgroup 에러로 한 번 실패했으나(WSL2 cgroup 상태 잔재로 추정) 나머지 핵심 서비스는 정상 복구.
- 아직 Ollama+qwen2.5:3b의 실제 한국어 출력 품질은 (부하 문제로) 검증 완료 못함 — 다음 세션 확인 필요.

## 6. LangGraph Studio

- Studio(웹 UI, smith.langchain.com에서 로드)는 로컬에서 도는 API 서버(`langgraph dev`)에 붙어서 실행 — 코드/데이터는 전부 이 컴퓨터 안에서만 처리됨.
- `.venv_check3`에 `langgraph-cli[inmem]` 설치.
- `langgraph-server/langgraph.json` 생성: `"gamer_publisher_report": "app.graph:GRAPH"` (파일 경로가 아니라 모듈 경로로 지정해야 `app` 패키지 내부의 상대 import가 깨지지 않음).
- `langgraph-server/.env.studio` 생성: 호스트에서 직접 도니까 docker 서비스명(`postgres`, `chromadb` 등) 대신 `localhost:15432`, `localhost:8200` 등 host-published 포트로 접속하도록 별도 env 파일 구성 (`.env`와 값은 같고 접속 방식만 다름). `.gitignore`에 추가.
- **의존성 충돌**: `langgraph-cli[inmem]` 설치가 chromadb가 필요로 하는 opentelemetry 버전을 다운그레이드시켜 그래프 로드가 깨짐 (`ModuleNotFoundError: opentelemetry.exporter.otlp.proto.common._exporter_metrics`). `opentelemetry-{api,sdk,proto,exporter-otlp-proto-common,exporter-otlp-proto-grpc}==1.44.0`로 재설치해서 해결 (pip이 "다른 패키지가 1.37.0을 요구한다"고 경고하지만 실제 런타임 임포트는 정상 동작).
- 실행 확인: `http://127.0.0.1:2024`에서 API 정상 응답, 그래프(`gamer_publisher_report`) 정상 등록.
- **접속**: https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024
- **주의**: `baseUrl=127.0.0.1`은 "요청을 보내는 브라우저가 있는 컴퓨터 자기 자신"을 가리키므로, **다른 컴퓨터에서 저 링크를 열면 UI만 뜨고 그래프 실행은 안 됨.** 다른 컴퓨터에서도 쓰려면 (1) `langgraph dev`를 `0.0.0.0`으로 바인딩 + (2) `baseUrl`을 이 컴퓨터의 실제 네트워크 주소로 교체 + (3) 인증 등 보안 설정 추가가 필요 — 아직 미설정.
- **미결 사항**: 사용자가 "도커로 띄우는 게 아니냐"고 질문 → 로컬 프로세스 대신 docker-compose 서비스로 옮길지 여부는 아직 답변 대기 중.

## 7. LangSmith

- 사용자가 이미 보유한 API 키를 본인이 직접 `.env`에 추가 (`LANGCHAIN_API_KEY`).
- `docker-compose.yml`의 `langgraph-server` 환경변수에 `LANGCHAIN_TRACING_V2`/`LANGCHAIN_API_KEY`/`LANGCHAIN_PROJECT`(`gamer-publisher`) 추가 — `langchain-core`가 이미 의존성으로 깔려있어서 이 env만 채우면 코드 변경 없이 자동 추적됨.
- 확인 방법: smith.langchain.com 로그인 → Tracing Projects → `gamer-publisher`.
- 현재 상태: **`LANGCHAIN_TRACING_V2=false`로 꺼둔 상태** (`.env`, `.env.studio` 둘 다) — Studio에서 이것저것 만지는 동안 트레이싱 노이즈 없게 하려고 사용자가 요청.

## 8. 현재 접속 가능한 것들

| 항목 | 주소 | 상태 |
|---|---|---|
| 프론트엔드 | http://localhost:3000 | 정상 |
| fastapi-server | http://localhost:8000 | 정상 |
| langgraph-server (도커) | http://localhost:8100 | 정상 |
| Ollama API | http://localhost:11434 | 정상 (모델 로드시 CPU 부하 주의) |
| Open WebUI | http://localhost:3001 | 정상, 로그인 없이 사용 가능하게 설정 |
| LangGraph Studio | https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024 | 로컬 `langgraph dev` 서버(venv) 떠 있어야 동작 |
| LangSmith | smith.langchain.com → gamer-publisher 프로젝트 | 트레이싱 꺼둔 상태 |
| Airflow | http://localhost:8080 | 이번 세션에서 별도 확인 안 함 (k3s 재기동 이슈로 스킵됨) |

## 9. 다음에 이어서 할 것

- Ollama + qwen2.5:3b 실제 한국어 리포트 생성 품질 검증 (아직 부하 문제로 못 함, 재시도 시 CPU/디스크 사용량 주의).
- 이번 주 weekly report 재생성 (현재 DB에 있는 `2026-08-10` 리포트는 mock 데이터 기반).
- LangGraph Studio를 docker-compose 서비스로 옮길지 결정.
- LangGraph Studio 원격(다른 컴퓨터) 접속 필요하면 `0.0.0.0` 바인딩 + baseUrl 교체 + 인증 설정.
- k3s 컨테이너 cgroup 에러 재확인 (Airflow/Spark 쪽 재기동 필요시).
