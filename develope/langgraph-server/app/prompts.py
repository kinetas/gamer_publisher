"""한국어 프롬프트 조립. 문자열 상수 대신 함수로 둬서, 취재 자료가 없을 때
(Steam/Reddit/RAG 실패) 해당 섹션을 프롬프트에서 통째로 빼도록 한다.
"""
from .state import CheckedDraft, GameRef, Research

_CATEGORY_LABEL = {
    "old_introductions": "옛 게임 소개",
    "recent_replays": "다시 추천",
    "recent_new": "신규 추천",
}


def placeholder_description(name: str) -> str:
    return f"{name} 소개 글 (LLM 미설정 또는 호출 실패로 자동 생성 안 됨)"


def _news_refs_lines(research: Research) -> list[str]:
    """게임메카 등 실제 근거기사 섹션. 요약만 저장해뒀으므로(rag.py 참고) 그대로
    베끼지 말고 참고해서 쓰게 하고, 실제로 썼으면 링크를 남기게 해서 원문
    트래픽을 돌려준다(저작권 안전장치의 핵심 — 링크 없이 인용만 하면 안 됨).
    """
    news = research.get("news_refs")
    if not news:
        return []
    lines = [
        "관련 기사(근거자료 — 아래 요약을 참고해서 사실관계를 반영하되 문장을 그대로",
        "베끼지 말고 네 표현으로 써라. 실제로 참고했다면 글 맨 마지막 줄에 정확히",
        "`출처: <링크>` 형식으로 하나만 남겨라. 참고 안 했으면 출처 줄을 쓰지 마라):",
    ]
    for ref in news[:2]:
        lines.append(f"- {ref['title']}: {ref['excerpt']} ({ref['link']})")
    return lines


def reporter_prompt(game: GameRef, research: Research) -> str:
    lines = [
        "다음 스팀 게임을 한국어로 2~3문장 소개하는 글을 써줘.",
        "게임 리포트 큐레이터 말투로, 과장 없이 담백하게.",
        f"카테고리: {_CATEGORY_LABEL.get(game['category'], game['category'])}",
        f"이름: {game['name']}",
        f"개발사: {game.get('developer') or '알 수 없음'}",
        f"현재 동시접속자(ccu): {game.get('ccu')}",
        f"긍정 리뷰 {game.get('positive')} / 부정 리뷰 {game.get('negative')}",
    ]

    steam = research.get("steam")
    if steam:
        if steam.get("genres"):
            lines.append(f"장르: {', '.join(steam['genres'])}")
        if steam.get("short_description"):
            lines.append(f"공식 소개(참고용): {steam['short_description']}")

    lines.extend(_news_refs_lines(research))

    reddit = research.get("reddit")
    if reddit and (reddit.get("titles") or reddit.get("comments")):
        lines.append("Reddit 반응(취재자료, 참고만 하고 그대로 인용하지 말 것):")
        for title in reddit.get("titles", [])[:3]:
            lines.append(f"- 게시글: {title}")
        for comment in reddit.get("comments", [])[:3]:
            lines.append(f"- 댓글: {comment}")

    past = research.get("past_writeups")
    if past:
        lines.append("이전에 이 게임을 소개했던 글(같은 표현/각도를 반복하지 말고 다르게 써라):")
        for text in past[:2]:
            lines.append(f"- {text}")

    return "\n".join(lines)


def reporter_revision_prompt(game: GameRef, research: Research, previous_text: str, feedback: str) -> str:
    """교열부가 반려한 초고를 재작성할 때 쓰는 프롬프트. Steam/Reddit/RAG는
    재취재하지 않고 원래 취재 자료를 그대로 재사용한다(reporter.py 참고).
    """
    lines = [
        "다음은 게임 소개 초고인데, 교열 데스크가 근거 부족/사실 왜곡 문제로 반려했다.",
        "아래 반려 사유를 반영해서 2~3문장으로 처음부터 다시 써줘.",
        "제공된 자료에 없는 내용은 쓰지 말고, 자료가 부족하면 단정적 표현 대신",
        "절제된 표현을 써라.",
        f"반려 사유: {feedback}",
        f"이전 초고: {previous_text}",
        "",
        f"이름: {game['name']}",
        f"개발사: {game.get('developer') or '알 수 없음'}",
    ]

    steam = research.get("steam")
    if steam:
        if steam.get("genres"):
            lines.append(f"장르: {', '.join(steam['genres'])}")
        if steam.get("short_description"):
            lines.append(f"공식 소개(참고용): {steam['short_description']}")

    lines.extend(_news_refs_lines(research))

    reddit = research.get("reddit")
    if reddit and (reddit.get("titles") or reddit.get("comments")):
        lines.append("Reddit 취재자료:")
        for title in reddit.get("titles", [])[:3]:
            lines.append(f"- 게시글: {title}")
        for comment in reddit.get("comments", [])[:3]:
            lines.append(f"- 댓글: {comment}")

    return "\n".join(lines)


def copy_desk_prompt(draft_text: str, research: Research) -> str:
    lines = [
        "다음은 게임 소개 초고야. 아래 Reddit/Steam/관련기사 취재자료를 기준으로 점검해줘.",
        "",
        "- 제공된 자료와 무관하게 사실을 지어냈거나 문장 단위 수정으로는 못 고칠",
        "  정도로 근거가 없으면: 첫 줄에 정확히 `REWRITE_NEEDED: <반려 사유 한 문장>`만",
        "  쓰고 그 외에는 아무것도 쓰지 마.",
        "- 그 정도가 아니면: 근거로 뒷받침되지 않는 단정적 주장만 완화하거나",
        "  삭제한 최종 문구를 그대로 출력해. 새로운 정보를 추가하지 말고,",
        "  문장 수와 말투는 그대로 유지해줘. 문제가 없으면 원문을 그대로 돌려줘.",
        "- 마지막 줄이 `출처: <링크>` 형식이면 그건 관련기사 인용 표시니까 절대",
        "  지우거나 고치지 말고 그대로 유지해라.",
        "",
        f"초고: {draft_text}",
    ]

    lines.extend(_news_refs_lines(research))

    reddit = research.get("reddit")
    if reddit and (reddit.get("titles") or reddit.get("comments")):
        lines.append("")
        lines.append("Reddit 취재자료:")
        for title in reddit.get("titles", [])[:3]:
            lines.append(f"- 게시글: {title}")
        for comment in reddit.get("comments", [])[:3]:
            lines.append(f"- 댓글: {comment}")

    return "\n".join(lines)


def editorial_prompt(checked: list[CheckedDraft]) -> str:
    """논설위원실(총평) 프롬프트 — 그래프에는 미등록이지만 코드는 유지."""
    lines = [
        "이번 주 게임 리포트에 소개된 게임들을 보고 3~4문장으로 총평을 써줘.",
        "특정 게임 하나에 치우치지 말고 이번 주 전체 흐름/분위기를 짚어줘.",
        "",
    ]
    for item in checked:
        lines.append(f"- {item['game']['name']}: {item['final_text']}")
    return "\n".join(lines)
