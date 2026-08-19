# TASK-014: PDF 통합 페이지 (명작 아카이브 + RSS 뉴스 + 감성분석) (Frontend)

- 완료 시각: 2026-08-19 (KST)
- 담당: Frontend Developer AI (TASK-014)

## 변경 내역

1. `ReportDocument.tsx` 확장 (수정 허용 대상)
   - `ReportDocumentProps`에 `startPage?: number` 추가, `let pageNumber = startPage ?? 1;`로 변경 (기본값 1 유지 → `Dashboard.tsx`의 기존 `<ReportDocument report={report} />` 호출은 그대로 컴파일/동작).
   - `export function countReportPages(report: WeeklyReport): number` 신설: `1 + chunkBalanced(report.oldIntroductions, DETAIL_ITEMS_PER_PAGE).length` (요약 그리드 1페이지 + 상세 페이지 수).

2. `NewsPrintSection.tsx` 컴포넌트 신규 (`E:\GP\develope\frontend\src\components\NewsPrintSection.tsx`)
   - props: `articles: NewsArticle[]`, `startPage: number`.
   - `chunkBalanced(articles, 4)`로 4개/페이지 단위 분할, `PageSheet`로 감싸 `page-sheet` 인쇄 규칙(자동 페이지 분리) 적용.
   - 각 기사: 출처/발행일(`formatPubDate`, `NewsCard.tsx`와 동일 방어 로직), 제목, 요약(`excerpt`, null 폴백), 원문 링크를 클릭 불가 환경(PDF) 대비 텍스트로도 노출(`article.link`, 없으면 "원문 링크 없음"). 이미지 있으면 `PlaceholderImage` 재사용.
   - 섹션 제목 "RSS 뉴스"를 `ReportDocument`와 동일한 스타일(`fontSize:20, fontWeight:700, borderBottom:"2px solid var(--color-accent)"`)로 표시, 2페이지 이상이면 "(계속)" 병기.
   - 빈 배열이어도 섹션 헤더 페이지 1장은 생성하고 "표시할 뉴스가 없습니다." 안내 문구로 처리.
   - `export function countNewsPages(articles, itemsPerPage = 4): number` 신설 (빈 배열이면 1 반환).

3. `SentimentPrintSection.tsx` 컴포넌트 신규 (`E:\GP\develope\frontend\src\components\SentimentPrintSection.tsx`)
   - props: `reports: SentimentReport[]`, `startPage: number`.
   - `chunkBalanced(reports, 3)`로 3개/페이지 단위 분할, `PageSheet` 재사용.
   - 각 항목: 게임명, 리뷰 총수, 긍/중/부정 비율 막대(`--color-positive`/`--color-negative`/`--color-text-muted`, `SentimentCard.tsx`와 동일 계산 로직), 숫자 텍스트 병기, LLM 요약(`summary`, null이면 "아직 요약이 생성되지 않았습니다."), 생성 시각(`formatGeneratedAt`, `ko-KR` 로케일).
   - 섹션 제목 "감성분석", 뉴스 섹션과 동일 스타일/빈 배열 처리 패턴.
   - `export function countSentimentPages(reports, itemsPerPage = 3): number` 신설.

4. `PrintReport.tsx` 확장 (원 태스크에서 수정 허용 대상, 새로 완성된 3섹션 문서로 교체)
   - `fetchReport(id)`, `fetchNews()`, `fetchSentimentList()`를 각각 독립된 `useEffect`로 호출(병렬 실행, 서로 실패에 영향 안 줌).
   - `report`는 실패 시 기존과 동일하게 에러 문구(`"리포트를 불러오지 못했습니다."`) 표시하고 렌더링 중단.
   - `news`/`sentiment`는 실패 시 각각 빈 배열(`[]`)로 폴백 — 전체 페이지 렌더링을 막지 않음.
   - `allLoaded = report !== null && news !== null && sentiment !== null` 조건으로 세 데이터 모두 로드된 뒤에만 문서 렌더링 및 `?print=1` 시 `window.print()` 호출(기존엔 `report`만 체크했던 것을 확장).
   - 렌더링 순서: `ReportDocument`(startPage 생략 → 1부터) → `NewsPrintSection`(`startPage = countReportPages(report) + 1`) → `SentimentPrintSection`(`startPage = newsStartPage + countNewsPages(news)`), 페이지 번호가 섹션을 넘어 연속되도록 함.
   - Header/Sidebar/Footer 없는 순수 출력 구조는 그대로 유지 (`/reports/archive-current` 헤드리스 캡처 대상이므로).

5. 다음 파일들은 지시대로 일절 수정하지 않고 import만 하여 재사용: `App.tsx`, `Header.tsx`, `types.ts`, `api.ts`, `pages/News.tsx`, `pages/Sentiment.tsx`, `components/NewsCard.tsx`, `components/SentimentCard.tsx`, `Dashboard.tsx`, `PageSheet.tsx`, `GameGrid.tsx`, `GameDetailRow.tsx`, `PlaceholderImage.tsx`, `utils/chunk.ts`, `styles/global.css`.

## 수정 파일 목록 (절대경로)

- `E:\GP\develope\frontend\src\pages\PrintReport.tsx` (수정)
- `E:\GP\develope\frontend\src\components\ReportDocument.tsx` (수정 — `startPage` prop, `countReportPages` export 추가)
- `E:\GP\develope\frontend\src\components\NewsPrintSection.tsx` (신규)
- `E:\GP\develope\frontend\src\components\SentimentPrintSection.tsx` (신규)

## 검증

- `E:\GP\develope\frontend`에서 `npx tsc --noEmit` 실행함(실행됨).
- 최초 실행 시 `PrintReport.tsx`에서 미사용 import(`countSentimentPages`) TS6133 에러 1건 발생 → 해당 import 제거 후 재실행.
- 최종 결과: 에러 0건 (출력 없음). 프로젝트 전체 컴파일 정상.

## 예상 토큰 소모량: 중(中)

이유: 기존 패턴(`ReportDocument.tsx`, `GameDetailRow.tsx`, `NewsCard.tsx`, `SentimentCard.tsx`, `PageSheet.tsx`, `chunk.ts`)이 지시문에 전문 그대로 제공되어 재탐색 없이 바로 응용 가능했던 점에서는 가벼웠으나, 신규 파일 2개 + 기존 파일 2개 수정에 걸쳐 페이지 번호 연속성(startPage 체인)을 여러 컴포넌트에 걸쳐 일관되게 설계·검증해야 했고, tsc 에러 1건을 원인 분석 후 수정하는 재작업 사이클이 한 차례 있어 소(小)보다는 다소 높은 중간 수준으로 판단.
