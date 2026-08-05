# Product Requirement Document

---

# Project Overview

## Project Name
gamer_publisher

## Project Objective
게임에 대한 정보 수집과 그에 대한 보고서 작성을 자동화하는 프로젝트

---

# User Requirements

## What do you want to build?
- Spark를 이용해 게임에 대한 정보를 수집
- Airflow로 수집 파이프라인을 자동화
- LangGraph의 서브 에이전트를 활용해 병렬 처리로 보고서 작성을 자동화
- RAG를 활용해 근거 기반 보고서 작성
- Reddit 등 커뮤니티에서 정보를 가져와 반응(여론) 분석
- 작성된 보고서를 조회/다운로드할 수 있는 웹사이트 제작

## Why are you building this?
- 할 것 없을 때 즐길 게임을 찾는 시간을 절약하기 위함
- 취업용 포트폴리오로 활용하기 위함

## Target Users
- 본인(개인 사용)뿐 아니라, 다른 사람들도 사용할 수 있는 서비스로 제공

---

# Core Features

## Required Features

- [ ] 게임 정보 수집 (Spark)
- [ ] 수집 파이프라인 자동화 (Airflow)
- [ ] 멀티 서브 에이전트 기반 보고서 작성 자동화 (LangGraph + RAG)
- [ ] 커뮤니티(Reddit 등) 반응 분석
- [ ] 보고서 조회/다운로드 웹사이트

## Priority Feature
정보 수집 (Spark) 기능을 최우선으로 구현

---

# Detailed Feature Requirements

## 게임 정보 수집 (Spark)

### Purpose
Steam, Reddit, Twitch, itch.io 등 외부 소스로부터 게임 관련 데이터를 수집하여 이후 보고서 작성 및 반응 분석의 기반 데이터로 활용

### Expected Behavior
Airflow가 스케줄에 따라 파이프라인을 트리거하면, Spark 작업이 각 외부 API/소스에서 데이터를 수집하고 정제하여 저장소(PostgreSQL/MinIO)에 적재

### Input
(추후 작성)

### Output
(추후 작성)

### Dependencies
- Dependencies: None

---

# UI / UX Requirements
미정 (추후 구체화 예정)

---

# Technical Requirements

## Preferred Language
- 데이터 수집/백엔드: Python
- 프론트엔드: TypeScript (React) — 세부 사항 미정

## Preferred Framework
- 백엔드: FastAPI
- 프론트엔드: 미정 (최후 순위로 결정 예정)

## Database
- PostgreSQL (정형 데이터)
- ChromaDB (벡터 DB, RAG용)

## Infrastructure
- Docker + 로컬 서버, Kubernetes로 오케스트레이션
- 컨테이너 구성: MinIO(오브젝트 스토리지/코드 저장소), PostgreSQL, Airflow, FastAPI 서버, ChromaDB, LangGraph 실행 서버
- CI/CD: Jenkins
- 워크플로우: Git에 코드 푸시 → MinIO에 코드 저장 → Airflow가 MinIO의 코드를 가져와 파이프라인(Spark 수집 등) 실행
- Spark 작업은 k3s(경량 Kubernetes) 위에서 Airflow의 KubernetesPodOperator로 실행, Spark History Server로 완료된 잡의 UI를 사후 조회
- 관리 UI(Airflow, Spark Driver/History Server 등)는 전부 접근 가능하도록 노출할 예정

### 메모 (2026-08-04)
- Spark 드라이버 UI(4040)와 Airflow 웹서버(8080)는 포트가 겹치지 않도록 관리 필요. Spark pod가 `hostNetwork: true`를 쓰면 여러 잡이 동시에 4040을 두고 충돌할 수 있음
- Spark 잡 종료 후에도 UI를 볼 수 있도록 History Server 도입 필요 (완료)
- 포트/네트워킹 정리는 추후 Jenkins CI/CD 파이프라인에 편입시킬 예정

### 메모 (2026-08-05) — 컨테이너 구성 확정
- 컨테이너 7개로 확정: ① k3s(쿠버네티스, Spark 워커 동적할당) ② frontend ③ fastapi-server ④ minio ⑤ airflow ⑥ langgraph-server ⑦ postgres
- postgres는 컨테이너 1개, DB 2개(`app_db`: 유저 로그인 + 프론트엔드용 gold 요약, `airflow_db`: Airflow 메타데이터)로 통합. `app_db`는 Airflow와 무관하지만 필요 시 gold 데이터를 담을 수 있음
- minio는 `datalake`(수집 원본 raw + 메달리언 가공 데이터: raw/bronze/silver/gold) 버킷과, Airflow용 코드(메달리언 스크립트 ingest/bronze/silver/gold.py + DAG)를 담는 `code` 버킷으로 구성. Airflow 컨테이너 자체에는 DAG(파이프라인 오케스트레이션 코드)만 두고, 파이프라인이 다루는 데이터는 전부 MinIO에 둠
- frontend는 기술스택 미정 상태라 placeholder(nginx) 컨테이너로만 자리 확보, 스택 확정 시 교체
- 관리 UI 포트: Airflow(8080), Spark Driver UI(4040, 잡 실행 중에만 포트포워딩), Spark History Server(18080), MinIO Console(9001) 전부 노출
- Docker 네트워크는 backend-net/app-net/k8s-net 3개로 분리 (보안 요구사항 반영)
- 상세 구현은 `develope/docker-compose.yml`, `develope/README.md`, `develope/Jenkinsfile` 참고

---

# External Tools / APIs

| Tool/API | Purpose |
|---|---|
| Reddit API | 커뮤니티 반응/여론 수집 |
| Steam API | 게임 정보 수집 |
| Twitch API | 스트리밍/시청 데이터 수집 |
| itch.io API | 인디 게임 정보 수집 |
| LLM API | 보고서 작성용 (자체 LLM 우선 시도, 불가 시 OpenAI로 대체) |

(목록은 개발 진행에 따라 추가/삭제될 수 있음)

---

# Development Rules

## Coding Style
언어별 표준 컨벤션을 따름 (Python은 PEP8/snake_case, TypeScript/React는 관용적 스타일인 camelCase/PascalCase)

## Architecture Style
- 전체 시스템: MSA (Microservice Architecture) — 수집, 파이프라인, 보고서 생성, API 서버를 독립 서비스로 분리
- 서비스 내부 구조: Layered Architecture (Router/Controller → Service → Repository)

---

# Performance Requirements

## Expected Scale
미정 (포트폴리오 단계, 추후 구체화)

## Optimization Priority
- 배치 처리(Spark/Airflow)의 처리량과 파이프라인 안정성을 우선시
- 보고서 조회 API는 캐싱(Redis 등) 도입 검토
- ChromaDB 벡터 검색 인덱스 전략(예: HNSW 파라미터) 관리
- Kubernetes는 초기엔 확장성 실습/시연 목적으로 두고, 실사용 규모에 맞춰 추후 튜닝

---

# Security Requirements
- 외부 API 키(Reddit, Steam, Twitch, itch.io, LLM)는 환경변수/Secret 관리로 다루고 코드 저장소에 하드코딩 금지
- 회원 기능 도입 시 JWT 인증 + 비밀번호 해싱(bcrypt) 적용
- LLM API 호출 비용 관리를 위한 Rate Limiting 적용
- PostgreSQL 접근 시 ORM(SQLAlchemy 등) 사용으로 SQL Injection 방지
- Jenkins CI/CD는 Credentials Store를 사용하여 시크릿 노출 방지
- Docker 네트워크 분리로 서비스 간 불필요한 접근 차단

---

# Future Plans
미정 — 개발을 진행하며 아쉬운 부분이 있으면 추가 예정

---

# Boss AI Instructions

Boss AI must:

1. Analyze all requirements.
2. Split tasks into smaller units.
3. Assign suitable AI for each task.
4. Spawn Manager AI per segment to coordinate Sub AI.
5. Follow Coding Rule.txt strictly.
6. Prioritize stability and readability.
7. Generate task workflow before development starts.

---

# Final Notes
