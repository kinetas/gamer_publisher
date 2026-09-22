# Project Report

Last Update: 2026-08-19

---

# Project Status

## Current Progress
- 변경 개발 완료 — recent_games_pipeline(신작 발굴) 폐기, RSS뉴스/명작아카이브/감성분석 3섹션 재구성 완료 (모든 세그먼트 완료, 2026-08-19)

## Overall Completion
- Planning: 100%
- Core System: 100%
- Extension System(감성분석 등 신규 기능 포함): 100%
- UI/UX: 100%

---

# Current Working Tasks

모든 세그먼트 완료 (2026-08-19)

| Task | Assigned AI | Status |
|---|---|---|
| [langgraph_contracts / Layer 1] TASK-001: 신규추천 제거 + 다시추천 통합 | langgraph_contracts | 완료 |
| [langgraph_contracts / Layer 1] TASK-002: 감성분석 LLM 요약 엔드포인트 | langgraph_contracts | 완료 |
| [data_pipelines / Layer 2] TASK-003: select_weekly_report 리팩터링 | Manager AI-2 | 완료 |
| [data_pipelines / Layer 2] TASK-004: recent_games_pipeline DAG → weekly_report_pipeline DAG로 재구성 | Manager AI-2 | 완료 |
| [data_pipelines / Layer 2] TASK-005: game_news 테이블 + RSS 저장 | Manager AI-2 | 완료 |
| [data_pipelines / Layer 2] TASK-006: sentiment_pipeline DAG 신설 | Manager AI-2 | 완료 |
| [data_pipelines / Layer 2] TASK-007: RSS 게임명→appid 매칭 | Manager AI-2 | 완료 |
| [fastapi_api / Layer 3] TASK-008: GET /news, GET /sentiment 엔드포인트 | Manager AI-3 | 완료 |
| [fastapi_api / Layer 3] TASK-009: /reports/latest 응답 스키마 조정 | Manager AI-3 | 완료 |
| [frontend_sections / Layer 4] TASK-010: 라우팅/3섹션 네비게이션 | Manager AI-4 | 완료 |
| [frontend_sections / Layer 4] TASK-011: 명작 아카이브 페이지 | Manager AI-4 | 완료 |
| [frontend_sections / Layer 4] TASK-012: RSS 뉴스 페이지 | Manager AI-4 | 완료 |
| [frontend_sections / Layer 4] TASK-013: 감성분석 페이지 | Manager AI-4 | 완료 |
| [frontend_sections / Layer 4] TASK-014: PDF 아카이브용 통합 페이지 | Manager AI-4 | 완료 |

모든 세그먼트 완료 (2026-08-19) — 전체 14개 태스크(4개 세그먼트) 변경 개발 완료

---

# Patch Notes

- langgraph_contracts 완료 — WeeklyReportRequest를 old_introductions 단일 필드로 통합(recent_new 제거, recent_replays 흡수), POST /sentiment/summarize 엔드포인트 신설
- data_pipelines 완료 — recent_games_pipeline을 weekly_report_pipeline+sentiment_pipeline으로 재구성, game_news/sentiment_reports 테이블 신설, 게임메카 RSS Postgres 저장 + appid 매칭, Steam 리뷰 수집+로컬 라이브러리 1차 분류+LLM 2차 요약 파이프라인 신설
- fastapi_api 완료 — GET /news, GET /news/{id}, GET /sentiment, GET /sentiment/{appid} 엔드포인트 신설, /reports/latest 응답에서 recentReplays/recentNew 키 제거
- frontend_sections 완료 — 라우팅/네비게이션(명작 아카이브/RSS뉴스/감성분석 3섹션), RSS뉴스 페이지, 감성분석 페이지, 명작 아카이브 개명+단일 리스트 통합, PDF 아카이브 통합 페이지 완료. 전체 14개 태스크(4개 세그먼트) 변경 개발 완료.

---

# Current Issues

| Priority | Issue | Status |
|---|---|---|
| - | fastapi-server의 recent_new/recent_replays 참조 (TASK-009에서 제거 완료, /reports/latest는 이제 oldIntroductions만 반환) | 해결됨 |
| - | spark-jobs 이미지를 실제로 빌드해 `sentiment_classify.py`의 `_load_classifier()`를 구동해보니, `sentencepiece`만으로는 `cardiffnlp/twitter-xlm-roberta-base-sentiment`의 tokenizer.model을 변환하지 못해(protobuf 없이 slow-tokenizer 변환 실패 → tiktoken 폴백도 미설치라 `ModuleNotFoundError: tiktoken`) 모델 로딩이 100% 실패하는 것을 재현. `spark-jobs/requirements.txt`에 `protobuf` 추가로 수정, 클린 재빌드 후 실제 문장 2건(긍/부정) 분류까지 재검증 완료 | 해결됨 (2026-09-22) |
| 높 | 실제 k3s+Airflow 스택에서 sentiment_pipeline을 끝까지 돌려보니, `_load_classifier()`의 `pipeline(..., truncation=True)`가 이 모델의 tokenizer_config에 `model_max_length`가 제대로 안 박혀 있어(사실상 무제한 sentinel 값) 효과가 없었음. 한국어 등 비-라틴 문자 리뷰가 512토큰(모델의 실제 한계, max_position_embeddings=514)을 넘기면 `RuntimeError: index 514 is out of bounds for dimension 1 with size 514`로 배치 전체가 죽는 것을 실제 Steam 리뷰 데이터로 재현. `sentiment_classify.py`에 `max_length=512` 명시로 수정, 재검증 완료 | 해결됨 (2026-09-22) |
| 높 | `scripts/push_code_to_minio.sh` / docker-compose `dags-sync`가 `mc mirror --overwrite`만 쓰고 `--remove`가 없어서, git에서 이미 삭제된 `recent_games_pipeline.py`(2026-08-19 폐기)가 MinIO code 버킷과 Airflow dags 볼륨에 그대로 남아 스케줄러가 폐기된 파이프라인을 계속 실행 중인 것을 실제로 확인(대상 게임 검색 API 문제로 폐기됐던 그 DAG). 두 mc mirror 명령에 `--remove` 추가, 재실행으로 stale 파일 제거 및 scheduler에서 사라짐 확인 | 해결됨 (2026-09-22) |
| 중 | 로컬 postgres 볼륨이 2026-08-19 이전부터 존재해 `postgres/init/04-create-news-table.sql`, `05-create-sentiment-table.sql`이 한 번도 실행되지 않았음(entrypoint init 스크립트는 빈 볼륨에서만 실행) → `game_news`/`sentiment_reports` 테이블이 없어 gamemeca_ingest_pipeline이 `UndefinedTable` 오류로 실패 중이던 것을 실제로 확인. 두 SQL을 수동 적용(`CREATE TABLE IF NOT EXISTS`라 안전)해 해결. **배포 시 유의**: 기존 postgres 볼륨을 재사용하는 모든 환경(스테이징 등)에서 같은 문제가 재현되므로, 새 init SQL이 추가될 때마다 기존 볼륨에는 수동 마이그레이션이 필요함 | 해결됨 (2026-09-22, 로컬) — 운영 배포 시 별도 확인 필요 |
| 중 | `config.py`의 `SENTIMENT_MODEL` env var가 docker-compose.yml의 langgraph-server 환경변수 블록과 `.env.example`에 빠져 있어 항상 기본값 `gpt-4o-mini`로 고정됨 → `LLM_BASE_URL`을 로컬 ollama로 돌린 환경에서 `/sentiment/summarize`가 "model 'gpt-4o-mini' not found"로 실패하고 폴백 문구만 저장되는 것을 실제로 재현. docker-compose.yml + `.env.example` + 로컬 `.env`에 `SENTIMENT_MODEL` 추가(다른 *_MODEL과 동일 패턴), 재검증 결과 실제 로컬 LLM(qwen2.5:3b)이 생성한 정상 요약이 sentiment_reports에 저장됨을 확인 | 해결됨 (2026-09-22) |

---

# Next Targets

배포 전 검증 3항목 모두 완료 (2026-09-22, 로컬 docker compose 전체 스택(k3s 포함)을 실제로 띄워 검증):
1. HuggingFace 의존성 — spark-jobs 이미지 실제 빌드/실행, protobuf 누락 버그 발견·수정, 클린 재빌드 이미지로 모델 로딩+분류 재검증
2. MinIO 업로드 + dags-sync — push_code_to_minio.sh/dags-sync 실제 실행, `--remove` 누락으로 폐기된 recent_games_pipeline.py가 계속 실행되던 버그 발견·수정
3. sentiment_pipeline 실제 Airflow 실행 검증 — select_sentiment_targets(old_games 2612건 실데이터) → sentiment_ingest(Spark-on-k3s pod, 실제 Steam appreviews API) → sentiment_classify(HuggingFace pod, max_length 버그 발견·수정 후) → summarize_and_save(SENTIMENT_MODEL 버그 발견·수정 후 실제 로컬 LLM 요약) 전 단계 실제 성공, sentiment_reports에 실 데이터 저장 확인. 동시에 game_news/sentiment_reports 테이블 누락(구 postgres 볼륨), gamemeca_ingest_pipeline 실패도 함께 발견·해결

남은 후속 조치: 위에서 고친 5개 항목을 커밋하고, 스테이징/운영 postgres 볼륨에도 04/05번 init SQL을 수동 적용해야 함(새 볼륨이 아니면 initdb 스크립트가 자동 실행되지 않음)

---

# AI Activity Summary

| AI | Activity |
|---|---|
| Boss AI | 시스템 초기화 |
| Boss AI | /changeStart 실행 — DAG 14개 태스크를 4개 세그먼트(순차 레이어)로 분할, langgraph_contracts 세그먼트부터 시작 |
| langgraph_contracts | TASK-001 완료 — WeeklyReportRequest를 old_introductions 단일 필드로 통합(recent_new 제거, recent_replays 흡수) |
| langgraph_contracts | TASK-002 완료 — POST /sentiment/summarize 엔드포인트 신설 (감성분석 2차 LLM 요약) |
| Manager AI-2 | data_pipelines 세그먼트(TASK-003~007) 착수 |
| Manager AI-2 | data_pipelines 세그먼트(TASK-003~007) 완료 — weekly_report_pipeline/sentiment_pipeline 재구성, game_news/sentiment_reports 테이블 신설, RSS 저장 + appid 매칭 |
| Manager AI-3 | fastapi_api 세그먼트(TASK-008~009) 착수 |
| Manager AI-3 | fastapi_api 세그먼트(TASK-008~009) 완료 — GET /news, GET /news/{id}, GET /sentiment, GET /sentiment/{appid} 엔드포인트 신설, /reports/latest에서 recentReplays/recentNew 키 제거 |
| Manager AI-4 | frontend_sections 세그먼트(TASK-010~014) 착수 |
| Manager AI-4 | frontend_sections 세그먼트(TASK-010~014) 완료 — 라우팅/네비게이션 기반, 명작 아카이브 단일 리스트 통합, News/Sentiment 페이지 신설, PDF 아카이브 통합 페이지(3섹션 연속 페이지네이션) 완료 |
| Collector AI | frontend_sections 세그먼트 완료 확인 — 전체 14개 태스크(4개 세그먼트) 변경 개발 완료, report.md 최종 갱신 |

---

# Reference Fragments

(없음)
