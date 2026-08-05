#!/usr/bin/env sh
# 로컬 코드를 MinIO code 버킷에 올린다.
#   airflow/dags/      -> code/dags/       (Airflow DAG 정의)
#   spark-jobs/jobs/   -> code/spark-jobs/ (ingest/bronze/silver/gold 메달리언 스크립트, 참조용 미러)
# 실제 운영에서는 Jenkins CI(Jenkinsfile)가 이 역할을 대신한다.
set -e
cd "$(dirname "$0")/.."

set -a
[ -f .env ] && . ./.env
set +a

docker run --rm \
  --network develope_backend-net \
  -v "$(pwd)/airflow/dags:/upload/dags:ro" \
  -v "$(pwd)/spark-jobs/jobs:/upload/spark-jobs:ro" \
  minio/mc:latest sh -c "
    mc alias set local http://minio:9000 '$MINIO_ROOT_USER' '$MINIO_ROOT_PASSWORD' &&
    mc mirror --overwrite /upload/dags local/code/dags &&
    mc mirror --overwrite /upload/spark-jobs local/code/spark-jobs
  "

echo '코드를 MinIO code 버킷에 업로드했습니다. Airflow에 반영하려면: docker compose run --rm dags-sync'
