"""감성분석 파이프라인 마지막 단계: LLM 요약 호출(soft-fail) + sentiment_reports upsert
(TASK-006, doc/CHANGE_REQUEST.md 항목 3 / 감성분석 섹션의 "2차 종합(LLM)" 단계).

sentiment_classify.py(develope/spark-jobs/jobs/, plain python KubernetesPodOperator)가
MinIO 고정 키 s3a://datalake/interim/sentiment/results.json 에 써 둔 appid별
집계(positive/negative/neutral/review_count) + 대표 샘플(최대 15개)을 읽어,
langgraph-server의 확정 계약 POST /sentiment/summarize(SentimentSummaryRequest ->
SentimentSummaryResponse, develope/langgraph-server/app/schemas.py, main.py)를
게임별로 호출하고, 응답 summary와 이미 계산해 둔 카운트를 sentiment_reports에
upsert(ON CONFLICT appid DO UPDATE)한다.

postgres_load.py에 합치지 않고 별도 모듈로 분리한 이유: postgres_load.py는 이미
gold->postgres upsert / 주간 리포트 선정 / 외부 서비스 알림 등 여러 책임을 지고
있어(select_weekly_report, notify_langgraph, load_gold_to_postgres,
archive_current_report, ingest_gamemeca_news, upsert_gamemeca_news), 감성분석
전용 함수들을 더 얹기보다 새 모듈로 독립시키는 편이 낫다고 판단했다 - TASK-007이
같은 이유로 game_matching.py를 분리한 선례를 그대로 따른다.

LLM 호출은 계약상 LLM이 실패해도 이 엔드포인트가 항상 200 + 폴백 문구를 반환하므로
soft-fail(타임아웃/예외 시 warning 로그만 남기고 다음 appid로 진행)로 관대하게
처리한다. 다만 완전히 응답을 못 받으면(네트워크 오류/타임아웃으로 응답 자체가 없는
경우) summary는 로컬 폴백 문구(_LOCAL_FALLBACK_SUMMARY)로 채우고, 이미 계산된
positive/negative/neutral/review_count는 그대로 upsert한다 - 로컬 집계는 LLM 호출과
무관하게 sentiment_classify.py가 이미 확보해 둔 값이므로 LLM 실패로 날리지 않는다
(매니저 지시사항 그대로).
"""
import json
import logging

import boto3
import requests
from airflow.hooks.base import BaseHook
from airflow.providers.postgres.hooks.postgres import PostgresHook
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

_BUCKET = "datalake"
_RESULTS_KEY = "interim/sentiment/results.json"

LANGGRAPH_SENTIMENT_URL = "http://langgraph-server:8100/sentiment/summarize"
# weekly_report_pipeline.notify_langgraph(전체 리포트 배치 호출이라 600초)와 달리
# 게임 1개당 요약 생성 1회 호출이라 그렇게 길 필요는 없지만, LLM 콜드스타트/재시도
# 여유를 위해 넉넉히 둔다. soft-fail이라 타임아웃 나도 파이프라인은 안 죽는다.
_LLM_TIMEOUT = 120
_LOCAL_FALLBACK_SUMMARY = "리뷰 요약을 생성하지 못했습니다 (LLM 서버 응답 없음)."


def _minio_client():
    conn = BaseHook.get_connection("minio_default")
    return boto3.client(
        "s3",
        endpoint_url="http://minio:9000",
        aws_access_key_id=conn.login,
        aws_secret_access_key=conn.password,
    )


def _fetch_results() -> list[dict]:
    client = _minio_client()
    try:
        body = client.get_object(Bucket=_BUCKET, Key=_RESULTS_KEY)["Body"].read()
    except ClientError as exc:
        logger.info(
            "sentiment classify 결과(%s) 없음 - classify 단계가 아직 안 돌았거나 "
            "대상/리뷰가 0개일 수 있음, 스킵 (%s)",
            _RESULTS_KEY, exc,
        )
        return []

    try:
        return json.loads(body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        logger.warning("sentiment classify 결과 파싱 실패: %s", exc)
        return []


def _summarize(entry: dict) -> str:
    """계약(SentimentSummaryRequest)에 맞춰 payload를 구성해 langgraph-server를
    호출한다. 실패해도 예외를 올리지 않고 로컬 폴백 문구를 반환한다(soft-fail).
    """
    payload = {
        "appid": entry["appid"],
        "name": entry.get("name") or "",
        "positive_count": entry.get("positive_count", 0),
        "negative_count": entry.get("negative_count", 0),
        "neutral_count": entry.get("neutral_count", 0),
        "review_count": entry.get("review_count", 0),
        "sample_reviews": entry.get("sample_reviews", []),
    }
    try:
        response = requests.post(LANGGRAPH_SENTIMENT_URL, json=payload, timeout=_LLM_TIMEOUT)
        response.raise_for_status()
        summary = response.json().get("summary")
        if not summary:
            raise ValueError("summary 필드 없음/빈 값")
        return summary
    except (requests.RequestException, ValueError, KeyError) as exc:
        logger.warning("sentiment summarize 호출 실패(appid=%s): %s", entry.get("appid"), exc)
        return _LOCAL_FALLBACK_SUMMARY


def summarize_and_save() -> None:
    """appid별로 LLM 요약을 받아 sentiment_reports에 upsert한다."""
    entries = _fetch_results()
    if not entries:
        logger.info("감성분석 대상 결과 없음, sentiment_reports upsert 스킵")
        return

    conn = PostgresHook(postgres_conn_id="postgres_app").get_conn()
    saved = 0
    try:
        with conn.cursor() as cur:
            for entry in entries:
                if not entry.get("appid"):
                    continue
                summary = _summarize(entry)
                cur.execute(
                    """
                    INSERT INTO sentiment_reports
                        (appid, name, positive_count, negative_count, neutral_count,
                         review_count, summary, generated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, now())
                    ON CONFLICT (appid) DO UPDATE SET
                        name = EXCLUDED.name,
                        positive_count = EXCLUDED.positive_count,
                        negative_count = EXCLUDED.negative_count,
                        neutral_count = EXCLUDED.neutral_count,
                        review_count = EXCLUDED.review_count,
                        summary = EXCLUDED.summary,
                        generated_at = now()
                    """,
                    (
                        entry["appid"],
                        entry.get("name") or "",
                        entry.get("positive_count", 0),
                        entry.get("negative_count", 0),
                        entry.get("neutral_count", 0),
                        entry.get("review_count", 0),
                        summary,
                    ),
                )
                # appid 하나가 LLM 타임아웃 등으로 오래 걸려도, 이미 upsert한 앞
                # 게임들이 이후 예외로 롤백되지 않도록 매 행마다 commit한다.
                conn.commit()
                saved += 1
    finally:
        conn.close()

    logger.info("sentiment_reports upsert 완료: %d/%d행", saved, len(entries))
