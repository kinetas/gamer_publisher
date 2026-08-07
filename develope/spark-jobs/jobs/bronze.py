"""메달리언 파이프라인 2단계: bronze.

datalake/raw/ 의 원본 데이터를 읽어 스키마를 맞추고 명백히 깨진 레코드만 걸러낸 뒤
datalake/bronze/ 에 적재한다. 비즈니스 로직 정제/중복 제거는 아직 하지 않는다 (silver에서 처리).

steam_app_list와 steamspy_all은 아직 통합하지 않고 각각 스키마 적용만 한다.
소스 간 통합(appid 기준 join)은 다음 단계(silver.py)에서 수행한다.
"""
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
    """명시된 스키마로 raw JSON을 읽고, 파싱 실패/필수 필드(appid) 누락 레코드를 제거한다."""
    df = spark.read.schema(schema).option("mode", "DROPMALFORMED").json(raw_path)
    return df.filter(col("appid").isNotNull())


def main() -> None:
    spark = SparkSession.builder.appName("bronze").getOrCreate()

    app_list = clean(spark, STEAM_APP_LIST_SCHEMA, "s3a://datalake/raw/steam/app_list/")
    app_list.write.mode("append").parquet("s3a://datalake/bronze/steam_app_list/")

    steamspy_all = clean(
        spark, STEAMSPY_ALL_SCHEMA, "s3a://datalake/raw/steam/steamspy_all/"
    )
    steamspy_all.write.mode("append").parquet("s3a://datalake/bronze/steamspy_all/")

    spark.stop()


if __name__ == "__main__":
    main()
