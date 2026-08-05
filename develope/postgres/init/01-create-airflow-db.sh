#!/usr/bin/env bash
# postgres 컨테이너 최초 기동 시 1회 실행된다 (/docker-entrypoint-initdb.d/).
# POSTGRES_DB(app_db)는 공식 이미지가 자동으로 만들어주므로,
# 여기서는 Airflow 메타데이터용 두 번째 데이터베이스(airflow_db)만 추가로 만든다.
# 같은 컨테이너, 같은 계정(POSTGRES_USER)을 공유하고 데이터베이스만 분리한다.
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    SELECT 'CREATE DATABASE ${AIRFLOW_POSTGRES_DB}'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${AIRFLOW_POSTGRES_DB}')\gexec
EOSQL
