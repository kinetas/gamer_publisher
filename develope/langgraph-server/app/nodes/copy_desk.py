"""교열부: 15개 초고가 모두 모였는지 확인하는 barrier(copy_desk) + 게임별로
병렬 실행되는 사실체크(copy_editor).

copy_editor는 reporter가 이미 가져온 Reddit/Steam 자료(draft.research)를
재사용한다 — 같은 데이터를 두 번 수집하지 않는다.

**반려 -> 재작성 루프(최대 1회)**: copy_editor가 "근거 없이 지어낸 초고"라고
판단하면(LLM이 REWRITE_NEEDED를 응답) Command로 reporter에게 직접 돌려보낸다.
이때 공유 barrier인 copy_desk/dispatch_copy_editors를 다시 거치지 않는다 —
거치면 dispatch_copy_editors가 state["drafts"]에 누적된 전체 목록을 또
fan-out해서 이미 끝난 다른 게임들까지 중복 실행되기 때문. 대신 reporter가
재작성을 마치면 copy_editor 한 명에게 곧장 Command로 돌아온다(reporter.py 참고).

layout_desk는 copy_editor -> layout_desk 고정 edge(graph.py)로 도달한다. 예전엔
"checked 개수가 기대치에 도달했는지"를 직접 세는 조건부 edge(dispatch_layout_desk)를
썼는데, Send로 도달한 노드(copy_editor)에 붙은 조건부 edge 함수는 같은 superstep 안
형제 브랜치들의 기여분(checked/old_introductions 등)을 볼 수 없어(LangGraph가
superstep 종료 후에만 reducer를 병합) expected가 항상 0으로 계산되는 버그가 있었다
— layout_desk가 아예 안 불려서 매번 postgres 저장이 조용히 스킵됐다
(doc/session-2026-08-11-local-llm-and-studio.md §12). 고정 edge는 대상 노드가
실제로 실행되는 시점(다음 superstep)에 정상적으로 병합된 전역 state를 받으므로
문제가 없다 — reporter -> copy_desk가 이미 같은 패턴으로 정상 동작 중.

반려/재작성 루프 때문에 재작성된 게임의 copy_editor는 별도 Send로 뒤늦게(다른
superstep에) 도착하므로, 그 케이스에서는 layout_desk가 두 번 실행될 수 있다
(최초 배치 완료 시 1회 + 재작성 완료 시 1회 더). db.save_weekly_report가
report_date 기준 upsert라 마지막 실행이 항상 전체 게임을 포함한 완전한 content로
덮어써서 최종 저장 결과는 정확하다.
"""
import logging
import time
from typing import Literal

from langgraph.types import Command, Send

from .. import prompts
from ..clients import llm
from ..config import COPY_DESK_MODEL
from ..state import CheckedDraft, CopyState, ReportState

logger = logging.getLogger(__name__)

_REWRITE_MARKER = "REWRITE_NEEDED"
_MAX_REWRITES = 1


async def copy_desk(state: ReportState) -> dict:
    drafts = state.get("drafts") or []
    return {"logs": [f"[copy_desk] {len(drafts)}개 초고 확인, 교열 시작"]}


def dispatch_copy_editors(state: ReportState) -> list[Send]:
    """최초 배치만 여기서 fan-out한다. 재작성분은 reporter가 Command로 이 barrier를
    우회해서 copy_editor에게 직접 보낸다 (docstring 참고).

    이미 checked에 들어간(=copy_editor를 이미 거친) appid는 다시 안 보낸다.
    이 함수는 정상적으로는 copy_desk barrier당 정확히 한 번만 불려야 하지만,
    reporter->copy_desk 고정 edge가 예상과 달리 재작성 경로에서도 다시 걸려
    이 함수가 중복 호출되는 경우를 실제로 겪었다 - 그때 이 가드가 없으면
    이미 끝난 원본 draft(retry_count=0)가 매번 다시 fan-out되어, 불안정한
    로컬 LLM이 계속 REWRITE_NEEDED를 내는 한 사실상 무한루프(같은 게임이
    수십 번 재작성/재검수되며 checked도 계속 불어남)로 이어진다. "몇 번
    불리는지"를 정확히 막기보다 "몇 번 불려도 같은 게임을 두 번 처리하지
    않는다"가 훨씬 견고한 방어다.
    """
    already_checked = {c["game"]["appid"] for c in (state.get("checked") or [])}
    return [
        Send("copy_editor", {"draft": d})
        for d in state.get("drafts") or []
        if d["game"]["appid"] not in already_checked
    ]


def _is_rewrite_needed(result_text: str | None) -> bool:
    return bool(result_text) and result_text.strip().upper().startswith(_REWRITE_MARKER)


def _is_malformed(result_text: str | None) -> bool:
    """지시사항(첫 줄에 정확히 REWRITE_NEEDED만 쓰거나, 아예 안 쓰거나)을 못 지키고
    본문 뒤에 REWRITE_NEEDED 마커를 덧붙이는 등 형식이 깨진 응답을 걸러낸다.
    로컬 소형 모델(qwen2.5:3b 등)이 실제로 이렇게 마커를 본문에 흘리는 경우가
    있어서, 이런 응답을 그대로 final_text로 쓰면 사용자에게 내부 지시문이
    그대로 노출된다. 첫 줄에 마커가 있는 정상 케이스(_is_rewrite_needed)는
    여기서 안 걸린다.
    """
    return bool(result_text) and _REWRITE_MARKER in result_text.upper() and not _is_rewrite_needed(
        result_text
    )


async def copy_editor(payload: CopyState) -> dict | Command[Literal["reporter"]]:
    draft = payload["draft"]
    game = draft["game"]
    research = draft["research"]
    retry_count = draft.get("retry_count", 0)

    prompt = prompts.copy_desk_prompt(draft["draft_text"], game, research)
    result_text = await llm.complete(
        prompt, model=COPY_DESK_MODEL, label=f"copy_editor({game['appid']})"
    )

    can_rewrite = not draft.get("error") and retry_count < _MAX_REWRITES
    if can_rewrite and _is_rewrite_needed(result_text):
        reason = result_text.strip()[len(_REWRITE_MARKER):].strip(" :-\n") or "근거 부족"
        return Command(
            update={
                "logs": [
                    f"[copy_editor] appid={game['appid']} 반려 -> 기자 재작성 요청 ({reason[:80]})"
                ]
            },
            goto=[
                Send(
                    "reporter",
                    {
                        "game": game,
                        "started_at": draft.get("started_at", time.monotonic()),
                        "is_revision": True,
                        "retry_count": retry_count + 1,
                        "revision_feedback": reason,
                        "previous_draft_text": draft["draft_text"],
                        "research": research,
                    },
                )
            ],
        )

    corrections: list[str] = []
    if result_text is None or draft.get("error"):
        final_text = draft["draft_text"]
    elif _is_rewrite_needed(result_text):
        # 재작성 상한에 걸려 더 반려할 수 없다 -> 강제 통과, 초고를 그대로 쓴다.
        final_text = draft["draft_text"]
    elif _is_malformed(result_text):
        # 형식이 깨진 응답(본문 뒤에 REWRITE_NEEDED가 새어 들어간 경우 등)을
        # 그대로 쓰면 내부 지시문이 사용자에게 노출된다 - 안전하게 초고로 폴백.
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
        "image": (research.get("steam") or {}).get("image", ""),
    }
    return {
        "checked": [checked],
        "logs": [
            f"[copy_editor] appid={game['appid']} 교열 완료 (수정={'O' if corrections else 'X'})"
        ],
    }
