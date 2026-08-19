# TASK-012: RSS 뉴스 페이지 (Frontend)

- 완료 시각: 2026-08-19 22:38 (KST)
- 담당: Frontend Developer AI (TASK-012)

## 변경 내역

1. `News.tsx` 페이지 신설
   - `App.tsx`(TASK-010 완료본, 미수정)가 기대하는 `./pages/News` default export 구현.
   - `fetchNews()`로 뉴스 목록을 불러와 로딩("불러오는 중...") / 에러("뉴스를 불러오지 못했습니다.") / 빈 목록("표시할 뉴스가 없습니다.") 상태를 Dashboard.tsx 패턴 그대로 처리.
   - Header + main(카드 리스트) + Footer 레이아웃. Sidebar는 요구사항대로 제외.
   - 페이지 상단에 "저작권 정책에 따라 요약만 제공..." 안내 문구 추가.

2. `NewsCard.tsx` 컴포넌트 신설 (카드 렌더링 분리)
   - 이미지: `imageUrl` 있으면 표시, 없거나 로드 실패 시 기존 `PlaceholderImage` 컴포넌트로 폴백.
   - 출처(`source`) + 발행일(`pubDate`, null이면 미표시, 존재 시 `ko-KR` 로케일로 `YYYY.MM.DD` 형태 포맷).
   - 제목(`title`), 요약(`excerpt`, null이면 "요약이 제공되지 않았습니다." 폴백 문구).
   - **원문 보기 링크**: `link`가 not null이면 `<a href={link} target="_blank" rel="noreferrer">원문 보기 →</a>` 노출(필수 요구사항 반영). `link`가 null이면 "원문 링크 없음" 텍스트로 대체(비활성 표시).

3. 기존 파일(`App.tsx`, `Header.tsx`, `types.ts`, `api.ts`, `Footer.tsx`, `PlaceholderImage.tsx`)은 일절 수정하지 않고 import만 하여 재사용.

## 수정 파일 목록 (절대경로)

- `E:\GP\develope\frontend\src\pages\News.tsx` (신규)
- `E:\GP\develope\frontend\src\components\NewsCard.tsx` (신규)

## 검증

- `E:\GP\develope\frontend`에서 `npx tsc --noEmit` 실행함(실행됨).
- 결과: `src/App.tsx(5,23): error TS2307: Cannot find module './pages/Sentiment'` 1건만 발생. 이는 TASK-013(Sentiment.tsx 미생성) 담당 영역이며 본 태스크 산출물(News.tsx, NewsCard.tsx)과 무관. News/NewsCard 자체에서 발생한 타입 에러는 없음.

## 예상 토큰 소모량: 소(小)

이유: 기존 코드 패턴(Dashboard.tsx, PlaceholderImage.tsx, Footer.tsx, Header.tsx)이 이미 명확히 제공되어 그대로 재사용/응용했고, 신규 파일 2개(약 100줄 내외)만 작성. 탐색이나 반복 수정 없이 단일 패스로 완료되어 컨텍스트/토큰 소모가 적음.
