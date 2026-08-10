"""429/5xx에 대한 지수 백오프 + 지터 재시도 헬퍼.

tenacity 같은 새 의존성을 추가하지 않기 위해 직접 구현한다 (chromadb-client가
tenacity를 이미 끌고 오지만, 그건 chroma 내부용이라 우리 코드가 직접 의존하지
않는다).
"""
import asyncio
import logging
import random
from typing import Awaitable, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

DEFAULT_RETRY_STATUS = (429, 500, 502, 503)


def _status_of(exc: Exception) -> int | None:
    status = getattr(exc, "status_code", None)
    if status is not None:
        return status
    response = getattr(exc, "response", None)
    return getattr(response, "status_code", None) if response is not None else None


def _retry_after_of(exc: Exception) -> float | None:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None) if response is not None else None
    value = headers.get("Retry-After") if headers else None
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


async def retry_async(
    fn: Callable[[], Awaitable[T]],
    *,
    attempts: int = 3,
    base_delay: float = 1.0,
    retry_on_status: tuple[int, ...] = DEFAULT_RETRY_STATUS,
    label: str = "call",
) -> T:
    """fn()을 실행하고, status_code가 retry_on_status에 속하는 예외만 재시도한다.

    그 외 예외(인증 실패, 잘못된 요청 등)는 즉시 재발생시킨다 — 무한정 재시도해도
    성공할 수 없는 오류를 백오프로 감추지 않기 위함.
    """
    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            return await fn()
        except Exception as exc:  # noqa: BLE001 - 재시도 여부 판단을 위해 넓게 잡음
            status = _status_of(exc)
            if status is not None and status not in retry_on_status:
                raise
            last_exc = exc
            if attempt == attempts - 1:
                break
            delay = _retry_after_of(exc) or base_delay * (2**attempt)
            delay += random.uniform(0, delay * 0.1)
            logger.warning(
                "%s: attempt %d/%d failed (%s), retrying in %.1fs",
                label, attempt + 1, attempts, exc, delay,
            )
            await asyncio.sleep(delay)
    assert last_exc is not None
    raise last_exc
