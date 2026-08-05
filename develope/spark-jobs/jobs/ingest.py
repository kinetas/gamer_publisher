"""메달리언 파이프라인 1단계: ingest.

Steam / Reddit / Twitch / itch.io 등 외부 소스에서 원본 데이터를 수집해
가공 없이 그대로 MinIO datalake 버킷의 raw 영역에 적재한다 (착륙 영역).

이후 단계(bronze.py)가 이 raw 데이터를 읽어 정제를 시작한다.
"""
from pyspark.sql import SparkSession


def main() -> None:
    spark = SparkSession.builder.appName("ingest").getOrCreate()
    # TODO: 외부 API(Steam/Reddit/Twitch/itch.io) 호출 -> DataFrame 변환
    # TODO: df.write.mode("append").json("s3a://datalake/raw/<source>/")
    spark.stop()


if __name__ == "__main__":
    main()
