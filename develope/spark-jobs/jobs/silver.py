"""메달리언 파이프라인 3단계: silver.

datalake/bronze/ 의 소스별 원시 테이블들을 정제/중복제거하고 공통 스키마로 통합하여
datalake/silver/ 에 적재한다. 이후 보고서 생성(LangGraph)과 반응 분석의 기반 데이터가 된다.

POOL 환경변수(old/recent)로 bronze/silver 경로를 분기한다. 평점 좋음(positive >=
negative) 필터는 두 풀 다 적용하지만, ccu 평균 이하 필터는 old pool 전용이다 -
old는 "사람들이 잘 못 찾은 좋은 게임"(옛 명작 발굴)이 목적이라 인기 없는 쪽을
일부러 찾지만, recent는 그냥 최근작 소개라 인기 있어도 상관없다 (오히려 인기
많은 신작일수록 리뷰가 많아서 나중 감정분석 파이프라인 원본으로도 낫다).
"""
import os

from pyspark.sql import SparkSession
from pyspark.sql.functions import avg, col

DROP_COLUMNS = [
    "average_forever",
    "average_2weeks",
    "median_forever",
    "median_2weeks",
    "userscore",
]


def main() -> None:
    spark = SparkSession.builder.appName("silver").getOrCreate()

    pool = os.environ.get("POOL", "old")
    source = "steamspy_recent" if pool == "recent" else "steamspy_all"

    # bronze는 raw를 append로 누적하는 착륙 영역이라 재실행/재수집 시 같은 appid가
    # 여러 번 들어있을 수 있다. gold 이후 postgres upsert가 appid를 PK로 쓰기 때문에
    # 여기서 반드시 정리해야 한다 (dropDuplicates 안 하면 같은 배치 안에 appid가
    # 중복돼 "ON CONFLICT DO UPDATE cannot affect row a second time" 에러가 난다).
    steamspy = (
        spark.read.parquet(f"s3a://datalake/bronze/{source}/")
        .drop(*DROP_COLUMNS)
        .dropDuplicates(["appid"])
    )

    rated_well = steamspy.filter(col("positive") >= col("negative"))

    if pool == "recent":
        filtered = rated_well
    else:
        # 전체 ccu 평균을 구하는 집계라 셔플이 발생한다 (파티션별 부분합 -> 최종 합산).
        ccu_avg = rated_well.select(avg("ccu")).first()[0]
        filtered = rated_well.filter(col("ccu") <= ccu_avg)

    # dropDuplicates가 셔플을 일으켜 파티션이 다시 늘어나는데(기본 200), 이 파이프라인의
    # 데이터 규모(수천 row)에서는 대부분 빈 파티션이 되어 MinIO(S3A) 커밋 단계에서
    # FileNotFoundException이 난다. 규모가 작으니 1개 파일로 합쳐서 쓴다.
    filtered.coalesce(1).write.mode("overwrite").parquet(f"s3a://datalake/silver/{source}/")

    spark.stop()


if __name__ == "__main__":
    main()
