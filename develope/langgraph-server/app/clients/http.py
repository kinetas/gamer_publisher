"""공유 httpx.AsyncClient. FastAPI lifespan에서 init/close한다 (요청마다 새로
만들면 커넥션 재사용이 안 돼서 15개 Steam 호출이 매번 새 TCP 핸드셰이크를 함).
"""
import httpx

_client: httpx.AsyncClient | None = None


def get_http_client() -> httpx.AsyncClient:
    if _client is None:
        raise RuntimeError("http client not initialized — call init_http_client() first")
    return _client


async def init_http_client() -> None:
    global _client
    _client = httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0))


async def close_http_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
