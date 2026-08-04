"""게임 정보 수집 작업 스켈레톤.

Steam / Reddit / Twitch / itch.io 에서 데이터를 모아 MinIO datalake 버킷에 적재한다.
"""
from pyspark.sql import SparkSession


def main() -> None:
    spark = SparkSession.builder.appName("collect_games").getOrCreate()
    # TODO: 외부 API에서 데이터 수집 -> DataFrame 변환 -> MinIO(datalake 버킷)에 적재
    spark.stop()


if __name__ == "__main__":
    main()
