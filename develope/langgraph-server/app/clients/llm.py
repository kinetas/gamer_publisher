"""AsyncOpenAI 래퍼. OPENAI_API_KEY가 없으면 client가 None이 되고, complete()/
embed_batch()는 그때 그냥 None을 돌려준다 — 호출부(기자/교열/RAG)가 기존
main.py의 `openai_client is None` 자리에 있던 placeholder 대체 로직을 그대로
쓸 수 있게 하기 위함.
"""
import logging

from openai import AsyncOpenAI

from ..config import LLM_SEM, OPENAI_API_KEY
from ._retry import retry_async

logger = logging.getLogger(__name__)

client: AsyncOpenAI | None = AsyncOpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None


async def complete(prompt: str, *, model: str, max_tokens: int = 300, label: str = "llm") -> str | None:
    if client is None:
        return None

    async def _call() -> str:
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
        )
        return (response.choices[0].message.content or "").strip()

    try:
        async with LLM_SEM:
            return await retry_async(_call, label=label)
    except Exception as exc:  # noqa: BLE001 - LLM 실패가 그래프를 죽이면 안 됨
        logger.warning("%s 호출 실패: %s", label, exc)
        return None


async def embed_batch(texts: list[str], *, model: str) -> list[list[float]] | None:
    """여러 텍스트를 한 번에 임베딩(배치 1콜)한다. 키가 없거나 실패하면 None."""
    if client is None or not texts:
        return None

    async def _call() -> list[list[float]]:
        response = await client.embeddings.create(model=model, input=texts)
        return [item.embedding for item in response.data]

    try:
        async with LLM_SEM:
            return await retry_async(_call, label="embed_batch")
    except Exception as exc:  # noqa: BLE001
        logger.warning("embed_batch 실패: %s", exc)
        return None
