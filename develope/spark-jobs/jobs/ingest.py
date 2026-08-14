"""메달리언 파이프라인 1단계: ingest.

POOL 환경변수로 두 가지 모드로 동작한다 (old_games_pipeline / recent_games_pipeline DAG가 각각 설정):

- POOL=old (기본값): SteamSpy `all` API를 페이지네이션으로 순회해 게임별
  소유자/리뷰 추정치를 raw로 적재한다 (옛 명작 발굴용, 월간 배치).
- POOL=recent: Steam Store 검색(평가 좋은 순)으로 "출시일 기준 3개월 전 ~ 오늘"
  구간에 출시된 게임 중 DLC/사운드트랙/데모 등을 뺀 진짜 게임(type=="game")의
  appid를 뽑고, 그 appid들로 SteamSpy `appdetails`를 개별 조회해 raw로
  적재한다 (최근작 발굴용, 주간 배치). 창이 매주 조금씩 밀리므로, 재실행은
  새 후보 발굴과 이미 아는 appid들의 positive/negative/ccu 갱신을 겸한다.

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
from datetime import date, datetime, timedelta

import requests
from pyspark.sql import SparkSession

STEAM_APP_LIST_URL = "https://api.steampowered.com/IStoreService/GetAppList/v1/"
STEAM_SEARCH_URL = "https://store.steampowered.com/search/results/"
STEAM_APPDETAILS_URL = "https://store.steampowered.com/api/appdetails"
STEAMSPY_URL = "https://steamspy.com/api.php"

STEAMSPY_REQUEST_INTERVAL_SECONDS = 60  # SteamSpy `all` 요청 제한 (1req/60s)
# SteamSpy `appdetails`(개별 조회)는 `all`(대량 페이지)보다 가벼운 요청이라
# 공개적으로 알려진 권장치인 1req/s를 사용한다. 차단이 관측되면 늘려야 한다.
STEAMSPY_APPDETAILS_INTERVAL_SECONDS = 1
STEAM_APP_LIST_MAX_RESULTS = 50000  # IStoreService/GetAppList 페이지당 최대값

# 최근작 발굴 창: 출시일 기준 "3개월 전부터 오늘까지"를 매번 훑는다. 1개월로
# 해봤더니(실측) sort_by=Reviews_DESC 조합에서 밀도가 너무 낮았다 - 이 정렬은
# 이미 평판이 쌓인 게임 위주라, 출시 30일 이내 게임은 아무리 좋아도 그 정도
# 평판을 쌓을 시간이 없어서 상위권에 잘 안 나온다. 몇 개월 정도는 지나야
# Reviews_DESC 앞쪽에 등장할 시간이 생긴다.
#
# 실측으로 확인한 중요한 제약: store.steampowered.com/search/results 의
# released=Custom&from=&to= 날짜 필터는 sort_by 값과 무관하게 완전히 무시된다 -
# 뭘 넘기든 그냥 "지금 인기/최신 목록"만 반환한다(PUBG/Palworld 같은 상시
# 인기작이나, 요청한 과거 구간과 무관하게 항상 오늘 날짜 게임만 나오는 걸
# 직접 확인함). 그래서 이 API로는 서버 쪽 날짜 필터링이 불가능하다.
#
# 또한 sort_by=Released_DESC(출시일순)로 최신순 훑기도 시도해봤는데, Steam이
# 하루에도 저품질 신작을 수백 건씩 등록하는 탓에 최신 100개를 확인해도 전부
# 리뷰 0개였다(실측). 그래서 discover_recent_game_appids는 sort_by=Reviews_DESC
# (평가 좋은 순)로 후보를 받고, 후보마다 Steam 공식 appdetails로 실제 출시일을
# 직접 확인해 이 창 안에 있는 것만 남긴다 - "일단 평가 좋은 순으로 넓게 긁고
# 하나하나 실제 값으로 거른다". 1년처럼 넓은 창에서는 이 방식으로도 몇백 번째
# 안에 리뷰 있는 최근작이 나왔지만(실측), 창을 1개월로 좁히면 그 안에서 조건에
# 맞는 후보를 만날 확률이 낮아지므로 STEAM_SEARCH_MAX_PAGES를 넉넉히 잡는다.
RECENT_WINDOW_SPAN_DAYS = 90
# 긍정 리뷰 100개 미만은 postgres(recent_games)에 저장조차 하지 않는다 -
# select_weekly_report(airflow/dags/common/postgres_load.py)가 어차피 이
# 기준으로 후보에서 뺀다면, gold까지 다 거쳐서 postgres에 넣어봤자 다시는
# 안 뽑힐 row로 용량만 차지한다. 여기서 SteamSpy 응답을 받은 직후(=positive를
# 이미 아는 시점) 바로 걸러낸다. 두 값은 반드시 같이 맞춰야 한다.
RECENT_MIN_POSITIVE_REVIEWS = 100
STEAM_SEARCH_PAGE_SIZE = 25  # Store 검색 API가 count 파라미터를 무시하고 고정 반환하는 개수
# 안전장치: sort_by=Reviews_DESC는 날짜순이 아니라서 "경계를 넘으면 멈춘다"를
# 못 쓰고 max_count를 채우거나 여기 도달할 때까지 계속 훑는다. 페이지당 최대
# 25개 후보 * appdetails 1회씩(1req/s) 순차 호출이라 값이 크면 오래 걸린다.
STEAM_SEARCH_MAX_PAGES = 300
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


def _fetch_release_search_page(start: int, sort_by: str = "Reviews_DESC") -> list[int]:
    """지정된 정렬로 검색 결과 한 페이지(최대 STEAM_SEARCH_PAGE_SIZE개)의 appid를
    가져온다. released=Custom 등 날짜 파라미터는 일부러 안 쓴다 -
    discover_recent_game_appids의 모듈 docstring 참고(날짜 필터가 무시되는
    문제가 있어서, 정렬만 쓰고 날짜 판단은 호출부가 appdetails로 직접 한다)."""
    response = requests.get(
        STEAM_SEARCH_URL,
        params={
            "query": "",
            "start": start,
            "sort_by": sort_by,
            "ndl": 1,
            "supportedlang": "english",
            "json": 1,
        },
        timeout=30,
    )
    if response.status_code == 429:
        return []
    response.raise_for_status()
    items = response.json().get("items", [])
    appids = []
    for item in items:
        match = APPID_FROM_LOGO_RE.search(item.get("logo", ""))
        if match:
            appids.append(int(match.group(1)))
    return appids


def _parse_steam_release_date(release_date_field: dict) -> date | None:
    """Steam appdetails의 release_date.date 문자열을 파싱한다. "Coming soon"이거나
    알려진 형식이 아니면(예: "Q1 2026"처럼 날짜가 불확실한 경우) None을 돌려준다 -
    판단 불가능한 건 window 경계를 넘겼다는 신호로 쓰지 않고 그냥 건너뛴다."""
    if release_date_field.get("coming_soon"):
        return None
    raw = release_date_field.get("date") or ""
    for fmt in ("%d %b, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def fetch_steam_official_appdetails(appid: int) -> dict | None:
    """Steam 공식 storefront API(appdetails)로 앱 상세를 조회한다 (키 불필요).

    SteamSpy가 아직 못 채운 신작 name/developer/publisher 보강(아래
    fetch_steam_official_name)과, discover_recent_game_appids의 type/출시일
    판단 양쪽에서 공유해서 쓴다.
    """
    response = requests.get(
        STEAM_APPDETAILS_URL,
        params={"appids": appid, "l": "english"},
        headers={"User-Agent": "gamer-publisher-ingest-bot/0.1"},
        timeout=30,
    )
    if response.status_code != 200:
        return None
    payload = response.json().get(str(appid))
    if not payload or not payload.get("success"):
        return None
    return payload.get("data") or {}


def fetch_steam_official_name(appid: int) -> dict | None:
    """SteamSpy가 아직 못 채운 신작(appid는 있는데 name 등이 빈 문자열)을 보강한다.

    SteamSpy는 커뮤니티가 스크래핑해서 채우는 데이터라 출시 2개월 시점(recent
    pool이 노리는 창)의 신작, 특히 인지도 낮은 인디는 appid만 인식하고 name/
    developer/publisher가 통째로 빈 채로 오는 경우가 잦다 (실측: appid는
    맞는데 나머지 필드 전부 "" — 에러가 아니라 SteamSpy 쪽 데이터 공백).
    Steam 공식 storefront API(키 불필요)는 출시 즉시 채워지므로 이걸로 메운다.
    owners/ccu 같은 SteamSpy 고유 추정치는 이 API에 없어서 SteamSpy를
    완전히 대체하진 않는다 - 딱 이름/개발사/배급사만 보강한다.
    """
    data = fetch_steam_official_appdetails(appid)
    if not data or not data.get("name"):
        return None
    return {
        "name": data["name"],
        "developer": ", ".join(data.get("developers") or []),
        "publisher": ", ".join(data.get("publishers") or []),
    }


def discover_recent_game_appids(
    window_span_days: int = RECENT_WINDOW_SPAN_DAYS,
    max_count: int | None = None,
) -> list[int]:
    """출시일 기준 "오늘부터 window_span_days일 전까지" 안에 나온, 평가가 좋은
    진짜 게임(type=="game", DLC/사운드트랙/데모/소프트웨어 제외)의 appid를 찾는다.

    store.steampowered.com/search/results의 released=Custom&from=&to= 날짜
    필터는 sort_by 값과 무관하게 실제로는 완전히 무시된다는 걸 확인했다 - 뭘
    넘기든 그냥 "지금 인기/최신 목록"만 돌아온다. 그래서 날짜 파라미터 없이
    sort_by=Reviews_DESC(평가 좋은 순 - 정확한 정렬 기준은 비공개지만, 실측상
    여러 연도에 걸친 우수작들이 우선 나옴)만 써서 후보를 받고, 후보마다 Steam
    공식 appdetails로 실제 출시일을 직접 확인해 window 안에 있는지 우리가
    스스로 판단한다 - "일단 넓게 긁고 하나하나 실제 값으로 거른다".

    sort_by=Released_DESC(출시일순)로 시도했을 때는 Steam이 하루에도 저품질
    신작을 수백 건씩 등록하는 탓에 최신순 100개를 확인해도 전부 리뷰 0개였다
    (실측). Reviews_DESC는 애초에 평가 좋은 게임 위주로 나와서, 좁은 최근 창
    안에서도 리뷰 100개 이상인 후보를 훨씬 잘 만난다(실측: 300번째 안에서
    바로 리뷰 수백 개짜리 최근작이 나옴). 대신 이 정렬은 날짜순이 아니라서
    "경계를 넘으면 멈춘다" 최적화는 못 쓰고, max_count를 채우거나
    STEAM_SEARCH_MAX_PAGES에 도달할 때까지 계속 훑으며 걸러야 한다.
    """
    window_start = date.today() - timedelta(days=window_span_days)
    today = date.today()

    result: list[int] = []
    seen: set[int] = set()
    start = 0
    for _ in range(STEAM_SEARCH_MAX_PAGES):
        page_appids = _fetch_release_search_page(start, sort_by="Reviews_DESC")
        if not page_appids:
            break
        for appid in page_appids:
            if appid in seen:
                continue
            seen.add(appid)

            data = fetch_steam_official_appdetails(appid)
            time.sleep(STEAM_SEARCH_REQUEST_INTERVAL_SECONDS)
            if not data:
                continue

            release = _parse_steam_release_date(data.get("release_date") or {})
            if release is None or release > today or release < window_start:
                # 파싱 불가("Coming soon" 등), 미래 날짜(이상치), window보다
                # 오래됨(Reviews_DESC는 날짜순이 아니라 언제든 나올 수 있음)
                # 전부 그냥 건너뛴다 - 멈추는 신호로는 안 쓴다.
                continue
            if data.get("type") == "game":
                result.append(appid)
                if max_count is not None and len(result) >= max_count:
                    return result

        start += STEAM_SEARCH_PAGE_SIZE
    return result


def fetch_steamspy_appdetails(appids: list[int]) -> list[dict]:
    """SteamSpy `appdetails`로 appid별 소유자/리뷰 추정치를 순회 조회한다.

    name이 비어있으면(위 docstring 참고) Steam 공식 API로 보강 시도한다.
    """
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
            if not data.get("name"):
                fallback = fetch_steam_official_name(appid)
                if fallback:
                    data.update(fallback)
                time.sleep(STEAMSPY_APPDETAILS_INTERVAL_SECONDS)
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
        # 개발/테스트 시 DAG의 env_vars로 RECENT_MAX_CANDIDATES를 넘겨 appdetails
        # 호출 개수를 제한한다 (appid당 1초, 미설정 시 1년치 전부 훑어서 몇 시간
        # 걸릴 수 있음 - discover_recent_game_appids 참고).
        max_candidates_env = os.environ.get("RECENT_MAX_CANDIDATES", "")
        max_candidates = int(max_candidates_env) if max_candidates_env else None
        appids = discover_recent_game_appids(max_count=max_candidates)
        games = fetch_steamspy_appdetails(appids)
        games = [g for g in games if (g.get("positive") or 0) >= RECENT_MIN_POSITIVE_REVIEWS]
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
