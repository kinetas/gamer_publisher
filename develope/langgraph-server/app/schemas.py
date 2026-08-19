"""외부(Airflow)에서 들어오는 요청의 pydantic 모델. main.py에서 분리."""
from typing import Literal

from pydantic import BaseModel


class GamePick(BaseModel):
    appid: int
    name: str
    developer: str | None = None
    publisher: str | None = None
    ccu: int | None = None
    positive: int | None = None
    negative: int | None = None
    last_recommended_at: str | None = None


class WeeklyReportRequest(BaseModel):
    old_introductions: list[GamePick]


class SentimentReviewSample(BaseModel):
    text: str
    sentiment: Literal["positive", "negative", "neutral"]


class SentimentSummaryRequest(BaseModel):
    """감성분석 2차 종합(LLM) 요청. 라이브러리가 1차 분류한 리뷰 집계 통계와
    대표 리뷰 샘플만 받는다 — 리뷰 원문 전량은 이 서비스 범위 밖(Airflow
    감성분석 DAG가 처리)이라 여기로 들어오지 않는다.
    """

    appid: int
    name: str
    positive_count: int
    negative_count: int
    neutral_count: int
    review_count: int
    sample_reviews: list[SentimentReviewSample]


class SentimentSummaryResponse(BaseModel):
    summary: str
