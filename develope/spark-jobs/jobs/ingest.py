"""메달리언 파이프라인 1단계: ingest.

1. Steam 공식 API(IStoreService/GetAppList)로 전체 앱(게임) 목록을 가져와 raw로 적재한다.
2. SteamSpy `all` API를 페이지네이션으로 끝까지 순회해 게임별 소유자/리뷰 추정치를 raw로 적재한다.

두 결과 모두 가공 없이 그대로 MinIO datalake 버킷의 raw 영역에 적재한다 (착륙 영역).
이후 단계(bronze.py)가 이 raw 데이터를 읽어 스키마 적용/정제를 시작한다.

SteamSpy `all` 요청은 페이지당 최대 1000개를 반환하고, 공식 문서상 요청 제한이
1req/60s라 전체 목록(수만 개)을 다 받으려면 수십 분~1시간 이상 걸린다.
빈 페이지가 나오면 전체 순회가 끝난 것으로 보고 멈춘다.
"""
import json
import os
import time

import requests
from pyspark.sql import SparkSession

STEAM_APP_LIST_URL = "https://api.steampowered.com/IStoreService/GetAppList/v1/"
STEAMSPY_URL = "https://steamspy.com/api.php"

STEAMSPY_REQUEST_INTERVAL_SECONDS = 60  # SteamSpy `all` 요청 제한 (1req/60s)
STEAM_APP_LIST_MAX_RESULTS = 50000  # IStoreService/GetAppList 페이지당 최대값


def fetch_steam_official_app_list(api_key: str) -> list[dict]:
    """IStoreService/GetAppList를 last_appid 오프셋으로 순회해 전체 앱 목록을 가져온다."""
    apps = []
    last_appid = 0
    while True:
        response = requests.get(
            STEAM_APP_LIST_URL,
            params={
                "key": api_key,
                "max_results": STEAM_APP_LIST_MAX_RESULTS,
                "last_appid": last_appid,
                "include_games": 1,
            },
            timeout=30,
        )
        response.raise_for_status()
        body = response.json()["response"]
        apps.extend(body.get("apps", []))
        if not body.get("have_more_results"):
            break
        last_appid = body["last_appid"]
    return apps


def fetch_all_steamspy_pages(max_pages: int | None = None) -> list[dict]:
    """SteamSpy `all` 엔드포인트를 page=0부터 빈 페이지가 나올 때까지 순회한다.

    페이지당 1000개, 요청 제한 1req/60s라 전체 목록(50페이지+)을 다 받으려면
    50분 이상 걸린다. max_pages가 주어지면 그만큼만 받고 멈춘다 (개발/테스트용).
    """
    games = []
    page = 0
    while max_pages is None or page < max_pages:
        response = requests.get(
            STEAMSPY_URL,
            params={"request": "all", "page": page},
            timeout=30,
        )
        response.raise_for_status()
        page_data = response.json()
        if not page_data:
            break
        games.extend(page_data.values())
        page += 1
        if max_pages is None or page < max_pages:
            time.sleep(STEAMSPY_REQUEST_INTERVAL_SECONDS)
    return games


def write_raw_json(spark: SparkSession, records: list[dict], path: str) -> None:
    # 레코드마다 필드 구성이 조금씩 다를 수 있어(예: score_rank 빈 값),
    # createDataFrame 대신 JSON 문자열을 read.json으로 읽어 스키마를 합집합으로 추론한다.
    raw_lines = spark.sparkContext.parallelize(json.dumps(r) for r in records)
    df = spark.read.json(raw_lines)
    df.write.mode("append").json(path)


def main() -> None:
    spark = SparkSession.builder.appName("ingest").getOrCreate()

    steam_api_key = os.environ["STEAM_API_KEY"]
    apps = fetch_steam_official_app_list(steam_api_key)
    write_raw_json(spark, apps, "s3a://datalake/raw/steam/app_list/")

    # 비워두면(미설정) 전체 수집(운영 배치용, 50분+). 개발/테스트 시에는 DAG의
    # env_vars로 STEAMSPY_MAX_PAGES를 넘겨 페이지 수를 제한한다.
    max_pages_env = os.environ.get("STEAMSPY_MAX_PAGES", "")
    max_pages = int(max_pages_env) if max_pages_env else None
    games = fetch_all_steamspy_pages(max_pages=max_pages)
    write_raw_json(spark, games, "s3a://datalake/raw/steam/steamspy_all/")

    spark.stop()


if __name__ == "__main__":
    main()
