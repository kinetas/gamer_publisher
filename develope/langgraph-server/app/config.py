"""환경변수 읽기 + 외부 호출 동시성 제한(세마포어) + 모델명 상수.

세마포어는 asyncio.Semaphore를 모듈 임포트 시점에 만든다. Python 3.10+에서는
Semaphore가 이벤트 루프에 바인딩되지 않으므로(과거 버전의 제약이 사라짐) 임포트
시점에 만들어도 안전하다. 이 프로젝트 Dockerfile은 python:3.11-slim.
"""
import asyncio
import os

DATABASE_URL = os.environ.get("DATABASE_URL")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY") or None

# Ollama 등 OpenAI 호환 로컬 서버를 쓰려면 LLM_BASE_URL만 채우면 된다
# (예: http://ollama:11434/v1 — 같은 docker-compose 네트워크 안에서 서비스명으로).
# 비어있으면 기존처럼 실제 OpenAI API로 붙는다. 로컬 서버는 키를 검사하지
# 않지만 SDK가 빈 문자열 키를 거부해서 OPENAI_API_KEY가 없을 때 더미 값을 쓴다.
LLM_BASE_URL = os.environ.get("LLM_BASE_URL") or None
LLM_API_KEY = OPENAI_API_KEY or ("local" if LLM_BASE_URL else None)

REDDIT_CLIENT_ID = os.environ.get("REDDIT_CLIENT_ID") or None
REDDIT_CLIENT_SECRET = os.environ.get("REDDIT_CLIENT_SECRET") or None
REDDIT_USER_AGENT = os.environ.get(
    "REDDIT_USER_AGENT", "python:gamer-publisher:0.1.0 (weekly game report bot)"
)

CHROMADB_HOST = os.environ.get("CHROMADB_HOST", "chromadb")
CHROMADB_PORT = int(os.environ.get("CHROMADB_PORT", "8000"))
# 게임메카 등에서 모아온 실제 근거자료(제목+짧은 요약+원문 링크)를 의미 검색으로
# 찾는 용도. "같은 게임 과거 소개글" 조회는 완전일치라 postgres로 옮겼다
# (db.lookup_past_writeups) — chromadb는 이제 이 용도 하나만 쓴다.
CHROMA_NEWS_COLLECTION = os.environ.get("CHROMA_NEWS_COLLECTION", "game_news_refs")

# 로컬 서버로 돌릴 때는 여기 기본값이 아니라 그쪽에 실제로 받아둔(pull/load한)
# 모델 식별자와 정확히 일치해야 한다 (예: Ollama면 "qwen2.5:3b"). env로 덮어쓴다.
REPORTER_MODEL = os.environ.get("REPORTER_MODEL", "gpt-4o-mini")
COPY_DESK_MODEL = os.environ.get("COPY_DESK_MODEL", "gpt-4o-mini")
EDITORIAL_MODEL = os.environ.get("EDITORIAL_MODEL", "gpt-4o-mini")
SENTIMENT_MODEL = os.environ.get("SENTIMENT_MODEL", "gpt-4o-mini")
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small")

# 데스크당 기자 수(=카테고리별 슬롯 수)와 일치. Airflow 쪽 OLD_SLOT_COUNT 등이
# 바뀌면 여기도 맞춰야 하지만, 이 값 자체는 그래프 구조를 고정하는 데 쓰이지 않고
# 로깅/검증용으로만 참조한다 (그래프는 입력 리스트 길이를 그대로 따라간다).
EXPECTED_SLOT_COUNT = 5

# 리소스별 동시 호출 제한. doc/error.md #13(Steam Store 429 이력)을 반복하지 않기
# 위한 안전장치 — 개수는 계획서(§동시성) 근거 참고.
STEAM_SEM = asyncio.Semaphore(4)
REDDIT_SEM = asyncio.Semaphore(3)
# 실제 OpenAI는 네트워크 병목이라 8개 동시 호출이 실제로 병렬 처리된다. 로컬
# CPU 서버(Ollama 등)는 컨테이너 하나가 물리적으로 순차 처리에 가까워서, 동시
# 요청을 많이 넣어봐야 서로 자원만 나눠 쓰며 다같이 느려진다 — LLM_BASE_URL을
# 쓸 때는 docker-compose에서 LLM_CONCURRENCY를 낮게(예: 2) 넘긴다.
LLM_SEM = asyncio.Semaphore(int(os.environ.get("LLM_CONCURRENCY", "8")))
CHROMA_SEM = asyncio.Semaphore(4)
