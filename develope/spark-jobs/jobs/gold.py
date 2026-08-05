"""메달리언 파이프라인 4단계: gold.

datalake/silver/ 를 집계해 프론트엔드/보고서가 바로 쓰기 좋은 형태로
datalake/gold/ 에 적재한다.

Airflow와는 무관하지만, 필요하면 이 gold 데이터의 요약본을 Postgres(app_db)에도
동기화해 프론트엔드가 MinIO를 거치지 않고 조회할 수 있게 한다 (선택 사항).
"""
from pyspark.sql import SparkSession


def main() -> None:
    spark = SparkSession.builder.appName("gold").getOrCreate()
    # TODO: spark.read.parquet("s3a://datalake/silver/...") 로 silver 데이터 로드
    # TODO: 집계/랭킹 등 프론트엔드 조회에 맞는 형태로 가공
    # TODO: df.write.mode("overwrite").parquet("s3a://datalake/gold/<view>/")
    # TODO(optional): 요약 테이블을 postgres(app_db)에도 JDBC로 upsert
    spark.stop()


if __name__ == "__main__":
    main()
