# Change Request

Date: 2026-08-19

## Summary
`recent_games_pipeline`(신작 발굴)이 Steam 비공식 검색 API의 한계로 느리고 히트율이 낮아 실효성이 없다고 판단, 이를 폐기하고 사이트를 3개 섹션(RSS 뉴스 / 명작 아카이브 / 감성분석) 체제로 재구성한다. 기존 `old_games_pipeline`(구작 명작 발굴)의 컨셉과 로직은 그대로 유지하되 섹션 제목만 변경한다.

## Problems & Complaints
- `recent_games_pipeline`이 "최근 N개월 + 리뷰 M개 이상" 신작을 발굴하는 방식이 Steam 비공식 검색 API 한계로 느리고(수십 분) 히트율이 낮음(수십 개 중 1~2개). 상세 원인은 `doc/recent-games-discovery-investigation.md` 참고
- 이 문제를 반복하지 않기 위해, 사이트에 이미 노출되는 게임(명작 아카이브, RSS 뉴스)의 알려진 appid만 다루고 "미지의 신작을 카탈로그 전체에서 찾아내는" 방식은 다시 쓰지 않는다

## Requested Changes

### 1. RSS 뉴스 섹션 신설 (recent_games_pipeline 대체)
- Type: feature (기존 기능 폐기 + 신규 대체)
- Current: `recent_games_pipeline`이 Steam 검색 API로 신작을 능동 발굴 시도 (느리고 저효율)
- Desired: 게임 미디어 RSS 피드를 구독해 최신 소식을 그대로 노출하는 섹션으로 대체. 1차로 게임메카 RSS만 연동하고, 이후 여러 매체로 확장 가능한 구조로 설계 (RSS 소스 목록을 설정/추가 가능하게)
- Priority: high

### 2. "오래된 게임" → "명작 아카이브" 개명
- Type: improvement (이름 변경, 로직 불변)
- Current: `old_games_pipeline`이 SteamSpy 기반으로 구작 명작을 발굴해 "오래된 게임" 섹션으로 노출
- Desired: 파이프라인 로직/컨셉은 완전히 그대로 유지하고, 프론트엔드 섹션 제목만 "명작 아카이브"로 변경
- Priority: medium

### 3. 감성분석 섹션 신설
- Type: feature
- Current: 없음. 리뷰 원문 텍스트는 현재 데이터레이크 어디에도 수집되어 있지 않음 (SteamSpy는 positive/negative **집계 숫자**만 제공, 원문 없음)
- Desired:
  - **신규 수집**: Steam 공식 `appreviews` API로 appid별 리뷰 원문 텍스트를 수집하는 ingest job 추가
  - **대상 게임 appid 확보**: 명작 아카이브는 `old_games_pipeline`이 이미 보유한 appid 재사용, RSS 뉴스는 기사에서 추출한 게임명을 Steam 공식 `storesearch`(이름 검색) API로 appid 매칭 — 카탈로그 전체를 순회하는 발굴이 아니라 이름 검색 1콜이므로 항목 1의 문제와 무관
  - **1차 분류(라이브러리, 로컬)**: 경량 사전학습 다국어 감성분석 라이브러리(HuggingFace transformers 기반)로 리뷰 원문 전량을 긍/부정/점수로 분류. API 호출 없이 로컬 처리라 비용/속도 이슈 없음
  - **2차 종합(LLM, 배치)**: 라이브러리 분류 결과 집계 + 대표 리뷰 샘플을 기존 LLM 파이프라인(자체 LLM 우선, OpenAI fallback)에 배치로 넣어 "왜 그런 평가인지" 요약 리포트 생성. 전체 리뷰가 아니라 요약/샘플만 LLM에 넣으므로 호출량 적음
  - **섹션 성격**: 명작 아카이브(항목 2)에 종속되지 않는 독립 섹션. 단, 분석 대상은 명작 아카이브 + RSS 뉴스에 노출되는 게임들로 한정 (사이트에 이미 등장하는 게임 범위와 일치)
- Priority: low

## Out of Scope
- 인프라(Airflow, Spark, k3s, Docker 네트워크 구성 등)와 DB 스키마는 원칙적으로 변경하지 않음
- 변경이 꼭 필요한 경우, 먼저 사용자에게 확인 질문 후 진행

## Priority Order
1. RSS 뉴스 섹션 신설 (recent_games_pipeline 대체)
2. "오래된 게임" → "명작 아카이브" 개명
3. 감성분석 섹션 신설
