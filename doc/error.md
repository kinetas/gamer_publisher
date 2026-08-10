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

## 8. Spark executor pod가 계속 생성 실패 ("Must specify the executor container image")

**증상**
```
org.apache.spark.SparkException: Must specify the executor container image
	at org.apache.spark.deploy.k8s.features.BasicExecutorFeatureStep...
```
driver pod는 정상 기동하지만 executor를 하나도 못 만들고 무한 재시도.

**원인**
`KubernetesPodOperator`의 `image=`는 driver pod(= 이 pod 자신, client 모드) 이미지만 지정한다. driver가 직접 만드는 executor pod에 쓸 이미지는 별도 spark-submit conf(`spark.kubernetes.container.image`)로 지정해야 하는데 빠져 있었음.

**해결**
`airflow/dags/common/spark_stage.py`의 `COMMON_SPARK_CONF`에 추가:
```
--conf spark.kubernetes.container.image=gamer_publisher/spark-jobs:latest
--conf spark.kubernetes.container.image.pullPolicy=Never
```

---

## 9. Spark executor pod가 뜨자마자 죽음 (UnknownHostException)

**증상**
```
Caused by: java.net.UnknownHostException: medallion-ingest-0a2wh1xb
```
executor가 driver pod 이름으로 재접속을 시도하다 실패, `ExecutorPodsAllocator: Max number of executor failures (10) reached`로 job 자체가 죽음.

**원인**
`--deploy-mode client`에서는 이 pod 자신이 driver인데, k8s DNS는 headless Service 없이는 bare pod 이름을 해석해주지 않는다. `spark.driver.host`를 명시적으로 안 줬음.

**해결**
Downward API로 pod 자신의 IP를 env var(`SPARK_DRIVER_POD_IP`)로 주입하고, k8s의 `$(VAR)` 치환을 이용해 spark-submit conf로 전달:
```python
k8s.V1EnvVar(
    name="SPARK_DRIVER_POD_IP",
    value_from=k8s.V1EnvVarSource(
        field_ref=k8s.V1ObjectFieldSelector(field_path="status.podIP")
    ),
)
```
```
--conf spark.driver.host=$(SPARK_DRIVER_POD_IP)
```

---

## 10. Git Bash에서 `docker run --entrypoint /bin/sh` 등이 엉뚱한 경로로 깨짐

**증상**
```
docker: Error response from daemon: failed to create task for container: ...
exec: "C:/Program Files/Git/usr/bin/sh": stat C:/Program Files/Git/usr/bin/sh: no such file or directory
```

**원인**
Git Bash(MSYS)가 컨테이너 내부 경로(`/bin/sh`, `/opt/airflow/dags/...` 등)를 Windows 경로로 자동 변환해버림.

**해결**
경로 인자가 들어가는 docker 명령 앞에 `MSYS_NO_PATHCONV=1`을 붙여서 자동변환을 끔:
```sh
MSYS_NO_PATHCONV=1 docker run --entrypoint /bin/sh ...
```

---

## 11. PowerShell/Git Bash에서 `bash scripts/xxx.sh` 실행 시 WSL 릴레이 에러

**증상**
```
<3>WSL (4331 - Relay) ERROR: CreateProcessCommon:818: execvpe(/bin/bash) failed: No such file or directory
```

**원인**
PATH상 `C:\Windows\System32\bash.exe`(WSL 릴레이)가 Git Bash보다 먼저 잡혀서, WSL에 배포판이 없는 상태로 그쪽이 실행됨.

**해결**
Git Bash 전체 경로를 직접 지정:
```powershell
& "C:\Program Files\Git\bin\bash.exe" scripts/xxx.sh
```

---

## 12. bronze 태스크가 `PATH_NOT_FOUND: s3a://datalake/raw/steam/app_list` 로 실패

**증상**
```
pyspark.errors.exceptions.captured.AnalysisException: [PATH_NOT_FOUND] Path does not exist: s3a://datalake/raw/steam/app_list.
```

**원인**
`ingest.py`에서 app_list 수집 부분을 주석 처리해서 그 경로에 데이터가 안 쓰이는데, `bronze.py`는 여전히 그 경로를 무조건 읽으려 함.

**해결**
`bronze.py`에서도 app_list 처리 부분을 동일하게 주석 처리 (ingest와 짝을 맞춤).

---

## 13. Steam Store 검색 API 페이지네이션이 429 Too Many Requests

**증상**
```
requests.exceptions.HTTPError: 429 Client Error: Too Many Requests for url: https://store.steampowered.com/search/results/...
```

**원인**
비공식 API라 명시된 rate limit이 없는데, 딜레이 없이 페이지를 빠르게 순회하다 막힘.

**해결**
`ingest.py`의 `fetch_recent_release_appids`에 페이지당 1초 딜레이 추가하고, 429를 받으면 에러로 죽는 대신 지금까지 모은 appid만으로 계속 진행하도록 변경.

---

## 14. Spark 잡이 빈 파티션 때문에 MinIO(S3A) 커밋 단계에서 FileNotFoundException (2번 발생)

**증상 (1) - ingest 단계, raw 저장 시**
```
org.apache.hadoop.fs.s3a.RemoteFileChangedException: ... File to rename not found on unguarded S3 store
```
**증상 (2) - silver 단계, dropDuplicates 이후 저장 시**
```
java.io.FileNotFoundException: No such file or directory: s3a://datalake/silver/steamspy_all/_temporary/0/task_...
```

**원인**
레코드 수보다 Spark 파티션 개수가 많으면 일부 태스크가 빈 출력만 내는데, MinIO는 AWS S3와 달리 이런 빈 파티션의 커밋(rename)을 제대로 처리 못 해서 실패함. (1)은 `parallelize()`가 기본 파티션 수로 나눈 게 원인, (2)는 `dropDuplicates`가 셔플을 일으켜 파티션이 다시 늘어난 게 원인.

**해결**
- `ingest.py`의 `write_raw_json`: `numSlices=min(len(records), spark.sparkContext.defaultParallelism)`로 레코드 수 이하로 제한
- `silver.py`: 최종 write 전에 `.coalesce(1)` 추가 (규모가 작아서 파일 1개로 합쳐도 무방)

---

## 15. postgres upsert가 "ON CONFLICT DO UPDATE command cannot affect row a second time"

**증상**
```
psycopg2.errors.CardinalityViolation: ON CONFLICT DO UPDATE command cannot affect row a second time
```

**원인**
`bronze`가 raw를 append로 누적하는 구조라, 같은 파이프라인을 재실행하면 같은 appid가 여러 번 쌓임. `silver`에 dedup 로직이 없어서 같은 appid가 중복된 채로 `gold` → postgres upsert 배치까지 흘러갔고, 같은 배치 안에서 같은 PK(appid)를 두 번 UPDATE하려다 postgres가 거부함.

**해결**
`silver.py`에서 bronze 읽은 직후 `.dropDuplicates(["appid"])` 추가.

---

## 16. langgraph-server / fastapi-server가 postgres 연결 실패 (DATABASE_URL 형식)

**원인**
`docker-compose.yml`의 기존 `DATABASE_URL`이 SQLAlchemy용 형식(`postgresql+psycopg2://...`)이었는데, 두 서비스는 raw `psycopg2.connect()`를 쓰기 때문에 `+psycopg2` 접두사를 이해하지 못함.

**해결**
`postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}` 순수 DSN 형태로 변경 (fastapi-server, langgraph-server 둘 다).

---

## 17. PDF 캡처 시 "리포트를 불러오지 못했습니다" (빈 PDF)

**증상**
`/reports/archive-current`가 성공 응답을 줬지만, 실제로 캡처된 PDF를 열어보면 프론트가 API 호출에 실패한 에러 화면만 찍혀 있었음.

**원인**
프론트 JS가 API 주소를 `http://${window.location.hostname}:8000`으로 계산했는데, 실사용자는 브라우저로 `localhost:3000`에 접속(→`localhost:8000`이 맞음)하지만, PDF 캡처용 Playwright는 도커 네트워크 내부에서 `http://frontend/print/:id`를 여는 상황이라 `window.location.hostname`이 `frontend`가 되어 `frontend:8000`(존재하지 않는 주소)으로 호출함.

**해결**
프론트 nginx에 `/api/*` → `http://fastapi-server:8000/` 리버스 프록시 추가하고, 프론트 JS는 항상 상대경로 `/api`만 쓰도록 변경 (`frontend/nginx.conf`, `frontend/src/api.ts`). 브라우저로 보든 헤드리스로 보든 "현재 origin + /api"는 항상 유효해서 문제 해결.

---

## 18. Airflow 태스크 실행 순서가 뒤섞임 ("state changed externally")

**증상**
```
ERROR - The executor reported that the task instance ... finished with state success, but the task instance's state attribute is queued.
```
`archive_current_report >> ingest` 순서로 의존성을 걸었는데, 실제로는 `ingest`가 `archive_current_report`보다 먼저(심지어 즉시 실패로) 실행됨.

**원인**
DAG 파일에 새 태스크(`archive_current_report`)를 추가하고 MinIO 동기화 직후 바로 트리거해서, 스케줄러가 아직 새 DAG 구조로 완전히 갱신(재직렬화)하기 전 상태로 트리거가 걸림.

**해결**
DAG 동기화 후 잠깐 안정화될 시간을 두고 재트리거. 코드 문제가 아니라 스케줄러 타이밍 이슈라 재실행으로 해결됨.

---

## 19. (설계 결정) SteamSpy만으로는 "발견 안 된 신작"을 못 찾음

**상황**
SteamSpy `all`은 인기순(owners) 정렬이라, `max_pages`를 제한해서 수집하면 무명 신작은 순위 밖이라 애초에 수집 대상에서 빠짐. SteamSpy 자체에는 출시일 필드도 없어서 "신작"인지 구분도 불가능.

**결정**
Steam Store의 비공식 검색 API(`store.steampowered.com/search/results`)로 출시일 range 필터(`released=Custom&from=...&to=...`)를 걸어 appid만 뽑고, 그 appid들로 SteamSpy `appdetails`(개별 조회)를 호출해 지표를 채우는 2단계 구조로 변경. 신작 발굴 창은 "출시 2개월 전 ~ 2개월 전+1주"로 잡아서, 리뷰가 어느 정도 쌓인 시점만 보되 매주 창이 달력 기준으로 한 칸씩 밀리도록 해서 별도 dedup 없이도 주차별로 겹치지 않는 게임이 나오게 함.

---

## 20. (설계 결정) "다시 추천"은 신규 추천 이력에서만 재소환

**상황**
주간 리포트는 매주 내용이 겹치면 안 되는데, "신규 추천" 풀은 출시일 기준 시간 윈도우가 매주 앞으로 이동하며 계속 새 게임이 들어오는 구조라, 한번 소개된 게임은 별도 장치가 없으면 두 번 다시 노출될 기회가 없음. 반면 "옛 작품 소개" 풀은 슬롯 자체가 이미 `last_recommended_at`이 오래된 순으로 매주 도는 구조라 자체적으로 로테이션됨.

**결정**
"다시 추천" 슬롯은 옛 작품 풀과는 무관하게, **"신규 추천"으로 한번 소개됐던 게임(`recent_games` 이력)에서만** `last_recommended_at`이 오래된 순으로 재소환한다. 이 때문에 `old_games`/`recent_games`를 완전히 분리된 테이블로 두고, `select_weekly_report`의 재추천 쿼리는 `recent_games` 테이블만 조회한다.

---

## 21. (설계 결정) gold 단계에서 Pool A/B를 합칠 필요 없음

**상황**
옛 작품/신규 후보 데이터가 각각 수천 row 수준으로 작고, postgres 이력 대조는 정렬+LIMIT 위주의 관계형 쿼리라 Spark의 분산 처리가 필요 없는 작업임. Spark로 두 풀을 미리 합쳐서 넘기면 파이프라인 단계만 하나 늘고(gold merge) 실제로 하는 일은 단순 union뿐임.

**결정**
gold의 merge 단계를 없애고, 각 풀별 gold task는 자기 풀의 최종 지표만 postgres(`old_games`/`recent_games`)에 upsert하는 역할로 재정의한다. 이력 대조/선정을 담당하는 Python task(`select_weekly_report`)가 두 postgres 테이블을 직접 읽어서 처리한다.

---

## 22. (설계 결정) PDF 생성은 헤드리스 브라우저 캡처, langgraph는 콘텐츠만

**상황**
과거 리포트는 프론트 메인 화면에 다시 띄우지 않고 다운로드 전용으로만 제공해야 하는 요구사항이 있었고, 이미 만들어둔 리포트 레이아웃(1페이지 그리드 + 상세 페이지)을 PDF에서도 그대로 재사용하는 게 유지보수 관점에서 유리함. langgraph 쪽에서 별도 PDF 라이브러리로 처음부터 다시 그리면 레이아웃을 두 군데서 관리해야 함.

**결정**
langgraph-server는 게임별 소개 글 생성 + postgres 저장까지만 담당한다. 프론트에 헤더/사이드바/푸터 없는 `/print/:id` 페이지를 따로 만들고, fastapi-server가 Playwright로 그 페이지를 캡처해서 MinIO에 저장한다. fastapi-server가 이 역할을 맡은 이유는 backend-net(postgres/minio)과 app-net(frontend) 양쪽에 걸쳐있는 유일한 서비스라서(Airflow는 app-net에 없어 frontend에 직접 접근 불가).

---

