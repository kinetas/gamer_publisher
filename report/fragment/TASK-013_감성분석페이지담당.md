# TASK-013: 감성분석 페이지 (Frontend)

- 완료 시각: 2026-08-19 (KST)
- 담당: Frontend Developer AI (TASK-013)

## 변경 내역

1. `Sentiment.tsx` 페이지 신설
   - `App.tsx`(TASK-010 완료본, 미수정)가 기대하는 `./pages/Sentiment` default export 구현.
   - `fetchSentimentList()`로 목록을 불러와 로딩("불러오는 중...") / 에러("감성분석 리포트를 불러오지 못했습니다.") / 빈 목록("표시할 감성분석 리포트가 없습니다.") 상태를 Dashboard.tsx 패턴 그대로 처리.
   - Header + main(카드 리스트) + Footer 레이아웃. Sidebar 없음. News.tsx와 톤(제목 + 안내 문구 + 카드 리스트, `--page-width` 중앙 정렬)을 맞춤.
   - 페이지 상단에 "Steam 리뷰를 긍정/부정/중립으로 1차 분류한 뒤, LLM이 평가 배경을 요약합니다." 안내 문구 추가.

2. `SentimentCard.tsx` 컴포넌트 신설 (카드 렌더링 분리)
   - 게임명(`name`), 전체 리뷰 수(`reviewCount`, `toLocaleString("ko-KR")`로 천단위 구분).
   - 긍정/부정/중립 비율 바: `positiveCount`/`negativeCount`/`neutralCount` 합계 대비 flex 너비(%) 계산 후 색깔 막대로 표현. 긍정 = `--color-positive`, 부정 = `--color-negative`, 중립 = `--color-text-muted`. 합계가 0이면 빈 막대(폭 0) 처리로 division-by-zero 방지.
   - 막대 아래에 각 카운트 숫자를 색상과 함께 텍스트로도 병기(긍정/중립/부정).
   - LLM 요약(`summary`) — `null`이면 "아직 요약이 생성되지 않았습니다." 폴백 문구.
   - `generatedAt`을 `ko-KR` 로케일로 `YYYY.MM.DD HH:mm` 형태로 작게 표시(파싱 실패 시 원본 문자열 그대로 폴백, `NewsCard.tsx`의 `formatPubDate` 패턴과 동일한 방어 로직).

3. 기존 파일(`App.tsx`, `Header.tsx`, `types.ts`, `api.ts`, `Footer.tsx`)은 일절 수정하지 않고 import만 하여 재사용. `News.tsx`/`NewsCard.tsx`(TASK-012)도 건드리지 않음.

## 수정 파일 목록 (절대경로)

- `E:\GP\develope\frontend\src\pages\Sentiment.tsx` (신규)
- `E:\GP\develope\frontend\src\components\SentimentCard.tsx` (신규)

## 검증

- `E:\GP\develope\frontend`에서 `npx tsc --noEmit` 실행함(실행됨).
- 결과: 에러 0건 (출력 없음). `App.tsx`가 참조하는 `./pages/Sentiment` 모듈 누락 에러도 해소됨. Sentiment.tsx / SentimentCard.tsx 자체 타입 에러 없음.

## 예상 토큰 소모량: 소(小)

이유: 기존 코드 패턴(Dashboard.tsx, News.tsx, NewsCard.tsx, Footer.tsx, Header.tsx, global.css)이 이미 명확히 제공되어 그대로 재사용/응용했고, 신규 파일 2개(약 150줄 내외)만 작성. 탐색이나 반복 수정 없이 단일 패스로 완료, tsc도 1회 실행으로 에러 없이 통과하여 재작업이 발생하지 않아 컨텍스트/토큰 소모가 적음.
