-- RSS 뉴스 섹션(TASK-005, doc/CHANGE_REQUEST.md 항목 1)에 노출할 게임 미디어 기사 저장소.
-- 1차로 게임메카(gamemeca.com) RSS만 연동하지만, source 컬럼을 두어 이후 다른
-- 매체(디스이즈게임, 인벤 등)로 확장 가능한 구조로 설계한다.
--
-- 이 테이블은 langgraph-server가 ChromaDB(game_news_refs)에 색인하는 RAG용
-- 저장소와는 완전히 별개다 (그쪽은 벡터 검색용, 이쪽은 프론트 RSS 뉴스 섹션에
-- 그대로 노출할 구조화 데이터용). 두 파이프라인은 같은 RSS를 각자 독립적으로 가져온다.
--
-- external_id: RSS item의 link를 고유키로 사용해 중복 수집을 막는다 (upsert 기준).
-- appid: 매칭 전에는 NULL. TASK-007이 기사 제목/본문에서 게임명을 추출해 Steam
-- storesearch API로 appid를 매칭한 뒤 UPDATE로 채운다. old_games/recent_games
-- 어디에도 속하지 않는 게임을 가리킬 수 있고, 매칭 전에는 항상 NULL이므로 FK를
-- 걸지 않는다.
CREATE TABLE IF NOT EXISTS game_news (
    id           SERIAL PRIMARY KEY,
    source       TEXT NOT NULL,
    external_id  TEXT UNIQUE NOT NULL,
    title        TEXT NOT NULL,
    excerpt      TEXT,
    link         TEXT,
    image_url    TEXT,
    pub_date     TIMESTAMPTZ,
    appid        INTEGER,
    ingested_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
