"""논설위원실(총평): state["checked"] 15개를 모아 한 번의 LLM 호출로 이번 주
총평을 쓴다.

토큰 비용 때문에 graph.py에서 그래프 등록(add_node/add_edge)이 주석 처리되어
있다 — 이 노드 자체는 정상 동작하니, 활성화하려면 graph.py에서 주석 처리된
3줄만 풀면 된다. layout_desk는 이미 state["commentary"]가 있으면
content["commentary"]에 얹도록 짜여 있다.
"""
import logging

from .. import prompts
from ..clients import llm
from ..config import EDITORIAL_MODEL
from ..state import ReportState

logger = logging.getLogger(__name__)


async def editorial_board(state: ReportState) -> dict:
    checked = state.get("checked") or []
    if not checked:
        return {"commentary": ""}

    prompt = prompts.editorial_prompt(checked)
    commentary = await llm.complete(prompt, model=EDITORIAL_MODEL, label="editorial_board")
    return {
        "commentary": commentary or "",
        "logs": [f"[editorial_board] 총평 작성 {'완료' if commentary else '실패(LLM 불가)'}"],
    }
