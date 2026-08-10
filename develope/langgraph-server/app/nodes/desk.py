"""데스크: 카테고리 하나(5개 게임)를 맡아 기자들에게 배분한다. LLM 호출 없음.

편집국장→데스크는 일반 conditional edge(Send)로 도달하지만, 데스크→기자는 이
노드가 다시 Send로 fan-out해야 해서 Command(goto=[Send, ...])를 쓴다. 이 한
군데만 이 API를 쓰는 이유는 계획서(§그래프 토폴로지) 참고 — Send로 도달한
노드가 다시 Send를 여러 개 던지는 유일한 구간이라 신형 API 표면을 여기로
최소화했다.
"""
from typing import Literal

from langgraph.types import Command, Send

from ..state import DeskState


async def desk(payload: DeskState) -> Command[Literal["reporter"]]:
    games = payload["games"]
    desk_name = payload["desk_name"]
    sends = [
        Send(
            "reporter",
            {
                "game": game,
                "desk_name": desk_name,
                "report_date": payload["report_date"],
                "started_at": payload["started_at"],
            },
        )
        for game in games
    ]
    return Command(
        update={"logs": [f"[{desk_name}] {len(games)}건 배정"]},
        goto=sends,
    )
