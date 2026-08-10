"""old_games_pipeline / recent_games_pipeline DAG이 공유하는 Spark stage task 빌더.

각 단계는 KubernetesPodOperator로 k3s 클러스터에 spark-jobs 이미지를 pod로 띄워
spark-submit을 실행한다. 실제 처리 로직은 develope/spark-jobs/jobs/{stage}.py 에 있고,
POOL 환경변수(old/recent)로 그 안에서 raw/bronze/silver/gold 경로를 분기한다.

Spark executor는 고정 개수가 아니라 k8s 네이티브 스케줄러 + dynamicAllocation으로
작업량에 따라 pod가 늘고 줄어든다 (spark 워커 동적할당). k8s에는 외부 셔플 서비스가 없으므로
shuffleTracking으로 대체한다.
"""
from airflow.hooks.base import BaseHook
from airflow.providers.cncf.kubernetes.operators.pod import KubernetesPodOperator
from kubernetes.client import models as k8s

# MinIO 자격증명은 코드에 넣지 않고, docker-compose.yml의
# AIRFLOW_CONN_MINIO_DEFAULT 로 등록된 Airflow Connection에서 읽는다.
minio_conn = BaseHook.get_connection("minio_default")

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
    # KubernetesPodOperator의 image=는 이 pod(=driver) 자신의 이미지만 지정한다.
    # client 모드에서 driver가 직접 만드는 executor pod는 이 conf가 따로 있어야
    # 이미지를 알 수 있다 (없으면 "Must specify the executor container image"로
    # executor 생성이 계속 실패하고 job이 멈춘다).
    "--conf", "spark.kubernetes.container.image=gamer_publisher/spark-jobs:latest",
    "--conf", "spark.kubernetes.container.image.pullPolicy=Never",
    # client 모드에서는 이 pod 자신이 driver라서, executor가 다시 접속해올 driver 주소를
    # 알려줘야 한다. k8s DNS는 (headless Service 없이는) bare pod 이름을 해석해주지
    # 않아서 executor가 "UnknownHostException: <driver pod 이름>"으로 죽는다.
    # Downward API로 주입한 이 pod 자신의 IP(SPARK_DRIVER_POD_IP, make_stage_task에서 설정)를
    # 그대로 driver.host로 써서 이 문제를 우회한다.
    "--conf", "spark.driver.host=$(SPARK_DRIVER_POD_IP)",
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
    stage: str, pool: str, env_vars: dict[str, str] | None = None
) -> KubernetesPodOperator:
    """단계 이름(ingest/bronze/silver/gold)과 풀(old/recent)을 받아 태스크를 만든다."""
    # SPARK_DRIVER_POD_IP: Downward API로 이 pod 자신의 IP를 주입해서
    # COMMON_SPARK_CONF의 spark.driver.host=$(SPARK_DRIVER_POD_IP)에서 참조한다
    # (k8s가 command/args의 $(VAR) 참조를 이 pod의 env 값으로 그대로 치환해준다).
    # POOL: spark-jobs/jobs/{stage}.py 안에서 raw/bronze/silver/gold 경로를 분기하는 데 쓴다.
    pod_env = [
        k8s.V1EnvVar(
            name="SPARK_DRIVER_POD_IP",
            value_from=k8s.V1EnvVarSource(
                field_ref=k8s.V1ObjectFieldSelector(field_path="status.podIP")
            ),
        ),
        k8s.V1EnvVar(name="POOL", value=pool),
        *(k8s.V1EnvVar(name=k, value=v) for k, v in (env_vars or {}).items()),
    ]
    return KubernetesPodOperator(
        task_id=stage,
        name=f"{pool}-{stage}",
        namespace="default",
        # client 모드라 이 pod 자체가 드라이버라서, spark.kubernetes.authenticate.driver.*
        # 설정(별도 드라이버 pod를 만들 때만 적용됨)과 무관하게 이 pod에 SA를 직접 지정해야
        # k3s-bootstrap이 만든 spark-role(RBAC)로 executor pod를 만들 권한이 생긴다.
        service_account_name="spark",
        # k3s/spark-driver-ui-service.yaml의 NodePort Service가 이 라벨로 "현재 실행 중인
        # 드라이버 pod"를 찾아서 localhost:4040에 연결해준다 (--deploy-mode client라서
        # 이 pod 자신이 드라이버). old/recent 파이프라인이 동시에 돌 수도 있어서 완벽하진
        # 않지만(둘 다 실행 중이면 마지막에 매칭된 pod만 보임), 기존 동작 그대로 유지.
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
        env_vars=pod_env,
        is_delete_operator_pod=True,
        get_logs=True,
    )
