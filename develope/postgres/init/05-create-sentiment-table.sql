-- 감성분석 섹션(TASK-006, doc/CHANGE_REQUEST.md 항목 3)의 최종 산출물 저장소.
-- appid별로 Steam 리뷰 원문을 로컬 경량 다국어 감성분석 라이브러리(HuggingFace
-- transformers, cardiffnlp/twitter-xlm-roberta-base-sentiment)로 1차 분류해 집계한
-- positive/negative/neutral_count와, 그 집계+대표 샘플을 langgraph-server
-- (POST /sentiment/summarize)에 보내 받은 "왜 그런 평가인지" 자연어 요약(summary)을
-- 함께 담는다. 파이프라인 상세: develope/airflow/dags/sentiment_pipeline.py.
--
-- old_games/recent_games/game_news 중 어느 테이블에서 유래한 appid든 섞여 들어올 수
-- 있고(대상 appid는 세 테이블의 합집합), 대상 게임이 나중에 그 테이블들에서
-- 사라져도(예: old_games 풀 갱신) sentiment_reports는 독립적으로 남는 별도의 요약
-- 테이블이라 FK는 걸지 않는다(game_news.appid가 FK 없이 독립적으로 존재하는 것과
-- 같은 이유, 04-create-news-table.sql 참고).
--
-- appid: PK. 같은 게임은 매주 재계산되어 upsert(ON CONFLICT DO UPDATE)된다.
-- generated_at: 이 요약이 마지막으로 (재)생성된 시각. summary가 LLM 실패로 로컬
-- 폴백 문구로 채워져도 로컬 집계(카운트)는 이미 확보된 값이라 그대로 저장하고
-- generated_at은 갱신한다 (develope/airflow/dags/common/sentiment_load.py 참고).
CREATE TABLE IF NOT EXISTS sentiment_reports (
    appid           INTEGER PRIMARY KEY,
    name            TEXT NOT NULL,
    positive_count  INTEGER NOT NULL DEFAULT 0,
    negative_count  INTEGER NOT NULL DEFAULT 0,
    neutral_count   INTEGER NOT NULL DEFAULT 0,
    review_count    INTEGER NOT NULL DEFAULT 0,
    summary         TEXT,
    generated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
