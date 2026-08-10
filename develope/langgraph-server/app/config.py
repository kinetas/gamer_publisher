"""환경변수 읽기 + 외부 호출 동시성 제한(세마포어) + 모델명 상수.

세마포어는 asyncio.Semaphore를 모듈 임포트 시점에 만든다. Python 3.10+에서는
Semaphore가 이벤트 루프에 바인딩되지 않으므로(과거 버전의 제약이 사라짐) 임포트
시점에 만들어도 안전하다. 이 프로젝트 Dockerfile은 python:3.11-slim.
"""
import asyncio
import os

DATABASE_URL = os.environ.get("DATABASE_URL")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY") or None

REDDIT_CLIENT_ID = os.environ.get("REDDIT_CLIENT_ID") or None
REDDIT_CLIENT_SECRET = os.environ.get("REDDIT_CLIENT_SECRET") or None
REDDIT_USER_AGENT = os.environ.get(
    "REDDIT_USER_AGENT", "python:gamer-publisher:0.1.0 (weekly game report bot)"
)

CHROMADB_HOST = os.environ.get("CHROMADB_HOST", "chromadb")
CHROMADB_PORT = int(os.environ.get("CHROMADB_PORT", "8000"))
CHROMA_COLLECTION = "weekly_writeups"

REPORTER_MODEL = "gpt-4o-mini"
COPY_DESK_MODEL = "gpt-4o-mini"
EDITORIAL_MODEL = "gpt-4o-mini"
EMBEDDING_MODEL = "text-embedding-3-small"

# 데스크당 기자 수(=카테고리별 슬롯 수)와 일치. Airflow 쪽 OLD_SLOT_COUNT 등이
# 바뀌면 여기도 맞춰야 하지만, 이 값 자체는 그래프 구조를 고정하는 데 쓰이지 않고
# 로깅/검증용으로만 참조한다 (그래프는 입력 리스트 길이를 그대로 따라간다).
EXPECTED_SLOT_COUNT = 5

# 리소스별 동시 호출 제한. doc/error.md #13(Steam Store 429 이력)을 반복하지 않기
# 위한 안전장치 — 개수는 계획서(§동시성) 근거 참고.
STEAM_SEM = asyncio.Semaphore(4)
REDDIT_SEM = asyncio.Semaphore(3)
LLM_SEM = asyncio.Semaphore(8)
CHROMA_SEM = asyncio.Semaphore(4)
