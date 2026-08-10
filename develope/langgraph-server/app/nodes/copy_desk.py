"""교열부: 15개 초고가 모두 모였는지 확인하는 barrier(copy_desk) + 게임별로
병렬 실행되는 사실체크(copy_editor).

copy_editor는 reporter가 이미 가져온 Reddit/Steam 자료(draft.research)를
재사용한다 — 같은 데이터를 두 번 수집하지 않는다.
"""
import logging

from langgraph.types import Send

from .. import prompts
from ..clients import llm
from ..config import COPY_DESK_MODEL
from ..state import CheckedDraft, CopyState, ReportState

logger = logging.getLogger(__name__)


async def copy_desk(state: ReportState) -> dict:
    drafts = state.get("drafts") or []
    return {"logs": [f"[copy_desk] {len(drafts)}개 초고 확인, 교열 시작"]}


def dispatch_copy_editors(state: ReportState) -> list[Send]:
    return [Send("copy_editor", {"draft": d}) for d in state.get("drafts") or []]


async def copy_editor(payload: CopyState) -> dict:
    draft = payload["draft"]
    game = draft["game"]
    research = draft["research"]

    prompt = prompts.copy_desk_prompt(draft["draft_text"], research)
    result_text = await llm.complete(
        prompt, model=COPY_DESK_MODEL, label=f"copy_editor({game['appid']})"
    )

    corrections: list[str] = []
    if result_text is None or draft.get("error"):
        # LLM 불가하거나 애초에 기자 단계가 placeholder였던 경우 초고를 그대로 통과시킨다.
        final_text = draft["draft_text"]
    else:
        final_text = result_text
        if final_text.strip() != draft["draft_text"].strip():
            corrections.append("교열 단계에서 문구 수정됨")

    checked: CheckedDraft = {
        "game": game,
        "final_text": final_text,
        "corrections": corrections,
        "embed_doc": final_text,
    }
    return {
        "checked": [checked],
        "logs": [
            f"[copy_editor] appid={game['appid']} 교열 완료 (수정={'O' if corrections else 'X'})"
        ],
    }
