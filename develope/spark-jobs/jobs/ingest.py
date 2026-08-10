"""메달리언 파이프라인 1단계: ingest.

POOL 환경변수로 두 가지 모드로 동작한다 (old_games_pipeline / recent_games_pipeline DAG가 각각 설정):

- POOL=old (기본값): SteamSpy `all` API를 페이지네이션으로 순회해 게임별
  소유자/리뷰 추정치를 raw로 적재한다 (옛 명작 발굴용, 월간 배치).
- POOL=recent: Steam Store 검색으로 "2개월 전 ~ 2개월 전+1주" 구간에 출시된
  게임의 appid를 뽑고, 그 appid들로 SteamSpy `appdetails`를 개별 조회해 raw로
  적재한다 (최근작 발굴용, 주간 배치). 창이 매주 한 칸씩 뒤로 밀리기 때문에
  주차별로 겹치지 않는 게임이 자연스럽게 나온다.

가공 없이 그대로 MinIO datalake 버킷의 raw 영역에 적재한다 (착륙 영역).
이후 단계(bronze.py)가 이 raw 데이터를 읽어 스키마 적용/정제를 시작한다.

SteamSpy `all` 요청은 페이지당 최대 1000개를 반환하고, 공식 문서상 요청 제한이
1req/60s라 전체 목록(수만 개)을 다 받으려면 수십 분~1시간 이상 걸린다.
빈 페이지가 나오면 전체 순회가 끝난 것으로 보고 멈춘다.
"""
import json
import os
import re
import time
from datetime import date, timedelta

import requests
from pyspark.sql import SparkSession

STEAM_APP_LIST_URL = "https://api.steampowered.com/IStoreService/GetAppList/v1/"
STEAM_SEARCH_URL = "https://store.steampowered.com/search/results/"
STEAMSPY_URL = "https://steamspy.com/api.php"

STEAMSPY_REQUEST_INTERVAL_SECONDS = 60  # SteamSpy `all` 요청 제한 (1req/60s)
# SteamSpy `appdetails`(개별 조회)는 `all`(대량 페이지)보다 가벼운 요청이라
# 공개적으로 알려진 권장치인 1req/s를 사용한다. 차단이 관측되면 늘려야 한다.
STEAMSPY_APPDETAILS_INTERVAL_SECONDS = 1
STEAM_APP_LIST_MAX_RESULTS = 50000  # IStoreService/GetAppList 페이지당 최대값

# 최근작 발굴 윈도우: 리뷰가 어느 정도 쌓이도록 "갓 나온 신작"은 제외하고,
# 출시 2개월 시점을 기준으로 1주일 폭만 본다. 파이프라인이 매주 실행되면서
# 이 창(from~to)이 달력 기준으로 한 칸씩 뒤로 밀리기 때문에, 주차별로
# 겹치지 않는 게임 목록이 자연스럽게 나온다 (recent_games 테이블의 dedup은
# 그래서 필수가 아니라 같은 주 재실행 시를 위한 안전장치).
RECENT_WINDOW_OFFSET_DAYS = 60
RECENT_WINDOW_SPAN_DAYS = 7
STEAM_SEARCH_PAGE_SIZE = 25  # Store 검색 API가 count 파라미터를 무시하고 고정 반환하는 개수
STEAM_SEARCH_MAX_PAGES = 40  # 안전장치 (최대 1000개까지)
STEAM_SEARCH_REQUEST_INTERVAL_SECONDS = 1  # 비공식 API라 너무 빨리 페이지네이션하면 429가 남

APPID_FROM_LOGO_RE = re.compile(r"/apps/(\d+)/")


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


def fetch_recent_release_appids(
    window_offset_days: int = RECENT_WINDOW_OFFSET_DAYS,
    window_span_days: int = RECENT_WINDOW_SPAN_DAYS,
) -> list[int]:
    """Steam Store 검색(비공식 API)으로 지정된 출시일 구간의 appid 목록을 가져온다.

    store.steampowered.com/search/results 는 공식 문서화된 API가 아니라 언제든
    바뀔 수 있다. count 파라미터는 무시되고 한 번에 STEAM_SEARCH_PAGE_SIZE개씩
    고정 반환하며, start로 페이지네이션한다. appid는 응답 필드에 직접 없고
    logo 이미지 URL(.../apps/{appid}/...)에서 정규식으로 추출한다.
    """
    to_date = date.today() - timedelta(days=window_offset_days)
    from_date = to_date - timedelta(days=window_span_days)

    appids: list[int] = []
    seen: set[int] = set()
    start = 0
    for i in range(STEAM_SEARCH_MAX_PAGES):
        response = requests.get(
            STEAM_SEARCH_URL,
            params={
                "query": "",
                "start": start,
                "sort_by": "Released_DESC",
                "released": "Custom",
                "from": from_date.isoformat(),
                "to": to_date.isoformat(),
                "ndl": 1,
                "supportedlang": "english",
                "json": 1,
            },
            timeout=30,
        )
        if response.status_code == 429:
            # 비공식 API라 문서화된 제한이 없다. 막히면 에러로 죽지 않고
            # 지금까지 모은 appid만으로 계속 진행한다.
            break
        response.raise_for_status()
        items = response.json().get("items", [])
        if not items:
            break
        for item in items:
            match = APPID_FROM_LOGO_RE.search(item.get("logo", ""))
            if not match:
                continue
            appid = int(match.group(1))
            if appid not in seen:
                seen.add(appid)
                appids.append(appid)
        start += STEAM_SEARCH_PAGE_SIZE
        if i < STEAM_SEARCH_MAX_PAGES - 1:
            time.sleep(STEAM_SEARCH_REQUEST_INTERVAL_SECONDS)
    return appids


def fetch_steamspy_appdetails(appids: list[int]) -> list[dict]:
    """SteamSpy `appdetails`로 appid별 소유자/리뷰 추정치를 순회 조회한다."""
    games = []
    for i, appid in enumerate(appids):
        response = requests.get(
            STEAMSPY_URL,
            params={"request": "appdetails", "appid": appid},
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        if data and data.get("appid"):
            games.append(data)
        if i < len(appids) - 1:
            time.sleep(STEAMSPY_APPDETAILS_INTERVAL_SECONDS)
    return games


def write_raw_json(spark: SparkSession, records: list[dict], path: str) -> None:
    if not records:
        return
    # 레코드마다 필드 구성이 조금씩 다를 수 있어(예: score_rank 빈 값),
    # createDataFrame 대신 JSON 문자열을 read.json으로 읽어 스키마를 합집합으로 추론한다.
    # 파티션 수가 레코드 수보다 많으면 일부 태스크가 빈 출력만 내고, MinIO(S3A)에서는
    # 이게 커밋(rename) 단계에서 "파일을 못 찾음"(RemoteFileChangedException) 오류로
    # 이어질 수 있다. 레코드 수 이하로 파티션을 맞춰 빈 파티션이 안 생기게 한다.
    num_slices = min(len(records), spark.sparkContext.defaultParallelism)
    raw_lines = spark.sparkContext.parallelize(
        (json.dumps(r) for r in records), numSlices=num_slices
    )
    df = spark.read.json(raw_lines)
    df.write.mode("append").json(path)


def main() -> None:
    spark = SparkSession.builder.appName("ingest").getOrCreate()

    pool = os.environ.get("POOL", "old")

    if pool == "recent":
        appids = fetch_recent_release_appids()
        # 개발/테스트 시 DAG의 env_vars로 RECENT_MAX_CANDIDATES를 넘겨 appdetails
        # 호출 개수를 제한한다 (appid당 1초, 미설정 시 수백 개라 10분+ 걸릴 수 있음).
        max_candidates_env = os.environ.get("RECENT_MAX_CANDIDATES", "")
        if max_candidates_env:
            appids = appids[: int(max_candidates_env)]
        games = fetch_steamspy_appdetails(appids)
        write_raw_json(spark, games, "s3a://datalake/raw/steam/steamspy_recent/")
    else:
        # steam_api_key = os.environ["STEAM_API_KEY"]
        # apps = fetch_steam_official_app_list(steam_api_key)
        # write_raw_json(spark, apps, "s3a://datalake/raw/steam/app_list/")

        # 비워두면(미설정) 전체 수집(운영 배치용, 50분+). 개발/테스트 시에는 DAG의
        # env_vars로 STEAMSPY_MAX_PAGES를 넘겨 페이지 수를 제한한다.
        max_pages_env = os.environ.get("STEAMSPY_MAX_PAGES", "")
        max_pages = int(max_pages_env) if max_pages_env else None
        games = fetch_all_steamspy_pages(max_pages=max_pages)
        write_raw_json(spark, games, "s3a://datalake/raw/steam/steamspy_all/")

    spark.stop()


if __name__ == "__main__":
    main()
