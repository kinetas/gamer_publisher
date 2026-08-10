"""chromadb RAG: 같은 게임의 과거 소개글을 찾아 기자가 표현을 반복하지 않게 돕는다.

"이 게임을 예전에 소개한 적 있는가"는 유사도 질문이 아니라 exact-match 질문이라,
벡터 검색이 아니라 appid 메타데이터 필터(collection.get(where=...))로 조회한다.
임베딩은 chromadb의 내장 임베딩 함수(동기, 이벤트루프 블로킹 + onnx 모델 필요)에
맡기지 않고 clients.llm.embed_batch로 직접 배치 계산해서 upsert 시 넘긴다.
"""
import asyncio
import logging

import chromadb

from ..config import CHROMA_COLLECTION, CHROMADB_HOST, CHROMADB_PORT, CHROMA_SEM, EMBEDDING_MODEL
from . import llm

logger = logging.getLogger(__name__)

_client = None  # chromadb.HttpClient(...)의 반환값. 지연 생성 + 재사용.


def _get_collection():
    global _client
    if _client is None:
        _client = chromadb.HttpClient(host=CHROMADB_HOST, port=CHROMADB_PORT)
    return _client.get_or_create_collection(CHROMA_COLLECTION)


async def lookup_by_appid(appid: int, *, limit: int = 3) -> list[str]:
    """같은 게임의 과거 소개글(최신순)을 최대 limit개 돌려준다. 실패/이력없음이면 []."""

    def _call() -> list[str]:
        collection = _get_collection()
        result = collection.get(where={"appid": appid}, include=["documents", "metadatas"])
        pairs = list(zip(result.get("metadatas") or [], result.get("documents") or []))
        pairs.sort(key=lambda p: p[0].get("report_date", ""), reverse=True)
        return [doc for _, doc in pairs[:limit]]

    try:
        async with CHROMA_SEM:
            return await asyncio.to_thread(_call)
    except Exception as exc:  # noqa: BLE001 - chroma 실패가 그래프를 죽이면 안 됨
        logger.warning("chroma lookup 실패 appid=%s: %s", appid, exc)
        return []


async def upsert_writeups(entries: list[dict]) -> None:
    """entries: [{"appid","name","category","report_date","genres","developer","text"}, ...]

    OPENAI_API_KEY가 없어 임베딩을 못 만들면 통째로 스킵한다 — EF를 설정하지 않은
    컬렉션은 임베딩 없는 add/upsert를 받아주지 않는다.
    """
    if not entries:
        return

    texts = [e["text"] for e in entries]
    embeddings = await llm.embed_batch(texts, model=EMBEDDING_MODEL)
    if embeddings is None:
        logger.warning("chroma upsert 스킵: 임베딩 생성 불가(OPENAI_API_KEY 미설정 등)")
        return

    def _call() -> None:
        collection = _get_collection()
        collection.upsert(
            ids=[f"{e['appid']}:{e['report_date']}" for e in entries],
            documents=texts,
            embeddings=embeddings,
            metadatas=[
                {
                    "appid": e["appid"],
                    "name": e["name"],
                    "category": e["category"],
                    "report_date": e["report_date"],
                    "genres": ",".join(e.get("genres") or []),
                    "developer": e.get("developer") or "",
                }
                for e in entries
            ],
        )

    try:
        async with CHROMA_SEM:
            await asyncio.to_thread(_call)
    except Exception as exc:  # noqa: BLE001
        logger.warning("chroma upsert 실패: %s", exc)
