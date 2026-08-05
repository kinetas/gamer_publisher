#!/usr/bin/env sh
# 실행 중인 Spark 드라이버 pod의 UI를 로컬 4040 포트로 연결한다.
# 잡이 끝나면 pod가 사라지므로 이 UI도 같이 사라진다 — 종료된 잡은 Spark History Server(18080)에서 본다.
#
# 사용법: ./scripts/spark-driver-ui.sh <pod-name>
#   pod 목록 확인: docker run --rm --network develope_k8s-net \
#     -v develope_kube-config:/kube:ro -e KUBECONFIG=/kube/config \
#     bitnami/kubectl:1.29 get pods
set -e
cd "$(dirname "$0")/.."

POD_NAME="$1"
if [ -z "$POD_NAME" ]; then
  echo "사용법: $0 <pod-name>"
  exit 1
fi

docker run --rm -it \
  --network develope_k8s-net \
  -v develope_kube-config:/kube:ro \
  -e KUBECONFIG=/kube/config \
  -p 4040:4040 \
  bitnami/kubectl:1.29 port-forward "pod/$POD_NAME" 4040:4040
