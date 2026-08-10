-- 완성된 주간 리포트(게임별 소개 글 포함)를 저장한다. old_games/recent_games는
-- 계속 갱신되는 지표 테이블이라, 리포트는 생성 시점의 스냅샷을 content(JSONB)에
-- 통째로 얼려서 저장한다 (나중에 old_games/recent_games가 바뀌어도 과거 리포트
-- 내용은 그대로 유지되어야 하므로).
--
-- pdf_path: 처음 만들어질 때는 NULL(그 주에는 프론트에서 라이브로 보여줌).
-- 다음 주 파이프라인이 시작되며 archive될 때 채워진다 (reports 버킷 경로).
CREATE TABLE IF NOT EXISTS weekly_reports (
    id           SERIAL PRIMARY KEY,
    report_date  DATE NOT NULL UNIQUE,
    content      JSONB NOT NULL,
    pdf_path     TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
