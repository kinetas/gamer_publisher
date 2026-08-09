# 에러 로그

Docker 스택 및 Airflow 파이프라인(`medallion_pipeline`) 실행 중 발생한 에러와 원인, 해결 방법을 기록합니다.
새 에러가 나올 때마다 아래에 항목을 추가합니다.

---

## 1. postgres 컨테이너가 5432 포트 바인딩 실패

**증상**
```
Error response from daemon: ports are not available: exposing port TCP 0.0.0.0:5432 -> 127.0.0.1:0:
listen tcp 0.0.0.0:5432: bind: An attempt was made to access a socket in a way forbidden by its access permissions.
```

**원인**
Windows(Hyper-V/WSL)가 동적 포트 예약 범위를 갖고 있는데, `netsh interface ipv4 show excludedportrange protocol=tcp` 결과 `5358–5457` 범위가 예약되어 있었고 postgres가 쓰려는 5432가 그 안에 포함됨. Docker가 해당 포트를 바인딩할 권한이 없어서 실패.

**해결**
`docker-compose.yml`의 postgres 호스트 포트를 `5432:5432` → `15432:5432`로 변경. 컨테이너 간 통신(`postgres:5432`)은 영향 없음.

---

## 2. postgres 컨테이너가 init 스크립트 실행 중 죽음 (airflow_db 생성 안 됨)

**증상**
```
env: 'bash\r': No such file or directory
env: use -[v]S to pass options in shebang lines
```
이후 `airflow-init`이 `could not translate host name "postgres" to address: Name or service not known` 로 실패 (postgres 컨테이너 자체가 죽어서 네트워크에서 사라짐).

**원인**
`postgres/init/01-create-airflow-db.sh` 등 쉘 스크립트 4개가 Windows CRLF 줄바꿈으로 저장되어 있어서, 컨테이너(Linux) 안에서 shebang이 `#!/usr/bin/env bash\r`로 해석되어 실행 자체가 깨짐. 로컬 Git 설정(`core.autocrlf=true`)이 체크아웃 시 LF를 CRLF로 바꾼 것이 원인.

**해결**
- 4개 스크립트를 LF로 변환 (`postgres/init/01-create-airflow-db.sh`, `scripts/load-image-to-k3s.sh`, `scripts/push_code_to_minio.sh`, `scripts/spark-driver-ui.sh`)
- 재발 방지를 위해 `.gitattributes` 추가: `*.sh`, `*.py`, `Dockerfile`을 `eol=lf`로 고정 (로컬 `core.autocrlf` 설정과 무관하게)
- 이미 깨진 상태로 초기화된 `postgres-data` 볼륨은 삭제 후 재생성 (init 스크립트는 최초 1회만 실행되므로)

---

## 3. coredns CrashLoopBackOff (k3s 클러스터)

**증상**
```
[WARNING] No files matching import glob pattern: /etc/coredns/custom/*.server
plugin/hosts: this plugin can only be used once per Server Block
```
`k3s-bootstrap`의 `kubectl rollout status deployment/coredns --timeout=60s`가 타임아웃.

**원인**
k3s 기본 Corefile이 이미 `hosts /etc/coredns/NodeHosts { ... }` 블록을 쓰고 있는데, `k3s/coredns-custom.yaml`(minio를 pod 안에서 이름 해석시키기 위한 커스텀 설정)이 `hosts { ... }` 블록을 하나 더 추가해서 "서버 블록당 hosts 플러그인은 한 번만 쓸 수 있다"는 CoreDNS 제약 위반.

**해결**
`k3s/coredns-custom.yaml`에서 `hosts` 플러그인 대신 `template` 플러그인으로 변경 — 다른 플러그인이라 충돌 없이 `minio.` 쿼리에 대해서만 고정 A 레코드(172.28.0.10)를 합성해서 응답:
```yaml
minio.override: |
  template IN A . {
    match "^minio\.$"
    answer "{{ .Name }} 60 IN A 172.28.0.10"
    fallthrough
  }
```

---

## 4. spark-history-server가 시작하자마자 죽음

**증상**
```
Exception in thread "main" java.io.FileNotFoundException: Log directory specified does not exist: s3a://spark-events/logs/
```

**원인**
S3(MinIO)에는 실제 디렉터리 개념이 없어서, Spark 잡을 한 번도 안 돌린 상태에서는 `spark-events` 버킷 안에 `logs/` 프리픽스 자체가 존재하지 않음. `FsHistoryProvider`가 시작 시점에 이 경로를 stat해서 없으면 즉시 죽음.

**해결**
`minio-init`의 버킷 생성 커맨드에 빈 마커 오브젝트 생성을 추가:
```sh
echo -n | mc pipe local/spark-events/logs/.keep
```

---

## 5. k3s-bootstrap이 완전 초기화된 클러스터에서 레이스 컨디션으로 실패

**증상**
```
Error from server (NotFound): deployments.apps "coredns" not found
```

**원인**
`k3s-data` 볼륨을 지우고 클러스터를 완전히 새로 초기화하면, k3s API 서버(`kubectl get nodes`)는 응답하기 시작해도 coredns Deployment는 k3s 내장 addon 컨트롤러가 비동기로 조금 늦게 생성함. 기존 대기 조건(`kubectl get nodes`)만으로는 이 타이밍을 못 잡음.

**해결**
`k3s-bootstrap` 커맨드에 coredns deployment 존재를 기다리는 대기 루프 추가:
```sh
until kubectl -n kube-system get deployment/coredns >/dev/null 2>&1; do sleep 2; done
```

---

## 6. Airflow 웹서버에 DAG이 하나도 안 보임

**증상**
Airflow UI/`airflow dags list`에 `medallion_pipeline`이 없음.

**원인**
이 프로젝트 구조상 Airflow는 로컬 `airflow/dags/` 폴더를 직접 마운트하지 않고, MinIO `code` 버킷의 `dags/` 프리픽스를 `dags-sync` 서비스가 미러링하는 방식(Jenkins CI/CD와 동일한 정식 플로우). `scripts/push_code_to_minio.sh`를 한 번도 실행하지 않아서 MinIO `code/dags`가 비어 있었고, `dags-sync`가 미러링할 게 없어서 그냥 건너뜀.

**해결**
```sh
./scripts/push_code_to_minio.sh
docker compose run --rm dags-sync
```
DAG을 수정할 때마다 이 두 스크립트를 다시 실행해야 Airflow에 반영됨 (자동 반영 아님).

---

## 7. ingest 태스크가 Steam API에서 403 Forbidden

**증상**
```
requests.exceptions.HTTPError: 403 Client Error: Forbidden for url:
https://api.steampowered.com/IStoreService/GetAppList/v1/?key=&max_results=50000&last_appid=0&include_games=1
```
(`key=`가 빈 값으로 전달됨)

**원인**
`.env`에 `STEAM_API_KEY` 값을 나중에 채웠지만, `airflow-scheduler`/`airflow-webserver` 컨테이너는 그 값이 채워지기 *전에* 이미 떠 있었음. Docker Compose는 `.env` 파일이 바뀌어도 이미 실행 중인 컨테이너의 환경변수를 자동으로 갱신하지 않고, 컨테이너를 재생성해야 반영됨.

**해결**
```sh
docker compose up -d
```
컨테이너를 재생성해 최신 `.env` 값을 반영. (`docker exec <container> printenv <VAR>`로 실제 컨테이너 환경변수를 먼저 확인하는 습관이 필요 — `.env` 파일 값과 실행 중인 컨테이너의 값은 다를 수 있음)

---

