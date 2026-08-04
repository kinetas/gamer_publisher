"""Spark 수집 파이프라인 예시 DAG.

KubernetesPodOperator로 k3s 클러스터에 spark-jobs 이미지를 pod로 띄워
spark-submit을 실행한다. 실제 수집 로직은 develope/spark-jobs/jobs/ 에 작성한다.

이 DAG이 스케줄러에 반영되려면:
  1. scripts/push_dags_to_minio.sh 로 MinIO code 버킷에 업로드
  2. `docker compose run --rm dags-sync` 로 dags 볼륨에 반영
"""
from datetime import datetime

from airflow import DAG
from airflow.hooks.base import BaseHook
from airflow.providers.cncf.kubernetes.operators.pod import KubernetesPodOperator

# MinIO 자격증명은 코드에 넣지 않고, docker-compose.yml의
# AIRFLOW_CONN_MINIO_DEFAULT 로 등록된 Airflow Connection에서 읽는다.
minio_conn = BaseHook.get_connection("minio_default")

with DAG(
    dag_id="example_spark_k8s_pipeline",
    schedule=None,
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["spark", "kubernetes", "example"],
) as dag:
    collect_game_info = KubernetesPodOperator(
        task_id="collect_game_info",
        name="collect-game-info",
        namespace="default",
        image="gamer_publisher/spark-jobs:latest",
        cmds=["spark-submit"],
        arguments=[
            "--master", "k8s://https://kubernetes.default.svc:443",
            "--deploy-mode", "client",
            "--conf", "spark.kubernetes.namespace=default",
            "--conf", "spark.kubernetes.authenticate.driver.serviceAccountName=spark",
            "--conf", "spark.eventLog.enabled=true",
            "--conf", "spark.eventLog.dir=s3a://spark-events/",
            "--conf", "spark.hadoop.fs.s3a.endpoint=http://minio:9000",
            "--conf", "spark.hadoop.fs.s3a.path.style.access=true",
            "--conf", f"spark.hadoop.fs.s3a.access.key={minio_conn.login}",
            "--conf", f"spark.hadoop.fs.s3a.secret.key={minio_conn.password}",
            "/opt/spark-jobs/jobs/collect_games.py",
        ],
        is_delete_operator_pod=True,
        get_logs=True,
    )
