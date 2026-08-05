"""메달리언 파이프라인 2단계: bronze.

datalake/raw/ 의 원본 데이터를 읽어 스키마를 맞추고 명백히 깨진 레코드만 걸러낸 뒤
datalake/bronze/ 에 적재한다. 비즈니스 로직 정제는 아직 하지 않는다 (silver에서 처리).
"""
from pyspark.sql import SparkSession


def main() -> None:
    spark = SparkSession.builder.appName("bronze").getOrCreate()
    # TODO: spark.read.json("s3a://datalake/raw/...") 로 원본 로드
    # TODO: 스키마 적용 + 파싱 실패/결측 레코드 제거
    # TODO: df.write.mode("append").parquet("s3a://datalake/bronze/<source>/")
    spark.stop()


if __name__ == "__main__":
    main()
