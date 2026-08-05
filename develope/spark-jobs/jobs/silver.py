"""메달리언 파이프라인 3단계: silver.

datalake/bronze/ 의 소스별 원시 테이블들을 정제/중복제거하고 공통 스키마로 통합하여
datalake/silver/ 에 적재한다. 이후 보고서 생성(LangGraph)과 반응 분석의 기반 데이터가 된다.
"""
from pyspark.sql import SparkSession


def main() -> None:
    spark = SparkSession.builder.appName("silver").getOrCreate()
    # TODO: spark.read.parquet("s3a://datalake/bronze/...") 로 소스별 bronze 테이블 로드
    # TODO: 중복 제거, 게임 식별자 기준 정합성 정리, 공통 스키마로 통합
    # TODO: df.write.mode("overwrite").parquet("s3a://datalake/silver/<entity>/")
    spark.stop()


if __name__ == "__main__":
    main()
