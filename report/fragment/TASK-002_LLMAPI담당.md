# TASK-002 완료 보고 — 감성분석 LLM 요약 엔드포인트

## 완료 시각
2026-08-19 21:55 (KST)

## 작업 개요
게임 정보 사이트 3섹션 재구성 중 "감성분석" 섹션의 2차 종합(LLM 요약) 부분을
langgraph-server(FastAPI)에 새 엔드포인트로 추가했다. 1차 분류(경량 다국어
감성분석 라이브러리, 로컬)와 리뷰 원문 수집(Steam appreviews API)은 이번
작업 범위 밖이며, 다음 레이어의 Airflow DAG가 담당한다. 이 엔드포인트는
"이미 분류된 집계 통계 + 대표 리뷰 샘플"을 입력받아 LLM으로 "왜 그런
평가인지"를 설명하는 자연어 요약을 반환하는 역할만 한다. 리뷰 전량이 아니라
게임당 1회 LLM 호출만 발생하므로, recent_games_pipeline이 겪었던 API 병목
문제가 재발하지 않는다.

## 변경 내역 요약 (파일별)

### app/schemas.py
파일 끝에 3개 pydantic 클래스 추가 (기존 GamePick/WeeklyReportRequest는
건드리지 않음):
- `SentimentReviewSample`: 대표 리뷰 샘플 1건 (text + sentiment 라벨)
- `SentimentSummaryRequest`: 엔드포인트 요청 바디
- `SentimentSummaryResponse`: 엔드포인트 응답 바디

`Literal` 타입 사용을 위해 `from typing import Literal` import를 파일 상단에
추가했다.

### app/config.py
기존 REPORTER_MODEL/COPY_DESK_MODEL/EDITORIAL_MODEL 상수 옆에 동일 패턴으로
`SENTIMENT_MODEL = os.environ.get("SENTIMENT_MODEL", "gpt-4o-mini")` 한 줄
추가.

### app/prompts.py
새 함수 `sentiment_summary_prompt(payload: SentimentSummaryRequest) -> str`
추가. 이 프로젝트 프롬프트 함수들의 컨벤션(문자열 조립, 한국어, "게임 리포트
큐레이터 말투")을 따랐다. 프롬프트 구성:
- 게임 이름, 긍정/부정/중립 집계 수치, 전체 리뷰 수 명시
- sample_reviews를 sentiment 필드 기준으로 긍정/부정/중립 리스트로 나눠서 나열
- "왜 이런 평가를 받는지, 주요 호평 포인트와 주요 불만 포인트를 3~5문장으로
  요약해달라"는 지시
- 제공된 자료 밖의 내용을 지어내지 말라는 가드 문구(기존 reporter_prompt의
  "지어내지 마라" 패턴을 그대로 따름), 한쪽 샘플이 없으면 억지로 채우지 말고
  생략하라는 지시 포함

이 함수는 `SentimentSummaryRequest` 타입을 참조하므로 `from .schemas import
SentimentSummaryRequest`를 파일 상단에 추가했다 (schemas.py는 프롬프트/상태
모듈을 import하지 않으므로 순환 참조 없음, py_compile로 확인 완료).

### app/main.py
- import 추가: `from . import prompts`, `from .clients import llm`,
  `from .config import SENTIMENT_MODEL`, `from .schemas import
  SentimentSummaryRequest, SentimentSummaryResponse`
- 기존 `from .clients import gamemeca, rag`, `from .schemas import
  WeeklyReportRequest` 줄은 TASK-001과의 충돌 방지를 위해 절대 수정하지 않고
  그대로 두었고, 필요한 신규 import는 전부 별도 줄로 추가했다.
- 파일 끝(`/reports/weekly` 핸들러 뒤)에 새 라우트 `POST /sentiment/summarize`
  추가. 기존 `/reports/weekly` 핸들러 코드는 한 글자도 건드리지 않았다.
  - `prompts.sentiment_summary_prompt(payload)`로 프롬프트 조립
  - `llm.complete(prompt, model=SENTIMENT_MODEL, label=f"sentiment-summarize({payload.appid})")` 호출
  - LLM 미설정/호출 실패로 `None`이 반환되면
    `f"{payload.name}에 대한 리뷰 요약을 생성하지 못했습니다 (LLM 미설정 또는 호출 실패)."`
    로 폴백 (editorial_board.py의 `commentary or ""` 폴백 패턴과 동일한 취지)

## 수정한 파일 목록 (절대경로)
- E:\GP\develope\langgraph-server\app\schemas.py
- E:\GP\develope\langgraph-server\app\config.py
- E:\GP\develope\langgraph-server\app\prompts.py
- E:\GP\develope\langgraph-server\app\main.py

(위 4개 외 다른 경로는 건드리지 않았다.)

## 확정 계약: POST /sentiment/summarize

### 요청 (SentimentSummaryRequest, JSON body)
| 필드 | 타입 | 설명 |
|---|---|---|
| appid | int | Steam appid |
| name | string | 게임명 |
| positive_count | int | 라이브러리 1차 분류 긍정 리뷰 집계 수 |
| negative_count | int | 라이브러리 1차 분류 부정 리뷰 집계 수 |
| neutral_count | int | 라이브러리 1차 분류 중립 리뷰 집계 수 |
| review_count | int | 전체 리뷰 수 |
| sample_reviews | list[SentimentReviewSample] | 대표 리뷰 샘플 목록 (개수 제한 없음, 10~20개 예상) |

**SentimentReviewSample**
| 필드 | 타입 | 설명 |
|---|---|---|
| text | string | 리뷰 원문(또는 발췌) 텍스트 |
| sentiment | `Literal["positive", "negative", "neutral"]` | 라이브러리가 매긴 감성 라벨 |

예시:
```json
{
  "appid": 620,
  "name": "Portal 2",
  "positive_count": 812,
  "negative_count": 34,
  "neutral_count": 12,
  "review_count": 858,
  "sample_reviews": [
    {"text": "퍼즐 디자인이 정말 훌륭하다", "sentiment": "positive"},
    {"text": "협동 모드 매칭이 잘 안 된다", "sentiment": "negative"}
  ]
}
```

### 응답 (SentimentSummaryResponse, JSON body)
| 필드 | 타입 | 설명 |
|---|---|---|
| summary | string | LLM이 생성한 자연어 요약 리포트 (LLM 미설정/실패 시 폴백 문구) |

예시:
```json
{
  "summary": "Portal 2는 정교한 퍼즐 디자인과 완성도 높은 스토리텔링으로 폭넓은 호평을 받고 있다. ..."
}
```

## 예상 토큰 소모량
**소(小)**. 기존 클라이언트(llm.py)/스키마 패턴을 그대로 재사용했고, 신규
로직은 순수 프롬프트 조립 함수 1개 + 라우트 함수 1개 + pydantic 클래스 3개 +
상수 1개 수준으로 작고 반복적인 변경이었다. 탐색보다 확정된 계약을 그대로
받아쓰는 작업이라 파일 재탐색/재확인 비용이 낮았다.

## 이슈/특이사항
- **TASK-001과의 충돌 여부**: 없음. 작업 시작 시 schemas.py/main.py를 다시
  Read해서 TASK-001이 이미 `WeeklyReportRequest`를 `old_introductions` 단일
  필드로 축소하고 `/reports/weekly` 핸들러를 그에 맞게 수정해둔 상태를
  확인했다. 그 변경사항은 전혀 건드리지 않고 그 위에 내 변경사항(새 클래스,
  새 import 줄, 새 라우트)만 얹었다. 특히 main.py의 `from .clients import
  gamemeca, rag`, `from .schemas import WeeklyReportRequest` 줄은 지시대로
  수정하지 않고 그대로 유지했으며, `llm`/`prompts`/`SENTIMENT_MODEL`/
  `SentimentSummaryRequest`/`SentimentSummaryResponse`는 전부 별도 import
  줄로 추가해 병합 충돌 가능성을 낮췄다.
- **문법 검증**: `python -m py_compile`로 schemas.py, config.py, prompts.py,
  main.py 4개 파일 모두 컴파일 성공 확인 완료 (COMPILE_OK).
- **LLM 클라이언트 재사용**: 새 LLM 클라이언트를 만들지 않고 기존
  `app/clients/llm.py`의 `complete()`를 그대로 사용했다 — `LLM_API_KEY`
  미설정 시 자동으로 `None`을 반환하는 기존 동작을 그대로 활용해 폴백 문구
  처리했다.
