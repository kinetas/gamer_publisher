# frontend

React + TypeScript + Vite. `npm run build`로 만든 `dist/`를 nginx가 서빙합니다 (Dockerfile 참고).

- `src/data/mockReport.ts`: 지금은 langgraph-server의 리포트 생성이 미구현이라 mock 데이터를 씁니다.
  실제 API가 생기면 이 부분만 교체하면 됩니다.
- 이미지는 전부 회색 placeholder(`PlaceholderImage`)이고, 실제 게임 이미지는 나중에 연결합니다.
- `border-radius`는 `src/styles/global.css`에서 전역으로 0 처리했습니다.

## 개발

```
npm install
npm run dev
```
