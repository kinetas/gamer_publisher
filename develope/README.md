# develope

이 폴더는 AI가 생성한 소스 코드가 저장되는 공간입니다.

- Developer AI가 코드를 이 폴더 안에 작성합니다.
- Debugger AI가 이 폴더의 코드를 검수합니다.
- 구조는 PRD의 Architecture Style을 따릅니다.

## 구조 (MSA)

| 폴더 | 역할 |
|---|---|
| `fastapi-server/` | 백엔드 API 서버 (FastAPI) |
| `airflow/` | 수집 파이프라인 오케스트레이션 (DAGs 포함) |
| `langgraph-server/` | LangGraph 기반 멀티 에이전트 보고서 생성 서비스 |
| `spark-jobs/` | Spark 수집 작업 이미지. 상시 컨테이너가 아니라 k3s pod로 실행되는 이미지 빌드 용도 |
| `frontend/` | 웹사이트 (기술 스택 미정, 플레이스홀더) |
| `scripts/` | 로컬 개발 보조 스크립트 (DAG 업로드, k3s 이미지 반입) |

`postgres`, `chromadb`, `minio`는 공식 이미지를 그대로 사용하며 별도 폴더 없이 `docker-compose.yml`에서 정의됩니다.

## Spark 실행 방식 (k3s + KubernetesPodOperator)

Spark 작업은 Airflow가 직접 실행하지 않고, `k3s`(경량 Kubernetes, 단일 노드)에 pod로 띄워 실행합니다.

- `k3s` : Docker 안에서 도는 k8s 클러스터 (`k8s-master-node`)
- `kubeconfig-prep` : k3s의 kubeconfig를 Airflow가 쓸 수 있게 변환해 공유 볼륨에 저장
- Airflow DAG은 `KubernetesPodOperator`로 `spark-jobs` 이미지를 pod로 띄워 `spark-submit` 실행 (예시: `airflow/dags/example_spark_k8s_pipeline.py`)
- `k3s-bootstrap` : Spark의 네이티브 k8s 스케줄러가 executor pod를 만들 수 있도록 RBAC(`k3s/spark-rbac.yaml`)를 1회 적용

`spark-jobs` 이미지는 `docker compose build`로 로컬 Docker에 만들어지지만, k3s는 별도의 컨테이너 런타임(containerd)을 쓰기 때문에 자동으로 보이지 않습니다. 아래 스크립트로 반입하세요.

```
./scripts/load-image-to-k3s.sh
```

## 관리 UI

| 서비스 | URL | 비고 |
|---|---|---|
| Airflow Webserver | http://localhost:8080 | DAG 관리/모니터링 |
| Spark History Server | http://localhost:18080 | 종료된 Spark 잡의 UI (eventLog 기반) |
| Spark Driver UI | `./scripts/spark-driver-ui.sh <pod-name>` 실행 후 http://localhost:4040 | 잡 실행 중에만 존재, 끝나면 History Server로 확인 |
| MinIO Console | http://localhost:9001 | 버킷/오브젝트 관리 |

## MinIO 버킷

| 버킷 | 용도 |
|---|---|
| `code` | Git → (Jenkins CI, 로컬에서는 스크립트) → 업로드되는 Airflow DAG 코드 |
| `datalake` | Spark가 수집한 원본/정제 게임 데이터 |
| `reports` | LangGraph가 생성한 보고서 파일 (웹에서 조회/다운로드) |
| `spark-events` | Spark History Server가 읽는 이벤트 로그 |

로컬에서 DAG을 고치면 아래 스크립트로 `code` 버킷에 올리고, `dags-sync`를 다시 실행해 Airflow에 반영합니다.

```
./scripts/push_dags_to_minio.sh
docker compose run --rm dags-sync
```

## 실행

```
cp .env.example .env   # 값 채운 후
docker compose up -d --build
./scripts/load-image-to-k3s.sh   # spark-jobs 이미지를 k3s에 반입
```

