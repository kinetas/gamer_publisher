FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# PDF archive(/reports/archive-current)가 헤드리스 크로미움으로 frontend의
# /print/:id 페이지를 캡처한다. 브라우저 바이너리 + OS 의존성을 같이 설치한다.
RUN playwright install --with-deps chromium

COPY app ./app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
