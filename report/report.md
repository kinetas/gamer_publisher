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
| 중 | sentiment_pipeline은 Airflow 미설치 샌드박스라 실제 DAG 실행 미검증 — 배포 후 1회 실행 확인 필요 | 확인 필요 |
| - | fastapi-server의 recent_new/recent_replays 참조 (TASK-009에서 제거 완료, /reports/latest는 이제 oldIntroductions만 반환) | 해결됨 |

---

# Next Targets

변경 개발 완료 — 배포 후 검증 필요 항목: (1) sentiment_pipeline Airflow 실제 실행 검증, (2) weekly_report_pipeline/sentiment_pipeline을 scripts/push_code_to_minio.sh로 MinIO에 반영 후 dags-sync, (3) HuggingFace 감성분석 모델 의존성이 실행 환경(requirements.txt/Dockerfile)에 실제로 설치되는지 확인

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
