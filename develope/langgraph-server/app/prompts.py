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
    return f"{name} 소개 글 (OPENAI_API_KEY 미설정으로 자동 생성 안 됨)"


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


def copy_desk_prompt(draft_text: str, research: Research) -> str:
    lines = [
        "다음은 게임 소개 초고야. 아래 Reddit/Steam 취재자료로 뒷받침되지 않는",
        "단정적 주장만 완화하거나 삭제해줘. 새로운 정보를 추가하지 말고,",
        "문장 수와 말투는 그대로 유지해줘. 문제가 없으면 원문을 그대로 돌려줘.",
        "",
        f"초고: {draft_text}",
    ]

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
