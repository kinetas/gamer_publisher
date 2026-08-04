#!/usr/bin/env sh
# 로컬 develope/airflow/dags 를 MinIO code 버킷(dags/ 프리픽스)에 올린다.
# 실제 운영에서는 Jenkins CI가 이 역할을 대신한다.
set -e
cd "$(dirname "$0")/.."

set -a
[ -f .env ] && . ./.env
set +a

docker run --rm \
  --network develope_default \
  -v "$(pwd)/airflow/dags:/upload:ro" \
  minio/mc:latest sh -c "
    mc alias set local http://minio:9000 '$MINIO_ROOT_USER' '$MINIO_ROOT_PASSWORD' &&
    mc mirror --overwrite /upload local/code/dags
  "

echo 'DAG를 MinIO code 버킷에 업로드했습니다. 반영하려면: docker compose run --rm dags-sync'
