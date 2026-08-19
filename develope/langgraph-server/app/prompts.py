"""한국어 프롬프트 조립. 문자열 상수 대신 함수로 둬서, 취재 자료가 없을 때
(Steam/Reddit/RAG 실패) 해당 섹션을 프롬프트에서 통째로 빼도록 한다.
"""
from .schemas import SentimentSummaryRequest
from .state import CheckedDraft, GameRef, Research

_CATEGORY_LABEL = {
    "old_introductions": "명작 아카이브",
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


def _tone_guidance(positive: int | None) -> list[str]:
    """리뷰 수 대비 과장된 톤으로 쓰지 않도록 하는 가드.

    사용자 피드백: 긍정 리뷰가 몇백 개 수준인 게임을 마치 유명 대작인 것처럼
    화려하게 소개하는 문제가 있었음 — positive < 1000이면 "숨겨진 맛집" 톤으로
    담백하게, positive < 100은 애초에 select_weekly_report(postgres_load.py)
    단계에서 후보군에서 제외된다.
    """
    if positive is None or positive >= 1000:
        return []
    return [
        f"- 이 게임은 긍정 리뷰가 {positive}개로 아직 많지 않다. 마치 유명 대작인",
        "  것처럼 과장하지 말고, '입소문은 안 났지만 괜찮은 숨은 게임'을 소개하는",
        "  '숨겨진 맛집' 톤으로 담백하게 써라. '엄청난', '대박', '화제의' 같은",
        "  과장된 수식어는 쓰지 마라.",
    ]


def reporter_prompt(game: GameRef, research: Research) -> str:
    lines = [
        f"다음 스팀 게임 '{game['name']}'을(를) 한국어로 2~3문장 소개하는 글을 써줘.",
        "게임 리포트 큐레이터 말투로, 과장 없이 담백하게.",
        "",
        "반드시 지킬 것:",
        f"- 오직 '{game['name']}' 이 게임 하나에 대해서만 써라. 아래 취재자료에",
        "  다른 게임 이름, 이벤트, 캐릭터, 할인/쿠폰 소식이 섞여 있어도 그건 이",
        f"  게임과 무관한 자료다 — 절대 가져다 쓰지 마라. '{game['name']}'과",
        "  직접 관련 없는 내용이면 그 자료 자체를 무시해라.",
        "- 글에는 게임명, 장르, 게임 소개(플레이 방식/특징), 평가(리뷰 반응)",
        "  네 가지 요소만 자연스럽게 녹여 써라. 그 외 잡다한 정보는 넣지 마라.",
        "- 아래 제공된 사실(장르/리뷰 수/ccu/공식 소개 등) 밖의 내용은 지어내지 마라.",
        *_tone_guidance(game.get("positive")),
        "",
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
        f"오직 '{game['name']}' 이 게임에 대해서만 써라 — 취재자료에 다른 게임/이벤트",
        "얘기가 섞여 있어도 그건 무관한 자료이니 절대 가져다 쓰지 마라.",
        *_tone_guidance(game.get("positive")),
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


def copy_desk_prompt(draft_text: str, game: GameRef, research: Research) -> str:
    game_name = game["name"]
    positive = game.get("positive")
    lines = [
        "다음은 게임 소개 초고야. 아래 Reddit/Steam/관련기사 취재자료를 기준으로 점검해줘.",
        "",
        f"- 가장 먼저 확인할 것: 이 초고가 정말 '{game_name}'이라는 이 게임 하나에",
        "  대한 설명인지 봐라. 다른 게임 이름/캐릭터/이벤트가 섞여 있거나, 이",
        "  게임과 무관한 내용(예: 취재자료에 있던 다른 게임 소식)이 그대로 들어가",
        "  있으면 그건 사실 왜곡이다 -> 아래 REWRITE_NEEDED 처리.",
    ]
    if positive is not None and positive < 1000:
        lines.append(
            f"- 이 게임은 긍정 리뷰가 {positive}개뿐이다. 그런데 초고가 '엄청난',"
        )
        lines.append(
            "  '대박', '화제의', '명작' 같은 표현으로 유명 대작인 것처럼 과장하고"
        )
        lines.append(
            "  있으면 리뷰 수와 안 맞는 과장이다 -> 아래 REWRITE_NEEDED 처리."
        )
    lines.extend(
        [
            "- 그 외에 제공된 자료와 무관하게 사실을 지어냈거나 문장 단위 수정으로는",
            "  못 고칠 정도로 근거가 없으면: 첫 줄에 정확히",
            "  `REWRITE_NEEDED: <반려 사유 한 문장>`만 쓰고 그 외에는 아무것도 쓰지 마.",
            "- 그 정도가 아니면: 근거로 뒷받침되지 않는 단정적 주장만 완화하거나",
            "  삭제한 최종 문구를 그대로 출력해. 새로운 정보를 추가하지 말고,",
            "  문장 수와 말투는 그대로 유지해줘. 문제가 없으면 원문을 그대로 돌려줘.",
            "- 마지막 줄이 `출처: <링크>` 형식이면 그건 관련기사 인용 표시니까 절대",
            "  지우거나 고치지 말고 그대로 유지해라.",
            "",
            f"게임명: {game_name}",
            f"초고: {draft_text}",
        ]
    )

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


def sentiment_summary_prompt(payload: SentimentSummaryRequest) -> str:
    """감성분석 2차 종합(LLM) 프롬프트. 라이브러리(HuggingFace transformers 기반
    경량 다국어 감성분석)가 리뷰 전량을 1차 분류한 집계 통계와 대표 리뷰 샘플만
    받아서 "왜 그런 평가를 받는지"를 자연어로 요약한다. 리뷰 원문 전량이 아니라
    집계+샘플만 넣으므로 게임당 LLM 호출은 이 프롬프트 1회로 끝난다.
    """
    lines = [
        f"다음은 스팀 게임 '{payload.name}'의 리뷰를 경량 감성분석 라이브러리로",
        "1차 분류한 집계 결과와 대표 리뷰 샘플이야. 이 자료를 바탕으로 이 게임이",
        "왜 이런 평가를 받는지, 주요 호평 포인트와 주요 불만 포인트를 자연스러운",
        "한국어 리포트 문구로 3~5문장 정도로 요약해줘.",
        "게임 리포트 큐레이터 말투로, 과장 없이 담백하게.",
        "",
        "반드시 지킬 것:",
        "- 아래 제공된 집계 수치와 리뷰 샘플 밖의 내용은 절대 지어내지 마라.",
        "- 리뷰 샘플에 없는 구체적인 기능/버그/이벤트를 상상해서 쓰지 마라.",
        "- 긍정과 부정 양쪽 근거가 모두 있으면 균형 있게 다뤄라. 한쪽 샘플이",
        "  없으면 그쪽은 억지로 지어내지 말고 언급을 생략해라.",
        "",
        f"게임명: {payload.name}",
        f"전체 리뷰 수: {payload.review_count}",
        f"긍정 {payload.positive_count} / 부정 {payload.negative_count} / 중립 {payload.neutral_count}",
        "",
    ]

    positive_samples = [s.text for s in payload.sample_reviews if s.sentiment == "positive"]
    negative_samples = [s.text for s in payload.sample_reviews if s.sentiment == "negative"]
    neutral_samples = [s.text for s in payload.sample_reviews if s.sentiment == "neutral"]

    if positive_samples:
        lines.append("긍정 리뷰 샘플:")
        for text in positive_samples:
            lines.append(f"- {text}")
        lines.append("")

    if negative_samples:
        lines.append("부정 리뷰 샘플:")
        for text in negative_samples:
            lines.append(f"- {text}")
        lines.append("")

    if neutral_samples:
        lines.append("중립 리뷰 샘플:")
        for text in neutral_samples:
            lines.append(f"- {text}")
        lines.append("")

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
