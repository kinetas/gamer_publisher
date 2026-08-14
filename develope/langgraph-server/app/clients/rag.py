"""chromadb RAG: 게임메카 등에서 모아온 실제 기사(제목+짧은 요약+원문 링크)를
의미 검색으로 찾아 기자가 근거자료로 참고하게 돕는다.

"같은 게임을 예전에 소개한 적 있는가"는 완전일치 질문이라 여기서 다루지
않는다 — 그건 db.lookup_past_writeups가 postgres로 직접 처리한다. 여기는
진짜 유사도 검색(게임 이름/장르로 관련 기사 찾기)만 담당한다.

저작권 문제를 피하려고 기사 본문 전체가 아니라 RSS가 제공하는 짧은 요약(리드
문단, 600~900자 정도)만 저장한다 — clients/gamemeca.py 참고. 검색 결과를 글에
쓸 때는 반드시 원문 링크를 같이 노출한다(prompts.py).
"""
import asyncio
import logging

import chromadb

from ..config import CHROMA_NEWS_COLLECTION, CHROMADB_HOST, CHROMADB_PORT, CHROMA_SEM, EMBEDDING_MODEL
from . import llm

logger = logging.getLogger(__name__)

_client = None  # chromadb.HttpClient(...)의 반환값. 지연 생성 + 재사용.


def _get_collection():
    global _client
    if _client is None:
        _client = chromadb.HttpClient(host=CHROMADB_HOST, port=CHROMADB_PORT)
    return _client.get_or_create_collection(CHROMA_NEWS_COLLECTION)


async def search_relevant_articles(query: str, *, game_name: str, limit: int = 3) -> list[dict]:
    """query(게임 이름 + 장르 등)와 의미상 가까운 기사를 최대 limit개 돌려준다.

    chroma의 벡터 검색은 유사도 임계값이 없어서 - 컬렉션에 이 게임과 관련된
    기사가 하나도 없어도 "그나마 제일 가까운" top-N을 무조건 돌려준다. 로컬
    소형 임베딩 모델(예: qwen2.5:3b/bge-m3)에서는 이게 실제로 전혀 무관한
    기사(예: 다른 게임의 이벤트 소식)를 "근거자료"로 프롬프트에 흘려보내
    reporter가 엉뚱한 내용을 사실인 양 섞어 쓰는 환각으로 이어졌다. 그래서
    game_name이 기사 제목/요약에 문자 그대로 등장하는 것만 최종 통과시킨다 -
    임베딩 거리 기반 컷오프보다 훨씬 보수적이지만, 오탐(전혀 다른 게임 얘기를
    근거자료로 착각)보다는 미탐(관련 기사인데 놓침)이 훨씬 안전한 실패 모드다.

    반환 항목: {"title", "excerpt", "link", "source"}. 컬렉션이 비어있거나
    임베딩 실패, chroma 조회 실패, 관련 기사 없음이면 [] (기존 Steam 소개글만으로
    작성하는 경로로 자연스럽게 폴백된다 — reporter.py/prompts.py 참고).
    """
    embeddings = await llm.embed_batch([query], model=EMBEDDING_MODEL)
    if not embeddings:
        return []

    def _call() -> list[dict]:
        collection = _get_collection()
        if collection.count() == 0:
            return []
        # 실제로 game_name 매칭되는 후보를 limit개 채울 수 있도록 넉넉히 뽑는다.
        result = collection.query(
            query_embeddings=embeddings, n_results=limit * 5, include=["documents", "metadatas"]
        )
        metadatas = (result.get("metadatas") or [[]])[0]
        candidates = [
            {
                "title": m.get("title", ""),
                "excerpt": doc,
                "link": m.get("link", ""),
                "source": m.get("source", ""),
            }
            for m, doc in zip(metadatas, (result.get("documents") or [[]])[0])
        ]
        needle = game_name.strip().lower()
        relevant = [
            c for c in candidates if needle and needle in f"{c['title']} {c['excerpt']}".lower()
        ]
        return relevant[:limit]

    try:
        async with CHROMA_SEM:
            return await asyncio.to_thread(_call)
    except Exception as exc:  # noqa: BLE001 - chroma 실패가 그래프를 죽이면 안 됨
        logger.warning("game_news_refs 검색 실패 query=%s: %s", query, exc)
        return []


async def upsert_articles(articles: list[dict]) -> None:
    """articles: clients.gamemeca.fetch_latest_articles()가 돌려주는 형태
    ({"id","title","excerpt","link","pub_date","image_url","source"}).

    임베딩 못 만들면(OPENAI_API_KEY/LLM_BASE_URL 미설정 등) 통째로 스킵한다.
    """
    if not articles:
        return

    texts = [f"{a['title']}\n{a['excerpt']}" for a in articles]
    embeddings = await llm.embed_batch(texts, model=EMBEDDING_MODEL)
    if embeddings is None:
        logger.warning("game_news_refs upsert 스킵: 임베딩 생성 불가")
        return

    def _call() -> None:
        collection = _get_collection()
        collection.upsert(
            ids=[a["id"] for a in articles],
            documents=[a["excerpt"] for a in articles],
            embeddings=embeddings,
            metadatas=[
                {
                    "title": a["title"],
                    "link": a["link"],
                    "source": a.get("source", ""),
                    "pub_date": a.get("pub_date", ""),
                    "image_url": a.get("image_url", ""),
                }
                for a in articles
            ],
        )

    try:
        async with CHROMA_SEM:
            await asyncio.to_thread(_call)
    except Exception as exc:  # noqa: BLE001
        logger.warning("game_news_refs upsert 실패: %s", exc)
