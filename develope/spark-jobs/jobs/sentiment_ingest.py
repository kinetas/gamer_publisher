"""감성분석 파이프라인 1단계: Steam appreviews 리뷰 원문 수집(ingest).

TASK-006, doc/CHANGE_REQUEST.md 항목 3 / doc/decision-record-2026-08-19-three-
section-restructure.md "설계가 중간에 바뀐 부분: 감성분석" 참고. 이 파일은 리뷰
"수집"만 담당한다 - 로컬 감성분석 1차 분류는 별도 단계(sentiment_classify.py,
plain python)에서 하고, LLM 2차 종합은 Airflow 쪽(common/sentiment_load.py)에서 한다.

대상 appid+name 목록은 Airflow의 select_sentiment_targets(common/
sentiment_targets.py)가 미리 s3a://datalake/interim/sentiment/targets.json 에
써 둔 것을 그대로 읽는다. XCom이나 pod env var로 목록을 주입하지 않고 고정 MinIO
키로 넘기는 이유는 develope/airflow/dags/sentiment_pipeline.py 모듈 docstring
("단계 간 데이터 전달을 MinIO 고정 키로 한 이유") 참고.

appid마다 최신 리뷰 최대 100개(1페이지, cursor 페이지네이션 없음)를 가져온다 -
대표 샘플/집계용으로는 충분하고, API 호출 수를 정확히 "대상 appid 수"로 예측
가능하게 유지하기 위한 선택이다(cursor로 여러 페이지를 더 받으면 appid당 호출
수가 게임마다 들쭉날쭉해져 전체 배치 소요시간을 가늠하기 어려워진다).

raw 저장은 기존 ingest.py의 write_raw_json(append 전용, datalake/raw/의 다른
소스(steamspy_all 등)와 동일하게 "raw 영역은 계속 쌓인다"는 이 레포의 기존
컨벤션)을 그대로 재사용한다(같은 jobs/ 디렉터리에 있어 spark-submit이 이 스크립트를
직접 실행할 때 sys.path에 자동으로 잡히는 디렉터리에서 바로 import된다).

같은 게임의 리뷰가 매주 재수집되면서 raw에 중복으로 쌓이는 문제(리뷰가 매주 100개씩
새로 나오지 않는 게임이 많음)는 여기서 처리하지 않는다 - old_games_pipeline의
silver.py가 appid 기준 dropDuplicates로 bronze 중복을 해소하는 것과 동일한 원칙으로,
sentiment_classify.py가 recommendationid 기준 dedup으로 해소한다(리뷰 원본에 별도
bronze/silver 단계를 새로 만들지 않고 classify 단계에 흡수했다 - 감성분석 파이프라인
전체 규모(수백 appid x 리뷰 최대 100개)가 medallion 4단계를 따로 둘 만큼 크지 않다는
판단).
"""
import time

import requests
from pyspark.sql import SparkSession

from ingest import write_raw_json  # 기존 ingest.py 재사용 (같은 jobs/ 디렉터리)

APPREVIEWS_URL_TEMPLATE = "https://store.steampowered.com/appreviews/{appid}"
_REQUEST_TIMEOUT = 30
_NUM_PER_PAGE = 100
# appreviews는 storesearch/appdetails처럼 공식 문서상 엄격한 요청 제한이 없지만,
# 이 레포의 다른 외부 API 호출이 전부 매너 sleep을 두는 것과 동일한 원칙으로 요청
# 사이 1초를 둔다. storesearch(game_matching.py, 0.7초)보다 조금 더 보수적으로 둔
# 이유는 appreviews가 리뷰 텍스트 최대 100개를 포함해 페이로드가 더 크고, 공식
# 스토어 API라 더 무거운 호출이라는 판단 때문이다.
_REQUEST_INTERVAL_SECONDS = 1.0

TARGETS_PATH = "s3a://datalake/interim/sentiment/targets.json"
RAW_REVIEWS_PATH = "s3a://datalake/raw/steam/reviews/"


def fetch_appid_reviews(appid: int, name: str) -> list[dict]:
    """appid 하나의 최신 리뷰 최대 100개를 raw record 리스트로 변환해 반환한다.

    실패해도(네트워크 오류, 타임아웃, 예상 밖 응답) 이 레포의 다른 외부 API 호출과
    동일하게 빈 리스트를 반환하는 soft-fail로 처리하고 다음 appid로 넘어간다 -
    게임 하나 실패했다고 전체 수집 배치가 죽으면 안 된다.
    """
    try:
        response = requests.get(
            APPREVIEWS_URL_TEMPLATE.format(appid=appid),
            params={
                "json": 1,
                "filter": "recent",
                "language": "all",
                "num_per_page": _NUM_PER_PAGE,
                "purchase_type": "all",
            },
            timeout=_REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        print(f"[sentiment_ingest] appreviews 조회 실패(appid={appid}): {exc}")
        return []

    if not data.get("success"):
        return []

    records = []
    for review in data.get("reviews") or []:
        text = (review.get("review") or "").strip()
        if not text:
            continue
        records.append(
            {
                "appid": appid,
                "name": name,
                "recommendationid": review.get("recommendationid"),
                "review_text": text,
                "voted_up": review.get("voted_up"),
                "language": review.get("language"),
                "timestamp_created": review.get("timestamp_created"),
            }
        )
    return records


def main() -> None:
    spark = SparkSession.builder.appName("sentiment_ingest").getOrCreate()

    targets_df = spark.read.json(TARGETS_PATH)
    targets = [row.asDict() for row in targets_df.collect()]

    all_records: list[dict] = []
    for i, target in enumerate(targets):
        appid = target["appid"]
        name = target.get("name") or ""
        all_records.extend(fetch_appid_reviews(appid, name))
        if i < len(targets) - 1:
            time.sleep(_REQUEST_INTERVAL_SECONDS)

    write_raw_json(spark, all_records, RAW_REVIEWS_PATH)

    print(
        f"[sentiment_ingest] 대상 {len(targets)}개 appid, 수집 리뷰 {len(all_records)}건 "
        f"raw 저장 완료: {RAW_REVIEWS_PATH}"
    )

    spark.stop()


if __name__ == "__main__":
    main()
