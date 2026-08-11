"""LangGraph 그래프 state 및 Send payload 타입 정의.

ReportState가 그래프의 전역 스키마다. 병렬로 여러 번 실행되는 노드(desk/reporter/
copy_editor)는 반드시 reducer가 걸린 채널(drafts/checked/logs)에만 값을 써야 한다.
그 외 채널(content/commentary/timings)에 병렬 브랜치에서 동시에 쓰면 LangGraph가
런타임에 InvalidUpdateError를 던진다 — 이 채널들은 barrier 이후 단일 노드
(layout_desk/editorial_board)만 쓴다.

Category 문자열은 weekly_reports.content의 최상위 키(old_introductions/
recent_replays/recent_new)와 정확히 일치해야 한다 — fastapi-server의
_row_to_report가 이 키만 읽고, 프론트 타입도 이 이름에 맞춰져 있다.
"""
import operator
from typing import Annotated, Literal, TypedDict

Category = Literal["old_introductions", "recent_replays", "recent_new"]


class SteamDetail(TypedDict, total=False):
    short_description: str
    genres: list[str]
    release_date: str
    is_free: bool
    image: str  # Steam appdetails의 header_image URL. 없으면 프론트가 placeholder를 그린다.


class RedditBuzz(TypedDict, total=False):
    titles: list[str]
    comments: list[str]


class GameRef(TypedDict):
    appid: int
    name: str
    developer: str | None
    publisher: str | None
    ccu: int | None
    positive: int | None
    negative: int | None
    category: Category
    order_index: int


class Research(TypedDict, total=False):
    steam: SteamDetail | None
    reddit: RedditBuzz | None
    past_writeups: list[str]


class Draft(TypedDict):
    game: GameRef
    research: Research
    draft_text: str
    error: str | None
    retry_count: int
    started_at: float


class CheckedDraft(TypedDict):
    game: GameRef
    final_text: str
    corrections: list[str]
    embed_doc: str
    image: str  # research.steam.image를 그대로 실어나른다 (없으면 "").


# --- Send payload 타입 (Send로 도달하는 노드는 전역 state가 아니라 이 payload만 본다) ---


class DeskState(TypedDict):
    desk_name: str
    category: Category
    games: list[GameRef]
    report_date: str
    started_at: float


class ReporterState(TypedDict, total=False):
    game: GameRef
    desk_name: str
    report_date: str
    started_at: float
    # 교열부 반려 -> 재작성 경로에서만 쓰는 필드. 최초 호출(desk가 보낸 Send)에는
    # 없고, reporter.py가 .get()으로 기본값 처리한다.
    is_revision: bool
    retry_count: int
    revision_feedback: str
    previous_draft_text: str
    research: Research  # 있으면 재취재(Steam/Reddit/RAG) 없이 그대로 재사용


class CopyState(TypedDict):
    draft: Draft


# --- 그래프 전역 state ---


class ReportState(TypedDict, total=False):
    # 입력. editor_in_chief 실행 전에는 GamePick 유래의 원시 dict, 실행 후에는
    # GameRef(카테고리/순번이 부여된)로 교체된다. 단일 writer라 reducer 불필요.
    old_introductions: list[GameRef]
    recent_replays: list[GameRef]
    recent_new: list[GameRef]

    report_date: str
    dry_run: bool
    started_at: float  # time.monotonic() 원점 — 병렬성 검증용 타이밍 로그 기준

    # 병렬 브랜치가 채우는 누적 채널
    drafts: Annotated[list[Draft], operator.add]
    checked: Annotated[list[CheckedDraft], operator.add]
    logs: Annotated[list[str], operator.add]

    # barrier 이후 단일 노드만 쓰는 채널
    content: dict
    commentary: str
    timings: dict
