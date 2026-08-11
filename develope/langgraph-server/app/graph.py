"""LangGraph 조립.

토폴로지:
  START -> editor_in_chief
             -> (Send x3) desk
                 -> Command(goto=[Send x5]) reporter   (desk.py 내부에서 처리)
                     -> copy_desk (barrier)
                         -> (Send x15) copy_editor
                             -> [정상] layout_desk (checked 개수가 다 찼을 때만)
                             -> [반려, 최대 1회] Command(goto=Send) reporter (재작성)
                                 -> Command(goto=Send) copy_editor (barrier 우회, 1:1)
             -> END

editor_in_chief/copy_desk는 일반 edge로 도달하므로 표준 add_conditional_edges를
쓴다. desk->reporter(Send로 도달한 노드가 다시 Send로 fan-out하는 구간)와
copy_editor<->reporter의 반려/재작성 루프는 Command(goto=[Send, ...])를 쓴다 —
재작성이 게임마다 다른 시점에 끝나므로 고정 barrier로는 표현할 수 없다.
그래서 copy_editor->layout_desk도 고정 edge가 아니라 checked 개수를 직접 세는
조건부 edge(dispatch_layout_desk)다. GRAPH는 모듈 임포트 시 1회 컴파일되는
싱글턴 — 요청마다 재컴파일하지 않는다.
"""
from langgraph.graph import END, START, StateGraph

from .nodes.copy_desk import copy_desk, copy_editor, dispatch_copy_editors, dispatch_layout_desk
from .nodes.desk import desk
from .nodes.editor_in_chief import dispatch_desks, editor_in_chief
from .nodes.editorial_board import editorial_board  # noqa: F401 - 미등록, 코드만 유지
from .nodes.layout_desk import layout_desk
from .nodes.reporter import reporter
from .state import ReportState


def build_graph():
    builder = StateGraph(ReportState)

    builder.add_node("editor_in_chief", editor_in_chief)
    builder.add_node("desk", desk)
    builder.add_node("reporter", reporter)
    builder.add_node("copy_desk", copy_desk)
    builder.add_node("copy_editor", copy_editor)
    builder.add_node("layout_desk", layout_desk)

    builder.add_edge(START, "editor_in_chief")
    builder.add_conditional_edges("editor_in_chief", dispatch_desks, ["desk"])
    # desk -> reporter는 desk.py 내부 Command(goto=[Send, ...])로 처리된다.
    # desk()/copy_editor()의 반환 타입 Command[Literal[...]] 주석이 있어야
    # compile()과 draw_mermaid()가 그 목적지를 도달 가능한 노드로 인식한다.
    builder.add_edge("reporter", "copy_desk")
    builder.add_conditional_edges("copy_desk", dispatch_copy_editors, ["copy_editor"])
    # copy_editor -> layout_desk: 반려/재작성 루프 때문에 게임마다 도착하는
    # superstep이 달라서 고정 edge를 못 쓴다. checked 개수가 기대치에 도달했을
    # 때만 트리거되는 조건부 edge로 barrier를 직접 구현한다.
    builder.add_conditional_edges("copy_editor", dispatch_layout_desk, ["layout_desk"])
    # copy_editor -> reporter(반려/재작성)와 reporter -> copy_editor(재작성 결과)는
    # 둘 다 Command(goto=Send(...))로 각 노드 안에서 직접 처리된다 (고정 edge 없음).

    # 논설위원실(총평): 토큰 비용 때문에 그래프 등록만 주석 처리. 코드는
    # nodes/editorial_board.py에 유지되어 있다. 활성화하려면 아래 3줄의 주석을
    # 풀고, dispatch_layout_desk가 "layout_desk" 대신 "editorial_board"를
    # 반환하도록 바꾼다.
    # builder.add_node("editorial_board", editorial_board)
    # builder.add_edge("editorial_board", "layout_desk")

    builder.add_edge("layout_desk", END)

    return builder.compile()


GRAPH = build_graph()
