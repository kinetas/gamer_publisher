#!/usr/bin/env sh
# 로컬에서 빌드한 spark-jobs 이미지를 k3s(containerd)로 넣는다.
# k3s는 Docker 데몬과 별개의 컨테이너 런타임(containerd)을 쓰기 때문에,
# `docker build`로 만든 이미지가 자동으로 보이지 않는다.
set -e
cd "$(dirname "$0")/.."

docker compose build spark-jobs
docker save gamer_publisher/spark-jobs:latest \
  | docker exec -i k8s-master-node ctr images import -

echo 'spark-jobs 이미지를 k3s로 가져왔습니다.'
