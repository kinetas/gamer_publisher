# TASK-010_프론트기반담당

완료 시각: 2026-08-19

## 배경 요약
사이트를 3섹션(명작 아카이브 / RSS 뉴스 / 감성분석) 체제로 재구성하는 작업의 프론트엔드
기반 태스크. 백엔드는 이미 `/news`, `/news/{id}`, `/sentiment`, `/sentiment/{appid}`
엔드포인트를 노출했고, `/reports/latest`, `/reports/{id}` 응답에서 `recentReplays`/
`recentNew` 키가 제거된 상태(TASK-008/TASK-009 완료본). 이번 태스크는 프론트엔드
쪽에서 이 계약을 반영할 라우팅/타입/API 클라이언트 기반을 만들고, 뒤따르는
TASK-011(ReportDocument 수정)/012(News 페이지)/013(Sentiment 페이지)/014가
그대로 가져다 쓸 인터페이스(App.tsx 라우트, Header 네비, types.ts, api.ts 함수
시그니처)를 확정하는 것.

## 변경 내역

### `src/App.tsx`
`./pages/News`, `./pages/Sentiment` import 및 `/news`, `/sentiment` 라우트 2개를
추가했다. 두 컴포넌트 파일은 아직 존재하지 않음(TASK-012/013이 나중에 생성) —
지시서대로 import 구문과 Route만 선반영. 기존 `/`, `/print/:id` 라우트는 그대로
유지.

### `src/components/Header.tsx`
`react-router-dom`의 `NavLink`를 사용해 "명작 아카이브"(`/`, `end` 옵션으로 정확히
루트일 때만 active), "RSS 뉴스"(`/news`), "감성분석"(`/sentiment`) 3개 네비 링크를
추가했다. 기존 로고+타이틀(`PlaceholderImage` + span)은 그대로 두고, header를
`justify-content: space-between`으로 바꿔 왼쪽에 로고+타이틀, 오른쪽에 `<nav>`를
배치했다. active 상태는 `var(--color-text)` + `var(--color-surface-raised)` 배경,
비active는 `var(--color-text-muted)` + 투명 배경으로 기존 다크 톤(`src/styles/global.css`)과
맞췄다. 스타일 함수를 `CSSProperties` 타입(전역 `React` 네임스페이스가 아니라
`import type { CSSProperties } from "react"`로 명시 import — 기존 코드베이스 다른
파일들의 관례를 따름)으로 타입 지정했다.

### `src/types.ts`
- `WeeklyReport`에서 `recentReplays`, `recentNew` 필드 제거 (`oldIntroductions`만
  유지) — 백엔드 계약 3번과 정확히 일치.
- `GameEntry`는 지시대로 손대지 않음 (`description`/`image` 필드는 `ReportDocument`/
  `GameGrid`/`GameDetailRow`가 이미 소비 중이라 그대로 유지).
- 신규 `NewsArticle` 인터페이스 추가: `id, source, title, excerpt, link, imageUrl,
  pubDate, appid` (지시서 스펙 그대로).
- 신규 `SentimentReport` 인터페이스 추가: `appid, name, positiveCount,
  negativeCount, neutralCount, reviewCount, summary, generatedAt` (지시서 스펙
  그대로).

### `src/api.ts`
기존 `request<T>` 헬퍼를 재사용해 4개 함수를 추가했다.
- `fetchNews(limit = 20, offset = 0): Promise<NewsArticle[]>` → `GET /news?limit=..&offset=..`
- `fetchNewsItem(id: number): Promise<NewsArticle>` → `GET /news/{id}`
- `fetchSentimentList(): Promise<SentimentReport[]>` → `GET /sentiment`
- `fetchSentimentItem(appid: number): Promise<SentimentReport>` → `GET /sentiment/{appid}`

`NewsArticle`, `SentimentReport`는 `./types`에서 import.

## 검증
- **타입체크 실행됨.** `node_modules`가 설치돼 있지 않아 `npm install
  --no-audit --no-fund`로 먼저 의존성을 설치(72개 패키지, 10초)한 뒤
  `npx tsc --noEmit`을 실행했다.
- 결과: 4개 에러 발생, 모두 예상된 것이며 이번 태스크 파일(App.tsx, Header.tsx,
  types.ts, api.ts) 자체의 에러는 아니다.
  - `src/App.tsx(4,18)`, `(5,23)`: `./pages/News`, `./pages/Sentiment` 모듈을 찾을
    수 없음 — 지시서에 명시된 대로 TASK-012/013이 나중에 만들 파일이라 정상.
  - `src/components/ReportDocument.tsx(21,37)`, `(22,37)`: `WeeklyReport`에
    `recentReplays`/`recentNew`가 더 이상 없어서 발생 — 지시서에 명시된 대로
    TASK-011 담당 범위이며 이번 태스크에서 의도적으로 남겨둔 상태.
- 위 4개를 제외하면 다른 에러 없음 — App.tsx/Header.tsx/types.ts/api.ts 자체는
  타입 에러 없이 통과.

## 수정 파일 목록 (절대경로)
- `E:\GP\develope\frontend\src\App.tsx`
- `E:\GP\develope\frontend\src\components\Header.tsx`
- `E:\GP\develope\frontend\src\types.ts`
- `E:\GP\develope\frontend\src\api.ts`

**생성:**
- `E:\GP\report\fragment\TASK-010_프론트기반담당.md` (본 보고서)

**참고 (수정하지 않음, 부수효과로 타입에러 존재 예정):**
- `E:\GP\develope\frontend\src\components\ReportDocument.tsx` (TASK-011 담당)

## 예상 토큰 소모량: 소 (small)
이유: 대상 파일 4개(App.tsx, Header.tsx, types.ts, api.ts) 모두 지시서에 전체
내용이 이미 제공되어 있어 별도 탐색 없이 바로 읽고 수정할 수 있었다. 신규 코드도
라우트 2개, 네비 링크 3개, 인터페이스 2개, API 함수 4개로 분량이 작다.
`npm install`이 예상보다 빨리 끝나(10초) 실제 `tsc --noEmit` 검증까지 수행했지만
반복 디버깅 없이 1회 실행으로 예상된 에러만 확인하고 종료했다.
