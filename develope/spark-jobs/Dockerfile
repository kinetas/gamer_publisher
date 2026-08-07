FROM bitnamilegacy/spark:3.5

WORKDIR /opt/spark-jobs

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY jobs ./jobs
