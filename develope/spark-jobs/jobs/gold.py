"""메달리언 파이프라인 4단계: gold.

datalake/silver/ 의 정제된 후보 목록에 수집 시각(ingested_at)을 붙여
datalake/gold/ 에 최종 스냅샷으로 적재한다. 이 스냅샷을 Airflow의 후속
Python task가 읽어서 postgres(old_games/recent_games)로 upsert한다
(Spark의 JDBC writer는 진짜 upsert를 지원하지 않아서, 관계형 upsert는
Spark 밖에서 처리한다).

POOL 환경변수(old/recent)로 silver/gold 경로 및 postgres 테이블명을 분기한다.
"""
import os

from pyspark.sql import SparkSession
from pyspark.sql.functions import current_timestamp


def main() -> None:
    spark = SparkSession.builder.appName("gold").getOrCreate()

    pool = os.environ.get("POOL", "old")
    source = "steamspy_recent" if pool == "recent" else "steamspy_all"
    table = "recent_games" if pool == "recent" else "old_games"

    silver = spark.read.parquet(f"s3a://datalake/silver/{source}/")
    gold = silver.withColumn("ingested_at", current_timestamp())

    gold.write.mode("overwrite").parquet(f"s3a://datalake/gold/{table}/")

    spark.stop()


if __name__ == "__main__":
    main()
