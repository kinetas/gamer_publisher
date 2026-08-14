"""메달리언 파이프라인 2단계: bronze.

datalake/raw/ 의 원본 데이터를 읽어 스키마를 맞추고 명백히 깨진 레코드만 걸러낸 뒤
datalake/bronze/ 에 적재한다. 비즈니스 로직 정제/중복 제거는 아직 하지 않는다 (silver에서 처리).

steam_app_list와 steamspy_all은 아직 통합하지 않고 각각 스키마 적용만 한다.
소스 간 통합(appid 기준 join)은 다음 단계(silver.py)에서 수행한다.

POOL 환경변수(old/recent)로 raw/bronze 경로를 분기한다. SteamSpy `appdetails`
(recent pool)와 `all`(old pool) 응답은 필드 구성이 같아서 스키마는 공유한다.
"""
import os

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.functions import col
from pyspark.sql.types import (
    IntegerType,
    LongType,
    StringType,
    StructField,
    StructType,
)

STEAM_APP_LIST_SCHEMA = StructType(
    [
        StructField("appid", IntegerType(), nullable=False),
        StructField("name", StringType(), nullable=True),
        StructField("last_modified", LongType(), nullable=True),
        StructField("price_change_number", LongType(), nullable=True),
    ]
)

STEAMSPY_ALL_SCHEMA = StructType(
    [
        StructField("appid", IntegerType(), nullable=False),
        StructField("name", StringType(), nullable=True),
        StructField("developer", StringType(), nullable=True),
        StructField("publisher", StringType(), nullable=True),
        StructField("score_rank", StringType(), nullable=True),
        StructField("positive", IntegerType(), nullable=True),
        StructField("negative", IntegerType(), nullable=True),
        StructField("userscore", IntegerType(), nullable=True),
        StructField("owners", StringType(), nullable=True),
        StructField("average_forever", IntegerType(), nullable=True),
        StructField("average_2weeks", IntegerType(), nullable=True),
        StructField("median_forever", IntegerType(), nullable=True),
        StructField("median_2weeks", IntegerType(), nullable=True),
        StructField("price", StringType(), nullable=True),
        StructField("initialprice", StringType(), nullable=True),
        StructField("discount", StringType(), nullable=True),
        StructField("ccu", IntegerType(), nullable=True),
    ]
)


def clean(spark: SparkSession, schema: StructType, raw_path: str) -> DataFrame:
    """명시된 스키마로 raw JSON을 읽고, 파싱 실패/필수 필드(appid) 누락 레코드를 제거한다.

    raw_path가 아예 없으면(recent pool에서 ingest.py의 RECENT_MIN_POSITIVE_REVIEWS
    필터를 통과한 후보가 이번 실행엔 하나도 없어서 write_raw_json이 아무 파일도
    안 쓴 경우) 빈 스키마 DataFrame으로 대체한다 - "이번 주는 후보가 0개일 수
    있다"는 정상적인 상황이라, PATH_NOT_FOUND로 파이프라인 전체가 죽으면 안 된다.
    """
    try:
        df = spark.read.schema(schema).option("mode", "DROPMALFORMED").json(raw_path)
    except Exception as exc:  # noqa: BLE001 - AnalysisException은 pyspark 버전마다 모듈 경로가 달라 문자열로 판별
        if "PATH_NOT_FOUND" not in str(exc):
            raise
        df = spark.createDataFrame([], schema)
    return df.filter(col("appid").isNotNull())


def main() -> None:
    spark = SparkSession.builder.appName("bronze").getOrCreate()

    pool = os.environ.get("POOL", "old")
    source = "steamspy_recent" if pool == "recent" else "steamspy_all"

    # app_list = clean(spark, STEAM_APP_LIST_SCHEMA, "s3a://datalake/raw/steam/app_list/")
    # app_list.write.mode("append").parquet("s3a://datalake/bronze/steam_app_list/")

    steamspy = clean(spark, STEAMSPY_ALL_SCHEMA, f"s3a://datalake/raw/steam/{source}/")
    steamspy.write.mode("append").parquet(f"s3a://datalake/bronze/{source}/")

    spark.stop()


if __name__ == "__main__":
    main()
