# develope

이 폴더는 AI가 생성한 소스 코드가 저장되는 공간입니다.

- Developer AI가 코드를 이 폴더 안에 작성합니다.
- Debugger AI가 이 폴더의 코드를 검수합니다.
- 구조는 PRD의 Architecture Style을 따릅니다.

## 구조 (MSA, 7개 컨테이너 단위)

| 폴더 | 역할 |
|---|---|
| `frontend/` | 웹사이트. 기술스택 미정 -> 지금은 nginx placeholder |
| `fastapi-server/` | 백엔드 API 서버 (FastAPI) |
| `langgraph-server/` | LangGraph 기반 멀티 에이전트 보고서 생성 서비스 |
| `airflow/` | 수집 파이프라인 오케스트레이션 (DAGs 포함, LocalExecutor) |
| `spark-jobs/` | Spark 메달리언 파이프라인 이미지. 상시 컨테이너가 아니라 k3s pod로 실행되는 이미지 빌드 용도 |
| `k3s/` | Spark 워커를 동적으로 띄우는 k3s용 매니페스트(RBAC 등) |
| `scripts/` | 로컬 개발 보조 스크립트 |

`postgres`, `minio`, `chromadb`는 공식 이미지를 그대로 사용하며 별도 폴더 없이 `docker-compose.yml`에서 정의됩니다.

## 컨테이너 목록

| # | 컨테이너 | 역할 |
|---|---|---|
| 1 | `k3s` (+ kubeconfig-prep, k3s-bootstrap) | 쿠버네티스 컨트롤플레인. Spark 워커(executor pod)를 작업량에 따라 동적 할당 |
| 2 | `frontend` | 웹사이트 (placeholder) |
| 3 | `fastapi-server` | 백엔드 API |
| 4 | `minio` (+ minio-init) | 데이터레이크(datalake) + Airflow/Spark 코드 저장소(code) + 보고서(reports) |
| 5 | `airflow-webserver` / `airflow-scheduler` (+ airflow-init, dags-sync) | 파이프라인(DAG) 오케스트레이션. DAG 코드는 여기서 관리하고, 파이프라인이 다루는 데이터는 전부 MinIO에 둔다 |
| 6 | `langgraph-server` | 멀티 에이전트 보고서 생성 |
| 7 | `postgres` | 컨테이너 1개, DB 2개(`app_db`, `airflow_db`). `app_db`는 유저 로그인 + 프론트엔드 조회용 gold 요약 데이터(Airflow와 무관, 필요 시에만 사용), `airflow_db`는 Airflow 메타데이터 |

## Spark 메달리언 파이프라인 (k3s + KubernetesPodOperator + dynamicAllocation)

Spark 작업은 Airflow가 직접 실행하지 않고, `k3s`(경량 Kubernetes, 단일 노드)에 pod로 띄워 실행합니다.
각 pod의 Spark 드라이버가 k8s 네이티브 스케줄러로 executor pod를 직접 만들며,
`spark.dynamicAllocation`이 켜져 있어 작업량에 따라 executor(워커) 수가 0~5 사이에서 자동으로 늘고 줍니다.

DAG(`airflow/dags/medallion_pipeline.py`)은 4단계를 순서대로 실행합니다:

```
ingest >> bronze >> silver >> gold
```

| 단계 | 파일 | 하는 일 | 결과 위치 |
|---|---|---|---|
| ingest | `spark-jobs/jobs/ingest.py` | 외부 API(Steam/Reddit/Twitch/itch.io) 원본 수집 | `s3a://datalake/raw/` |
| bronze | `spark-jobs/jobs/bronze.py` | 스키마 적용, 깨진 레코드 제거 | `s3a://datalake/bronze/` |
| silver | `spark-jobs/jobs/silver.py` | 중복 제거, 공통 스키마로 통합 | `s3a://datalake/silver/` |
| gold | `spark-jobs/jobs/gold.py` | 집계/랭킹 등 프론트엔드용 가공 (필요 시 postgres `app_db`에도 요약 동기화) | `s3a://datalake/gold/` |

`spark-jobs` 이미지는 `docker compose build`로 로컬 Docker에 만들어지지만, k3s는 별도의 컨테이너 런타임(containerd)을 쓰기 때문에 자동으로 보이지 않습니다. 아래 스크립트로 반입하세요.

```
./scripts/load-image-to-k3s.sh
```

## 관리 UI (전부 접근 가능하도록 노출)

| 서비스 | URL | 비고 |
|---|---|---|
| Airflow Webserver | http://localhost:8080 | DAG 관리/모니터링 |
| Spark History Server | http://localhost:18080 | 종료된 Spark 잡의 UI (eventLog 기반) |
| Spark Driver UI | `./scripts/spark-driver-ui.sh <pod-name>` 실행 후 http://localhost:4040 | 잡 실행 중에만 존재, 끝나면 History Server로 확인 |
| MinIO Console | http://localhost:9001 | 버킷/오브젝트 관리 |
| Frontend | http://localhost:3000 | placeholder |
| FastAPI | http://localhost:8000 | `/health` |
| LangGraph | http://localhost:8100 | `/health` |

## MinIO 버킷

| 버킷 | 용도 |
|---|---|
| `datalake` | 수집 원본(raw) + 메달리언 가공 데이터. 프리픽스: `raw/`, `bronze/`, `silver/`, `gold/` |
| `code` | Git → (Jenkins CI) → 업로드되는 Airflow DAG (`code/dags/`) |
| `reports` | LangGraph가 생성한 보고서 파일 (웹에서 조회/다운로드) |
| `spark-events` | Spark History Server가 읽는 이벤트 로그 |

로컬에서 DAG 코드를 고치면 아래 스크립트로 `code` 버킷에 올리고, `dags-sync`를 다시 실행해 Airflow에 반영합니다.
(Jenkins CI/CD가 구성되면 이 두 단계는 파이프라인이 자동으로 수행합니다 — `Jenkinsfile` 참고.)

Spark 잡 코드(`spark-jobs/jobs/`)는 MinIO를 거치지 않고 이미지에 직접 박제됩니다. 수정 후에는
`./scripts/load-image-to-k3s.sh`로 이미지를 재빌드 + k3s에 반입해야 반영됩니다.

```
./scripts/push_code_to_minio.sh
docker compose run --rm dags-sync
```

## Docker 네트워크 분리 (PRD 보안 요구사항)

서비스 간 불필요한 접근을 막기 위해 3개 네트워크로 분리되어 있습니다.

| 네트워크 | 소속 서비스 |
|---|---|
| `backend-net` | postgres, chromadb, minio(-init), fastapi-server, langgraph-server, spark-history-server, dags-sync, airflow-init/webserver/scheduler, k3s |
| `app-net` | frontend, fastapi-server, langgraph-server |
| `k8s-net` | k3s, kubeconfig-prep, k3s-bootstrap, airflow-webserver, airflow-scheduler |

`frontend`는 `backend-net`에 물려있지 않아서 postgres/minio/chromadb에 직접 접근할 수 없고,
반드시 `fastapi-server`(app-net)를 거쳐야 합니다.

## CI/CD (Jenkins)

`Jenkinsfile` 참고. Git push -> 이미지 빌드 -> spark-jobs 이미지를 k3s로 반입 -> DAG/Spark 코드를
MinIO code 버킷에 업로드 -> Airflow dags 볼륨에 반영 -> 변경된 서비스 재배포 순서로 동작합니다.
`.env`는 저장소에 커밋하지 않고 Jenkins Credentials Store의 Secret file(`gamer_publisher-env`)로 주입합니다.

## 실행

```
cp .env.example .env   # 값 채운 후
docker compose up -d --build
./scripts/load-image-to-k3s.sh   # spark-jobs 이미지를 k3s에 반입
```
