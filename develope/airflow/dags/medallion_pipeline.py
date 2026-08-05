"""게임 정보 수집 메달리언 파이프라인: ingest >> bronze >> silver >> gold.

각 단계는 KubernetesPodOperator로 k3s 클러스터에 spark-jobs 이미지를 pod로 띄워
spark-submit을 실행한다. 실제 변환 로직은 develope/spark-jobs/jobs/{stage}.py 에 작성한다.

Spark executor는 고정 개수가 아니라 k8s 네이티브 스케줄러 + dynamicAllocation으로
작업량에 따라 pod가 늘고 줄어든다 (spark 워커 동적할당). k8s에는 외부 셔플 서비스가 없으므로
shuffleTracking으로 대체한다.

이 DAG이 스케줄러에 반영되려면:
  1. scripts/push_dags_to_minio.sh 로 MinIO code 버킷(code/dags)에 업로드
  2. `docker compose run --rm dags-sync` 로 dags 볼륨에 반영
(Jenkins CI/CD가 구성되면 위 두 단계는 파이프라인이 자동으로 수행한다.)
"""
from datetime import datetime

from airflow import DAG
from airflow.hooks.base import BaseHook
from airflow.providers.cncf.kubernetes.operators.pod import KubernetesPodOperator

# MinIO 자격증명은 코드에 넣지 않고, docker-compose.yml의
# AIRFLOW_CONN_MINIO_DEFAULT 로 등록된 Airflow Connection에서 읽는다.
minio_conn = BaseHook.get_connection("minio_default")

# 모든 단계가 공유하는 spark-submit 옵션.
# --master/--deploy-mode: k3s 위에 떠 있는 이 pod 자신이 Spark 드라이버가 되어
#   k8s 네이티브 스케줄러로 executor pod를 직접 만든다 (client 모드).
# dynamicAllocation: 단계별 데이터량에 맞춰 executor pod 수를 0~5 사이에서 자동 조절한다.
COMMON_SPARK_CONF = [
    "--master", "k8s://https://kubernetes.default.svc:443",
    "--deploy-mode", "client",
    "--conf", "spark.kubernetes.namespace=default",
    "--conf", "spark.kubernetes.authenticate.driver.serviceAccountName=spark",
    "--conf", "spark.dynamicAllocation.enabled=true",
    "--conf", "spark.dynamicAllocation.shuffleTracking.enabled=true",
    "--conf", "spark.dynamicAllocation.minExecutors=0",
    "--conf", "spark.dynamicAllocation.maxExecutors=5",
    "--conf", "spark.eventLog.enabled=true",
    "--conf", "spark.eventLog.dir=s3a://spark-events/",
    "--conf", "spark.hadoop.fs.s3a.endpoint=http://minio:9000",
    "--conf", "spark.hadoop.fs.s3a.path.style.access=true",
    "--conf", f"spark.hadoop.fs.s3a.access.key={minio_conn.login}",
    "--conf", f"spark.hadoop.fs.s3a.secret.key={minio_conn.password}",
]


def make_stage_task(stage: str) -> KubernetesPodOperator:
    """단계 이름(ingest/bronze/silver/gold)을 받아 해당 스크립트를 실행하는 태스크를 만든다."""
    return KubernetesPodOperator(
        task_id=stage,
        name=f"medallion-{stage}",
        namespace="default",
        image="gamer_publisher/spark-jobs:latest",
        cmds=["spark-submit"],
        arguments=[*COMMON_SPARK_CONF, f"/opt/spark-jobs/jobs/{stage}.py"],
        is_delete_operator_pod=True,
        get_logs=True,
    )


with DAG(
    dag_id="medallion_pipeline",
    schedule=None,
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["spark", "kubernetes", "medallion"],
) as dag:
    ingest = make_stage_task("ingest")
    bronze = make_stage_task("bronze")
    silver = make_stage_task("silver")
    gold = make_stage_task("gold")

    ingest >> bronze >> silver >> gold
