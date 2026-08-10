-- 주간 게임 추천 리포트용 데이터 저장소.
-- old_games: SteamSpy `all` 기반 옛 명작 발굴 풀 (old_games_pipeline, 월간 갱신)
-- recent_games: 최근 출시작 발굴 풀 (recent_games_pipeline, 주간 갱신)
-- 두 테이블 모두 "데이터 원본"이자 "추천 이력"을 겸한다: gold 단계가 지표 컬럼을
-- upsert하고, 주간 리포트 선정 단계가 recommend_count/last_recommended_at을 갱신한다.

CREATE TABLE IF NOT EXISTS old_games (
    appid                 INTEGER PRIMARY KEY,
    name                  TEXT,
    developer             TEXT,
    publisher             TEXT,
    positive              INTEGER,
    negative              INTEGER,
    owners                TEXT,
    ccu                   INTEGER,
    ingested_at           TIMESTAMPTZ,
    first_recommended_at  TIMESTAMPTZ,
    last_recommended_at   TIMESTAMPTZ,
    recommend_count       INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS recent_games (
    appid                 INTEGER PRIMARY KEY,
    name                  TEXT,
    developer             TEXT,
    publisher             TEXT,
    positive              INTEGER,
    negative              INTEGER,
    owners                TEXT,
    ccu                   INTEGER,
    ingested_at           TIMESTAMPTZ,
    first_recommended_at  TIMESTAMPTZ,
    last_recommended_at   TIMESTAMPTZ,
    recommend_count       INTEGER NOT NULL DEFAULT 0
);
