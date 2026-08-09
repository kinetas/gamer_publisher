"""게임 정보 수집 메달리언 파이프라인: ingest >> bronze >> silver >> gold.

각 단계는 KubernetesPodOperator로 k3s 클러스터에 spark-jobs 이미지를 pod로 띄워
spark-submit을 실행한다. 실제 변환 로직은 develope/spark-jobs/jobs/{stage}.py 에 작성한다.

Spark executor는 고정 개수가 아니라 k8s 네이티브 스케줄러 + dynamicAllocation으로
작업량에 따라 pod가 늘고 줄어든다 (spark 워커 동적할당). k8s에는 외부 셔플 서비스가 없으므로
shuffleTracking으로 대체한다.

이 DAG이 스케줄러에 반영되려면:
  1. scripts/push_code_to_minio.sh 로 MinIO code 버킷(code/dags)에 업로드
  2. `docker compose run --rm dags-sync` 로 dags 볼륨에 반영
(Jenkins CI/CD가 구성되면 위 두 단계는 파이프라인이 자동으로 수행한다.)
"""
import os
from datetime import datetime

from airflow import DAG
from airflow.hooks.base import BaseHook
from airflow.models import Variable
from airflow.providers.cncf.kubernetes.operators.pod import KubernetesPodOperator

# MinIO 자격증명은 코드에 넣지 않고, docker-compose.yml의
# AIRFLOW_CONN_MINIO_DEFAULT 로 등록된 Airflow Connection에서 읽는다.
minio_conn = BaseHook.get_connection("minio_default")

# Steam API 키는 docker-compose.yml의 STEAM_API_KEY 환경변수로 스케줄러/웹서버에
# 전달되고, 여기서 읽어 ingest pod에만 env_vars로 주입한다.
steam_api_key = os.environ["STEAM_API_KEY"]

# SteamSpy `all`은 페이지당 1000개, 요청 제한 1req/60s라 전체 수집에 50분+ 걸린다.
# Airflow Variable "steamspy_max_pages"로 페이지 수를 제한할 수 있다 (기본값 3 = 몇 분 내 완료,
# 개발/파이프라인 동작 확인용). 실제 전체 배치 수집을 돌리려면 Airflow UI에서 이 Variable을
# 빈 문자열로 비우거나 지우면 된다 (ingest.py: 미설정 시 전체 수집).
steamspy_max_pages = Variable.get("steamspy_max_pages", default_var="3")

# 모든 단계가 공유하는 spark-submit 옵션.
# --master/--deploy-mode: k3s 위에 떠 있는 이 pod 자신이 Spark 드라이버가 되어
#   k8s 네이티브 스케줄러로 executor pod를 직접 만든다 (client 모드).
# dynamicAllocation: 단계별 데이터량에 맞춰 executor pod 수를 0~5 사이에서 자동 조절한다.
# eventLog.dir: 버킷 루트(s3a://spark-events/)를 그대로 쓰면 Hadoop S3A의
#   "path must be absolute" 버그에 걸려서, 버킷 안 서브패스(/logs/)를 써야 한다.
#   spark-history-server의 logDirectory 설정과 반드시 같은 경로를 가리켜야 한다.
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
    "--conf", "spark.eventLog.dir=s3a://spark-events/logs/",
    "--conf", "spark.hadoop.fs.s3a.endpoint=http://minio:9000",
    "--conf", "spark.hadoop.fs.s3a.path.style.access=true",
    "--conf", f"spark.hadoop.fs.s3a.access.key={minio_conn.login}",
    "--conf", f"spark.hadoop.fs.s3a.secret.key={minio_conn.password}",
]


def make_stage_task(
    stage: str, env_vars: dict[str, str] | None = None
) -> KubernetesPodOperator:
    """단계 이름(ingest/bronze/silver/gold)을 받아 해당 스크립트를 실행하는 태스크를 만든다."""
    return KubernetesPodOperator(
        task_id=stage,
        name=f"medallion-{stage}",
        namespace="default",
        # client 모드라 이 pod 자체가 드라이버라서, spark.kubernetes.authenticate.driver.*
        # 설정(별도 드라이버 pod를 만들 때만 적용됨)과 무관하게 이 pod에 SA를 직접 지정해야
        # k3s-bootstrap이 만든 spark-role(RBAC)로 executor pod를 만들 권한이 생긴다.
        service_account_name="spark",
        # k3s/spark-driver-ui-service.yaml의 NodePort Service가 이 라벨로 "현재 실행 중인
        # 드라이버 pod"를 찾아서 localhost:4040에 연결해준다 (--deploy-mode client라서
        # 이 pod 자신이 드라이버).
        labels={"spark-driver-ui": "true"},
        image="gamer_publisher/spark-jobs:latest",
        image_pull_policy="Never",  # load-image-to-k3s.sh로 containerd에 반입한 로컬 전용 이미지
        cmds=["spark-submit"],
        arguments=[*COMMON_SPARK_CONF, f"/opt/spark-jobs/jobs/{stage}.py"],
        # cmds가 bitnami 이미지의 entrypoint(유저 홈 디렉토리 설정)를 건너뛰기 때문에,
        # 컨테이너 UID가 /etc/passwd에 없는 상태가 되어 Java가 user.home을 "?"로 깨뜨린다
        # (spark-history-server와 동일한 원인). root로 실행해서 /etc/passwd 조회가 되게 한다.
        # HOME은 명시적으로 건드리지 않는다 - 이미지에 baked된 HOME=/ 기준으로
        # pip install된 requests가 /.local/... 에 깔려있어서, HOME을 바꾸면 그게 안 잡힌다.
        security_context={"runAsUser": 0},
        env_vars=env_vars or {},
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
    ingest = make_stage_task(
        "ingest",
        env_vars={
            "STEAM_API_KEY": steam_api_key,
            "STEAMSPY_MAX_PAGES": steamspy_max_pages,
        },
    )
    bronze = make_stage_task("bronze")
    silver = make_stage_task("silver")
    gold = make_stage_task("gold")

    ingest >> bronze >> silver >> gold
