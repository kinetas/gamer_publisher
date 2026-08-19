FROM bitnamilegacy/spark:3.5

WORKDIR /opt/spark-jobs

COPY requirements.txt .
# torch는 기본 PyPI 인덱스에서 받으면 CUDA 빌드가 딸려와 이미지가 수 GB로 불어난다.
# 이 프로젝트는 k3s pod에서 CPU로만 추론한다(감성분석 1차 분류, sentiment_classify.py -
# 대용량 분산처리가 필요 없는 규모라 GPU가 애초에 필요 없음)하므로 CPU 전용 wheel을
# 명시적으로 먼저 설치해 용량을 크게 줄인다. requirements.txt에는 torch를 넣지 않았다
# (아래 두 번째 pip install이 기본 인덱스로 torch를 다시 끌어와 이 설치를 덮어쓰는
# 것을 막기 위함).
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements.txt

COPY jobs ./jobs
