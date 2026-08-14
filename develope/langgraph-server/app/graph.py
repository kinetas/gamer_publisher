"""LangGraph 조립.

토폴로지:
  START -> editor_in_chief
             -> (Send x3) desk
                 -> Command(goto=[Send x5]) reporter   (desk.py 내부에서 처리)
                     -> copy_desk (barrier)
                         -> (Send x15) copy_editor
                             -> [정상] layout_desk (고정 edge, 자연 barrier)
                             -> [반려, 최대 1회] Command(goto=Send) reporter (재작성)
                                 -> Command(goto=Send) copy_editor (barrier 우회, 1:1)
                                     -> layout_desk (고정 edge, 재작성분 도착 시 한 번 더)
             -> END

editor_in_chief/copy_desk는 일반 edge로 도달하므로 표준 add_conditional_edges를
쓴다. desk->reporter(Send로 도달한 노드가 다시 Send로 fan-out하는 구간)와
copy_editor<->reporter의 반려/재작성 루프는 Command(goto=[Send, ...])를 쓴다 —
재작성이 게임마다 다른 시점에 끝나므로 고정 barrier 하나로는 "언제 전부 끝났는지"를
셀 수 없다. 대신 copy_editor->layout_desk를 고정 edge(add_edge)로 두고, 대신
layout_desk/db.save_weekly_report가 report_date 기준 upsert라 재작성이 있으면
두 번 실행돼도 마지막 실행이 항상 완전한 결과로 덮어쓴다(copy_desk.py 참고) —
"몇 번 도착하는 정확히 세기"보다 "몇 번 실행되든 마지막이 항상 옳다"가 이 문제의
더 견고한 해법이다. GRAPH는 모듈 임포트 시 1회 컴파일되는 싱글턴 — 요청마다
재컴파일하지 않는다.
"""
from langgraph.graph import END, START, StateGraph

from .nodes.copy_desk import copy_desk, copy_editor, dispatch_copy_editors
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
    # copy_editor -> layout_desk: 고정 edge. reporter -> copy_desk와 동일한 자연
    # barrier 패턴 — 한 Send 배치의 모든 copy_editor가 끝나야 이 edge가 실제로
    # 발동하고, 그 시점엔 layout_desk가 정상 병합된 전역 state를 받는다(도달 노드는
    # Send-branch 로컬 뷰가 아니라 진짜 전역 state를 보므로). 재작성된 게임은
    # 별도 Send로 나중에(다른 superstep에) 도착해 이 edge를 한 번 더 태우지만,
    # save_weekly_report가 upsert라 마지막 실행 결과가 최종값이 된다(copy_desk.py 참고).
    builder.add_edge("copy_editor", "layout_desk")
    # copy_editor -> reporter(반려/재작성)와 reporter -> copy_editor(재작성 결과)는
    # 둘 다 Command(goto=Send(...))로 각 노드 안에서 직접 처리된다 (고정 edge 없음).

    # 논설위원실(총평): 토큰 비용 때문에 그래프 등록만 주석 처리. 코드는
    # nodes/editorial_board.py에 유지되어 있다. 활성화하려면 아래 3줄의 주석을
    # 풀고, 위 "copy_editor" -> "layout_desk" 고정 edge를
    # "copy_editor" -> "editorial_board"로 바꾼다.
    # builder.add_node("editorial_board", editorial_board)
    # builder.add_edge("editorial_board", "layout_desk")

    builder.add_edge("layout_desk", END)

    return builder.compile()


GRAPH = build_graph()
